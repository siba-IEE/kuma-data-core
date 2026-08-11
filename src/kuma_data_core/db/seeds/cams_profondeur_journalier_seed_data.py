"""Seed offline CAMS Radiation profondeur journalier - chargeur, GÉNÉRÉ, ne pas éditer.

Blocs par série ``{localite_code, grandeur_code, valeurs: {date: valeur}}``
des 34 points, ghi, dhi et dni all-sky, fenêtre 2004-02 -> 2025-12, convertis
en kWh/m2/jour. Un compagnon .json.gz par ville, consommé en streaming via
``iter_blocs_cams_journalier()``. Produit par
scripts/preparer_seed_cams_profondeur.py. Patron NE-OFFLINE. Attribution
CC-BY Copernicus/CAMS requise.
"""

from __future__ import annotations

import gzip
import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any

_DOSSIER = Path(__file__).parent


def iter_blocs_cams_journalier() -> Iterator[dict[str, Any]]:
    """Streame les blocs (ville x grandeur), un fichier gzip à la fois."""
    for chemin in sorted(_DOSSIER.glob("cams_profondeur_journalier_seed_data_*.json.gz")):
        bloc_fichier: dict[str, Any] = json.loads(gzip.decompress(chemin.read_bytes()))
        yield from bloc_fichier["journalier"]
