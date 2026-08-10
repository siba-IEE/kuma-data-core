"""Preparation du seed offline precipitation NASA POWER (soiling).

Script ponctuel (hors CI). Tire la precipitation journaliere
``PRECTOTCORR`` de NASA POWER pour les 6 villes pilotes, filtre la sentinelle
``-999`` et ecrit le seed committe
``src/kuma_data_core/db/seeds/precipitation_seed_data.py`` (chargeur) + son
compagnon gzippe ``precipitation_seed_data.json.gz``. La migration d'insertion
(080) ne depend QUE de ce fichier seed : **aucun appel reseau au runtime
migration ni en CI** (discipline seed-offline).

Choix de la voie (pas un clone du pipeline live ``ingestion/nasa_power_daily``,
qui joue le reseau en migration) : reutilise seulement le client HTTP bas niveau
``external.nasa_power.fetch_daily`` pour produire un artefact statique committe,
exactement comme ``preparer_seed_era5_land.py`` et ``preparer_seed_cams.py``.

PRECTOTCORR : "Precipitation Corrected" (mm/jour), source amont MERRA-2 GMAO /
IMERG selon la periode. Sentinelle manquante ``-999`` filtree.

Fenetre 2021-2025 : alignee sur la cohorte journaliere NASA POWER existante
(ghi/dni/dhi/t2m/rh2m/vent/albedo, series ``*_nasa_power_2021_2025``). Le PM
EAC4 (a venir) couvrira un sous-intervalle de cette fenetre ; le soiling operera
sur l'intersection PM ∩ pluie.

Usage :
    uv run python scripts/preparer_seed_precipitation.py

Idempotence : le seed produit est trie de facon stable (localite, date).
"""

from __future__ import annotations

import argparse
import gzip
import json
from datetime import date
from pathlib import Path
from typing import Any

from kuma_data_core.db.seeds.localites_prefectures_seed_data import PREFECTURES_GUINEE
from kuma_data_core.db.seeds.localites_seed_data import LOCALITES_SEED
from kuma_data_core.external.nasa_power import (
    SENTINELLE_VALEUR_MANQUANTE,
    fetch_daily,
)

# === Perimetre =============================================================

LOCALITES_PILOTES: tuple[str, ...] = (
    "gin_conakry_kaloum",
    "gin_kankan",
    "gin_kindia",
    "gin_labe",
    "gin_mamou",
    "gin_nzerekore",
)

PARAMETRE_NASA: str = "PRECTOTCORR"
ANNEE_DEBUT, ANNEE_FIN = 2021, 2025

# Calendrier complet 2021-2025 = 365*4 + 366 (2024 bissextile) = 1826 jours. NASA POWER
# daily renvoie une entree par jour (sentinelle -999 incluse) ; un retour incomplet =
# capture partielle a refuser a la source (garde de completude).
JOURS_ATTENDUS: int = 1826

CHEMIN_SEED = Path("src/kuma_data_core/db/seeds/precipitation_seed_data.py")
CHEMIN_SEED_DENSIF = Path("src/kuma_data_core/db/seeds/precipitation_densification_seed_data.py")


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

    Memes 28 que CAMS (PREFECTURES_GUINEE, ``existante is None``). Les 6 pilotes
    (capitales regionales + Conakry) en sont exclus : ils ont deja leur precipitation."""
    return {
        p["commune_code"]: (float(p["lat"]), float(p["lon"]))
        for p in PREFECTURES_GUINEE
        if p["existante"] is None
    }


# === Extraction par ville ==================================================


def _date_iso(cle_yyyymmdd: str) -> str:
    return f"{cle_yyyymmdd[:4]}-{cle_yyyymmdd[4:6]}-{cle_yyyymmdd[6:8]}"


def extraire_precipitation(
    code: str, lat: float, lon: float
) -> tuple[list[dict[str, Any]], dict[str, float]]:
    """Tire PRECTOTCORR journalier (mm/jour), filtre la sentinelle.

    Retourne (lignes triees, point geographique renvoye par NASA POWER : la
    cellule 0.5deg la plus proche).
    """
    print(f"  NASA POWER daily {PARAMETRE_NASA} {code} ({lat:.4f}, {lon:.4f})...")
    reponse = fetch_daily(
        latitude=lat,
        longitude=lon,
        parameters=[PARAMETRE_NASA],
        start=date(ANNEE_DEBUT, 1, 1),
        end=date(ANNEE_FIN, 12, 31),
    )
    serie = reponse.properties.parameter[PARAMETRE_NASA]
    # Garde de completude : calendrier complet AVANT filtrage -999
    # (capture partielle refusee a la source).
    if len(serie) != JOURS_ATTENDUS:
        raise RuntimeError(
            f"{code} : NASA POWER a renvoye {len(serie)} jours, attendu {JOURS_ATTENDUS} "
            f"(calendrier 2021-2025 complet, avant filtrage sentinelle). Capture partielle refusee."
        )
    lon_pt, lat_pt, alt_pt = reponse.geometry.coordinates
    lignes: list[dict[str, Any]] = []
    for cle in sorted(serie):
        valeur = serie[cle]
        if valeur == SENTINELLE_VALEUR_MANQUANTE:
            continue
        lignes.append(
            {
                "localite_code": code,
                "date": _date_iso(cle),
                "valeur": round(float(valeur), 4),
            }
        )
    point = {"latitude": float(lat_pt), "longitude": float(lon_pt), "altitude": float(alt_pt)}
    return lignes, point


# === Emission du seed ======================================================


# Module-chargeur ecrit en lieu et place du seed : la donnee (11 000 mesures)
# vit dans un compagnon gzippe pour rester sous la limite de taille du depot
# (pre-commit check-added-large-files, 1 Mo). gzip + json sont stdlib : aucune
# dependance scientifique au runtime (discipline seed-offline).
_MODULE_LOADER = '''\
"""Seed offline precipitation NASA POWER (Vague 5 soiling Lot B) - chargeur,
GENERE, ne pas editer.

Donnees reelles NASA POWER PRECTOTCORR (mm/jour) produites par
scripts/preparer_seed_precipitation.py. La donnee vit dans le compagnon gzippe
precipitation_seed_data.json.gz (sous la limite de taille du depot). gzip + json
sont stdlib : aucune dependance reseau ou scientifique au runtime migration.
"""

from __future__ import annotations

import gzip
import json
from pathlib import Path
from typing import Any

_DATA: dict[str, Any] = json.loads(
    gzip.decompress((Path(__file__).parent / "precipitation_seed_data.json.gz").read_bytes())
)

PRECIPITATION_POINTS: dict[str, dict[str, float]] = _DATA["points"]
PRECIPITATION_JOURNALIER_SEED: list[dict[str, Any]] = _DATA["journalier"]
'''


def emettre_seed(journalier: list[dict[str, Any]], points: dict[str, dict[str, float]]) -> None:
    journalier_tri = sorted(journalier, key=lambda r: (r["localite_code"], r["date"]))
    data = {
        "points": dict(sorted(points.items())),
        "journalier": journalier_tri,
    }
    chemin_gz = CHEMIN_SEED.parent / "precipitation_seed_data.json.gz"
    charge = json.dumps(data, separators=(",", ":")).encode("utf-8")
    chemin_gz.write_bytes(gzip.compress(charge, compresslevel=9))
    CHEMIN_SEED.write_text(_MODULE_LOADER, encoding="utf-8", newline="\n")
    print(f"  Seed: {len(journalier_tri)} mesures journalieres -> {chemin_gz}")


# Chargeur densification : seed SEPARE des 28 communes (le seed pilote reste intact,
# mirror du seed densification CAMS).
_MODULE_LOADER_DENSIF = '''\
"""Seed offline precipitation NASA POWER (densification 28 communes) - chargeur,
GENERE, ne pas editer.

Donnees reelles NASA POWER PRECTOTCORR (mm/jour) pour les 28 communes chef-lieu,
produites par scripts/preparer_seed_precipitation.py --densification. La donnee vit
dans le compagnon gzippe precipitation_densification_seed_data.json.gz (sous la limite
de taille du depot). gzip + json sont stdlib : aucune dependance reseau ou scientifique
au runtime migration.
"""

from __future__ import annotations

import gzip
import json
from pathlib import Path
from typing import Any

_DATA: dict[str, Any] = json.loads(
    gzip.decompress(
        (Path(__file__).parent / "precipitation_densification_seed_data.json.gz").read_bytes()
    )
)

PRECIPITATION_DENSIFICATION_POINTS: dict[str, dict[str, float]] = _DATA["points"]
PRECIPITATION_DENSIFICATION_SEED: list[dict[str, Any]] = _DATA["journalier"]
'''


def emettre_seed_densification(
    journalier: list[dict[str, Any]], points: dict[str, dict[str, float]]
) -> None:
    """Ecrit le seed densification 28 communes (fichier SEPARE, pilotes intacts)."""
    journalier_tri = sorted(journalier, key=lambda r: (r["localite_code"], r["date"]))
    data = {"points": dict(sorted(points.items())), "journalier": journalier_tri}
    chemin_gz = CHEMIN_SEED_DENSIF.parent / "precipitation_densification_seed_data.json.gz"
    charge = json.dumps(data, separators=(",", ":")).encode("utf-8")
    chemin_gz.write_bytes(gzip.compress(charge, compresslevel=9))
    CHEMIN_SEED_DENSIF.write_text(_MODULE_LOADER_DENSIF, encoding="utf-8", newline="\n")
    print(f"  Seed densif: {len(journalier_tri)} mesures journalieres -> {chemin_gz}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Prepare le seed offline precipitation NASA POWER (PRECTOTCORR)."
    )
    parser.add_argument(
        "--densification",
        action="store_true",
        help="28 communes chef-lieu (seed separe), au lieu des 6 pilotes.",
    )
    args = parser.parse_args()

    if args.densification:
        print("=== Preparation seed precipitation NASA POWER (densification 28 communes) ===")
        coords = coordonnees_densification()
        if len(coords) != 28:
            raise RuntimeError(f"Densification : attendu 28 communes, obtenu {len(coords)}.")
    else:
        print("=== Preparation seed precipitation NASA POWER (Vague 5 soiling Lot B) ===")
        coords = coordonnees_pilotes()

    journalier: list[dict[str, Any]] = []
    points: dict[str, dict[str, float]] = {}
    for code, (lat, lon) in coords.items():
        lignes, point = extraire_precipitation(code, lat, lon)
        journalier.extend(lignes)
        points[code] = point

    if args.densification:
        emettre_seed_densification(journalier, points)
        print("\nOK. Lancer ensuite la migration 094 puis les tests d'integration.")
    else:
        emettre_seed(journalier, points)
        print("\nOK. Lancer ensuite la migration 080 puis les tests d'integration.")


if __name__ == "__main__":
    main()
