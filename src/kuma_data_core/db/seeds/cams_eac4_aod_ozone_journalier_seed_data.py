"""Seed offline EAC4 AOD 550 nm et ozone de surface journaliers - chargeur.

Données de la réanalyse Copernicus CAMS EAC4 (ADS, cams-global-reanalysis-eac4)
aux 34 points (6 pilotes + 28 communes chef-lieu), produites par
scripts/preparer_seed_cams_eac4_aod_ozone.py. Un compagnon gzippé par localité,
``cams_eac4_aod_ozone_journalier_seed_data_<localite>.json.gz``, de la forme
``{capture: {...}, journalier: [blocs]}`` ; un bloc est
``{localite_code, grandeur_code, pixel: {latitude, longitude}, valeurs: {date: valeur}}``
pour ``aod_550``, ``aod_poussiere_550`` (sans unité), ``ozone_surface`` et
``ozone_surface_diurne`` (ppb). ``capture`` porte la période réellement capturée,
la date de capture et les jours exclus.

gzip + json de la bibliothèque standard uniquement : aucune dépendance
scientifique ni réseau au moment des migrations. Tolérant à l'absence de
compagnons : les itérateurs ne produisent alors rien. Attribution CC-BY
Copernicus/CAMS requise.
"""

from __future__ import annotations

import gzip
import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any

_DOSSIER = Path(__file__).parent
_MOTIF_COMPAGNONS = "cams_eac4_aod_ozone_journalier_seed_data_*.json.gz"


def _iter_fichiers() -> Iterator[dict[str, Any]]:
    for chemin in sorted(_DOSSIER.glob(_MOTIF_COMPAGNONS)):
        contenu: dict[str, Any] = json.loads(gzip.decompress(chemin.read_bytes()))
        yield contenu


def iter_blocs_cams_eac4_aod_ozone() -> Iterator[dict[str, Any]]:
    """Streame les blocs (localité x grandeur), un fichier gzip à la fois."""
    for contenu in _iter_fichiers():
        yield from contenu["journalier"]


def iter_captures_cams_eac4_aod_ozone() -> Iterator[tuple[str, dict[str, Any]]]:
    """Streame ``(localite_code, capture)`` : métadonnées de capture par localité."""
    for contenu in _iter_fichiers():
        blocs: list[dict[str, Any]] = contenu["journalier"]
        if blocs:
            yield str(blocs[0]["localite_code"]), contenu["capture"]
