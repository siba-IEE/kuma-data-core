"""Seed offline NASA POWER monthly - chargeur, GÉNÉRÉ, ne pas éditer.

Payloads JSON bruts NASA POWER monthly (9 paramètres, 34 points, climato
1991-2020), capturés par scripts/preparer_seed_nasa_monthly.py. Permettent à
l'ingestion de renvoyer la donnée hors-ligne (KUMA_INGESTION_MODE=offline) sans
appel réseau, restreinte par paramètres/fenêtre d'années côté module. gzip + json
stdlib ; un compagnon .json.gz par ville. Clé : round(lat,4)_round(lon,4).
"""

from __future__ import annotations

import gzip
import json
from pathlib import Path
from typing import Any

_DOSSIER = Path(__file__).parent

NASA_MONTHLY_PAYLOADS: dict[str, Any] = {}
for _chemin in sorted(_DOSSIER.glob("nasa_power_monthly_seed_data_*.json.gz")):
    _bloc: dict[str, Any] = json.loads(gzip.decompress(_chemin.read_bytes()))
    NASA_MONTHLY_PAYLOADS.update(_bloc["payloads"])
