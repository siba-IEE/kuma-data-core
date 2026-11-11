"""Texte historique du commentaire de ``degenerescence_pixel``.

Des migrations déjà appliquées appellent ce générateur sur une base neuve, et
une migration ultérieure retrouve ses textes par égalité exacte pour les
réécrire : sa sortie ne doit pas bouger d'un octet.
"""

from __future__ import annotations

import pytest

from kuma_data_core.services.grandeurs.degenerescence_pixel import _commentaire, _ConfigSource

pytestmark = pytest.mark.unit

_FINALE = (
    " Indicateur exact (identite structurelle observee, non modelise), tague confiance B : "
    "A est reservee aux mesures terrain et l'echelle A/B/C classe la fiabilite d'une mesure "
    "de substrat, pas la certitude d'un fait structurel."
)
_CERES: _ConfigSource = {
    "source_code": "nasa_power",
    "grandeur_code": "ghi",
    "periode_debut": "1991-01-01",
    "grille": "CERES SYN1deg",
    "resolution": "1 deg (110 km)",
    "grille_fixe": True,
}
_SARAH: _ConfigSource = {
    "source_code": "sarah3_monthly",
    "grandeur_code": "ghi",
    "periode_debut": "2021-01-01",
    "grille": "PVGIS-SARAH3 (interpole)",
    "resolution": "5 km",
    "grille_fixe": False,
}


def test_cellule_partagee() -> None:
    assert _commentaire(_CERES, "ghi", ["gin_dalaba", "gin_mamou"]) == (
        "Degenerescence de pixel : partage la cellule CERES SYN1deg (1 deg (110 km)) avec 2 "
        "autre(s) point(s) (gin_dalaba, gin_mamou). Series ghi identiques (meme pixel source) "
        "-> ne pas presenter comme des mesures independantes (D-29 generalise)." + _FINALE
    )


def test_point_seul_dans_sa_cellule() -> None:
    assert _commentaire(_CERES, "kt", []) == (
        "Point resolu sur CERES SYN1deg (1 deg (110 km)) : aucun autre point partageant la "
        "cellule pour kt." + _FINALE
    )


def test_source_interpolee() -> None:
    assert _commentaire(_SARAH, "ghi", []) == (
        "Source interpolee au point (PVGIS-SARAH3 (interpole), 5 km) : valeurs distinctes par "
        "construction. Resolution reelle 5 km -> finesse sub-maille illusoire (caveat de "
        "resolution, pas une degenerescence mesurable)." + _FINALE
    )
