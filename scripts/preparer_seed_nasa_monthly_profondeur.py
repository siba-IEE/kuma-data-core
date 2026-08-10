"""Préparation du seed offline NASA POWER mensuel profondeur (séries longues).

Script ponctuel (hors CI). Capture en **live** les séries
mensuelles NASA POWER **pleine profondeur** (1981-2025) des **34 points**
(6 villes pilotes + 28 communes chef-lieu), les convertit en lignes finales
``(localite_code, grandeur_code, annee, mois, valeur)`` et écrit un seed
committé **par ville** (patron NE-OFFLINE, mirror CAMS/EAC4/ERA5 : la
migration lit le seed directement, aucun module d'ingestion ni réseau au
runtime migration).

**Distinct du seed climato** ``nasa_power_monthly_seed_data_*`` (payloads
bruts 1991-2020 consommés en offline par les migrations immuables
041/050/087) : on ne touche pas à ce snapshot — le remplacer par une
re-capture exposerait les migrations mergées à un reprocessing NASA
silencieux. Namespace séparé ``nasa_power_monthly_profondeur_seed_data_*``.

Profondeurs réelles par palier (sonde API du 2026-08-09, pixel Conakry) :

- **1981-01** : t2m, rh2m, vent_2m, vent_10m, precipitation (MERRA-2) ;
- **1984-01** : ghi, dhi (ère satellitaire radiation) ;
- **2001-01** : dni, kt, albedo_surface (début des observations CERES).

Le script ne code PAS ces paliers en dur : il demande 1981-2025 pour les 10
paramètres, filtre sentinelles ``-999`` et clés annuelles ``YYYY13`` (mêmes
briques que le seam mensuel : fidélité), puis **vérifie l'uniformité de la
couverture entre les 34 villes** (par grandeur, même ensemble (annee, mois)
partout — toute asymétrie est une erreur dure à examiner). Les fenêtres
découvertes sont imprimées : la migration d'insertion les fige avec gardes.

Découpage par ville : un compagnon ``.json.gz`` par ville (~40-60 Ko :
10 params x jusqu'à 45 ans x 12 mois), loin sous le hook
``check-added-large-files``. Cache brut par ville sous
``data/nasa_power_monthly_profondeur/`` (relance sans re-fetch).

Usage : ``uv run --group dev python scripts/preparer_seed_nasa_monthly_profondeur.py``
"""

from __future__ import annotations

import gzip
import json
from pathlib import Path
from typing import Any

from kuma_data_core.db.seeds.localites_prefectures_seed_data import PREFECTURES_GUINEE
from kuma_data_core.db.seeds.localites_seed_data import LOCALITES_SEED
from kuma_data_core.external.nasa_power import (
    SENTINELLE_VALEUR_MANQUANTE,
    fetch_monthly_raw,
)
from kuma_data_core.ingestion.nasa_power_monthly import _parse_cle_yyyymm

# === Périmètre : 34 points = 6 pilotes + 28 communes densification =========

LOCALITES_PILOTES: tuple[str, ...] = (
    "gin_conakry_kaloum",
    "gin_kankan",
    "gin_kindia",
    "gin_labe",
    "gin_mamou",
    "gin_nzerekore",
)

# 10 paramètres mensuels (code NASA -> grandeur Kuma), fenêtre pleine 1981-2025.
PARAMETRES_NASA: dict[str, str] = {
    "ALLSKY_SFC_SW_DWN": "ghi",
    "ALLSKY_SFC_SW_DIFF": "dhi",
    "ALLSKY_SFC_SW_DNI": "dni",
    "ALLSKY_KT": "kt",
    "ALLSKY_SRF_ALB": "albedo_surface",
    "T2M": "t2m",
    "RH2M": "rh2m",
    "WS2M": "vent_2m",
    "WS10M": "vent_10m",
    "PRECTOTCORR": "precipitation",
}
ANNEE_DEBUT = 1981
ANNEE_FIN = 2025

REPERTOIRE_CACHE = Path("data/nasa_power_monthly_profondeur")
DOSSIER_SEED = Path("src/kuma_data_core/db/seeds")
CHEMIN_LOADER = DOSSIER_SEED / "nasa_power_monthly_profondeur_seed_data.py"

_MODULE_LOADER = '''\
"""Seed offline NASA POWER mensuel profondeur - chargeur, GÉNÉRÉ, ne pas éditer.

Lignes finales ``(localite_code, grandeur_code, annee, mois, valeur)`` des 34
points (6 pilotes + 28 communes), produites par
scripts/preparer_seed_nasa_monthly_profondeur.py (sentinelles -999 et clés
annuelles YYYY13 déjà filtrées). Patron NE-OFFLINE : consommé directement par
la migration d'insertion, aucun réseau au runtime. gzip + json stdlib ; un
compagnon .json.gz par ville.
"""

from __future__ import annotations

import gzip
import json
from pathlib import Path
from typing import Any

_DOSSIER = Path(__file__).parent

NASA_MONTHLY_PROFONDEUR_SEED: list[dict[str, Any]] = []
for _chemin in sorted(_DOSSIER.glob("nasa_power_monthly_profondeur_seed_data_*.json.gz")):
    _bloc: dict[str, Any] = json.loads(gzip.decompress(_chemin.read_bytes()))
    NASA_MONTHLY_PROFONDEUR_SEED.extend(_bloc["mensuel"])
'''


def coordonnees_tous_points() -> dict[str, tuple[float, float]]:
    """Coordonnées (lat, lon) des 34 points : 6 pilotes + 28 communes densification."""
    index = {e["code"]: e for e in LOCALITES_SEED}
    coords: dict[str, tuple[float, float]] = {}
    for code in LOCALITES_PILOTES:
        if code not in index:
            raise RuntimeError(f"Pilote absent de LOCALITES_SEED : {code}")
        coords[code] = (float(index[code]["latitude"]), float(index[code]["longitude"]))
    for p in PREFECTURES_GUINEE:
        if p["existante"] is None:
            coords[p["commune_code"]] = (float(p["lat"]), float(p["lon"]))
    if len(coords) != 34:
        raise RuntimeError(f"Attendu 34 points, obtenu {len(coords)}")
    return coords


def telecharger_payload(code: str, lat: float, lon: float) -> dict[str, Any]:
    """Payload brut NASA monthly 10 params 1981-2025, avec cache disque par ville."""
    REPERTOIRE_CACHE.mkdir(parents=True, exist_ok=True)
    chemin_cache = REPERTOIRE_CACHE / f"{code}_{ANNEE_DEBUT}_{ANNEE_FIN}.json"
    if chemin_cache.exists():
        payload: dict[str, Any] = json.loads(chemin_cache.read_text(encoding="utf-8"))
        return payload
    payload = fetch_monthly_raw(
        latitude=lat,
        longitude=lon,
        parameters=list(PARAMETRES_NASA),
        annee_debut=ANNEE_DEBUT,
        annee_fin=ANNEE_FIN,
        httpx_client=None,
    )
    chemin_cache.write_text(json.dumps(payload), encoding="utf-8")
    return payload


def extraire(code: str, payload: dict[str, Any]) -> list[dict[str, Any]]:
    """Convertit un payload ville en lignes finales (filtres identiques au seam mensuel)."""
    param_source: dict[str, dict[str, float]] = payload["properties"]["parameter"]
    manquants = set(PARAMETRES_NASA) - set(param_source)
    if manquants:
        raise RuntimeError(f"{code} : paramètre(s) absent(s) du payload : {sorted(manquants)}")
    lignes: list[dict[str, Any]] = []
    for parametre_nasa, grandeur_code in PARAMETRES_NASA.items():
        for cle, valeur in param_source[parametre_nasa].items():
            annee_mois = _parse_cle_yyyymm(cle)
            if annee_mois is None:
                continue  # clé annuelle YYYY13
            if valeur == SENTINELLE_VALEUR_MANQUANTE:
                continue
            annee, mois = annee_mois
            lignes.append(
                {
                    "localite_code": code,
                    "grandeur_code": grandeur_code,
                    "annee": annee,
                    "mois": mois,
                    "valeur": float(valeur),
                }
            )
    return lignes


def verifier_uniformite(lignes_par_ville: dict[str, list[dict[str, Any]]]) -> None:
    """Garde : par grandeur, même couverture (annee, mois) sur les 34 villes."""
    reference: dict[str, frozenset[tuple[int, int]]] = {}
    ville_reference: str = ""
    for ville, lignes in lignes_par_ville.items():
        couverture: dict[str, set[tuple[int, int]]] = {g: set() for g in PARAMETRES_NASA.values()}
        for ligne in lignes:
            couverture[ligne["grandeur_code"]].add((ligne["annee"], ligne["mois"]))
        figee = {g: frozenset(c) for g, c in couverture.items()}
        if not reference:
            reference = figee
            ville_reference = ville
            continue
        for grandeur, ensemble in figee.items():
            if ensemble != reference[grandeur]:
                delta = ensemble ^ reference[grandeur]
                raise RuntimeError(
                    f"Couverture asymétrique pour {grandeur!r} : {ville} vs "
                    f"{ville_reference}, {len(delta)} mois d'écart, ex. {sorted(delta)[:5]}"
                )


def emettre_seed_ville(code: str, lignes: list[dict[str, Any]]) -> Path:
    """Écrit le compagnon .json.gz d'une ville (lignes triées, déterministe)."""
    lignes_triees = sorted(
        lignes, key=lambda r: (r["localite_code"], r["grandeur_code"], r["annee"], r["mois"])
    )
    chemin_gz = DOSSIER_SEED / f"nasa_power_monthly_profondeur_seed_data_{code}.json.gz"
    charge = json.dumps({"mensuel": lignes_triees}, separators=(",", ":")).encode("utf-8")
    chemin_gz.write_bytes(gzip.compress(charge, compresslevel=9))
    return chemin_gz


def main() -> None:
    print("=== Préparation seed NASA POWER mensuel profondeur (34 points, 1981-2025) ===")
    coords = coordonnees_tous_points()
    lignes_par_ville: dict[str, list[dict[str, Any]]] = {}
    for code, (lat, lon) in coords.items():
        print(f"  NASA monthly {code} ({lat:.4f}, {lon:.4f}) : 10 params 1981-2025...")
        payload = telecharger_payload(code, lat, lon)
        lignes = extraire(code, payload)
        print(f"    {len(lignes)} mois-valeurs")
        lignes_par_ville[code] = lignes

    verifier_uniformite(lignes_par_ville)

    # Fenêtres découvertes par grandeur (à figer dans la migration d'insertion).
    ville_temoin = next(iter(lignes_par_ville))
    fenetres: dict[str, tuple[int, int, int]] = {}
    for grandeur in PARAMETRES_NASA.values():
        mois_grandeur = sorted(
            (ligne["annee"], ligne["mois"])
            for ligne in lignes_par_ville[ville_temoin]
            if ligne["grandeur_code"] == grandeur
        )
        premier, dernier = mois_grandeur[0], mois_grandeur[-1]
        fenetres[grandeur] = (premier[0], dernier[0], len(mois_grandeur))
        print(
            f"  fenetre {grandeur}: {premier[0]}-{premier[1]:02d} -> "
            f"{dernier[0]}-{dernier[1]:02d} ({len(mois_grandeur)} mois/ville)"
        )

    total = 0
    for code, lignes in lignes_par_ville.items():
        chemin = emettre_seed_ville(code, lignes)
        total += len(lignes)
        print(f"    -> {chemin.name} ({chemin.stat().st_size / 1024:.0f} Ko)")
    CHEMIN_LOADER.write_text(_MODULE_LOADER, encoding="utf-8", newline="\n")
    print(f"  Loader: {CHEMIN_LOADER}")
    print(f"OK. {len(coords)} villes, {total} mesures mensuelles au total.")


if __name__ == "__main__":
    main()
