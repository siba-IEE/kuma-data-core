"""Seed offline NASA POWER daily profondeur - chargeur, GÉNÉRÉ, ne pas éditer.

Blocs par série ``{localite_code, grandeur_code, valeurs: {date: valeur}}``
des 34 points (6 pilotes + 28 communes), fenêtre 1981-2020, produits par
scripts/preparer_seed_nasa_daily_profondeur.py (sentinelles -999 déjà
filtrées). Format groupé par série (4,1 M de valeurs) : consommer via
``iter_blocs_daily_profondeur()`` qui streame fichier par fichier, la
migration n'a jamais tout le seed en mémoire d'un coup. Patron NE-OFFLINE :
aucun réseau au runtime. gzip + json stdlib ; un compagnon .json.gz par
ville x décennie.
"""

from __future__ import annotations

import gzip
import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any

_DOSSIER = Path(__file__).parent


def iter_blocs_daily_profondeur() -> Iterator[dict[str, Any]]:
    """Streame les blocs (ville x grandeur x décennie), un fichier gzip à la fois."""
    for chemin in sorted(_DOSSIER.glob("nasa_power_daily_profondeur_seed_data_*.json.gz")):
        bloc_fichier: dict[str, Any] = json.loads(gzip.decompress(chemin.read_bytes()))
        yield from bloc_fichier["journalier"]
