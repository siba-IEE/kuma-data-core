"""Seed offline ESMAP/WAPP GHI horaire - kankan - chargeur, GÉNÉRÉ, ne pas éditer.

Données réelles GHI sol (campagne ESMAP/WAPP « Solar Development in Sub-Saharan
Africa », CC-BY-4.0) agrégées 1-min -> horaire par scripts/preparer_seed_esmap_wapp.py.
La donnée vit dans le compagnon gzippé kankan_ghi_esmap_wapp_2021_2023_seed_data.json.gz (sous la limite de taille du
dépôt). gzip + json stdlib : aucune dépendance scientifique au runtime.
Attribution CC-BY requise (World Bank / ESMAP / WAPP ; cf. commentaire des séries).
"""

from __future__ import annotations

import gzip
import json
from pathlib import Path
from typing import Any

_CHEMIN = Path(__file__).parent / "kankan_ghi_esmap_wapp_2021_2023_seed_data.json.gz"
_DATA: dict[str, Any] = json.loads(gzip.decompress(_CHEMIN.read_bytes()))

KANKAN_GHI_HORAIRE_2021_2023_SEED: list[dict[str, Any]] = _DATA["horaire"]
