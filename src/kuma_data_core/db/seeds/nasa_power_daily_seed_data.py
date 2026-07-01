"""Seed offline NASA POWER daily - chargeur, GÉNÉRÉ, ne pas éditer.

Payloads JSON bruts NASA POWER daily (9 paramètres, 6 villes pilotes, 2021-2025),
capturés par scripts/preparer_seed_nasa_daily.py. Permettent à l'ingestion de
renvoyer la donnée hors-ligne (KUMA_INGESTION_MODE=offline) sans appel réseau,
restreinte par paramètres/fenêtre côté module. gzip + json stdlib ; un compagnon
.json.gz par ville (sous check-added-large-files --maxkb=1024).
Clé : round(lat,4)_round(lon,4).
"""

from __future__ import annotations

import gzip
import json
from pathlib import Path
from typing import Any

_DOSSIER = Path(__file__).parent

NASA_DAILY_PAYLOADS: dict[str, Any] = {}
for _chemin in sorted(_DOSSIER.glob("nasa_power_daily_seed_data_*.json.gz")):
    _bloc: dict[str, Any] = json.loads(gzip.decompress(_chemin.read_bytes()))
    NASA_DAILY_PAYLOADS.update(_bloc["payloads"])
