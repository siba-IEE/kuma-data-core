"""Règles de sélection des lignes servies : texte exact des fragments SQL, alias validé."""

from __future__ import annotations

from typing import get_args

import pytest

from kuma_data_core.editorial import selection
from kuma_data_core.editorial.selection import (
    VUE_GRANDEURS_EN_VIGUEUR,
    StatutValide,
    lignes_en_vigueur,
    lignes_en_vigueur_validees,
)
from kuma_data_core.editorial.statuts import STATUTS_EDITORIAUX_AUTORISES, STATUTS_VALIDES

pytestmark = pytest.mark.unit


def test_lignes_en_vigueur_sans_alias() -> None:
    assert lignes_en_vigueur() == "valide_au IS NULL AND statut <> 'deprecie'"


def test_lignes_en_vigueur_avec_alias() -> None:
    assert lignes_en_vigueur("m") == "m.valide_au IS NULL AND m.statut <> 'deprecie'"


def test_lignes_en_vigueur_validees_sans_alias() -> None:
    assert lignes_en_vigueur_validees() == (
        "valide_au IS NULL AND statut IN ('valide_auto', 'valide_humain', 'publie')"
    )


def test_lignes_en_vigueur_validees_avec_alias() -> None:
    assert lignes_en_vigueur_validees("mh") == (
        "mh.valide_au IS NULL AND mh.statut IN ('valide_auto', 'valide_humain', 'publie')"
    )


@pytest.mark.parametrize("alias", ["m", "mh", "gm", "_t", "t_2"])
def test_alias_en_forme_d_identifiant_admis(alias: str) -> None:
    assert lignes_en_vigueur(alias).startswith(f"{alias}.valide_au ")
    assert lignes_en_vigueur_validees(alias).startswith(f"{alias}.valide_au ")


@pytest.mark.parametrize(
    "alias",
    ["", "M", "2m", "m.x", "m x", "m;", "m'", "m--", "m\n", "é", "m OR 1=1"],
)
def test_alias_invalide_refuse(alias: str) -> None:
    """L'alias est inséré tel quel dans le SQL : rien d'autre qu'un identifiant ne passe."""
    with pytest.raises(ValueError, match="alias de table invalide"):
        lignes_en_vigueur(alias)
    with pytest.raises(ValueError, match="alias de table invalide"):
        lignes_en_vigueur_validees(alias)


def test_la_regle_validee_suit_statuts_valides(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(selection, "STATUTS_VALIDES", ("publie",))
    assert lignes_en_vigueur_validees("m") == "m.valide_au IS NULL AND m.statut IN ('publie')"


def test_statuts_valides_ni_brut_ni_deprecie() -> None:
    """La règle validée écarte le rejeté et le retiré ; la règle simple n'écarte que le retiré."""
    assert set(STATUTS_VALIDES) == STATUTS_EDITORIAUX_AUTORISES - {"brut", "deprecie"}


def test_le_type_des_statuts_valides_suit_statuts_valides() -> None:
    """Le type des statuts servis par la règle validée et la liste qu'elle filtre vont ensemble."""
    assert get_args(StatutValide) == STATUTS_VALIDES


def test_vue_des_grandeurs_en_vigueur() -> None:
    assert VUE_GRANDEURS_EN_VIGUEUR == "v_grandeurs_metier_courantes"
