"""Tests d'integration : collection des fiches d'incertitude inter-source (atlas).

``GET /v1/grandeurs/incertitude_inter_source`` (sans path param). Les 34 fiches de
l'atlas en un appel, enveloppe paginee ``{items, total, limit, offset}`` (identique a
/v1/series). Chaque item = la fiche par-localite (Temps 2) + lat/lon. Lecture pure.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

pytestmark = pytest.mark.integration

_URL = "/v1/grandeurs/incertitude_inter_source"


def test_sans_auth_rejete(client: TestClient) -> None:
    assert client.get(_URL).status_code == 401


def test_collection_34_points_enveloppe_paginee(
    client: TestClient, headers_auth: dict[str, str]
) -> None:
    """Enveloppe paginee {items,total,limit,offset} ; total = 34 points de l'atlas.

    Note : 34 est un compteur DB -> l'autorite reste la CI fraiche ; ici on verifie la
    forme + la coherence total/len."""
    r = client.get(_URL, headers=headers_auth)
    assert r.status_code == 200
    p = r.json()
    assert set(p) >= {"items", "total", "limit", "offset"}
    assert p["total"] == 34
    assert len(p["items"]) == 34  # limit defaut 100 >= 34


def test_item_structure_complete(client: TestClient, headers_auth: dict[str, str]) -> None:
    """Chaque item = deux axes distincts + coords + B + limite 'd-67'."""
    items = client.get(_URL, headers=headers_auth).json()["items"]
    for it in items:
        assert it["code_grandeur"] == "incertitude_inter_source"
        assert isinstance(it["ecarts"], list) and len(it["ecarts"]) >= 1
        assert isinstance(it["degenerescence"], dict)
        assert isinstance(it["latitude_deg"], (int, float))
        assert isinstance(it["longitude_deg"], (int, float))
        assert it["niveau_confiance"] == "B"
        assert "d-67" in it["limite"].lower()


def test_recoupe_unitaire_gin_boffa(client: TestClient, headers_auth: dict[str, str]) -> None:
    """Le point gin_boffa de la collection == la reponse de l'endpoint par-localite."""
    coll = client.get(_URL, headers=headers_auth).json()["items"]
    boffa_coll = next(it for it in coll if it["code_localite"] == "gin_boffa")
    boffa_unit = client.get(f"{_URL}/gin_boffa", headers=headers_auth).json()
    assert boffa_coll["ecarts"] == boffa_unit["ecarts"]
    assert boffa_coll["degenerescence"] == boffa_unit["degenerescence"]
    assert boffa_coll["niveau_confiance"] == boffa_unit["niveau_confiance"]


def test_temoin_jumeaux_gin_kindia(client: TestClient, headers_auth: dict[str, str]) -> None:
    """Temoin a jumeaux : gin_kindia (triplet) -> n_jumeaux>=1 dans la collection."""
    coll = client.get(_URL, headers=headers_auth).json()["items"]
    kindia = next(it for it in coll if it["code_localite"] == "gin_kindia")
    assert kindia["degenerescence"]["n_jumeaux"] >= 1
    assert "gin_mamou" in kindia["degenerescence"]["note"] or (
        "gin_dalaba" in kindia["degenerescence"]["note"]
    )


def test_pagination(client: TestClient, headers_auth: dict[str, str]) -> None:
    """limit/offset paginent ; total reste 34."""
    page1 = client.get(f"{_URL}?limit=10&offset=0", headers=headers_auth).json()
    assert page1["total"] == 34 and len(page1["items"]) == 10
    derniere = client.get(f"{_URL}?limit=10&offset=30", headers=headers_auth).json()
    assert derniere["total"] == 34 and len(derniere["items"]) == 4  # 34 - 30


def test_ecart_abs_primaire_par_item(client: TestClient, headers_auth: dict[str, str]) -> None:
    """|ecart| >= 0 sur chaque paire de chaque item."""
    for it in client.get(_URL, headers=headers_auth).json()["items"]:
        for e in it["ecarts"]:
            assert e["ecart_abs_pct"] >= 0.0
