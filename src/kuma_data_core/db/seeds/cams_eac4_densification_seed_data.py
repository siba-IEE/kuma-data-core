"""Seed offline EAC4 PM2.5/PM10 densification 28 communes - chargeur, GENERE, ne pas editer.

Donnees reelles EAC4 (ADS Copernicus, cams-global-reanalysis-eac4) pour les 28 communes
chef-lieu, produites par scripts/preparer_seed_cams_eac4.py --densification. La donnee vit
dans le compagnon gzippe cams_eac4_densification_seed_data.json.gz (sous la limite 1 Mo du
depot). gzip + json stdlib : aucune dependance scientifique ni reseau au runtime migration.

Entree particules du HSU pour les 28 communes : deverrouille le
proxy taux_salissure_proxy aux 28 (le resolveur pluie nasa_power est data-driven).
Seed pilote (migration 081) intact, fichier distinct.
"""

from __future__ import annotations

import gzip
import json
from pathlib import Path
from typing import Any

_CHEMIN_GZ = Path(__file__).parent / "cams_eac4_densification_seed_data.json.gz"
_DATA: dict[str, Any] = (
    json.loads(gzip.decompress(_CHEMIN_GZ.read_bytes()))
    if _CHEMIN_GZ.exists()
    else {"pixels": {}, "journalier": []}
)

CAMS_EAC4_DENSIFICATION_PIXELS: dict[str, dict[str, float]] = _DATA["pixels"]
CAMS_EAC4_DENSIFICATION_JOURNALIER_SEED: list[dict[str, Any]] = _DATA["journalier"]
