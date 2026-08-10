"""Tire l'artefact CAMS clear-sky DNI (BNIc) HORAIRE - Kankan - test du socle.

Script ponctuel (dev deps), hors CI, **hors base, hors migration**.
Re-tire ``cams-solar-radiation-timeseries`` (ADS Copernicus) au pas **horaire**
pour le pixel Kankan, recouvrement 2021-2023, et extrait les deux composantes du
faisceau normal :

- **col 6 = Clear sky BNI** (``BNIc``) - le DNI **ciel-clair modélisé** de CAMS
  (socle turbidité/aérosol, sans nuages) ;
- **col 10 = BNI** all-sky - le DNI réel (déjà la série Core mensuelle).

Écrit un **artefact committé trimmé** (gzip CSV) lu par
``scripts/analyse_clear_sky_dni_kankan.py``, pour que le test du socle soit
**reproductible hors-réseau**. Ce n'est PAS un seed (rien n'entre en base) : c'est
une donnée de référence d'analyse, attribution CC-BY Copernicus/CAMS requise.

Faits API **vérifiés** (``preparer_seed_cams.py``, sondage ADS 2026-06-16) :
endpoint ADS ``…/api`` ; dataset ``cams-solar-radiation-timeseries`` ;
``sky_type=observed_cloud`` (livre clear-sky ET all-sky dans le même CSV) ;
``time_reference=universal_time`` ; CSV ``;``-séparé, en-têtes ``#``.

**Unité** : au pas horaire, l'intégrale ``Wh/m²`` sur 1 h **vaut la moyenne
``W/m²`` de l'heure** → directement comparable au DNI sol horaire (W/m²).

Usage : ``uv run --group dev python scripts/preparer_artefact_cams_bnic_horaire.py``
"""

from __future__ import annotations

import datetime as dt
import gzip
import math
import os
from pathlib import Path

import cdsapi  # type: ignore[import-untyped]

from kuma_data_core.db.seeds.localites_seed_data import LOCALITES_SEED

# === Périmètre =============================================================

LOCALITE = "gin_kankan"
DATASET = "cams-solar-radiation-timeseries"
ADS_URL = "https://ads.atmosphere.copernicus.eu/api"
ANNEE_DEBUT, ANNEE_FIN = 2021, 2023

COL_BNIC = 5  # col 6 (1-indexée) = Clear sky BNI (DNI ciel-clair modélisé)
COL_BNI = 9  # col 10 = BNI all-sky (DNI réel)
COL_FIAB = 10  # col 11 = Reliability (0-1)

REPERTOIRE_CACHE = Path("data/cams")  # cache brut (git-ignoré)
REPERTOIRE_ARTEFACT = Path("scripts/donnees")  # artefact committé (reproductibilité)
NOM_ARTEFACT = "cams_bnic_horaire_kankan_2021_2023.csv.gz"


def _coords() -> tuple[float, float]:
    index = {e["code"]: e for e in LOCALITES_SEED}
    e = index[LOCALITE]
    return float(e["latitude"]), float(e["longitude"])


def _client() -> cdsapi.Client:
    """Client cdsapi pointé sur l'ADS, token réutilisé du ``.cdsapirc``."""
    rc: dict[str, str] = {}
    with open(os.path.expanduser("~/.cdsapirc")) as f:
        for line in f:
            if line.strip() and ":" in line:
                cle, val = line.split(":", 1)
                rc[cle.strip()] = val.strip()
    return cdsapi.Client(url=ADS_URL, key=rc["key"])


def telecharger(client: cdsapi.Client, lat: float, lon: float) -> Path:
    chemin = REPERTOIRE_CACHE / f"{LOCALITE}_bnic_horaire_{ANNEE_DEBUT}_{ANNEE_FIN}.csv"
    if chemin.exists():
        print(f"  cache présent : {chemin}")
        return chemin
    REPERTOIRE_CACHE.mkdir(parents=True, exist_ok=True)
    print(f"  CAMS horaire {LOCALITE} ({lat:.4f}, {lon:.4f}) - file d'attente possible...")
    client.retrieve(
        DATASET,
        {
            "sky_type": "observed_cloud",
            "location": {"latitude": lat, "longitude": lon},
            "altitude": ["-999."],
            "date": [f"{ANNEE_DEBUT}-01-01/{ANNEE_FIN}-12-31"],
            "time_step": "1hour",
            "time_reference": "universal_time",
            "format": "csv",
        },
        str(chemin),
    )
    return chemin


def trimmer(chemin: Path) -> list[tuple[str, float, float, float]]:
    """CSV CAMS brut → lignes (instant_utc hour-beginning, bnic, bni, fiabilite)."""
    lignes: list[tuple[str, float, float, float]] = []
    for ln in chemin.read_text(encoding="utf-8", errors="replace").splitlines():
        if not ln or ln.startswith("#"):
            continue
        cols = ln.split(";")
        if len(cols) <= COL_FIAB:
            continue
        debut = cols[0].split("/")[0].strip()  # '2021-01-01T00:00:00.0'
        instant = dt.datetime.fromisoformat(debut[:19]).replace(tzinfo=dt.UTC)
        bnic, bni, fiab = (
            float(cols[COL_BNIC]),
            float(cols[COL_BNI]),
            float(cols[COL_FIAB]),
        )
        if math.isnan(bnic) or math.isnan(bni):
            continue
        lignes.append(
            (instant.strftime("%Y-%m-%dT%H:%M:%S+00:00"), round(bnic, 3), round(bni, 3), fiab)
        )
    lignes.sort(key=lambda r: r[0])
    return lignes


def emettre(lignes: list[tuple[str, float, float, float]]) -> None:
    REPERTOIRE_ARTEFACT.mkdir(parents=True, exist_ok=True)
    chemin = REPERTOIRE_ARTEFACT / NOM_ARTEFACT
    contenu = "instant_utc;bnic_wmh;bni_wmh;fiabilite\n" + "\n".join(
        f"{i};{bnic};{bni};{fiab}" for (i, bnic, bni, fiab) in lignes
    )
    chemin.write_bytes(gzip.compress(contenu.encode("utf-8"), compresslevel=9))
    print(f"  Artefact : {len(lignes)} heures -> {chemin} ({chemin.stat().st_size} octets)")


def main() -> None:
    lat, lon = _coords()
    print(f"=== Artefact CAMS BNIc horaire {LOCALITE} {ANNEE_DEBUT}-{ANNEE_FIN} ===")
    chemin = telecharger(_client(), lat, lon)
    lignes = trimmer(chemin)
    if lignes:
        print(f"  Plage : {lignes[0][0]} -> {lignes[-1][0]}")
        bnic_vals = [r[1] for r in lignes]
        print(f"  BNIc horaire (Wh/m²/h ≈ W/m²) : min={min(bnic_vals)} max={max(bnic_vals)}")
    emettre(lignes)
    print("OK.")


if __name__ == "__main__":
    main()
