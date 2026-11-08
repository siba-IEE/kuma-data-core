"""Textes servis par l'API sans vocabulaire de chantier interne (migration 129).

- Le document OpenAPI construit depuis l'application (descriptions de routes,
  docstrings des schémas, descriptions de champs) ne porte aucun motif de
  ``JARGON_INTERNE``.
- Les avertissements ``limite`` renvoyés par les grandeurs calculées à la volée
  (salissure, PR réaliste dans tous ses modes, exceedance GHI avec et sans ville
  jumelle, incertitude inter-source) non plus, et gardent leur contenu.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any, get_args

import pytest

from kuma_data_core.api.main import creer_application
from kuma_data_core.api.v1.grandeurs import (
    _construire_limite_ghi_exceedance,
    _construire_limite_incertitude_inter_source,
)
from kuma_data_core.api.v1.schemas.grandeurs import ModeCorrectionPR
from kuma_data_core.services.grandeurs.pr_realiste import calculer_pr_realiste
from kuma_data_core.services.grandeurs.soiling_hsu import calculer_taux_salissure_proxy
from tests._jargon import JARGON_INTERNE

pytestmark = pytest.mark.unit


def _chaines(objet: Any, chemin: str = "") -> Iterator[tuple[str, str]]:
    """Toutes les chaînes (clés comprises) d'un document JSON, avec leur chemin."""
    if isinstance(objet, dict):
        for cle, valeur in objet.items():
            yield f"{chemin}/<cle>", str(cle)
            yield from _chaines(valeur, f"{chemin}/{cle}")
    elif isinstance(objet, list):
        for i, valeur in enumerate(objet):
            yield from _chaines(valeur, f"{chemin}[{i}]")
    elif isinstance(objet, str):
        yield chemin, objet


def test_openapi_sans_jargon_interne() -> None:
    document = creer_application().openapi()
    chaines = list(_chaines(document))
    assert len(chaines) > 1000, "document OpenAPI anormalement court"
    fautifs = [
        (chemin, m.group(0)) for chemin, texte in chaines if (m := JARGON_INTERNE.search(texte))
    ]
    assert fautifs == []


def test_limite_salissure_sans_jargon() -> None:
    limite = calculer_taux_salissure_proxy([]).limite
    assert JARGON_INTERNE.search(limite) is None
    assert "spin-up" in limite
    assert "pas une mesure de salissure au sol" in limite


@pytest.mark.parametrize("mode", get_args(ModeCorrectionPR))
def test_limite_pr_realiste_sans_jargon(mode: ModeCorrectionPR) -> None:
    limite = calculer_pr_realiste([], 0.8, mode, 45.0, -0.4).limite
    assert JARGON_INTERNE.search(limite) is None
    assert "doctrine PR-reference" in limite
    assert ("spin-up" in limite) == (mode in ("salissure", "temperature_salissure"))
    assert ("biais de moyennage journalier" in limite) == (
        mode in ("temperature", "temperature_salissure")
    )


@pytest.mark.parametrize(
    ("localite", "jumelle"),
    [("gin_kindia", "gin_mamou"), ("gin_mamou", "gin_kindia"), ("gin_conakry_kaloum", None)],
)
def test_limite_ghi_exceedance_sans_jargon(localite: str, jumelle: str | None) -> None:
    limite = _construire_limite_ghi_exceedance(localite)
    assert JARGON_INTERNE.search(limite) is None
    if jumelle is None:
        assert "Co-localisation" not in limite
    else:
        assert f"Co-localisation : cette localite et {jumelle!r}" in limite


def test_limite_incertitude_inter_source_sans_jargon() -> None:
    limite = _construire_limite_incertitude_inter_source()
    assert JARGON_INTERNE.search(limite) is None
    assert "mesure sol" in limite
