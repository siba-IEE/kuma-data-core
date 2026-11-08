"""Fixtures partagées.

``get_settings`` est en cache et son validateur refuse une config prod
incohérente : l'environnement de test est donc posé avant tout import de
l'application, puis le cache est vidé.
"""

from __future__ import annotations

import os
from collections.abc import Iterator

import pytest


@pytest.fixture(scope="session", autouse=True)
def _configurer_env_test() -> None:
    """Force l'environnement de test avant tout import d'application."""
    os.environ["API_ENVIRONNEMENT"] = "dev"
    os.environ["API_DOCS_ACTIVES"] = "false"
    os.environ["API_CLE_SOLAR_BRIDGE"] = "test_cle_solar_xxxxxxxx"
    os.environ["API_CLE_ADMIN"] = "test_cle_admin_yyyyyyyy"
    os.environ["LOG_FORMAT"] = "json"
    os.environ["LOG_NIVEAU"] = "WARNING"

    # Un plugin pytest a pu importer l'application avant cette fixture.
    from kuma_data_core.core.config import get_settings

    get_settings.cache_clear()


@pytest.fixture
def client() -> Iterator[TestClient]:  # noqa: F821
    """Client HTTP de l'application, importée tard pour lire l'environnement de test."""
    from fastapi.testclient import TestClient

    from kuma_data_core.api.main import app

    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def cle_solar_valide() -> str:
    """Clé API valide associée au consommateur ``solar_bridge`` en test."""
    return "test_cle_solar_xxxxxxxx"


@pytest.fixture
def cle_admin_valide() -> str:
    """Clé API valide associée au consommateur ``admin`` en test."""
    return "test_cle_admin_yyyyyyyy"


@pytest.fixture
def headers_auth(cle_solar_valide: str) -> dict[str, str]:
    """Headers d'authentification prêts à l'emploi avec une clé valide."""
    return {"Authorization": f"Bearer {cle_solar_valide}"}
