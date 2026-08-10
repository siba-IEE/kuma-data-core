"""Préparation du seed offline NASA POWER daily profondeur (séries longues).

Livrable **humain ponctuel** (hors CI). Capture en **live** le journalier NASA
POWER **pleine profondeur** (1981-01-01 -> 2020-12-31) des **34 points**
(6 pilotes + 28 communes chef-lieu), le convertit en lignes finales
``(localite_code, grandeur_code, date, valeur)`` et écrit un seed committé
**par ville x décennie** (patron NE-OFFLINE : la migration lit le seed
directement, aucun module d'ingestion ni réseau au runtime migration).

**Distinct du seed daily 2021-2025** ``nasa_power_daily_seed_data_*``
(payloads bruts consommés en offline par les migrations immuables
018/020/022/029/048/086) : namespace séparé, zéro retouche du snapshot
existant. Le backfill s'arrête au 2020-12-31, borne d'adjacence exacte avec
les séries daily 2021-2025 en base.

Profondeurs réelles par palier (sondes API des 2026-08-09) :

- **1981-01-01** : t2m, rh2m, vent_2m, vent_10m, precipitation (MERRA-2) ;
- **1984-01-01** : ghi, dhi ;
- **2001-01-01** : dni, kt, albedo_surface (début des observations CERES).

Le script ne code PAS ces paliers en dur : il demande 1981-2020 pour les 10
paramètres et filtre les sentinelles ``-999`` (sonde vérifiée : sur fenêtre
mixte, l'API renvoie le paramètre avec sentinelles avant son plancher).
Contrairement au mensuel (couverture parfaitement uniforme), le journalier
peut porter des trous sporadiques par ville : le script IMPRIME le décompte
par grandeur x ville et les bornes ; la migration d'insertion pose des gardes
plancher/cap et dérive ses comptes du seed (patron précipitation).

**Découpage par ville x décennie** (4 fenêtres : 1981-1990, 1991-2000,
2001-2010, 2011-2020) : 136 compagnons ``.json.gz``, chacun loin sous le hook
``check-added-large-files --maxkb=1024``. Cache brut par ville x décennie sous
``data/nasa_power_daily_profondeur/`` (relance sans re-fetch).

Usage : ``uv run --group dev python scripts/preparer_seed_nasa_daily_profondeur.py``
"""

from __future__ import annotations

import gzip
import json
from datetime import date
from pathlib import Path
from typing import Any

from kuma_data_core.db.seeds.localites_prefectures_seed_data import PREFECTURES_GUINEE
from kuma_data_core.db.seeds.localites_seed_data import LOCALITES_SEED
from kuma_data_core.external.nasa_power import (
    SENTINELLE_VALEUR_MANQUANTE,
    fetch_daily_raw,
)

# === Périmètre : 34 points = 6 pilotes + 28 communes densification =========

LOCALITES_PILOTES: tuple[str, ...] = (
    "gin_conakry_kaloum",
    "gin_kankan",
    "gin_kindia",
    "gin_labe",
    "gin_mamou",
    "gin_nzerekore",
)

# 10 paramètres journaliers (code NASA -> grandeur Kuma), fenêtre 1981-2020.
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

# Décennies de capture et de chunking du seed (fin exclusive au 31 décembre).
DECENNIES: tuple[tuple[date, date], ...] = (
    (date(1981, 1, 1), date(1990, 12, 31)),
    (date(1991, 1, 1), date(2000, 12, 31)),
    (date(2001, 1, 1), date(2010, 12, 31)),
    (date(2011, 1, 1), date(2020, 12, 31)),
)

REPERTOIRE_CACHE = Path("data/nasa_power_daily_profondeur")
DOSSIER_SEED = Path("src/kuma_data_core/db/seeds")
CHEMIN_LOADER = DOSSIER_SEED / "nasa_power_daily_profondeur_seed_data.py"

_MODULE_LOADER = '''\
"""Seed offline NASA POWER daily profondeur - chargeur, GÉNÉRÉ, ne pas éditer.

Blocs par série ``{localite_code, grandeur_code, valeurs: {date: valeur}}``
des 34 points (6 pilotes + 28 communes), fenêtre 1981-2020, produits par
scripts/preparer_seed_nasa_daily_profondeur.py (sentinelles -999 déjà
filtrées). Format groupé par série (4,1 M de valeurs) : consommer via
``iter_blocs_daily_profondeur()`` qui streame fichier par fichier, la
migration n'a jamais tout le seed en mémoire d'un coup. Patron NE-OFFLINE :
aucun réseau au runtime. gzip + json stdlib ; un compagnon .json.gz par
ville x décennie.
"""

from __future__ import annotations

import gzip
import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any

_DOSSIER = Path(__file__).parent


def iter_blocs_daily_profondeur() -> Iterator[dict[str, Any]]:
    """Streame les blocs (ville x grandeur x décennie), un fichier gzip à la fois."""
    for chemin in sorted(_DOSSIER.glob("nasa_power_daily_profondeur_seed_data_*.json.gz")):
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


def telecharger_payload(
    code: str, lat: float, lon: float, debut: date, fin: date
) -> dict[str, Any]:
    """Payload brut NASA daily 10 params sur une décennie, avec cache disque."""
    REPERTOIRE_CACHE.mkdir(parents=True, exist_ok=True)
    chemin_cache = REPERTOIRE_CACHE / f"{code}_{debut.year}_{fin.year}.json"
    if chemin_cache.exists():
        payload: dict[str, Any] = json.loads(chemin_cache.read_text(encoding="utf-8"))
        return payload
    payload = fetch_daily_raw(
        latitude=lat,
        longitude=lon,
        parameters=list(PARAMETRES_NASA),
        start=debut,
        end=fin,
        httpx_client=None,
    )
    chemin_cache.write_text(json.dumps(payload), encoding="utf-8")
    return payload


def extraire(code: str, payload: dict[str, Any]) -> dict[str, dict[str, float]]:
    """Convertit un payload ville x décennie en cartes ``grandeur -> {date: valeur}``.

    Format groupé par série (pas de lignes plates) : la migration itère 340
    blocs (ville x grandeur) au lieu de charger 4,1 M de dicts en mémoire.
    Sentinelles ``-999`` filtrées ici.
    """
    param_source: dict[str, dict[str, float]] = payload["properties"]["parameter"]
    cartes: dict[str, dict[str, float]] = {}
    for parametre_nasa, grandeur_code in PARAMETRES_NASA.items():
        # Un paramètre peut être absent si toute la fenêtre précède son
        # plancher (cas 1981-1990 x CERES selon les époques de l'API).
        carte = {
            f"{cle[:4]}-{cle[4:6]}-{cle[6:8]}": float(valeur)
            for cle, valeur in param_source.get(parametre_nasa, {}).items()
            if valeur != SENTINELLE_VALEUR_MANQUANTE
        }
        if carte:
            cartes[grandeur_code] = carte
    return cartes


def emettre_seed_chunk(code: str, debut: date, cartes: dict[str, dict[str, float]]) -> Path:
    """Écrit le compagnon .json.gz d'une ville x décennie (blocs par grandeur triés)."""
    blocs = [
        {
            "localite_code": code,
            "grandeur_code": grandeur,
            "valeurs": dict(sorted(cartes[grandeur].items())),
        }
        for grandeur in sorted(cartes)
    ]
    chemin_gz = DOSSIER_SEED / f"nasa_power_daily_profondeur_seed_data_{code}_{debut.year}.json.gz"
    charge = json.dumps({"journalier": blocs}, separators=(",", ":")).encode("utf-8")
    chemin_gz.write_bytes(gzip.compress(charge, compresslevel=9))
    return chemin_gz


def main() -> None:
    print("=== Préparation seed NASA POWER daily profondeur (34 points, 1981-2020) ===")
    coords = coordonnees_tous_points()
    compte_par_grandeur_ville: dict[tuple[str, str], int] = {}
    bornes_par_grandeur: dict[str, tuple[str, str]] = {}
    total = 0
    taille_max_ko = 0.0
    for code, (lat, lon) in coords.items():
        for debut, fin in DECENNIES:
            payload = telecharger_payload(code, lat, lon, debut, fin)
            cartes = extraire(code, payload)
            chemin = emettre_seed_chunk(code, debut, cartes)
            taille_ko = chemin.stat().st_size / 1024
            taille_max_ko = max(taille_max_ko, taille_ko)
            n_chunk = sum(len(c) for c in cartes.values())
            total += n_chunk
            for grandeur, carte in cartes.items():
                cle_gv = (grandeur, code)
                compte_par_grandeur_ville[cle_gv] = compte_par_grandeur_ville.get(cle_gv, 0) + len(
                    carte
                )
                d_min, d_max = min(carte), max(carte)
                lo_hi = bornes_par_grandeur.get(grandeur)
                bornes_par_grandeur[grandeur] = (
                    (d_min, d_max)
                    if lo_hi is None
                    else (min(lo_hi[0], d_min), max(lo_hi[1], d_max))
                )
            print(
                f"  {code} {debut.year}-{fin.year} : {n_chunk} valeurs "
                f"-> {chemin.name} ({taille_ko:.0f} Ko)"
            )

    print("\n=== Synthèse par grandeur (min/max de lignes par ville, bornes) ===")
    for grandeur in sorted(set(PARAMETRES_NASA.values())):
        comptes = [n for (g, _v), n in compte_par_grandeur_ville.items() if g == grandeur]
        lo, hi = bornes_par_grandeur[grandeur]
        print(
            f"  {grandeur}: villes={len(comptes)} min={min(comptes)} max={max(comptes)} "
            f"bornes {lo} .. {hi}"
        )
    CHEMIN_LOADER.write_text(_MODULE_LOADER, encoding="utf-8", newline="\n")
    print(f"  Loader: {CHEMIN_LOADER}")
    print(f"OK. 34 villes, {total} mesures journalières, chunk max {taille_max_ko:.0f} Ko.")


if __name__ == "__main__":
    main()
