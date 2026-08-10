"""Préparation du seed offline PVGIS-SARAH3.

Script ponctuel (hors CI). Capture en **live** le payload JSON brut
PVGIS MRcalc (SARAH-3 ICDR 2021-2023) des 6 villes pilotes et écrit le seed
committé ``src/kuma_data_core/db/seeds/sarah3_monthly_seed_data.py`` (+ compagnon
``.json.gz``). En CI, sous ``KUMA_INGESTION_MODE=offline``, l'ingestion renvoie
ce payload au lieu d'appeler JRC (réseau nul).

**Fidélité** : la capture reproduit la donnée live courante → les 216 lignes
SARAH-3 et l'écart restent identiques, sans recalage des tests.

Coordonnées : ``LOCALITES_SEED`` (mêmes lat/lon que la migration 041 via la table
``localites``). Clé de seed : ``round(lat,4)_round(lon,4)_2021_2023``.

Usage : ``uv run --group dev python scripts/preparer_seed_sarah3.py``
(mode ``live`` requis : ne pas poser ``KUMA_INGESTION_MODE=offline``).
"""

from __future__ import annotations

import gzip
import json
from pathlib import Path
from typing import Any

from kuma_data_core.db.seeds.localites_prefectures_seed_data import PREFECTURES_GUINEE
from kuma_data_core.db.seeds.localites_seed_data import LOCALITES_SEED
from kuma_data_core.ingestion.sarah3_monthly import (
    _cle_payload_offline,
    _fetch_sarah3_monthly_raw,
)

# === Périmètre : 6 pilotes (041) + densification (28 communes) =========

LOCALITES_1_7A: tuple[str, ...] = (
    "gin_conakry_kaloum",
    "gin_kankan",
    "gin_kindia",
    "gin_labe",
    "gin_mamou",
    "gin_nzerekore",
)
# Densification : les 28 nouvelles communes chef-lieu. Les 6 pilotes sont charges
# du seed existant (ICDR fige, zero re-fetch).
LOCALITES_DENSIFICATION: tuple[str, ...] = tuple(
    p["commune_code"] for p in PREFECTURES_GUINEE if p["existante"] is None
)
ANNEE_DEBUT, ANNEE_FIN = 2021, 2023

CHEMIN_SEED = Path("src/kuma_data_core/db/seeds/sarah3_monthly_seed_data.py")

_MODULE_LOADER = '''\
"""Seed offline PVGIS-SARAH3 ICDR mensuel (D-40 lot 1) - chargeur, GÉNÉRÉ, ne pas éditer.

Payloads JSON bruts PVGIS MRcalc (SARAH-3 2021-2023, 6 villes pilotes 1-7a),
capturés par scripts/preparer_seed_sarah3.py. Permettent à l'ingestion de
renvoyer la donnée hors-ligne (KUMA_INGESTION_MODE=offline) sans appel réseau
JRC. gzip + json stdlib ; la donnée vit dans le compagnon
sarah3_monthly_seed_data.json.gz. Clé : round(lat,4)_round(lon,4)_2021_2023.
"""

from __future__ import annotations

import gzip
import json
from pathlib import Path
from typing import Any

_DATA: dict[str, Any] = json.loads(
    gzip.decompress((Path(__file__).parent / "sarah3_monthly_seed_data.json.gz").read_bytes())
)

SARAH3_PAYLOADS: dict[str, Any] = _DATA["payloads"]
'''


def coordonnees_pilotes() -> dict[str, tuple[float, float]]:
    index = {e["code"]: e for e in LOCALITES_SEED}
    manquants = [c for c in LOCALITES_1_7A if c not in index]
    if manquants:
        raise RuntimeError(f"Localités absentes de LOCALITES_SEED : {manquants}")
    return {c: (float(index[c]["latitude"]), float(index[c]["longitude"])) for c in LOCALITES_1_7A}


def coordonnees_densification() -> dict[str, tuple[float, float]]:
    """Coordonnées (lat, lon) des 28 nouvelles communes, depuis le référentiel des communes."""
    return {
        p["commune_code"]: (float(p["lat"]), float(p["lon"]))
        for p in PREFECTURES_GUINEE
        if p["existante"] is None
    }


def emettre_seed(payloads: dict[str, Any]) -> None:
    chemin_gz = CHEMIN_SEED.parent / "sarah3_monthly_seed_data.json.gz"
    charge = json.dumps({"payloads": payloads}, separators=(",", ":"), sort_keys=True).encode(
        "utf-8"
    )
    chemin_gz.write_bytes(gzip.compress(charge, compresslevel=9))
    CHEMIN_SEED.write_text(_MODULE_LOADER, encoding="utf-8", newline="\n")
    print(f"  Seed: {len(payloads)} payloads -> {chemin_gz}")


def main() -> None:
    print("=== Préparation seed PVGIS-SARAH3 (D-40 lot 1 + densification B-2a) ===")
    # Charge les payloads existants (6 pilotes) pour ne pas les re-fetcher
    # (SARAH-3 ICDR fige) : zero retrofit, bytes pilotes preserves.
    try:
        from kuma_data_core.db.seeds.sarah3_monthly_seed_data import SARAH3_PAYLOADS

        payloads: dict[str, Any] = dict(SARAH3_PAYLOADS)
        print(f"  {len(payloads)} payload(s) existant(s) charge(s) (pilotes).")
    except Exception:  # premier run : seed absent
        payloads = {}

    # Ajoute les 28 nouvelles communes (skip si la cle est deja presente).
    fetchees = 0
    for code, (lat, lon) in coordonnees_densification().items():
        cle = _cle_payload_offline(lat, lon, ANNEE_DEBUT, ANNEE_FIN)
        if cle in payloads:
            print(f"  SKIP {code} (deja present)")
            continue
        print(f"  PVGIS {code} ({lat:.4f}, {lon:.4f})...")
        payloads[cle] = _fetch_sarah3_monthly_raw(
            latitude=lat,
            longitude=lon,
            annee_debut=ANNEE_DEBUT,
            annee_fin=ANNEE_FIN,
            timeout=60.0,
            httpx_client=None,
        )
        fetchees += 1
    emettre_seed(payloads)
    print(f"OK. {fetchees} commune(s) fetchee(s), {len(payloads)} payload(s) total.")


if __name__ == "__main__":
    main()
