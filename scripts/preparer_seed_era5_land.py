"""Préparation du seed offline ERA5-Land.

Livrable **humain ponctuel** (dev deps), exécuté hors CI. Télécharge
ERA5-Land depuis le CDS Copernicus, extrait par ville pilote, applique les
conversions et écrit le fichier seed committé
``src/kuma_data_core/db/seeds/era5_land_seed_data.py``. La migration
d'insertion (069) ne dépend QUE de ce fichier seed (aucun ``cdsapi`` /
``xarray`` / ``netCDF4`` ni réseau au runtime migration - discipline alpha).

Deux voies, choisies après vérification empirique (2026-06-16) :

- **Mensuel climato 2001-2020** : dataset grillé ``reanalysis-era5-land-monthly-means``
  (1 requête/ville, léger). Sélection du pixel 0.1° au plus proche, avec
  **repli terrestre** (Conakry-Kaloum côtier, masque océan ERA5-Land).
  ``ssrd`` mensuel = accumulation moyenne quotidienne → ÷ 3.6e6.
- **Journalier 2021-2025** : dataset **``reanalysis-era5-land-timeseries``**
  (ARCO/Zarr, point unique, rapide, sans limite de coût gridée). ``ssrd`` y est
  **dé-accumulé** (flux horaire J/m²) : total quotidien = **somme des 24 flux**
  ÷ 3.6e6 (vérifié : somme = plateau accumulé de la grille). Le point demandé
  est le **pixel terrestre résolu par le mensuel** (sinon NaN sur Conakry).

Faits API vérifiés : le CDS renvoie un ``.zip`` (1+ ``.nc``) ; variables
``ssrd`` (J m⁻²), ``t2m`` (K), ``u10``/``v10`` (m s⁻¹) ; dimension ``valid_time``.

Authentification : ``~/.cdsapirc``. Licence **CC-BY** à accepter une fois.

Usage :
    uv run --group dev python scripts/preparer_seed_era5_land.py

Idempotence : les ``.zip`` cachés dans ``data/era5_land/`` ne sont pas
re-téléchargés ; le seed produit est trié de façon stable.
"""

from __future__ import annotations

import argparse
import gzip
import json
import math
import zipfile
from collections import defaultdict
from pathlib import Path
from typing import Any

import cdsapi  # type: ignore[import-untyped]
import numpy as np
import xarray as xr  # type: ignore[import-untyped]

from kuma_data_core.db.seeds.localites_prefectures_seed_data import PREFECTURES_GUINEE
from kuma_data_core.db.seeds.localites_seed_data import LOCALITES_SEED

# === Périmètre =============================================================

LOCALITES_PILOTES: tuple[str, ...] = (
    "gin_conakry_kaloum",
    "gin_kankan",
    "gin_kindia",
    "gin_labe",
    "gin_mamou",
    "gin_nzerekore",
)

VARIABLES_CDS: tuple[str, ...] = (
    "surface_solar_radiation_downwards",
    "2m_temperature",
    "10m_u_component_of_wind",
    "10m_v_component_of_wind",
)

ANNEE_DEBUT_MENSUEL, ANNEE_FIN_MENSUEL = 2001, 2020
ANNEE_DEBUT_JOURNALIER, ANNEE_FIN_JOURNALIER = 2021, 2025

DATASET_MENSUEL = "reanalysis-era5-land-monthly-means"
DATASET_TIMESERIES = "reanalysis-era5-land-timeseries"

DEMI_FENETRE_DEG = 0.35  # marge pour le repli pixel terrestre (Conakry côtier)

REPERTOIRE_DONNEES = Path("data/era5_land")
CHEMIN_SEED = Path("src/kuma_data_core/db/seeds/era5_land_seed_data.py")
CHEMIN_SEED_DENSIF = Path("src/kuma_data_core/db/seeds/era5_land_densification_seed_data.py")

# Densification 28 communes : seed SEPARE par granularite (la migration pilote 069
# immuable itere tout son seed). Allowlist de fenetres legitimes (mirror CAMS) :
# mensuel 2001-2020, daily 2021-2025. Toute autre fenetre rejetee.
FENETRES_DENSIFICATION: dict[tuple[int, int], str] = {
    (ANNEE_DEBUT_MENSUEL, ANNEE_FIN_MENSUEL): "mensuel",
    (ANNEE_DEBUT_JOURNALIER, ANNEE_FIN_JOURNALIER): "journalier",
}
# Repli pixel terrestre densification : bbox elargie (cotieres) + plafond explicite.
# Au-dela de MAX_REPLI_DEG, on leve (un chef-lieu cotier ne doit jamais heriter en
# silence d'un pixel interieur lointain = autre climat).
DEMI_FENETRE_DENSIF_DEG = 0.7
MAX_REPLI_DEG = 0.7

JOULES_PAR_KWH = 3.6e6
ZERO_CELSIUS_EN_KELVIN = 273.15
HEURES_PAR_JOUR = 24


# === Coordonnées (depuis le référentiel, non ré-encodées) ==================


def coordonnees_pilotes() -> dict[str, tuple[float, float]]:
    index = {e["code"]: e for e in LOCALITES_SEED}
    manquants = [c for c in LOCALITES_PILOTES if c not in index]
    if manquants:
        raise RuntimeError(f"Localités absentes de LOCALITES_SEED : {manquants}")
    return {
        c: (float(index[c]["latitude"]), float(index[c]["longitude"])) for c in LOCALITES_PILOTES
    }


def coordonnees_densification() -> dict[str, tuple[float, float]]:
    """28 communes chef-lieu (densification), coords decret 2025 / migration 085.

    Memes 28 que CAMS/precip (PREFECTURES_GUINEE, ``existante is None``). Les 6 pilotes
    en sont exclus : ils ont deja leur ERA5-Land (migration 069)."""
    return {
        p["commune_code"]: (float(p["lat"]), float(p["lon"]))
        for p in PREFECTURES_GUINEE
        if p["existante"] is None
    }


def _bbox_cds(lat: float, lon: float, demi: float = DEMI_FENETRE_DEG) -> list[float]:
    """Fenêtre CDS [Nord, Ouest, Sud, Est]."""
    return [lat + demi, lon - demi, lat - demi, lon + demi]


# === Téléchargement + ouverture ============================================


def _telecharger(dataset: str, requete: dict[str, Any], chemin_zip: Path) -> None:
    if chemin_zip.exists():
        return
    chemin_zip.parent.mkdir(parents=True, exist_ok=True)
    print(f"  CDS {dataset} -> {chemin_zip.name} (file d'attente possible)...")
    cdsapi.Client().retrieve(dataset, {**requete, "data_format": "netcdf"}, str(chemin_zip))


def _ouvrir(chemin_zip: Path) -> xr.Dataset:
    """Ouvre le(s) ``.nc`` du zip CDS (fusionne si plusieurs - cas timeseries
    multi-variables, groupées par famille). Aplatit les singletons sauf le
    temps."""
    if not zipfile.is_zipfile(chemin_zip):
        ds = xr.open_dataset(chemin_zip, engine="netcdf4")
    else:
        rep = chemin_zip.parent / (chemin_zip.stem + "_nc")
        rep.mkdir(exist_ok=True)
        with zipfile.ZipFile(chemin_zip) as z:
            z.extractall(rep)
        ncs = sorted(rep.glob("*.nc"))
        if not ncs:
            raise RuntimeError(f"Aucun .nc dans {chemin_zip.name}.")
        dsets = [xr.open_dataset(n, engine="netcdf4") for n in ncs]
        ds = xr.merge(dsets, compat="override") if len(dsets) > 1 else dsets[0]
    # Une requête mono-pas (valid_time taille 1) ne doit pas perdre sa dim temps.
    dims_singleton = [d for d in ds.dims if ds.sizes[d] == 1 and d not in ("valid_time", "time")]
    return ds.squeeze(dims_singleton, drop=True) if dims_singleton else ds


# === Sélection du pixel (repli terrestre pour Conakry) =====================


def selectionner_pixel(
    ds: xr.Dataset, lat: float, lon: float, max_repli_deg: float | None = None
) -> tuple[float, float, bool]:
    """(lat_pixel, lon_pixel, repli) du pixel terrestre le plus proche.
    ERA5-Land masque les océans : le plus proche peut être NaN.

    ``max_repli_deg`` (densification) : plafond explicite sur la distance du repli ;
    au-dela on leve (pas de pixel interieur lointain = autre climat, pris en silence)."""
    proche = ds.sel(latitude=lat, longitude=lon, method="nearest")
    if not bool(np.isnan(proche["t2m"].values).all()):
        return float(proche["latitude"]), float(proche["longitude"]), False
    candidats: list[tuple[float, float, float]] = []
    for la in (float(v) for v in ds["latitude"].values):
        for lo in (float(v) for v in ds["longitude"].values):
            if not bool(np.isnan(ds["t2m"].sel(latitude=la, longitude=lo).values).all()):
                candidats.append((math.hypot(la - lat, lo - lon), la, lo))
    if not candidats:
        raise RuntimeError(
            f"Aucun pixel terrestre autour de ({lat}, {lon}). Élargir DEMI_FENETRE_DEG."
        )
    dist, la, lo = min(candidats)
    if max_repli_deg is not None and dist > max_repli_deg:
        raise RuntimeError(
            f"Pixel terrestre le plus proche de ({lat}, {lon}) a {dist:.3f} deg > plafond "
            f"{max_repli_deg} deg : refuse (climat distinct). Verifier la localite/cote."
        )
    return la, lo, True


# === Conversions ===========================================================


def _kwh(j_par_m2: float) -> float:
    return j_par_m2 / JOULES_PAR_KWH


def _celsius(kelvin: float) -> float:
    return kelvin - ZERO_CELSIUS_EN_KELVIN


def _module(u: float, v: float) -> float:
    return math.hypot(u, v)


# === Extraction mensuelle (grille, 2001-2020) ==============================


def extraire_mensuel(
    code: str,
    lat: float,
    lon: float,
    demi_fenetre: float = DEMI_FENETRE_DEG,
    max_repli_deg: float | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    zip_path = REPERTOIRE_DONNEES / f"{code}_mensuel_{ANNEE_DEBUT_MENSUEL}_{ANNEE_FIN_MENSUEL}.zip"
    _telecharger(
        DATASET_MENSUEL,
        {
            "product_type": "monthly_averaged_reanalysis",
            "variable": list(VARIABLES_CDS),
            "year": [str(a) for a in range(ANNEE_DEBUT_MENSUEL, ANNEE_FIN_MENSUEL + 1)],
            "month": [f"{m:02d}" for m in range(1, 13)],
            "time": "00:00",
            "area": _bbox_cds(lat, lon, demi_fenetre),
        },
        zip_path,
    )
    ds = _ouvrir(zip_path)
    la, lo, repli = selectionner_pixel(ds, lat, lon, max_repli_deg)
    pt = ds.sel(latitude=la, longitude=lo)
    temps = np.atleast_1d(pt["valid_time"].values)
    ssrd = np.atleast_1d(pt["ssrd"].values).reshape(-1)
    t2m = np.atleast_1d(pt["t2m"].values).reshape(-1)
    u10 = np.atleast_1d(pt["u10"].values).reshape(-1)
    v10 = np.atleast_1d(pt["v10"].values).reshape(-1)
    lignes: list[dict[str, Any]] = []
    for i, t in enumerate(temps):
        annee, mois = int(str(t)[:4]), int(str(t)[5:7])
        lignes.append(
            {
                "localite_code": code,
                "grandeur_code": "ghi",
                "annee": annee,
                "mois": mois,
                "valeur": round(_kwh(float(ssrd[i])), 4),
            }
        )
        lignes.append(
            {
                "localite_code": code,
                "grandeur_code": "t2m",
                "annee": annee,
                "mois": mois,
                "valeur": round(_celsius(float(t2m[i])), 4),
            }
        )
        # Caveat assumé : module des composantes mensuelles moyennes.
        lignes.append(
            {
                "localite_code": code,
                "grandeur_code": "vent_10m",
                "annee": annee,
                "mois": mois,
                "valeur": round(_module(float(u10[i]), float(v10[i])), 4),
            }
        )
    ds.close()
    return lignes, {"latitude": la, "longitude": lo, "repli_applique": repli}


# === Extraction journalière (timeseries ARCO, 2021-2025) ===================


def extraire_journalier(code: str, la: float, lo: float) -> list[dict[str, Any]]:
    """Journalier via le dataset timeseries (point unique = pixel résolu).

    ``ssrd`` y est **dé-accumulé** (flux horaire) : total quotidien = somme des
    24 valeurs ÷ 3.6e6. ``t2m`` / vent : moyenne quotidienne des 24 pas.
    """
    zip_path = REPERTOIRE_DONNEES / f"{code}_ts_{ANNEE_DEBUT_JOURNALIER}_{ANNEE_FIN_JOURNALIER}.zip"
    if not zip_path.exists():
        zip_path.parent.mkdir(parents=True, exist_ok=True)
        print(f"  CDS timeseries {code} ({la:.2f}, {lo:.2f})...")
        cdsapi.Client().retrieve(
            DATASET_TIMESERIES,
            {
                "variable": list(VARIABLES_CDS),
                "location": {"latitude": la, "longitude": lo},
                "date": [f"{ANNEE_DEBUT_JOURNALIER}-01-01/{ANNEE_FIN_JOURNALIER}-12-31"],
                "data_format": "netcdf",
            },
            str(zip_path),
        )
    ds = _ouvrir(zip_path)
    temps = np.atleast_1d(ds["valid_time"].values)
    ssrd = np.atleast_1d(ds["ssrd"].values).reshape(-1)
    t2m = np.atleast_1d(ds["t2m"].values).reshape(-1)
    u10 = np.atleast_1d(ds["u10"].values).reshape(-1)
    v10 = np.atleast_1d(ds["v10"].values).reshape(-1)

    par_jour: dict[str, dict[str, list[float]]] = defaultdict(
        lambda: {"ssrd": [], "t2m": [], "vent": []}
    )
    for i, t in enumerate(temps):
        jour = str(t)[:10]
        d = par_jour[jour]
        if not math.isnan(float(ssrd[i])):
            d["ssrd"].append(float(ssrd[i]))
        if not math.isnan(float(t2m[i])):
            d["t2m"].append(float(t2m[i]))
        if not (math.isnan(float(u10[i])) or math.isnan(float(v10[i]))):
            d["vent"].append(_module(float(u10[i]), float(v10[i])))

    lignes: list[dict[str, Any]] = []
    for jour in sorted(par_jour):
        d = par_jour[jour]
        # GHI : somme des flux horaires, seulement sur jour complet (24 pas).
        if len(d["ssrd"]) >= HEURES_PAR_JOUR:
            lignes.append(
                {
                    "localite_code": code,
                    "grandeur_code": "ghi",
                    "date": jour,
                    "valeur": round(_kwh(sum(d["ssrd"])), 4),
                }
            )
        if d["t2m"]:
            lignes.append(
                {
                    "localite_code": code,
                    "grandeur_code": "t2m",
                    "date": jour,
                    "valeur": round(_celsius(sum(d["t2m"]) / len(d["t2m"])), 4),
                }
            )
        if d["vent"]:
            lignes.append(
                {
                    "localite_code": code,
                    "grandeur_code": "vent_10m",
                    "date": jour,
                    "valeur": round(sum(d["vent"]) / len(d["vent"]), 4),
                }
            )
    ds.close()
    return lignes


# === Émission du seed ======================================================


# Module-chargeur écrit en lieu et place du seed : la donnée massive (37 000
# mesures) vit dans un compagnon gzippé pour rester sous la limite de taille du
# dépôt (pre-commit check-added-large-files, 1 Mo). L'interface (3 constantes)
# est inchangée pour la migration 069.
_MODULE_LOADER = '''\
"""Seed offline ERA5-Land (Vague 4, Lot A) - chargeur, GÉNÉRÉ, ne pas éditer.

Données réelles ERA5-Land (CDS Copernicus) produites par
scripts/preparer_seed_era5_land.py. La donnée vit dans le compagnon gzippé
era5_land_seed_data.json.gz (sous la limite de taille du dépôt). gzip + json
sont stdlib : aucune dépendance scientifique au runtime (discipline alpha).
"""

from __future__ import annotations

import gzip
import json
from pathlib import Path
from typing import Any

_DATA: dict[str, Any] = json.loads(
    gzip.decompress((Path(__file__).parent / "era5_land_seed_data.json.gz").read_bytes())
)

ERA5_LAND_PIXELS: dict[str, dict[str, Any]] = _DATA["pixels"]
ERA5_LAND_MENSUEL_SEED: list[dict[str, Any]] = _DATA["mensuel"]
ERA5_LAND_JOURNALIER_SEED: list[dict[str, Any]] = _DATA["journalier"]
'''


def emettre_seed(
    mensuel: list[dict[str, Any]],
    journalier: list[dict[str, Any]],
    pixels: dict[str, dict[str, Any]],
) -> None:
    mensuel_tri = sorted(
        mensuel, key=lambda r: (r["localite_code"], r["grandeur_code"], r["annee"], r["mois"])
    )
    journalier_tri = sorted(
        journalier, key=lambda r: (r["localite_code"], r["grandeur_code"], r["date"])
    )
    data = {
        "pixels": dict(sorted(pixels.items())),
        "mensuel": mensuel_tri,
        "journalier": journalier_tri,
    }
    chemin_gz = CHEMIN_SEED.parent / "era5_land_seed_data.json.gz"
    charge = json.dumps(data, separators=(",", ":")).encode("utf-8")
    chemin_gz.write_bytes(gzip.compress(charge, compresslevel=9))
    CHEMIN_SEED.write_text(_MODULE_LOADER, encoding="utf-8", newline="\n")
    print(f"  Seed: {len(mensuel_tri)} mens + {len(journalier_tri)} jour -> {chemin_gz}")


# === Densification 28 communes (seed SEPARE par granularite, pilotes intacts) ===


def _stem_densif(granularite: str) -> str:
    return f"era5_land_densification_{granularite}_seed_data"


def _module_loader_densif(granularite: str) -> str:
    stem = _stem_densif(granularite)
    cle = "mensuel" if granularite == "mensuel" else "journalier"
    var = f"ERA5_LAND_DENSIFICATION_{granularite.upper()}_SEED"
    return f'''\
"""Seed offline ERA5-Land densification 28 communes ({granularite}) - chargeur,
GENERE, ne pas editer.

Donnees reelles ERA5-Land (CDS Copernicus) pour les 28 communes chef-lieu, produites par
scripts/preparer_seed_era5_land.py --densification. La donnee vit dans le compagnon gzippe
{stem}.json.gz. gzip + json stdlib : aucune dependance scientifique au runtime migration.
Attribution CC-BY Copernicus.
"""

from __future__ import annotations

import gzip
import json
from pathlib import Path
from typing import Any

_CHEMIN = Path(__file__).parent / "{stem}.json.gz"
_DATA: dict[str, Any] = json.loads(gzip.decompress(_CHEMIN.read_bytes()))

ERA5_LAND_DENSIFICATION_PIXELS: dict[str, dict[str, Any]] = _DATA["pixels"]
{var}: list[dict[str, Any]] = _DATA["{cle}"]
'''


def emettre_seed_densification(
    mesures: list[dict[str, Any]], pixels: dict[str, dict[str, Any]], granularite: str
) -> None:
    """Ecrit le seed densification 28 communes (fichier SEPARE par granularite)."""
    cle = "mensuel" if granularite == "mensuel" else "journalier"
    tri_key = (
        (lambda r: (r["localite_code"], r["grandeur_code"], r["annee"], r["mois"]))
        if granularite == "mensuel"
        else (lambda r: (r["localite_code"], r["grandeur_code"], r["date"]))
    )
    data = {"pixels": dict(sorted(pixels.items())), cle: sorted(mesures, key=tri_key)}
    stem = _stem_densif(granularite)
    chemin_gz = CHEMIN_SEED_DENSIF.parent / f"{stem}.json.gz"
    chemin_gz.write_bytes(gzip.compress(json.dumps(data, separators=(",", ":")).encode(), 9))
    (CHEMIN_SEED_DENSIF.parent / f"{stem}.py").write_text(
        _module_loader_densif(granularite), encoding="utf-8", newline="\n"
    )
    print(f"  Seed densif {granularite}: {len(mesures)} mesures -> {chemin_gz}")


def _capturer_densif_mensuel() -> None:
    coords = coordonnees_densification()
    if len(coords) != 28:
        raise RuntimeError(f"Densification : attendu 28 communes, obtenu {len(coords)}.")
    print("=== Preparation seed ERA5-Land densification 28 communes (mensuel 2001-2020) ===")
    mensuel: list[dict[str, Any]] = []
    pixels: dict[str, dict[str, Any]] = {}
    for code, (lat, lon) in coords.items():
        print(f"\n[{code}] ({lat:.5f}, {lon:.5f})")
        lignes_m, pixel = extraire_mensuel(
            code, lat, lon, demi_fenetre=DEMI_FENETRE_DENSIF_DEG, max_repli_deg=MAX_REPLI_DEG
        )
        pixels[code] = pixel
        if pixel["repli_applique"]:
            print(f"  REPLI pixel terrestre : ({pixel['latitude']:.2f}, {pixel['longitude']:.2f})")
        mensuel.extend(lignes_m)
    emettre_seed_densification(mensuel, pixels, "mensuel")
    print("\nOK. Lancer ensuite la migration 096 (parite B lot 3a) puis les tests.")


# Chargeur journalier densif : seed CHUNKE par-ville (le daily 153k mesures depasserait le
# hook 1 Mo en un fichier) -> glob des compagnons par-commune (mirror NASA daily).
_MODULE_LOADER_DENSIF_JOURNALIER = '''\
"""Seed offline ERA5-Land densification 28 communes (journalier) - chargeur, GENERE,
ne pas editer.

Donnees reelles ERA5-Land daily (CDS Copernicus timeseries) pour les 28 communes chef-lieu,
produites par scripts/preparer_seed_era5_land.py 2021 2025 --densification. La donnee massive
(153k mesures) est CHUNKEE par-ville (..._journalier_seed_data_gin_*.json.gz) pour rester sous
la limite de taille du depot (1 Mo/fichier). gzip + json stdlib. Attribution CC-BY Copernicus.
"""

from __future__ import annotations

import gzip
import json
from pathlib import Path
from typing import Any

_DOSSIER = Path(__file__).parent
_MOTIF = "era5_land_densification_journalier_seed_data_gin_*.json.gz"
ERA5_LAND_DENSIFICATION_JOURNALIER_SEED: list[dict[str, Any]] = []
for _chemin in sorted(_DOSSIER.glob(_MOTIF)):
    _bloc: dict[str, Any] = json.loads(gzip.decompress(_chemin.read_bytes()))
    ERA5_LAND_DENSIFICATION_JOURNALIER_SEED.extend(_bloc["journalier"])
'''


def _capturer_densif_journalier() -> None:
    """Daily 28 communes via le dataset timeseries (meme methode que les pilotes,
    ``extraire_journalier``). Reutilise les pixels resolus par la passe mensuelle
    (zero re-resolution ocean). Seed CHUNKE par-ville + loader glob."""
    from kuma_data_core.db.seeds.era5_land_densification_mensuel_seed_data import (
        ERA5_LAND_DENSIFICATION_PIXELS,
    )

    coords = coordonnees_densification()
    if len(coords) != 28:
        raise RuntimeError(f"Densification : attendu 28 communes, obtenu {len(coords)}.")
    manquants = [c for c in coords if c not in ERA5_LAND_DENSIFICATION_PIXELS]
    if manquants:
        raise RuntimeError(
            f"Pixels 3a manquants pour {manquants} : lancer la densification 3a (mensuel) d'abord."
        )
    print("=== Preparation seed ERA5-Land densification 28 communes (journalier 2021-2025) ===")
    for code in sorted(coords):
        pixel = ERA5_LAND_DENSIFICATION_PIXELS[code]
        la, lo = float(pixel["latitude"]), float(pixel["longitude"])
        print(f"\n[{code}] pixel ({la:.2f}, {lo:.2f})")
        lignes = sorted(
            extraire_journalier(code, la, lo), key=lambda r: (r["grandeur_code"], r["date"])
        )
        stem = f"{_stem_densif('journalier')}_{code}"
        chemin_gz = CHEMIN_SEED_DENSIF.parent / f"{stem}.json.gz"
        charge = json.dumps({"journalier": lignes}, separators=(",", ":")).encode("utf-8")
        chemin_gz.write_bytes(gzip.compress(charge, compresslevel=9))
        print(f"  {code}: {len(lignes)} mesures -> {chemin_gz.name}")
    (CHEMIN_SEED_DENSIF.parent / f"{_stem_densif('journalier')}.py").write_text(
        _MODULE_LOADER_DENSIF_JOURNALIER, encoding="utf-8", newline="\n"
    )
    print("\nOK. Lancer ensuite la migration 097 (parite B lot 3b) puis les tests.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Prepare le seed offline ERA5-Land.")
    parser.add_argument("annee_debut", nargs="?", type=int)
    parser.add_argument("annee_fin", nargs="?", type=int)
    parser.add_argument(
        "--densification",
        action="store_true",
        help="28 communes (seed separe). 2001 2020 (mensuel 3a) ou 2021 2025 (daily 3b).",
    )
    args = parser.parse_args()

    if not args.densification:
        print("=== Préparation seed ERA5-Land (Vague 4 Lot A, 6 pilotes) ===")
        coords = coordonnees_pilotes()
        mensuel: list[dict[str, Any]] = []
        journalier: list[dict[str, Any]] = []
        pixels: dict[str, dict[str, Any]] = {}
        for code, (lat, lon) in coords.items():
            print(f"\n[{code}] ({lat:.5f}, {lon:.5f})")
            lignes_m, pixel = extraire_mensuel(code, lat, lon)
            pixels[code] = pixel
            if pixel["repli_applique"]:
                print(f"  REPLI pixel : ({pixel['latitude']:.2f}, {pixel['longitude']:.2f})")
            mensuel.extend(lignes_m)
            journalier.extend(
                extraire_journalier(code, float(pixel["latitude"]), float(pixel["longitude"]))
            )
        emettre_seed(mensuel, journalier, pixels)
        print("\nOK. Lancer ensuite les migrations 068/069 puis les tests d'intégration.")
        return

    fenetre = (args.annee_debut, args.annee_fin)
    granularite = FENETRES_DENSIFICATION.get(fenetre)
    if granularite is None:
        parser.error(
            f"--densification : fenetre {fenetre} hors allowlist "
            f"{sorted(FENETRES_DENSIFICATION)} (anti-typo / fenetre arbitraire)."
        )
    if granularite == "mensuel":
        _capturer_densif_mensuel()
    else:
        _capturer_densif_journalier()


if __name__ == "__main__":
    main()
