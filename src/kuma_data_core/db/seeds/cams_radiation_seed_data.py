"""Seed offline CAMS Radiation DNI - chargeur, GÉNÉRÉ, ne pas éditer.

Données réelles CAMS Radiation (`BNI` all-sky = DNI aérosol-corrigé, ADS
Copernicus) produites par scripts/preparer_seed_cams.py. La donnée vit dans le
compagnon gzippé cams_radiation_seed_data.json.gz (sous la limite de taille du dépôt).
gzip + json sont stdlib : aucune dépendance scientifique au runtime (discipline
alpha). Attribution CC-BY Copernicus/CAMS requise (cf. commentaire des séries).
"""

from __future__ import annotations

import gzip
import json
from pathlib import Path
from typing import Any

_DATA: dict[str, Any] = json.loads(
    gzip.decompress((Path(__file__).parent / "cams_radiation_seed_data.json.gz").read_bytes())
)

CAMS_DNI_MENSUEL_SEED: list[dict[str, Any]] = _DATA["mensuel"]
