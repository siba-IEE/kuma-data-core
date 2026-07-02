"""Tests unitaires de la configuration d'édition publique (ADR-0003, WP4).

Tests sans DB, sur ``Settings`` directement. Couvrent :

1. Défauts : ``edition_db`` absent (la référence est servie),
   ``edition_figee`` désactivé - le comportement local/dev est inchangé
   par le chantier édition.
2. Repointage D1 : ``edition_db`` défini prime sur ``postgres_db`` dans
   ``database_url``.
3. QO-3 tranchée : ``api_environnement`` accepte ``integration`` (doc
   de référence §health) et refuse l'ancien ``staging``.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from kuma_data_core.core.config import Settings

pytestmark = pytest.mark.unit


def test_defauts_edition_inchanges_en_local() -> None:
    s = Settings(postgres_password="mdp")
    assert s.edition_db is None
    assert s.edition_figee is False


def test_database_url_sans_edition_db_sert_la_reference() -> None:
    s = Settings(postgres_password="mdp")
    assert s.database_url.endswith(f"/{s.postgres_db}")


def test_database_url_avec_edition_db_prime_sur_la_reference() -> None:
    s = Settings(postgres_password="mdp", edition_db="kuma_edition_20260702_abcdef123456")
    assert s.database_url.endswith("/kuma_edition_20260702_abcdef123456")
    assert s.postgres_db not in s.database_url.rsplit("/", 1)[1]


def test_api_environnement_accepte_integration() -> None:
    s = Settings(postgres_password="mdp", api_environnement="integration")
    assert s.api_environnement == "integration"


def test_api_environnement_refuse_staging() -> None:
    """QO-3 : l'ancienne valeur ``staging`` (jamais documentée) est rejetée."""
    with pytest.raises(ValidationError):
        Settings(postgres_password="mdp", api_environnement="staging")  # type: ignore[arg-type]


def test_prod_refuse_cle_admin_vide() -> None:
    """Durcissement sécurité : une clé admin vide en prod bloque le démarrage.

    Sans cette garde, ``API_CLE_ADMIN=""`` passe ``is None`` mais rendrait
    un Bearer vide administrateur.
    """
    with pytest.raises(ValidationError):
        Settings(
            postgres_password="mdp",
            api_environnement="prod",
            api_docs_actives=False,
            log_format="json",
            api_cle_admin="",
        )


def test_prod_accepte_cle_admin_non_vide() -> None:
    s = Settings(
        postgres_password="mdp",
        api_environnement="prod",
        api_docs_actives=False,
        log_format="json",
        api_cle_admin="cle_admin_reelle",
    )
    assert s.api_environnement == "prod"
