"""Seed offline SARAH-3 profondeur (GHI/DNI mensuels 2005-2023) - chargeur, GÉNÉRÉ, ne pas éditer.

Lignes finales ``(localite_code, grandeur_code, annee, mois, valeur)`` des 34
points, converties en kWh/m2/jour. Produit par
scripts/preparer_seed_sarah3_profondeur.py. Patron NE-OFFLINE.
"""

from __future__ import annotations

import gzip
import json
from pathlib import Path
from typing import Any

_CHEMIN = Path(__file__).parent / "sarah3_profondeur_seed_data.json.gz"
_DATA: dict[str, Any] = json.loads(gzip.decompress(_CHEMIN.read_bytes()))

SARAH3_PROFONDEUR_SEED: list[dict[str, Any]] = _DATA["mensuel"]
