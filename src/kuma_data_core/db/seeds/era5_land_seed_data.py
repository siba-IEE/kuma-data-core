"""Seed offline ERA5-Land - chargeur, GÉNÉRÉ, ne pas éditer.

Données réelles ERA5-Land (CDS Copernicus) produites par
scripts/preparer_seed_era5_land.py. La donnée vit dans le compagnon gzippé
era5_land_seed_data.json.gz (sous la limite de taille du dépôt). gzip + json
sont stdlib : aucune dépendance scientifique au runtime (discipline alpha).
"""

from __future__ import annotations

import gzip
import json
from pathlib import Path
from typing import Any

_DATA: dict[str, Any] = json.loads(
    gzip.decompress((Path(__file__).parent / "era5_land_seed_data.json.gz").read_bytes())
)

ERA5_LAND_PIXELS: dict[str, dict[str, Any]] = _DATA["pixels"]
ERA5_LAND_MENSUEL_SEED: list[dict[str, Any]] = _DATA["mensuel"]
ERA5_LAND_JOURNALIER_SEED: list[dict[str, Any]] = _DATA["journalier"]
