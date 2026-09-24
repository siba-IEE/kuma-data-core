"""CORS : origines admises à appeler l'API depuis un navigateur.

La console API de kumascience.com appelle l'API avec la clé de
l'utilisateur ; Solar Bridge (Tauri) reste admis. Toute autre origine
ne reçoit aucun en-tête CORS : le navigateur bloque la réponse.
Les requêtes de pré-vérification (OPTIONS) sont traitées par le
middleware, sans toucher la base.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from kuma_data_core.api.main import app


@pytest.fixture(scope="module")
def client() -> TestClient:
    return TestClient(app)


def _preverifier(client: TestClient, origine: str, methode: str, entetes: str) -> dict[str, str]:
    reponse = client.options(
        "/v1/series",
        headers={
            "Origin": origine,
            "Access-Control-Request-Method": methode,
            "Access-Control-Request-Headers": entetes,
        },
    )
    return {k.lower(): v for k, v in reponse.headers.items()}


@pytest.mark.parametrize("origine", ["https://kumascience.com", "https://www.kumascience.com"])
def test_console_du_site_admise_en_get_avec_cle(client: TestClient, origine: str) -> None:
    entetes = _preverifier(client, origine, "GET", "authorization")
    assert entetes.get("access-control-allow-origin") == origine
    assert "authorization" in entetes.get("access-control-allow-headers", "").lower()


def test_console_du_site_admise_en_post_json(client: TestClient) -> None:
    entetes = _preverifier(client, "https://kumascience.com", "POST", "content-type")
    assert entetes.get("access-control-allow-origin") == "https://kumascience.com"
    assert "POST" in entetes.get("access-control-allow-methods", "")


def test_solar_bridge_reste_admis(client: TestClient) -> None:
    entetes = _preverifier(client, "tauri://localhost", "GET", "authorization")
    assert entetes.get("access-control-allow-origin") == "tauri://localhost"


@pytest.mark.parametrize("origine", ["https://exemple.org", "http://kumascience.com"])
def test_autre_origine_refusee(client: TestClient, origine: str) -> None:
    entetes = _preverifier(client, origine, "GET", "authorization")
    assert "access-control-allow-origin" not in entetes


def test_pas_de_credentials_cross_origin(client: TestClient) -> None:
    entetes = _preverifier(client, "https://kumascience.com", "GET", "authorization")
    assert "access-control-allow-credentials" not in entetes


def test_methodes_d_ecriture_hors_emission_refusees(client: TestClient) -> None:
    entetes = _preverifier(client, "https://kumascience.com", "DELETE", "authorization")
    assert "DELETE" not in entetes.get("access-control-allow-methods", "")
