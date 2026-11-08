"""Une seule définition de la mesure utilisable, appliquée par l'API et les calculs.

Journalier et mensuel : courante et non dépréciée. Horaire : courante et passée
par le contrôle qualité (``valide_auto``, ``valide_humain``, ``publie``).
Grandeurs calculées : ``v_grandeurs_metier_courantes``. Chaque test change un
statut dans une transaction annulée en fin de test.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session

from kuma_data_core.db.session import get_engine, obtenir_session
from kuma_data_core.services.capsule.acquisition import SourceCore
from kuma_data_core.services.grandeurs.referentiels import _lire_kuma_mensuel

pytestmark = pytest.mark.integration

_GHI_JOUR = "gin_conakry_ghi_nasa_power_2021_2025"
_GHI_MOIS = "gin_conakry_ghi_power_1991_2020"
_LOCALITE = "gin_conakry_kaloum"


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


def _changer_statut(
    session: Session, table: str, code_serie: str, condition: str, statut: str
) -> int:
    """Passe au ``statut`` les mesures courantes de la série qui vérifient ``condition``."""
    return session.execute(  # type: ignore[attr-defined, no-any-return]
        text(
            f"UPDATE {table} SET statut = :statut "
            "WHERE serie_id = (SELECT id FROM series_metadonnees WHERE code = :code) "
            f"AND valide_au IS NULL AND {condition}"
        ),
        {"statut": statut, "code": code_serie},
    ).rowcount


def test_journalier_deprecie_exclu_des_lectures_api(
    client: TestClient, headers_auth: dict[str, str], session_api: Session
) -> None:
    """Un jour déprécié disparaît du détail de série et des calculs à la volée."""
    n = _changer_statut(
        session_api, "mesures_ressource", _GHI_JOUR, "instant_mesure = '2024-01-03'", "deprecie"
    )
    assert n == 1
    detail = client.get(
        f"/v1/series/{_GHI_JOUR}",
        params={"from": "2024-01-01", "to": "2024-01-05"},
        headers=headers_auth,
    )
    assert detail.status_code == 200
    jours = [m["instant_mesure"] for m in detail.json()["mesures"]]
    assert jours == ["2024-01-01", "2024-01-02", "2024-01-04", "2024-01-05"]

    poa = client.get(
        "/v1/grandeurs/poa_parametrable",
        params={
            "code_serie_source": _GHI_JOUR,
            "periode_debut": "2024-01-01",
            "periode_fin": "2024-01-05",
            "inclinaison_deg": "20",
            "orientation_deg": "180",
        },
        headers=headers_auth,
    )
    assert poa.status_code == 200
    assert "2024-01-03" not in {r["instant"] for r in poa.json()["resultats"]}


def test_journalier_brut_reste_utilisable(
    client: TestClient, headers_auth: dict[str, str], session_api: Session
) -> None:
    """Le journalier est entièrement ``brut`` : il reste servi."""
    detail = client.get(
        f"/v1/series/{_GHI_JOUR}",
        params={"from": "2024-01-01", "to": "2024-01-05"},
        headers=headers_auth,
    )
    assert detail.status_code == 200
    assert {m["statut"] for m in detail.json()["mesures"]} == {"brut"}
    assert len(detail.json()["mesures"]) == 5


def test_mensuel_deprecie_exclu_du_detail_de_serie(
    client: TestClient, headers_auth: dict[str, str], session_api: Session
) -> None:
    n = _changer_statut(
        session_api,
        "mesures_ressource_mensuelles",
        _GHI_MOIS,
        "annee = 1991 AND mois = 2",
        "deprecie",
    )
    assert n == 1
    detail = client.get(
        f"/v1/series/{_GHI_MOIS}",
        params={"from": "1991-01", "to": "1991-03"},
        headers=headers_auth,
    )
    assert detail.status_code == 200
    assert [m["mois"] for m in detail.json()["mesures"]] == [1, 3]


def test_journalier_deprecie_exclu_des_calculs_stockes(session_api: Session) -> None:
    """Les services de calcul lisent la même règle : un mois entièrement déprécié disparaît."""
    assert (2024, 1) in _lire_kuma_mensuel(session_api, _GHI_JOUR)
    _changer_statut(
        session_api,
        "mesures_ressource",
        _GHI_JOUR,
        "instant_mesure BETWEEN '2024-01-01' AND '2024-01-31'",
        "deprecie",
    )
    assert (2024, 1) not in _lire_kuma_mensuel(session_api, _GHI_JOUR)


def test_grandeur_calculee_depreciee_exclue_de_l_atlas(
    client: TestClient, headers_auth: dict[str, str], session_api: Session
) -> None:
    """L'atlas lit les grandeurs calculées courantes, comme ``/v1/series``."""
    url = f"/v1/grandeurs/incertitude_inter_source/{_LOCALITE}"
    avant = {
        e["grandeur"]: e["n_mois"] for e in client.get(url, headers=headers_auth).json()["ecarts"]
    }
    n = session_api.execute(
        text(
            "UPDATE grandeurs_metier SET statut = 'deprecie' "
            "WHERE grandeur_code = 'ecart_relatif_referentiel' AND valide_au IS NULL "
            "AND localite_id = (SELECT id FROM localites WHERE code = :loc) "
            "AND annee_debut = 2021 AND mois = 1"
        ),
        {"loc": _LOCALITE},
    ).rowcount  # type: ignore[attr-defined]
    assert n == 1
    apres = {
        e["grandeur"]: e["n_mois"] for e in client.get(url, headers=headers_auth).json()["ecarts"]
    }
    assert apres == {**avant, "ghi": avant["ghi"] - 1}


def test_horaire_valide_humain_servi_avec_son_statut(
    client: TestClient, headers_auth: dict[str, str], session_api: Session
) -> None:
    code = session_api.execute(
        text(
            "SELECT sm.code FROM series_metadonnees sm JOIN localites l ON l.id = sm.localite_id "
            "WHERE l.code = :loc AND sm.grandeur_code = 'ghi' AND sm.granularite = 'horaire' "
            "AND sm.actif ORDER BY sm.id LIMIT 1"
        ),
        {"loc": _LOCALITE},
    ).scalar_one()
    n = _changer_statut(
        session_api,
        "mesures_ressource_horaires",
        code,
        "statut = 'valide_auto' AND instant_mesure >= '2022-06-01T00:00Z' "
        "AND instant_mesure < '2022-06-01T06:00Z'",
        "valide_humain",
    )
    assert n == 6
    r = client.get(
        f"/v1/horaire/{_LOCALITE}/ghi",
        params={"periode_debut": "2022-06-01", "periode_fin": "2022-06-01"},
        headers=headers_auth,
    )
    assert r.status_code == 200
    statuts = [res["statut_editorial"] for res in r.json()["resultats"]]
    assert statuts == ["valide_humain"] * 6 + ["valide_auto"] * 18


def test_capsule_horaire_inclut_valide_humain(session_api: Session) -> None:
    """La séquence horaire de la capsule garde un point relu (``valide_humain``)."""
    localite_id = session_api.execute(
        text("SELECT id FROM localites WHERE code = :loc"), {"loc": _LOCALITE}
    ).scalar_one()
    source = SourceCore(session=session_api, annee_min=2022, annee_max=2022)
    sequence, _, provenance = source._sequence_horaire(int(localite_id))
    n_avant = len(sequence["ghi"])
    n = _changer_statut(
        session_api,
        "mesures_ressource_horaires",
        provenance["code"],
        "statut = 'valide_auto' AND instant_mesure >= '2022-06-01T00:00Z' "
        "AND instant_mesure < '2022-06-02T00:00Z'",
        "valide_humain",
    )
    assert n == 24
    sequence, _, _ = source._sequence_horaire(int(localite_id))
    assert len(sequence["ghi"]) == n_avant
