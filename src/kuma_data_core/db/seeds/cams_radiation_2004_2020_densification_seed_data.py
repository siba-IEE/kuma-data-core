"""Seed offline CAMS Radiation DNI (densification 28 communes 2004-2020) - chargeur, GÉNÉRÉ, ne pas éditer.

Données réelles CAMS Radiation (`BNI` all-sky = DNI aérosol-corrigé, ADS
Copernicus) produites par scripts/preparer_seed_cams.py. La donnée vit dans le
compagnon gzippé cams_radiation_2004_2020_densification_seed_data.json.gz (sous la limite de taille du dépôt). gzip + json
stdlib : aucune dépendance scientifique au runtime (discipline alpha).
Attribution CC-BY Copernicus/CAMS requise (cf. commentaire des séries).
"""

from __future__ import annotations

import gzip
import json
from pathlib import Path
from typing import Any

_CHEMIN = Path(__file__).parent / "cams_radiation_2004_2020_densification_seed_data.json.gz"
_DATA: dict[str, Any] = json.loads(gzip.decompress(_CHEMIN.read_bytes()))

CAMS_DNI_MENSUEL_2004_2020_DENSIFICATION_SEED: list[dict[str, Any]] = _DATA["mensuel"]
