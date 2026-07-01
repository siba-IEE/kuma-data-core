"""Seed offline PVGIS-SARAH3 ICDR mensuel - chargeur, GÉNÉRÉ, ne pas éditer.

Payloads JSON bruts PVGIS MRcalc (SARAH-3 2021-2023, 6 villes pilotes),
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
