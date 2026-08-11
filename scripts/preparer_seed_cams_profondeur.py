"""Préparation des seeds offline CAMS Radiation profondeur (mensuel et journalier).

Script ponctuel (dev deps), exécuté manuellement hors CI. Télécharge depuis
l'ADS Copernicus, pour chacun des **34 points** (6 pilotes + 28 communes), le
CSV ``cams-solar-radiation-timeseries`` sur la fenêtre pleine 2004-2025, aux
pas **mensuel** et **journalier**. Le même CSV porte les quatre composantes
all-sky (GHI, BHI, DHI, BNI) : une requête par ville et par pas suffit, soit
68 requêtes au total (file d'attente ADS possible, cache disque par ville).

En dérive trois seeds NE-OFFLINE (lignes finales converties, aucun réseau au
runtime migration), dans des namespaces séparés des seeds existants :

- ``cams_profondeur_mensuel_seed_data`` : ghi et dhi mensuels, fenêtre pleine
  2004-02 -> 2025-12 (les migrations découpent climato 2004-2020 et récent
  2021-2025) ;
- ``cams_profondeur_journalier_seed_data_<ville>`` : ghi, dhi et dni
  journaliers 2004-02 -> 2025-12, un compagnon par ville.

Le DNI mensuel n'est pas re-seedé : ses fenêtres existantes (climato 2004-2020,
récent 2021-2023 aligné sur l'atlas) restent la référence de l'écart
inter-source ; la période 2024-2025 du direct arrive par le journalier.

Conversions : mensuel Wh/m2 par mois -> kWh/m2/jour (division par 1000 puis
par le nombre réel de jours du mois) ; journalier Wh/m2 par jour ->
kWh/m2/jour (division par 1000). Caveat D-71 à reconduire côté migrations.

Usage : uv run --group dev python scripts/preparer_seed_cams_profondeur.py
"""

from __future__ import annotations

import calendar
import gzip
import json
import math
import os
from pathlib import Path
from typing import Any

import cdsapi  # type: ignore[import-untyped]

from kuma_data_core.db.seeds.localites_prefectures_seed_data import PREFECTURES_GUINEE
from kuma_data_core.db.seeds.localites_seed_data import LOCALITES_SEED

LOCALITES_PILOTES: tuple[str, ...] = (
    "gin_conakry_kaloum",
    "gin_kankan",
    "gin_kindia",
    "gin_labe",
    "gin_mamou",
    "gin_nzerekore",
)

DATASET = "cams-solar-radiation-timeseries"
ADS_URL = "https://ads.atmosphere.copernicus.eu/api"
FENETRE = ("2004-01-01", "2025-12-31")

# Colonnes du CSV CAMS (0-indexées) : 6 = GHI all-sky, 8 = DHI all-sky,
# 9 = BNI all-sky (constat du lot DNI existant, colonne 10 en 1-indexé).
COLONNES = {"ghi": 6, "dhi": 8, "dni": 9}
GRANDEURS_MENSUEL = ("ghi", "dhi")
GRANDEURS_JOURNALIER = ("ghi", "dhi", "dni")
WH_PAR_KWH = 1000.0

REPERTOIRE_CACHE = Path("data/cams_profondeur")
DOSSIER_SEED = Path("src/kuma_data_core/db/seeds")

_LOADER_MENSUEL = '''\
"""Seed offline CAMS Radiation profondeur mensuel - chargeur, GÉNÉRÉ, ne pas éditer.

Lignes finales ``(localite_code, grandeur_code, annee, mois, valeur)`` des 34
points, ghi et dhi all-sky, fenêtre 2004-02 -> 2025-12, converties en
kWh/m2/jour. Produit par scripts/preparer_seed_cams_profondeur.py. Patron
NE-OFFLINE. Attribution CC-BY Copernicus/CAMS requise.
"""

from __future__ import annotations

import gzip
import json
from pathlib import Path
from typing import Any

_CHEMIN = Path(__file__).parent / "cams_profondeur_mensuel_seed_data.json.gz"
_DATA: dict[str, Any] = json.loads(gzip.decompress(_CHEMIN.read_bytes()))

CAMS_PROFONDEUR_MENSUEL_SEED: list[dict[str, Any]] = _DATA["mensuel"]
'''

_LOADER_JOURNALIER = '''\
"""Seed offline CAMS Radiation profondeur journalier - chargeur, GÉNÉRÉ, ne pas éditer.

Blocs par série ``{localite_code, grandeur_code, valeurs: {date: valeur}}``
des 34 points, ghi, dhi et dni all-sky, fenêtre 2004-02 -> 2025-12, convertis
en kWh/m2/jour. Un compagnon .json.gz par ville, consommé en streaming via
``iter_blocs_cams_journalier()``. Produit par
scripts/preparer_seed_cams_profondeur.py. Patron NE-OFFLINE. Attribution
CC-BY Copernicus/CAMS requise.
"""

from __future__ import annotations

import gzip
import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any

_DOSSIER = Path(__file__).parent


def iter_blocs_cams_journalier() -> Iterator[dict[str, Any]]:
    """Streame les blocs (ville x grandeur), un fichier gzip à la fois."""
    for chemin in sorted(_DOSSIER.glob("cams_profondeur_journalier_seed_data_*.json.gz")):
        bloc_fichier: dict[str, Any] = json.loads(gzip.decompress(chemin.read_bytes()))
        yield from bloc_fichier["journalier"]
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


def _client() -> cdsapi.Client:
    rc: dict[str, str] = {}
    with open(os.path.expanduser("~/.cdsapirc")) as f:
        for line in f:
            if line.strip() and ":" in line:
                cle, val = line.split(":", 1)
                rc[cle.strip()] = val.strip()
    return cdsapi.Client(url=ADS_URL, key=rc["key"])


def telecharger(client: cdsapi.Client, code: str, lat: float, lon: float, pas: str) -> Path:
    chemin = REPERTOIRE_CACHE / f"{code}_{pas}_2004_2025.csv"
    if chemin.exists():
        return chemin
    REPERTOIRE_CACHE.mkdir(parents=True, exist_ok=True)
    print(f"  ADS {code} pas={pas} ({lat:.4f}, {lon:.4f}) - file d'attente possible...")
    client.retrieve(
        DATASET,
        {
            "sky_type": "observed_cloud",
            "location": {"latitude": lat, "longitude": lon},
            "altitude": ["-999."],
            "date": [f"{FENETRE[0]}/{FENETRE[1]}"],
            "time_step": pas,
            "time_reference": "universal_time",
            "format": "csv",
        },
        str(chemin),
    )
    return chemin


def _lignes_csv(chemin: Path) -> list[list[str]]:
    lignes = []
    for ln in chemin.read_text(encoding="utf-8", errors="replace").splitlines():
        if not ln or ln.startswith("#"):
            continue
        cols = ln.split(";")
        if len(cols) > max(COLONNES.values()):
            lignes.append(cols)
    return lignes


def extraire_mensuel(code: str, chemin: Path) -> list[dict[str, Any]]:
    """Wh/m2/mois -> kWh/m2/jour, lignes plates (ghi, dhi)."""
    sortie: list[dict[str, Any]] = []
    for cols in _lignes_csv(chemin):
        periode = cols[0].strip()  # '2021-01-01T00:00:00.0/2021-02-01T00:00:00.0'
        annee, mois = int(periode[:4]), int(periode[5:7])
        n_jours = calendar.monthrange(annee, mois)[1]
        for grandeur in GRANDEURS_MENSUEL:
            brut = float(cols[COLONNES[grandeur]].strip())
            if math.isnan(brut):
                continue
            sortie.append(
                {
                    "localite_code": code,
                    "grandeur_code": grandeur,
                    "annee": annee,
                    "mois": mois,
                    "valeur": round((brut / WH_PAR_KWH) / n_jours, 4),
                }
            )
    return sortie


def extraire_journalier(code: str, chemin: Path) -> list[dict[str, Any]]:
    """Wh/m2/jour -> kWh/m2/jour, blocs par grandeur (streaming côté migration)."""
    cartes: dict[str, dict[str, float]] = {g: {} for g in GRANDEURS_JOURNALIER}
    for cols in _lignes_csv(chemin):
        jour = cols[0].strip()[:10]  # '2021-01-01'
        for grandeur in GRANDEURS_JOURNALIER:
            brut = float(cols[COLONNES[grandeur]].strip())
            if math.isnan(brut):
                continue
            cartes[grandeur][jour] = round(brut / WH_PAR_KWH, 4)
    return [
        {"localite_code": code, "grandeur_code": g, "valeurs": dict(sorted(c.items()))}
        for g, c in cartes.items()
        if c
    ]


def main() -> None:
    print("=== Préparation seeds CAMS profondeur (34 points, 2004-2025) ===")
    coords = coordonnees_tous_points()
    client = _client()

    mensuel: list[dict[str, Any]] = []
    for code, (lat, lon) in coords.items():
        chemin = telecharger(client, code, lat, lon, "1month")
        lignes = extraire_mensuel(code, chemin)
        print(f"  mensuel {code}: {len(lignes)} valeurs")
        mensuel.extend(lignes)
    mensuel.sort(key=lambda r: (r["localite_code"], r["grandeur_code"], r["annee"], r["mois"]))
    chemin_gz = DOSSIER_SEED / "cams_profondeur_mensuel_seed_data.json.gz"
    chemin_gz.write_bytes(
        gzip.compress(
            json.dumps({"mensuel": mensuel}, separators=(",", ":")).encode("utf-8"),
            compresslevel=9,
        )
    )
    (DOSSIER_SEED / "cams_profondeur_mensuel_seed_data.py").write_text(
        _LOADER_MENSUEL, encoding="utf-8", newline="\n"
    )
    print(f"  Seed mensuel : {len(mensuel)} valeurs -> {chemin_gz.name}")

    total_journalier = 0
    for code, (lat, lon) in coords.items():
        chemin = telecharger(client, code, lat, lon, "1day")
        blocs = extraire_journalier(code, chemin)
        n = sum(len(b["valeurs"]) for b in blocs)
        total_journalier += n
        chemin_gz = DOSSIER_SEED / f"cams_profondeur_journalier_seed_data_{code}.json.gz"
        chemin_gz.write_bytes(
            gzip.compress(
                json.dumps({"journalier": blocs}, separators=(",", ":")).encode("utf-8"),
                compresslevel=9,
            )
        )
        print(f"  journalier {code}: {n} valeurs -> {chemin_gz.name}")
    (DOSSIER_SEED / "cams_profondeur_journalier_seed_data.py").write_text(
        _LOADER_JOURNALIER, encoding="utf-8", newline="\n"
    )
    print(f"OK. Mensuel {len(mensuel)} valeurs ; journalier {total_journalier} valeurs.")


if __name__ == "__main__":
    main()
