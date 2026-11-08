"""Tests d'integration : collection des fiches d'incertitude inter-source (atlas).

``GET /v1/grandeurs/incertitude_inter_source`` (sans path param). Les 34 fiches de
l'atlas en un appel, enveloppe paginee ``{items, total, limit, offset}`` (identique a
/v1/series). Chaque item = la fiche par-localite + lat/lon. Lecture pure.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event, text
from sqlalchemy.orm import Session

from kuma_data_core.db.session import get_engine, obtenir_session

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
        assert "mesure sol" in it["limite"]
        assert "D-67" not in it["limite"]


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


@pytest.fixture
def session_api() -> Iterator[Session]:
    """Session servie à l'API dans une transaction annulée en fin de test."""
    from kuma_data_core.api.main import app

    connection = get_engine().connect()
    transaction = connection.begin()
    session = Session(bind=connection, join_transaction_mode="create_savepoint")

    def _session() -> Iterator[Session]:
        yield session

    app.dependency_overrides[obtenir_session] = _session
    try:
        yield session
    finally:
        app.dependency_overrides.pop(obtenir_session, None)
        session.close()
        transaction.rollback()
        connection.close()


def test_ecart_hors_fenetre_hors_perimetre(
    client: TestClient, headers_auth: dict[str, str], session_api: Session
) -> None:
    """Un écart postérieur à la fenêtre 2021-2023 n'ajoute pas de point sans fiche."""
    code_hors_atlas = session_api.execute(
        text(
            """
            INSERT INTO grandeurs_metier (
                grandeur_code, localite_id, series_metadonnees_id, periode_type,
                annee_debut, annee_fin, mois, version_formule, valeur,
                niveau_confiance_derive)
            SELECT gm.grandeur_code, hors.id, gm.series_metadonnees_id, gm.periode_type,
                   2024, 2024, gm.mois, gm.version_formule, gm.valeur,
                   gm.niveau_confiance_derive
            FROM grandeurs_metier gm
            JOIN localites l ON l.id = gm.localite_id,
            LATERAL (
                SELECT h.id, h.code FROM localites h
                WHERE NOT EXISTS (
                    SELECT 1 FROM grandeurs_metier e
                    WHERE e.localite_id = h.id AND e.grandeur_code IN
                        ('ecart_relatif_referentiel', 'ecart_relatif_dni_cams'))
                ORDER BY h.code LIMIT 1
            ) hors
            WHERE l.code = 'gin_boffa' AND gm.grandeur_code = 'ecart_relatif_referentiel'
              AND gm.annee_debut = 2021 AND gm.mois = 1 AND gm.valide_au IS NULL
            RETURNING (SELECT code FROM localites WHERE id = localite_id)
            """
        )
    ).scalar_one()

    r = client.get(_URL, headers=headers_auth)
    assert r.status_code == 200
    p = r.json()
    assert p["total"] == 34
    assert code_hors_atlas not in {it["code_localite"] for it in p["items"]}


def _niveau_ecart_boffa(session: Session, niveau: str) -> None:
    n = session.execute(
        text(
            "UPDATE grandeurs_metier SET niveau_confiance_derive = :n "
            "WHERE grandeur_code = 'ecart_relatif_referentiel' AND valide_au IS NULL "
            "AND localite_id = (SELECT id FROM localites WHERE code = 'gin_boffa') "
            "AND annee_debut = 2021 AND mois = 1"
        ),
        {"n": niveau},
    ).rowcount  # type: ignore[attr-defined]
    assert n == 1


def test_fiche_en_c_si_un_ecart_est_en_c(
    client: TestClient, headers_auth: dict[str, str], session_api: Session
) -> None:
    """Un écart en C (entrée dégradée) rend la fiche C, par localité et en collection."""
    _niveau_ecart_boffa(session_api, "C")
    fiche = client.get(f"{_URL}/gin_boffa", headers=headers_auth)
    assert fiche.status_code == 200
    assert fiche.json()["niveau_confiance"] == "C"
    assert "confiance C" in fiche.json()["limite"]
    items = {
        it["code_localite"]: it for it in client.get(_URL, headers=headers_auth).json()["items"]
    }
    assert items["gin_boffa"]["niveau_confiance"] == "C"
    assert {it["niveau_confiance"] for c, it in items.items() if c != "gin_boffa"} == {"B"}


def test_fiche_500_si_un_ecart_est_en_a(
    client: TestClient, headers_auth: dict[str, str], session_api: Session
) -> None:
    """A est réservé aux mesures au sol : un écart en A trahit une dérive (500)."""
    _niveau_ecart_boffa(session_api, "A")
    assert client.get(f"{_URL}/gin_boffa", headers=headers_auth).status_code == 500


def test_point_aux_ecarts_tous_null_hors_perimetre(
    client: TestClient, headers_auth: dict[str, str], session_api: Session
) -> None:
    """Une localité dont tous les écarts sont NULL n'a pas de fiche : elle sort du périmètre."""
    n = session_api.execute(
        text(
            "UPDATE grandeurs_metier SET valeur = NULL WHERE valide_au IS NULL "
            "AND grandeur_code IN ('ecart_relatif_referentiel', 'ecart_relatif_dni_cams') "
            "AND localite_id = (SELECT id FROM localites WHERE code = 'gin_boffa')"
        )
    ).rowcount  # type: ignore[attr-defined]
    assert n > 0
    assert client.get(f"{_URL}/gin_boffa", headers=headers_auth).status_code == 404
    r = client.get(_URL, headers=headers_auth)
    assert r.status_code == 200, r.text
    p = r.json()
    assert p["total"] == 33
    assert "gin_boffa" not in {it["code_localite"] for it in p["items"]}


@pytest.mark.parametrize(
    ("params", "requetes_max"),
    [({"limit": 1000}, 3), ({"limit": 1}, 3), ({"offset": 500}, 2)],
)
def test_collection_en_requetes_ensemblistes(
    client: TestClient,
    headers_auth: dict[str, str],
    session_api: Session,
    params: dict[str, int],
    requetes_max: int,
) -> None:
    """Page, écarts et dégénérescences : nombre fixe de requêtes, quelle que soit la page."""
    requetes: list[str] = []

    def _compter(_conn: object, _curseur: object, sql: str, *_args: object) -> None:
        requetes.append(sql)

    connexion = session_api.connection()
    event.listen(connexion, "before_cursor_execute", _compter)
    try:
        r = client.get(_URL, params=params, headers=headers_auth)
    finally:
        event.remove(connexion, "before_cursor_execute", _compter)
    assert r.status_code == 200, r.text
    assert len(requetes) <= requetes_max, requetes
