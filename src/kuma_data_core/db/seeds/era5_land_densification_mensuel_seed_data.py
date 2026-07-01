"""Seed offline ERA5-Land densification 28 communes (mensuel) - chargeur,
GENERE, ne pas editer.

Donnees reelles ERA5-Land (CDS Copernicus) pour les 28 communes chef-lieu, produites par
scripts/preparer_seed_era5_land.py --densification. La donnee vit dans le compagnon gzippe
era5_land_densification_mensuel_seed_data.json.gz. gzip + json stdlib : aucune dependance scientifique au runtime migration.
Attribution CC-BY Copernicus.
"""

from __future__ import annotations

import gzip
import json
from pathlib import Path
from typing import Any

_CHEMIN = Path(__file__).parent / "era5_land_densification_mensuel_seed_data.json.gz"
_DATA: dict[str, Any] = json.loads(gzip.decompress(_CHEMIN.read_bytes()))

ERA5_LAND_DENSIFICATION_PIXELS: dict[str, dict[str, Any]] = _DATA["pixels"]
ERA5_LAND_DENSIFICATION_MENSUEL_SEED: list[dict[str, Any]] = _DATA["mensuel"]
