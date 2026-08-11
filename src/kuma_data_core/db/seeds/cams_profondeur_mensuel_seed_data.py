"""Seed offline CAMS Radiation profondeur mensuel - chargeur, GÉNÉRÉ, ne pas éditer.

Lignes finales ``(localite_code, grandeur_code, annee, mois, valeur)`` des 34
points, ghi et dhi all-sky, fenêtre 2004-02 -> 2025-12, converties en
kWh/m2/jour. Produit par scripts/preparer_seed_cams_profondeur.py. Patron
NE-OFFLINE. Attribution CC-BY Copernicus/CAMS requise.
"""

from __future__ import annotations

import gzip
import json
from pathlib import Path
from typing import Any

_CHEMIN = Path(__file__).parent / "cams_profondeur_mensuel_seed_data.json.gz"
_DATA: dict[str, Any] = json.loads(gzip.decompress(_CHEMIN.read_bytes()))

CAMS_PROFONDEUR_MENSUEL_SEED: list[dict[str, Any]] = _DATA["mensuel"]
