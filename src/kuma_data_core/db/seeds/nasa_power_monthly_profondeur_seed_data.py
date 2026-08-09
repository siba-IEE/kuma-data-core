"""Seed offline NASA POWER mensuel profondeur - chargeur, GÉNÉRÉ, ne pas éditer.

Lignes finales ``(localite_code, grandeur_code, annee, mois, valeur)`` des 34
points (6 pilotes + 28 communes), produites par
scripts/preparer_seed_nasa_monthly_profondeur.py (sentinelles -999 et clés
annuelles YYYY13 déjà filtrées). Patron NE-OFFLINE : consommé directement par
la migration d'insertion, aucun réseau au runtime. gzip + json stdlib ; un
compagnon .json.gz par ville.
"""

from __future__ import annotations

import gzip
import json
from pathlib import Path
from typing import Any

_DOSSIER = Path(__file__).parent

NASA_MONTHLY_PROFONDEUR_SEED: list[dict[str, Any]] = []
for _chemin in sorted(_DOSSIER.glob("nasa_power_monthly_profondeur_seed_data_*.json.gz")):
    _bloc: dict[str, Any] = json.loads(gzip.decompress(_chemin.read_bytes()))
    NASA_MONTHLY_PROFONDEUR_SEED.extend(_bloc["mensuel"])
