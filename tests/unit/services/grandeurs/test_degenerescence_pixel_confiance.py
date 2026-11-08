"""``degenerescence_pixel`` garde la confiance B : exemption documentée à la règle P."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock

import pytest

from kuma_data_core.editorial.niveaux_confiance import NIVEAU_CONFIANCE_DEGENERESCENCE_PIXEL
from kuma_data_core.services.grandeurs import degenerescence_pixel as dp

pytestmark = pytest.mark.unit


def _session_factice(inserees: list[dict[str, Any]]) -> MagicMock:
    """Deux localités jumelles sur chaque (source, paramètre) ; capture les insertions."""
    lignes = [
        SimpleNamespace(
            loc_id=loc,
            loc_code=f"loc{loc}",
            serie_id=loc,
            an_deb=1991,
            an_fin=2020,
            annee=1991,
            mois=1,
            valeur=5.0,
        )
        for loc in (1, 2)
    ]

    def _execute(_requete: object, params: object = None) -> MagicMock:
        if isinstance(params, list):
            inserees.extend(params)
        resultat = MagicMock()
        resultat.all.return_value = lignes
        return resultat

    session = MagicMock()
    session.execute.side_effect = _execute
    return session


@pytest.mark.parametrize(
    "orchestrateur",
    [dp.calculer_et_inserer_degenerescence_pixel, dp.calculer_et_inserer_degenerescence],
)
def test_degenerescence_reste_b(orchestrateur: Any) -> None:
    """Le niveau ne dépend pas des entrées : la géométrie de la grille, pas la qualité."""
    inserees: list[dict[str, Any]] = []
    orchestrateur(_session_factice(inserees))
    assert inserees
    assert {lig["niveau_confiance_derive"] for lig in inserees} == {"B"}
    assert NIVEAU_CONFIANCE_DEGENERESCENCE_PIXEL == "B"
