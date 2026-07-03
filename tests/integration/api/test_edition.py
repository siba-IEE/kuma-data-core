"""Tests d'intégration de ``GET /v1/edition`` et du champ ``edition`` du
health (ADR-0003, D7 / WP5).

Couvre les deux régimes :

- **Régime local** (base de référence, pas de table
  ``edition_metadonnees``) : ``/v1/edition`` -> 404
  ``RESSOURCE_INTROUVABLE``, ``/v1/health`` -> ``edition: null``.
- **Régime édition** (fixture qui matérialise la table comme le fait
  le script d'export) : ``/v1/edition`` -> 200 avec métadonnées +
  couverture, ``/v1/health`` -> ``edition`` renseigné.

Les deux endpoints sont non authentifiés : aucun header dans ces tests.
La fixture crée la table puis la supprime (DDL transactionnel côté
PostgreSQL, teardown en ``DROP IF EXISTS`` par sûreté).
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from kuma_data_core.api.codes_erreur import CodeErreur
from kuma_data_core.db.session import get_engine
from kuma_data_core.publication.sql_edition import sql_metadonnees

pytestmark = pytest.mark.integration

_EDITION_ID_TEST = "edition_20260702"
_REVISION_TEST = "abcdef123456"


@pytest.fixture
def edition_metadonnees_presente() -> Iterator[None]:
    """Matérialise ``edition_metadonnees`` avec le SQL réel de l'export.

    Consomme ``sql_metadonnees`` (WP1) plutôt qu'un DDL dupliqué : le
    test intègre exactement ce que le script d'export injecte dans une
    édition - un drift export/endpoint casserait ici.
    """
    sql = sql_metadonnees(_EDITION_ID_TEST, "2026-07-02", _REVISION_TEST)
    engine = get_engine()
    with engine.begin() as connexion:
        for instruction in sql.split(";"):
            if instruction.strip():
                connexion.execute(text(instruction))
    yield
    with engine.begin() as connexion:
        connexion.execute(text("DROP TABLE IF EXISTS edition_metadonnees"))


def test_edition_absente_renvoie_404(client: TestClient) -> None:
    """Régime local : pas d'édition servie -> 404 explicite."""
    r = client.get("/v1/edition")
    assert r.status_code == 404
    assert r.json()["erreur"]["code"] == CodeErreur.RESSOURCE_INTROUVABLE.value


def test_health_edition_null_en_regime_local(client: TestClient) -> None:
    r = client.get("/v1/health")
    assert r.status_code == 200
    payload = r.json()
    assert "edition" in payload
    assert payload["edition"] is None


def test_edition_presente_renvoie_metadonnees_et_couverture(
    client: TestClient, edition_metadonnees_presente: None
) -> None:
    """Régime édition : métadonnées exactes + volumétrie non nulle."""
    r = client.get("/v1/edition")
    assert r.status_code == 200
    payload = r.json()
    assert payload["edition_id"] == _EDITION_ID_TEST
    assert payload["date_publication"] == "2026-07-02"
    assert payload["revision_source"] == _REVISION_TEST
    assert payload["couverture_resumee"]["localites"] > 0
    assert payload["couverture_resumee"]["series"] > 0


def test_edition_sans_authentification(
    client: TestClient, edition_metadonnees_presente: None
) -> None:
    """Même statut public que /v1/health : aucun Bearer requis."""
    r = client.get("/v1/edition")
    assert r.status_code == 200


def test_health_expose_l_edition_courante(
    client: TestClient, edition_metadonnees_presente: None
) -> None:
    r = client.get("/v1/health")
    assert r.status_code == 200
    assert r.json()["edition"] == _EDITION_ID_TEST
