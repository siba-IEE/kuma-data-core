"""Tests d'intégration de la densification SARAH-3 (migration 088).

Les 28 nouvelles communes chef-lieu recoivent la reference PVGIS-SARAH3 ICDR (GHI
mensuel 2021-2023), seedee offline. C'est la 1re reference d'ecart inter-source aux
nouveaux points (avec NASA deja en base -> ecart calculable = couche atlas).

- 28 series (gin_<commune>_ghi_sarah3_2021_2023), granularite mensuel, source
  sarah3_monthly ;
- 1 008 mesures = 28 x 36 mois (jeu ICDR fige, deterministe) ;
- ingestion offline : 0 reseau (client garde) ;
- 6 pilotes intacts (041, zero retrofit) ;
- overlap NASA + SARAH-3 sur 2021-2023 aux nouveaux points (ecart calculable).

Fixture ``db_session`` (conftest.py). Base d'integration a head (088).
"""

from __future__ import annotations

import httpx
import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

from kuma_data_core.db.seeds.localites_prefectures_seed_data import PREFECTURES_GUINEE
from kuma_data_core.ingestion.sarah3_monthly import _fetch_sarah3_monthly_raw

pytestmark = pytest.mark.integration

_COMMUNES: dict[str, tuple[float, float]] = {
    p["commune_code"]: (float(p["lat"]), float(p["lon"]))
    for p in PREFECTURES_GUINEE
    if p["existante"] is None
}


def _client_garde() -> httpx.Client:
    def _interdit(request: httpx.Request) -> httpx.Response:
        raise AssertionError(f"Appel reseau interdit en mode offline : {request.url}")

    return httpx.Client(transport=httpx.MockTransport(_interdit))


def test_28_series_sarah3(db_session: Session) -> None:
    n = db_session.execute(
        text(
            """
            SELECT COUNT(*) FROM series_metadonnees sm
            JOIN localites l ON l.id = sm.localite_id
            WHERE l.code = ANY(:c) AND sm.granularite = 'mensuel'
            AND sm.source_id = (SELECT id FROM sources WHERE code = 'sarah3_monthly')
            """
        ),
        {"c": list(_COMMUNES)},
    ).scalar_one()
    assert n == 28


def test_volume_1008_mesures(db_session: Session) -> None:
    n = db_session.execute(
        text(
            """
            SELECT COUNT(*) FROM mesures_ressource_mensuelles m
            JOIN series_metadonnees sm ON sm.id = m.serie_id
            JOIN localites l ON l.id = sm.localite_id
            WHERE l.code = ANY(:c)
            AND sm.source_id = (SELECT id FROM sources WHERE code = 'sarah3_monthly')
            """
        ),
        {"c": list(_COMMUNES)},
    ).scalar_one()
    assert n == 1008  # 28 communes x 36 mois (2021-2023)


def test_offline_zero_reseau(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("KUMA_INGESTION_MODE", "offline")
    monkeypatch.setenv("API_ENVIRONNEMENT", "dev")
    lat, lon = _COMMUNES["gin_boffa"]
    with _client_garde() as garde:
        p1 = _fetch_sarah3_monthly_raw(
            latitude=lat,
            longitude=lon,
            annee_debut=2021,
            annee_fin=2023,
            timeout=1.0,
            httpx_client=garde,
        )
        p2 = _fetch_sarah3_monthly_raw(
            latitude=lat,
            longitude=lon,
            annee_debut=2021,
            annee_fin=2023,
            timeout=1.0,
            httpx_client=garde,
        )
    assert len(p1["outputs"]["monthly"]) == 36  # 3 ans x 12 mois, 0 reseau
    assert p1 == p2  # deterministe


def test_6_pilotes_intacts(db_session: Session) -> None:
    n = db_session.execute(
        text(
            """
            SELECT COUNT(*) FROM series_metadonnees sm
            JOIN localites l ON l.id = sm.localite_id
            WHERE l.code IN ('gin_conakry_kaloum', 'gin_kankan', 'gin_kindia',
                             'gin_labe', 'gin_mamou', 'gin_nzerekore')
            AND sm.source_id = (SELECT id FROM sources WHERE code = 'sarah3_monthly')
            """
        )
    ).scalar_one()
    assert n == 6  # 6 villes x 1 GHI SARAH-3 (041, zero retrofit)


def test_overlap_nasa_sarah3_ecart_calculable(db_session: Session) -> None:
    """Aux nouveaux points, NASA (daily) ET SARAH-3 couvrent 2021-2023 -> ecart calculable."""
    # NASA ghi daily 2021-2023 present sur un nouveau point.
    n_nasa = db_session.execute(
        text(
            """
            SELECT COUNT(*) FROM mesures_ressource mr
            JOIN series_metadonnees sm ON sm.id = mr.serie_id
            JOIN localites l ON l.id = sm.localite_id
            WHERE l.code = 'gin_boffa' AND sm.grandeur_code = 'ghi'
            AND sm.granularite = 'journalier'
            AND mr.instant_mesure BETWEEN '2021-01-01' AND '2023-12-31'
            """
        )
    ).scalar_one()
    # SARAH-3 ghi monthly 2021-2023 present sur le meme point.
    n_sarah = db_session.execute(
        text(
            """
            SELECT COUNT(*) FROM mesures_ressource_mensuelles m
            JOIN series_metadonnees sm ON sm.id = m.serie_id
            JOIN localites l ON l.id = sm.localite_id
            WHERE l.code = 'gin_boffa'
            AND sm.source_id = (SELECT id FROM sources WHERE code = 'sarah3_monthly')
            """
        )
    ).scalar_one()
    assert n_nasa > 0 and n_sarah == 36  # overlap reel -> ecart inter-source calculable
