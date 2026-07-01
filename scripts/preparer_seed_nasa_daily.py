"""Préparation du seed offline NASA POWER daily.

Livrable **humain ponctuel** (hors CI). Capture en **live** le payload JSON brut
NASA POWER daily (les 9 paramètres de l'union des migrations daily, fenêtre pleine
2021-2025) des 6 villes pilotes, et écrit un seed committé **par ville**
``nasa_power_daily_seed_data_<code>.json.gz`` + le chargeur
``src/kuma_data_core/db/seeds/nasa_power_daily_seed_data.py``. En CI, sous
``KUMA_INGESTION_MODE=offline``, l'ingestion renvoie ce payload (restreint aux
paramètres et à la fenêtre demandés côté module) au lieu d'appeler NASA POWER ->
réseau nul.

**Fidélité** : la capture fige la donnée live courante (snapshot daté) ; le
tranchage côté module reproduit chaque appel des migrations 018/020/022/029/048
-> mêmes lignes, décomptes déterministes.

**Découpage par ville** : un compagnon ``.json.gz`` par ville pour rester sous le
hook ``check-added-large-files --maxkb=1024`` (9 params x 1826 jours x 6 villes).

Union des 9 paramètres (clé Kuma -> code NASA), sourcée des migrations :
GHI (018), DNI/DHI/T2M/RH2M (020/022), kt (029), vent_2m/vent_10m/albedo (048).

Usage : ``uv run --group dev python scripts/preparer_seed_nasa_daily.py``
(mode ``live`` requis : ne pas poser ``KUMA_INGESTION_MODE=offline``).
"""

from __future__ import annotations

import gzip
import json
from datetime import date
from pathlib import Path
from typing import Any

from kuma_data_core.db.seeds.localites_prefectures_seed_data import PREFECTURES_GUINEE
from kuma_data_core.db.seeds.localites_seed_data import LOCALITES_SEED
from kuma_data_core.external.nasa_power import fetch_daily_raw
from kuma_data_core.ingestion.nasa_power_daily import _cle_ville_offline

# === Périmètre (union des migrations daily 018/020/022/029/048) ============

LOCALITES_DAILY: tuple[str, ...] = (
    "gin_conakry_kaloum",
    "gin_kankan",
    "gin_kindia",
    "gin_labe",
    "gin_mamou",
    "gin_nzerekore",
)

# Densification : les 28 nouvelles communes chef-lieu (les 33 prefectures moins
# les 5 capitales regionales deja ingerees). Coordonnees lues du seed chef-lieu.
# Les 6 pilotes ci-dessus gardent leur snapshot mûri (zero re-pull) via le
# skip-if-exists de main().
LOCALITES_DAILY_DENSIFICATION: tuple[str, ...] = tuple(
    p["commune_code"] for p in PREFECTURES_GUINEE if p["existante"] is None
)

# Union des paramètres NASA POWER ingérés en daily (code NASA -> grandeur Kuma).
# Capturés en un seul appel multi-paramètres par ville (NASA autorise 20 max).
PARAMETRES_NASA_DAILY: tuple[str, ...] = (
    "ALLSKY_SFC_SW_DWN",  # ghi (018/022)
    "ALLSKY_SFC_SW_DNI",  # dni (020/022)
    "ALLSKY_SFC_SW_DIFF",  # dhi (020/022)
    "T2M",  # t2m (020/022)
    "RH2M",  # rh2m (020/022)
    "ALLSKY_KT",  # kt (029)
    "WS2M",  # vent_2m (048)
    "WS10M",  # vent_10m (048)
    "ALLSKY_SRF_ALB",  # albedo_surface (048)
)

PERIODE_DEBUT = date(2021, 1, 1)
PERIODE_FIN = date(2025, 12, 31)

DOSSIER_SEED = Path("src/kuma_data_core/db/seeds")
CHEMIN_LOADER = DOSSIER_SEED / "nasa_power_daily_seed_data.py"

_MODULE_LOADER = '''\
"""Seed offline NASA POWER daily (D-40 / D-74, lot 2) - chargeur, GÉNÉRÉ, ne pas éditer.

Payloads JSON bruts NASA POWER daily (9 paramètres, 6 villes pilotes, 2021-2025),
capturés par scripts/preparer_seed_nasa_daily.py. Permettent à l'ingestion de
renvoyer la donnée hors-ligne (KUMA_INGESTION_MODE=offline) sans appel réseau,
restreinte par paramètres/fenêtre côté module. gzip + json stdlib ; un compagnon
.json.gz par ville (sous check-added-large-files --maxkb=1024).
Clé : round(lat,4)_round(lon,4).
"""

from __future__ import annotations

import gzip
import json
from pathlib import Path
from typing import Any

_DOSSIER = Path(__file__).parent

NASA_DAILY_PAYLOADS: dict[str, Any] = {}
for _chemin in sorted(_DOSSIER.glob("nasa_power_daily_seed_data_*.json.gz")):
    _bloc: dict[str, Any] = json.loads(gzip.decompress(_chemin.read_bytes()))
    NASA_DAILY_PAYLOADS.update(_bloc["payloads"])
'''


def coordonnees_pilotes() -> dict[str, tuple[float, float]]:
    """Coordonnées (lat, lon) des 6 villes, depuis LOCALITES_SEED."""
    index = {e["code"]: e for e in LOCALITES_SEED}
    manquants = [c for c in LOCALITES_DAILY if c not in index]
    if manquants:
        raise RuntimeError(f"Localités absentes de LOCALITES_SEED : {manquants}")
    return {c: (float(index[c]["latitude"]), float(index[c]["longitude"])) for c in LOCALITES_DAILY}


def coordonnees_densification() -> dict[str, tuple[float, float]]:
    """Coordonnées (lat, lon) des 28 nouvelles communes, depuis le référentiel des communes."""
    return {
        p["commune_code"]: (float(p["lat"]), float(p["lon"]))
        for p in PREFECTURES_GUINEE
        if p["existante"] is None
    }


def coordonnees_cibles() -> dict[str, tuple[float, float]]:
    """6 pilotes + 28 nouvelles communes. main() saute celles deja seedees."""
    return {**coordonnees_pilotes(), **coordonnees_densification()}


def emettre_seed_ville(code: str, cle: str, payload: dict[str, Any]) -> Path:
    """Écrit le compagnon .json.gz d'une ville et retourne son chemin."""
    chemin_gz = DOSSIER_SEED / f"nasa_power_daily_seed_data_{code}.json.gz"
    charge = json.dumps({"payloads": {cle: payload}}, separators=(",", ":"), sort_keys=True).encode(
        "utf-8"
    )
    chemin_gz.write_bytes(gzip.compress(charge, compresslevel=9))
    return chemin_gz


def main() -> None:
    print("=== Préparation seed NASA POWER daily (D-40 / D-74 lot 2 + densification B-1) ===")
    coords = coordonnees_cibles()
    fetchees = 0
    for code, (lat, lon) in coords.items():
        chemin_gz = DOSSIER_SEED / f"nasa_power_daily_seed_data_{code}.json.gz"
        if chemin_gz.exists():
            print(f"  SKIP {code} (seed deja present : {chemin_gz.name})")
            continue
        print(
            f"  NASA daily {code} ({lat:.4f}, {lon:.4f}) : {len(PARAMETRES_NASA_DAILY)} params..."
        )
        payload = fetch_daily_raw(
            latitude=lat,
            longitude=lon,
            parameters=list(PARAMETRES_NASA_DAILY),
            start=PERIODE_DEBUT,
            end=PERIODE_FIN,
            httpx_client=None,
        )
        chemin = emettre_seed_ville(code, _cle_ville_offline(lat, lon), payload)
        print(f"    -> {chemin.name} ({chemin.stat().st_size / 1024:.0f} Ko)")
        fetchees += 1
    CHEMIN_LOADER.write_text(_MODULE_LOADER, encoding="utf-8", newline="\n")
    print(f"  Loader: {CHEMIN_LOADER}")
    print(f"OK. {fetchees} ville(s) fetchee(s), {len(coords) - fetchees} saut(s).")


if __name__ == "__main__":
    main()
