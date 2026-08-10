"""Preparation du seed offline EAC4 PM2.5/PM10 (soiling).

Script ponctuel (dev deps, hors CI). Telecharge la reanalyse EAC4
(``cams-global-reanalysis-eac4``, ADS Copernicus) sur les 6 villes pilotes, extrait
le point de grille le plus proche, agrege en moyenne journaliere, convertit en
ug/m3 et ecrit le seed committe ``src/kuma_data_core/db/seeds/cams_eac4_seed_data.py``
(chargeur) + son compagnon ``cams_eac4_seed_data.json.gz``. La migration d'insertion
(081) ne dependra QUE de ce fichier seed : **aucun ``cdsapi`` / ``xarray`` /
``netCDF4`` ni reseau au runtime migration** (discipline seed-offline).

Entree particules du modele de salissure ``pvlib.soiling.hsu``.

PM = concentration (grandeur **intensive**) : agregation = **MOYENNE** des pas du
jour, jamais la somme (a la difference du chemin ``ssrd`` d'ERA5, ou ssrd est un
flux cumule). EAC4 natif en **kg/m3** : conversion ug/m3 = x 1e9.

FAITS EAC4 CONFIRMES EMPIRIQUEMENT (sonde Conakry janvier 2021, le 2026-06-18) :

- dataset ADS ``cams-global-reanalysis-eac4`` ;
- variables de **requete** ADS ``particulate_matter_2.5um`` /
  ``particulate_matter_10um`` ;
- variables dans le **.nc** : ``pm2p5`` / ``pm10`` (le script echoue en listant les
  variables reelles si un nom change un jour, garde-fou conserve) ;
- unite native **kg m**-3** (kg/m3) -> conversion ug/m3 = x 1e9 ;
- pas temporel **3-horaire** (248 pas pour janvier = 31 j x 8) ;
- resolution de grille **0,75 deg** (``DEMI_FENETRE_DEG = 1,0`` capte une boite 3x3) ;
- couverture **ocean** confirmee : Conakry cotier non-NaN -> **aucun repli pixel
  terrestre** (le script avertit seulement si un point retenu est tout-NaN) ;
- endpoint **ADS** ``https://ads.atmosphere.copernicus.eu/api`` ; le token ECMWF de
  ``~/.cdsapirc`` (meme pointe sur le CDS) fonctionne sur l'ADS (compte unifie),
  licence CAMS a accepter une fois.

Usage :
    uv run --group dev python scripts/preparer_seed_cams_eac4.py                # 6 pilotes
    uv run --group dev python scripts/preparer_seed_cams_eac4.py --densification # 28 communes

``--densification`` cible les 28 communes chef-lieu (migration 098) et ecrit un
seed SEPARE ``cams_eac4_densification_seed_data`` : le seed pilote (migration 081)
reste intact (les migrations pilotes immuables iterent tout leur seed). Ce lot
deverrouille le proxy de salissure aux 28 (le resolveur pluie ``nasa_power`` est
data-driven).

Idempotence : les ``.zip`` caches dans ``data/cams_eac4/`` ne sont pas
re-telecharges ; le seed produit est trie de facon stable.
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

# === Perimetre =============================================================

LOCALITES_PILOTES: tuple[str, ...] = (
    "gin_conakry_kaloum",
    "gin_kankan",
    "gin_kindia",
    "gin_labe",
    "gin_mamou",
    "gin_nzerekore",
)

# Fenetre temporelle. Defaut 2021-2025 (recouvre la precipitation NASA ->
# maximise l'intersection PM ∩ pluie du HSU). Repli possible 2021-2023
# (aligne sur le CAMS radiation existant) si la disponibilite / le cout EAC4 le
# justifie : a trancher, non fige dans le code.
ANNEE_DEBUT, ANNEE_FIN = 2021, 2025

# --- Constantes ADS / EAC4 (confirmees empiriquement le 2026-06-18, cf. docstring) ---
# EAC4 est servi par l'ADS (cams-global-reanalysis-eac4), endpoint distinct du CDS.
# Le token ECMWF de ~/.cdsapirc (meme s'il pointe url CDS) est unifie et fonctionne
# sur l'ADS : on force l'URL ADS ici, la cle est lue dans ~/.cdsapirc.
ADS_URL = "https://ads.atmosphere.copernicus.eu/api"
DATASET_EAC4 = "cams-global-reanalysis-eac4"
VARIABLES_ADS_REQUETE: tuple[str, ...] = (
    "particulate_matter_2.5um",
    "particulate_matter_10um",
)
# Nom de variable dans le .nc -> grandeur Kuma (confirme : le .nc EAC4 expose pm2p5
# / pm10). Le script leve une erreur listant les variables reelles si un nom est
# absent : aucune valeur n'est inventee silencieusement (garde-fou conserve).
VAR_NC_VERS_GRANDEUR: dict[str, str] = {
    "pm2p5": "pm2_5",
    "pm10": "pm10",
}
TEMPS_3H: tuple[str, ...] = (
    "00:00",
    "03:00",
    "06:00",
    "09:00",
    "12:00",
    "15:00",
    "18:00",
    "21:00",
)

# Grille EAC4 0,75 deg : demi-fenetre 1,0 deg => boite 2x2 deg, garantit >= 1 point.
DEMI_FENETRE_DEG = 1.0

MICROGRAMMES_PAR_KG = 1e9  # kg/m3 (natif EAC4) -> ug/m3

REPERTOIRE_DONNEES = Path("data/cams_eac4")
CHEMIN_SEED = Path("src/kuma_data_core/db/seeds/cams_eac4_seed_data.py")
CHEMIN_SEED_DENSIFICATION = Path("src/kuma_data_core/db/seeds/cams_eac4_densification_seed_data.py")

# Noms de coordonnees attendus dans le .nc (candidats, cf. ERA5).
_NOMS_TEMPS = ("valid_time", "time")


# === Coordonnees (depuis le referentiel, non re-encodees) ==================


def coordonnees_pilotes() -> dict[str, tuple[float, float]]:
    index = {e["code"]: e for e in LOCALITES_SEED}
    manquants = [c for c in LOCALITES_PILOTES if c not in index]
    if manquants:
        raise RuntimeError(f"Localites absentes de LOCALITES_SEED : {manquants}")
    return {
        c: (float(index[c]["latitude"]), float(index[c]["longitude"])) for c in LOCALITES_PILOTES
    }


def coordonnees_densification() -> dict[str, tuple[float, float]]:
    """28 communes chef-lieu (densification), coords decret 2025 / migration 085.

    Memes coordonnees que les autres lots de densification (CAMS, ERA5) : on lit
    ``PREFECTURES_GUINEE`` (nouvelles communes ``existante is None``), pas de
    re-encodage. Les codes (``gin_boffa``, ...) sont disjoints des 6 pilotes."""
    return {
        p["commune_code"]: (float(p["lat"]), float(p["lon"]))
        for p in PREFECTURES_GUINEE
        if p["existante"] is None
    }


def _bbox_cds(lat: float, lon: float) -> list[float]:
    """Fenetre CDS/ADS [Nord, Ouest, Sud, Est]."""
    return [
        lat + DEMI_FENETRE_DEG,
        lon - DEMI_FENETRE_DEG,
        lat - DEMI_FENETRE_DEG,
        lon + DEMI_FENETRE_DEG,
    ]


# === Telechargement + ouverture (clone ERA5) ===============================


def _telecharger(requete: dict[str, Any], chemin_zip: Path) -> None:
    if chemin_zip.exists():
        return
    chemin_zip.parent.mkdir(parents=True, exist_ok=True)
    print(f"  ADS {DATASET_EAC4} -> {chemin_zip.name} (file d'attente possible)...")
    cdsapi.Client(url=ADS_URL).retrieve(
        DATASET_EAC4, {**requete, "data_format": "netcdf"}, str(chemin_zip)
    )


def _ouvrir(chemin_zip: Path) -> xr.Dataset:
    """Ouvre le(s) .nc du zip ADS (fusionne si plusieurs). Aplatit les singletons
    sauf le temps. Clone du helper ERA5."""
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
    dims_singleton = [d for d in ds.dims if ds.sizes[d] == 1 and d not in ("valid_time", "time")]
    return ds.squeeze(dims_singleton, drop=True) if dims_singleton else ds


def _coord_temps(ds: xr.Dataset) -> str:
    for nom in _NOMS_TEMPS:
        if nom in ds.variables:
            return nom
    raise RuntimeError(
        f"Coordonnee temps introuvable (cherche {_NOMS_TEMPS}). "
        f"Variables presentes : {list(ds.variables)}."
    )


def _variable_nc(ds: xr.Dataset, nom_candidat: str) -> str:
    """Confirme la presence d'une variable .nc ; sinon leve en listant le reel.

    Garde-fou discipline : si le nom candidat ne correspond pas au .nc EAC4 reel,
    on n'invente rien, on expose les vrais noms pour mise a jour de la constante.
    """
    if nom_candidat in ds.data_vars:
        return nom_candidat
    raise RuntimeError(
        f"Variable {nom_candidat!r} absente du .nc EAC4. "
        f"data_vars reelles : {list(ds.data_vars)}. "
        "Mettre a jour VAR_NC_VERS_GRANDEUR avec les noms confirmes."
    )


# === Selection du pixel (pas de repli : EAC4 couvre l'ocean) ===============


def selectionner_pixel(ds: xr.Dataset, lat: float, lon: float, var_nc: str) -> tuple[float, float]:
    """(lat_pixel, lon_pixel) du point de grille le plus proche.

    EAC4 est un champ atmospherique couvrant l'ocean : le plus proche suffit, pas de
    repli pixel terrestre (contrairement a ERA5-Land surface, masque mer). Avertit
    si le point retenu est tout-NaN (a remonter : signifierait que l'hypothese
    couverture ocean est fausse pour ce point)."""
    proche = ds.sel(latitude=lat, longitude=lon, method="nearest")
    if bool(np.isnan(proche[var_nc].values).all()):
        print(
            f"  AVERTISSEMENT : pixel le plus proche tout-NaN pour ({lat}, {lon}). "
            "Hypothese couverture ocean a verifier."
        )
    return float(proche["latitude"]), float(proche["longitude"])


# === Extraction journaliere (moyenne du pas 3-horaire) =====================


def _extraire_mesures(
    ds: xr.Dataset, code: str, lat_px: float, lon_px: float, var_nc_par_grandeur: dict[str, str]
) -> list[dict[str, Any]]:
    """Moyenne journaliere par grandeur au pixel retenu, conversion kg/m3 -> ug/m3.

    Opere sur toute la plage temporelle du ``ds`` (un .nc multi-annees ici)."""
    pt = ds.sel(latitude=lat_px, longitude=lon_px)
    temps = np.atleast_1d(pt[_coord_temps(ds)].values)
    series_par_grandeur = {
        grandeur: np.atleast_1d(pt[var_nc].values).reshape(-1).astype("float64")
        for grandeur, var_nc in var_nc_par_grandeur.items()
    }

    par_jour: dict[str, dict[str, list[float]]] = defaultdict(
        lambda: {grandeur: [] for grandeur in var_nc_par_grandeur}
    )
    for i, t in enumerate(temps):
        jour = str(t)[:10]
        for grandeur, valeurs in series_par_grandeur.items():
            v = float(valeurs[i])
            if not math.isnan(v):
                par_jour[jour][grandeur].append(v)

    lignes: list[dict[str, Any]] = []
    for jour in sorted(par_jour):
        for grandeur in var_nc_par_grandeur:
            pas = par_jour[jour][grandeur]
            if pas:
                # MOYENNE des pas du jour (concentration intensive), puis ug/m3.
                moyenne_kg_m3 = sum(pas) / len(pas)
                lignes.append(
                    {
                        "localite_code": code,
                        "grandeur_code": grandeur,
                        "date": jour,
                        "valeur": round(moyenne_kg_m3 * MICROGRAMMES_PAR_KG, 4),
                    }
                )
    return lignes


def extraire_ville(
    code: str, lat: float, lon: float
) -> tuple[list[dict[str, Any]], dict[str, float]]:
    """Telecharge EAC4 pour la plage complete en **une requete** (la file d'attente
    ADS, 20 min/requete, domine le cout total : on minimise le nombre de requetes,
    pas leur taille ; un fichier 5 ans / boite 3x3 reste petit, 1 Mo)."""
    zip_path = REPERTOIRE_DONNEES / f"{code}_{ANNEE_DEBUT}_{ANNEE_FIN}.zip"
    _telecharger(
        {
            "variable": list(VARIABLES_ADS_REQUETE),
            "date": [f"{ANNEE_DEBUT}-01-01/{ANNEE_FIN}-12-31"],
            "time": list(TEMPS_3H),
            "area": _bbox_cds(lat, lon),
        },
        zip_path,
    )
    ds = _ouvrir(zip_path)
    # Resolution des noms .nc reels (candidat -> grandeur), confirmee sur ds.
    var_nc_par_grandeur = {
        grandeur: _variable_nc(ds, nom_candidat)
        for nom_candidat, grandeur in VAR_NC_VERS_GRANDEUR.items()
    }
    premier_var = next(iter(var_nc_par_grandeur.values()))
    la, lo = selectionner_pixel(ds, lat, lon, premier_var)
    lignes = _extraire_mesures(ds, code, la, lo, var_nc_par_grandeur)
    ds.close()
    return lignes, {"latitude": la, "longitude": lo}


# === Emission du seed ======================================================


# Module-chargeur ecrit en lieu et place du seed (clone ERA5). Identique au fichier
# cams_eac4_seed_data.py livre initialement : la re-execution du script ne change
# que le .json.gz. gzip + json stdlib uniquement, AUCUN import scientifique.
_MODULE_LOADER = '''\
"""Seed offline EAC4 PM2.5/PM10 (Vague 5 soiling Lot A) - chargeur, GENERE, ne pas editer.

Donnees reelles EAC4 (ADS Copernicus, cams-global-reanalysis-eac4) produites par
scripts/preparer_seed_cams_eac4.py. La donnee vit dans le compagnon gzippe
cams_eac4_seed_data.json.gz (sous la limite de taille du depot). gzip + json sont
stdlib : aucune dependance scientifique ni reseau au runtime migration.

Tolerant au seed absent : le Groupe A livre le script + ce chargeur ; le pull ADS
et la generation du .json.gz viennent ensuite (Siba). Tant que le compagnon n'existe
pas, le chargeur expose des donnees vides (la migration Groupe B creera alors les
series avec 0 mesure, cf. pattern seed vide ERA5/precipitation).
"""

from __future__ import annotations

import gzip
import json
from pathlib import Path
from typing import Any

_CHEMIN_GZ = Path(__file__).parent / "cams_eac4_seed_data.json.gz"
_DATA: dict[str, Any] = (
    json.loads(gzip.decompress(_CHEMIN_GZ.read_bytes()))
    if _CHEMIN_GZ.exists()
    else {"pixels": {}, "journalier": []}
)

CAMS_EAC4_PIXELS: dict[str, dict[str, float]] = _DATA["pixels"]
CAMS_EAC4_JOURNALIER_SEED: list[dict[str, Any]] = _DATA["journalier"]
'''


def emettre_seed(journalier: list[dict[str, Any]], pixels: dict[str, dict[str, float]]) -> None:
    journalier_tri = sorted(
        journalier, key=lambda r: (r["localite_code"], r["grandeur_code"], r["date"])
    )
    data = {
        "pixels": dict(sorted(pixels.items())),
        "journalier": journalier_tri,
    }
    chemin_gz = CHEMIN_SEED.parent / "cams_eac4_seed_data.json.gz"
    charge = json.dumps(data, separators=(",", ":")).encode("utf-8")
    chemin_gz.write_bytes(gzip.compress(charge, compresslevel=9))
    CHEMIN_SEED.write_text(_MODULE_LOADER, encoding="utf-8", newline="\n")
    print(f"  Seed: {len(journalier_tri)} mesures journalieres -> {chemin_gz}")


# === Emission du seed densification (28 communes, seed separe) =============

# Chargeur du seed densification. Tolerant au seed absent (mirror pilote) : tant que
# le .json.gz n'existe pas, expose des donnees vides (la migration 098 cree alors les
# 56 series avec 0 mesure). Variante FICHIER UNIQUE : la taille mesuree post-capture
# decide d'un eventuel passage au chunk par-ville (mirror ERA5 daily, cf. avertissement
# dans emettre_seed_densification).
_MODULE_LOADER_DENSIFICATION = '''\
"""Seed offline EAC4 PM2.5/PM10 densification 28 communes - chargeur, GENERE, ne pas editer.

Donnees reelles EAC4 (ADS Copernicus, cams-global-reanalysis-eac4) pour les 28 communes
chef-lieu, produites par scripts/preparer_seed_cams_eac4.py --densification. La donnee vit
dans le compagnon gzippe cams_eac4_densification_seed_data.json.gz (sous la limite 1 Mo du
depot). gzip + json stdlib : aucune dependance scientifique ni reseau au runtime migration.

Entree particules du HSU pour les 28 communes (parite Groupe C lot C-1) : deverrouille le
proxy taux_salissure_proxy aux 28 (le resolveur pluie nasa_power est data-driven depuis la
parite B lot 1). Seed pilote (Lot A, migration 081) intact, fichier distinct.
"""

from __future__ import annotations

import gzip
import json
from pathlib import Path
from typing import Any

_CHEMIN_GZ = Path(__file__).parent / "cams_eac4_densification_seed_data.json.gz"
_DATA: dict[str, Any] = (
    json.loads(gzip.decompress(_CHEMIN_GZ.read_bytes()))
    if _CHEMIN_GZ.exists()
    else {"pixels": {}, "journalier": []}
)

CAMS_EAC4_DENSIFICATION_PIXELS: dict[str, dict[str, float]] = _DATA["pixels"]
CAMS_EAC4_DENSIFICATION_JOURNALIER_SEED: list[dict[str, Any]] = _DATA["journalier"]
'''


def emettre_seed_densification(
    journalier: list[dict[str, Any]], pixels: dict[str, dict[str, float]]
) -> None:
    journalier_tri = sorted(
        journalier, key=lambda r: (r["localite_code"], r["grandeur_code"], r["date"])
    )
    data = {"pixels": dict(sorted(pixels.items())), "journalier": journalier_tri}
    chemin_gz = CHEMIN_SEED_DENSIFICATION.parent / "cams_eac4_densification_seed_data.json.gz"
    charge = json.dumps(data, separators=(",", ":")).encode("utf-8")
    chemin_gz.write_bytes(gzip.compress(charge, compresslevel=9))
    CHEMIN_SEED_DENSIFICATION.write_text(
        _MODULE_LOADER_DENSIFICATION, encoding="utf-8", newline="\n"
    )
    taille_ko = chemin_gz.stat().st_size / 1024
    print(
        f"  Seed densification: {len(journalier_tri)} mesures journalieres -> "
        f"{chemin_gz} ({taille_ko:.0f} Ko)"
    )
    if taille_ko > 900:
        print(
            f"  AVERTISSEMENT : {taille_ko:.0f} Ko proche du hook 1024 Ko : passer au chunk "
            "par-ville (mirror ERA5 daily) + loader glob avant commit."
        )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Prepare le seed offline EAC4 PM2.5/PM10 (6 pilotes ou 28 communes)."
    )
    parser.add_argument(
        "--densification",
        action="store_true",
        help="28 communes chef-lieu (seed separe cams_eac4_densification), au lieu des 6 pilotes.",
    )
    args = parser.parse_args()

    if args.densification:
        print("=== Preparation seed EAC4 PM2.5/PM10 densification (28 communes, parite C-1) ===")
        coords = coordonnees_densification()
    else:
        print("=== Preparation seed EAC4 PM2.5/PM10 (Vague 5 soiling Lot A, 6 pilotes) ===")
        coords = coordonnees_pilotes()

    journalier: list[dict[str, Any]] = []
    pixels: dict[str, dict[str, float]] = {}
    for code, (lat, lon) in coords.items():
        print(f"\n[{code}] ({lat:.5f}, {lon:.5f})")
        lignes, pixel = extraire_ville(code, lat, lon)
        journalier.extend(lignes)
        pixels[code] = pixel

    if args.densification:
        emettre_seed_densification(journalier, pixels)
        print(f"\nOK. {len(coords)} communes capturees -> migration 098 (parite Groupe C lot C-1).")
    else:
        emettre_seed(journalier, pixels)
        print("\nOK. Remonter les faits EAC4 confirmes a Siba, puis Groupe B (migration 081).")


if __name__ == "__main__":
    main()
