"""Seed offline CAMS Radiation DNI (extension 2021-2023) - chargeur, GÉNÉRÉ, ne pas éditer.

Données réelles CAMS Radiation (`BNI` all-sky = DNI aérosol-corrigé, ADS
Copernicus) produites par scripts/preparer_seed_cams.py. La donnée vit dans le
compagnon gzippé cams_radiation_2021_2023_seed_data.json.gz (sous la limite de taille du dépôt). gzip + json
stdlib : aucune dépendance scientifique au runtime (discipline alpha).
Attribution CC-BY Copernicus/CAMS requise (cf. commentaire des séries).
"""

from __future__ import annotations

import gzip
import json
from pathlib import Path
from typing import Any

_CHEMIN = Path(__file__).parent / "cams_radiation_2021_2023_seed_data.json.gz"
_DATA: dict[str, Any] = json.loads(gzip.decompress(_CHEMIN.read_bytes()))

CAMS_DNI_MENSUEL_2021_2023_SEED: list[dict[str, Any]] = _DATA["mensuel"]
