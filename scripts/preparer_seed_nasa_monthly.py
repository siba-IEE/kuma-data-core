"""Préparation du seed offline NASA POWER monthly.

Livrable **humain ponctuel** (hors CI). Capture en **live** le payload JSON brut
NASA POWER monthly (climato 1991-2020, 9 paramètres) des **34 points** (6 villes
pilotes + 28 nouvelles communes densification), et écrit un seed committé **par
ville** ``nasa_power_monthly_seed_data_<code>.json.gz`` + le chargeur
``src/kuma_data_core/db/seeds/nasa_power_monthly_seed_data.py``. En CI, sous
``KUMA_INGESTION_MODE=offline``, l'ingestion renvoie ce payload (restreint aux
paramètres et à la fenêtre d'années demandés côté module) au lieu d'appeler NASA
POWER -> réseau nul.

**Climato long-terme = figée** : un seul snapshot stable, pas de maturation
(contrairement au daily NRT). Le seed couvre les 6 pilotes (**retrofit** : la
migration 050 immuable les lit en mode offline, comme le daily l'a fait sans
éditer 018/020/...) ET les 28 nouvelles communes.

**Fenêtre du seed : 1991-2020 pour les 9 paramètres.** Les paramètres CERES
(DHI/DNI/KT/albédo) sont sentinelle avant 2001 ; le tranchage offline restreint
chaque requête à sa fenêtre réelle (1991-2020 pour MERRA-2, 2001-2020 pour CERES).

**Découpage par ville** : un compagnon ``.json.gz`` par ville (10-20 Ko : 9
params x 30 ans x 12 mois), bien sous le hook ``check-added-large-files``.

Usage : ``uv run --group dev python scripts/preparer_seed_nasa_monthly.py``
(mode ``live`` ; le script appelle ``fetch_monthly_raw`` directement, hors seam).
"""

from __future__ import annotations

import gzip
import json
from pathlib import Path
from typing import Any

from kuma_data_core.db.seeds.localites_prefectures_seed_data import PREFECTURES_GUINEE
from kuma_data_core.db.seeds.localites_seed_data import LOCALITES_SEED
from kuma_data_core.external.nasa_power import fetch_monthly_raw
from kuma_data_core.ingestion.nasa_power_monthly import _cle_ville_offline

# === Périmètre : 34 points = 6 pilotes (migration 050) + 28 communes ========

LOCALITES_PILOTES: tuple[str, ...] = (
    "gin_conakry_kaloum",
    "gin_kankan",
    "gin_kindia",
    "gin_labe",
    "gin_mamou",
    "gin_nzerekore",
)
LOCALITES_DENSIFICATION: tuple[str, ...] = tuple(
    p["commune_code"] for p in PREFECTURES_GUINEE if p["existante"] is None
)

# Union des 9 paramètres monthly (code NASA -> grandeur Kuma), fenêtre pleine.
PARAMETRES_NASA_MONTHLY: tuple[str, ...] = (
    "ALLSKY_SFC_SW_DWN",  # ghi (041, 1991-2020)
    "T2M",  # t2m (050, 1991-2020)
    "RH2M",  # rh2m (050, 1991-2020)
    "WS2M",  # vent_2m (050, 1991-2020)
    "WS10M",  # vent_10m (050, 1991-2020)
    "ALLSKY_SFC_SW_DIFF",  # dhi (050, 2001-2020 CERES)
    "ALLSKY_SFC_SW_DNI",  # dni (050, 2001-2020 CERES)
    "ALLSKY_KT",  # kt (050, 2001-2020 CERES)
    "ALLSKY_SRF_ALB",  # albedo_surface (050, 2001-2020 CERES)
)
ANNEE_DEBUT = 1991
ANNEE_FIN = 2020

DOSSIER_SEED = Path("src/kuma_data_core/db/seeds")
CHEMIN_LOADER = DOSSIER_SEED / "nasa_power_monthly_seed_data.py"

_MODULE_LOADER = '''\
"""Seed offline NASA POWER monthly (D-40 lot 3) - chargeur, GÉNÉRÉ, ne pas éditer.

Payloads JSON bruts NASA POWER monthly (9 paramètres, 34 points, climato
1991-2020), capturés par scripts/preparer_seed_nasa_monthly.py. Permettent à
l'ingestion de renvoyer la donnée hors-ligne (KUMA_INGESTION_MODE=offline) sans
appel réseau, restreinte par paramètres/fenêtre d'années côté module. gzip + json
stdlib ; un compagnon .json.gz par ville. Clé : round(lat,4)_round(lon,4).
"""

from __future__ import annotations

import gzip
import json
from pathlib import Path
from typing import Any

_DOSSIER = Path(__file__).parent

NASA_MONTHLY_PAYLOADS: dict[str, Any] = {}
for _chemin in sorted(_DOSSIER.glob("nasa_power_monthly_seed_data_*.json.gz")):
    _bloc: dict[str, Any] = json.loads(gzip.decompress(_chemin.read_bytes()))
    NASA_MONTHLY_PAYLOADS.update(_bloc["payloads"])
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
    return coords


def emettre_seed_ville(code: str, cle: str, payload: dict[str, Any]) -> Path:
    """Écrit le compagnon .json.gz d'une ville et retourne son chemin."""
    chemin_gz = DOSSIER_SEED / f"nasa_power_monthly_seed_data_{code}.json.gz"
    charge = json.dumps({"payloads": {cle: payload}}, separators=(",", ":"), sort_keys=True).encode(
        "utf-8"
    )
    chemin_gz.write_bytes(gzip.compress(charge, compresslevel=9))
    return chemin_gz


def main() -> None:
    print("=== Préparation seed NASA POWER monthly (D-40 lot 3) ===")
    coords = coordonnees_tous_points()
    for code, (lat, lon) in coords.items():
        print(
            f"  NASA monthly {code} ({lat:.4f}, {lon:.4f}) : "
            f"{len(PARAMETRES_NASA_MONTHLY)} params {ANNEE_DEBUT}-{ANNEE_FIN}..."
        )
        payload = fetch_monthly_raw(
            latitude=lat,
            longitude=lon,
            parameters=list(PARAMETRES_NASA_MONTHLY),
            annee_debut=ANNEE_DEBUT,
            annee_fin=ANNEE_FIN,
            httpx_client=None,
        )
        chemin = emettre_seed_ville(code, _cle_ville_offline(lat, lon), payload)
        print(f"    -> {chemin.name} ({chemin.stat().st_size / 1024:.0f} Ko)")
    CHEMIN_LOADER.write_text(_MODULE_LOADER, encoding="utf-8", newline="\n")
    print(f"  Loader: {CHEMIN_LOADER}")
    print(f"OK. {len(coords)} villes.")


if __name__ == "__main__":
    main()
