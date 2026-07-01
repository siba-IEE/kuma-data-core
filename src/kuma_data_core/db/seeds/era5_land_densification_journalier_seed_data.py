"""Seed offline ERA5-Land densification 28 communes (journalier) - chargeur, GENERE,
ne pas editer.

Donnees reelles ERA5-Land daily (CDS Copernicus timeseries) pour les 28 communes chef-lieu,
produites par scripts/preparer_seed_era5_land.py 2021 2025 --densification. La donnee massive
(153k mesures) est CHUNKEE par-ville (..._journalier_seed_data_gin_*.json.gz) pour rester sous
la limite de taille du depot (1 Mo/fichier). gzip + json stdlib. Attribution CC-BY Copernicus.
"""

from __future__ import annotations

import gzip
import json
from pathlib import Path
from typing import Any

_DOSSIER = Path(__file__).parent
_MOTIF = "era5_land_densification_journalier_seed_data_gin_*.json.gz"
ERA5_LAND_DENSIFICATION_JOURNALIER_SEED: list[dict[str, Any]] = []
for _chemin in sorted(_DOSSIER.glob(_MOTIF)):
    _bloc: dict[str, Any] = json.loads(gzip.decompress(_chemin.read_bytes()))
    ERA5_LAND_DENSIFICATION_JOURNALIER_SEED.extend(_bloc["journalier"])
