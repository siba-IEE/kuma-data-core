"""Tests unitaires de la règle de propagation P sur les réponses de ``/v1/grandeurs``.

Chaque résultat prend le niveau effectif le plus bas des mesures lues pour son
jour ou son mois, sans dépasser le plafond de la grandeur (ADR-0008).
"""

from __future__ import annotations

from datetime import date

import pytest

from kuma_data_core.api.v1.grandeurs import _propager
from kuma_data_core.api.v1.schemas.grandeurs import ResultatJournalier, ResultatMensuel
from kuma_data_core.editorial.niveaux_confiance import NiveauxEntrees

pytestmark = pytest.mark.unit


def _jour(jour: date) -> ResultatJournalier:
    return ResultatJournalier(instant=jour, valeur=1.0, unite="kWh/m2", niveau_confiance="B")


def test_resultat_journalier_au_niveau_de_son_jour() -> None:
    niveaux = NiveauxEntrees()
    niveaux.ajouter(date(2024, 7, 1), "A")
    niveaux.ajouter(date(2024, 7, 2), "A")
    niveaux.ajouter(date(2024, 7, 2), "C")

    resultats = _propager([_jour(date(2024, 7, 1)), _jour(date(2024, 7, 2))], niveaux, "A")

    assert [r.niveau_confiance for r in resultats] == ["A", "C"]


def test_resultat_mensuel_au_niveau_de_son_mois() -> None:
    niveaux = NiveauxEntrees()
    niveaux.ajouter(date(2024, 7, 1), "A")
    niveaux.ajouter(date(2024, 8, 1), "A")
    niveaux.ajouter(date(2024, 8, 2), "B")
    mensuels = [
        ResultatMensuel(instant=m, valeur=1.0, unite="°C·j", niveau_confiance="B")
        for m in ("2024-07", "2024-08")
    ]

    assert [r.niveau_confiance for r in _propager(mensuels, niveaux, "A")] == ["A", "B"]


def test_plafond_de_la_grandeur() -> None:
    """Une grandeur à modèle ou hypothèse (plafond B) reste B sur des mesures A, C sur une C."""
    niveaux = NiveauxEntrees()
    niveaux.ajouter(date(2024, 7, 1), "A")
    niveaux.ajouter(date(2024, 7, 2), "C")

    resultats = _propager([_jour(date(2024, 7, 1)), _jour(date(2024, 7, 2))], niveaux, "B")

    assert [r.niveau_confiance for r in resultats] == ["B", "C"]


def test_jour_sans_entree_rangee_prend_le_niveau_de_toutes_les_entrees() -> None:
    """Jour sans entrée rangée (calcul groupé hors UTC) : repli prudent sur toutes les entrées."""
    niveaux = NiveauxEntrees()
    niveaux.ajouter(date(2024, 7, 1), "A")
    niveaux.ajouter(date(2024, 7, 2), "C")

    assert _propager([_jour(date(2024, 7, 3))], niveaux, "A")[0].niveau_confiance == "C"
