"""Seed offline EAC4 PM2.5/PM10 (soiling) - chargeur, GÉNÉRÉ, ne pas éditer.

Données réelles EAC4 (ADS Copernicus, cams-global-reanalysis-eac4) produites par
scripts/preparer_seed_cams_eac4.py. La donnée vit dans le compagnon gzippé
cams_eac4_seed_data.json.gz (sous la limite de taille du dépôt). gzip + json sont
stdlib : aucune dépendance scientifique ni réseau au runtime migration.

Tolérant au seed absent : le script + ce chargeur sont livrés d'abord ; le pull ADS
et la génération du .json.gz viennent ensuite (Siba). Tant que le compagnon n'existe
pas, le chargeur expose des données vides (la migration créera alors les
séries avec 0 mesure, cf. pattern seed vide ERA5/precipitation).
"""

from __future__ import annotations

import gzip
import json
from pathlib import Path
from typing import Any

_CHEMIN_GZ = Path(__file__).parent / "cams_eac4_seed_data.json.gz"
_DATA: dict[str, Any] = (
    json.loads(gzip.decompress(_CHEMIN_GZ.read_bytes()))
    if _CHEMIN_GZ.exists()
    else {"pixels": {}, "journalier": []}
)

CAMS_EAC4_PIXELS: dict[str, dict[str, float]] = _DATA["pixels"]
CAMS_EAC4_JOURNALIER_SEED: list[dict[str, Any]] = _DATA["journalier"]
