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
