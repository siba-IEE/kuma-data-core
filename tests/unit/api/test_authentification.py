"""Tests unitaires de la dépendance ``verifier_cle_api``.

Ne touchent ni à FastAPI ni à la base : on appelle directement la
fonction et on inspecte l'``ExceptionKuma`` levée. Les couches
``main.py`` et ``health.py`` sont validées séparément côté
intégration.
"""

from __future__ import annotations

import pytest

from kuma_data_core.api.codes_erreur import CodeErreur
from kuma_data_core.api.dependencies import verifier_cle_api
from kuma_data_core.api.erreurs import ExceptionKuma


@pytest.mark.unit
def test_authentification_header_manquant_leve_auth_header_manquant() -> None:
    with pytest.raises(ExceptionKuma) as info:
        verifier_cle_api(authorization=None)
    assert info.value.code is CodeErreur.AUTH_HEADER_MANQUANT
    assert info.value.statut_http == 401


@pytest.mark.unit
def test_authentification_format_sans_bearer_leve_auth_format_invalide() -> None:
    with pytest.raises(ExceptionKuma) as info:
        verifier_cle_api(authorization="Token test_cle_solar_xxxxxxxx")
    assert info.value.code is CodeErreur.AUTH_FORMAT_INVALIDE
    assert info.value.statut_http == 401


@pytest.mark.unit
def test_authentification_cle_inconnue_leve_auth_cle_invalide() -> None:
    with pytest.raises(ExceptionKuma) as info:
        verifier_cle_api(authorization="Bearer cle_qui_nexiste_pas")
    assert info.value.code is CodeErreur.AUTH_CLE_INVALIDE
    assert info.value.statut_http == 401


@pytest.mark.unit
def test_authentification_cle_valide_retourne_cle(cle_solar_valide: str) -> None:
    cle_retournee = verifier_cle_api(authorization=f"Bearer {cle_solar_valide}")
    assert cle_retournee == cle_solar_valide


@pytest.mark.unit
@pytest.mark.parametrize("entete", ["Bearer ", "Bearer    ", "Bearer \t"])
def test_authentification_bearer_vide_refuse(entete: str) -> None:
    """Durcissement : un Bearer vide ne matche jamais (garde clé vide).

    Défense contre une clé d'environnement vide qui, sans ce refus,
    rendrait ``compare_digest("", "")`` vrai et authentifierait un anonyme.
    """
    with pytest.raises(ExceptionKuma) as info:
        verifier_cle_api(authorization=entete)
    assert info.value.code is CodeErreur.AUTH_CLE_INVALIDE
    assert info.value.statut_http == 401
