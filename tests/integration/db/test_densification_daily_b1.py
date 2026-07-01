"""Tests d'integration de la densification daily (migration 086).

Les 28 nouvelles communes chef-lieu sont seedees en NASA POWER daily 2021-2025
depuis le seed offline committe :

- 252 series (28 communes x 9 grandeurs brutes), ``granularite='journalier'``,
  ``methode_collecte='modele_satellitaire'``, source ``nasa_power`` ;
- mesures derivees du seed committe (volume = compte non-sentinelles, pas un
  litteral magique) ;
- niveau de confiance derive identique aux 6 pilotes (meme methode/source) ;
- ingestion offline : 0 appel reseau (client garde) + deterministe.

Fixture ``db_session`` (conftest.py). La base d'integration est a head (086).
"""

from __future__ import annotations

from datetime import date

import httpx
import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

from kuma_data_core.db.seeds.localites_prefectures_seed_data import PREFECTURES_GUINEE
from kuma_data_core.db.seeds.nasa_power_daily_seed_data import NASA_DAILY_PAYLOADS
from kuma_data_core.external.nasa_power import SENTINELLE_VALEUR_MANQUANTE
from kuma_data_core.ingestion.nasa_power_daily import _cle_ville_offline, _fetch_nasa_daily_raw

pytestmark = pytest.mark.integration


# 9 parametres NASA daily (union du seed), alignes sur la migration 086.
_PARAMS9: tuple[str, ...] = (
    "ALLSKY_SFC_SW_DWN",
    "ALLSKY_SFC_SW_DNI",
    "ALLSKY_SFC_SW_DIFF",
    "T2M",
    "RH2M",
    "ALLSKY_KT",
    "WS2M",
    "WS10M",
    "ALLSKY_SRF_ALB",
)

# 28 nouvelles communes (code -> (lat, lon)), depuis le seed.
_COMMUNES: dict[str, tuple[float, float]] = {
    p["commune_code"]: (float(p["lat"]), float(p["lon"]))
    for p in PREFECTURES_GUINEE
    if p["existante"] is None
}

_LIKE_DAILY = "%\\_nasa\\_power\\_2021\\_2025"  # echappe les _ (wildcard SQL LIKE)


def _client_garde() -> httpx.Client:
    """Client httpx qui leve sur tout appel reseau (preuve 0-reseau en offline)."""

    def _interdit(request: httpx.Request) -> httpx.Response:
        raise AssertionError(f"Appel reseau interdit en mode offline : {request.url}")

    return httpx.Client(transport=httpx.MockTransport(_interdit))


def test_280_series_densification(db_session: Session) -> None:
    """28 communes x 10 series daily nasa_power = 280 : 9 grandeurs (migration 086)
    + precipitation (migration 094). Parite avec les pilotes (10 series/ville,
    cf. test_5_pilotes_intacts). Champs conformes."""
    n = db_session.execute(
        text(
            """
            SELECT COUNT(*) FROM series_metadonnees sm
            JOIN localites l ON l.id = sm.localite_id
            WHERE l.code = ANY(:c) AND sm.code LIKE :pat ESCAPE '\\'
            AND sm.granularite = 'journalier'
            AND sm.methode_collecte = 'modele_satellitaire'
            AND sm.source_id = (SELECT id FROM sources WHERE code = 'nasa_power')
            """
        ),
        {"c": list(_COMMUNES), "pat": _LIKE_DAILY},
    ).scalar_one()
    assert n == 280


def test_volume_mesures_derive_du_seed(db_session: Session) -> None:
    """Volume mesures des 28 = compte non-sentinelles du seed (deterministe).

    Exclut precipitation : elle a son seed dedie (migration 094) hors de
    NASA_DAILY_PAYLOADS ; son volume est verifie dans test_parite_b1_precipitation."""
    db_n = db_session.execute(
        text(
            """
            SELECT COUNT(*) FROM mesures_ressource mr
            JOIN series_metadonnees sm ON sm.id = mr.serie_id
            JOIN localites l ON l.id = sm.localite_id
            WHERE l.code = ANY(:c) AND sm.code LIKE :pat ESCAPE '\\'
            AND sm.grandeur_code <> 'precipitation'
            """
        ),
        {"c": list(_COMMUNES), "pat": _LIKE_DAILY},
    ).scalar_one()

    seed_n = 0
    for lat, lon in _COMMUNES.values():
        params = NASA_DAILY_PAYLOADS[_cle_ville_offline(lat, lon)]["properties"]["parameter"]
        for nom in _PARAMS9:
            seed_n += sum(1 for v in params[nom].values() if v != SENTINELLE_VALEUR_MANQUANTE)

    assert db_n == seed_n


def test_confiance_coherente_avec_pilotes(db_session: Session) -> None:
    """Le niveau de confiance derive des 28 = un seul niveau, identique aux pilotes."""
    niveaux_28 = {
        r[0]
        for r in db_session.execute(
            text(
                """
                SELECT DISTINCT mr.niveau_confiance_derive FROM mesures_ressource mr
                JOIN series_metadonnees sm ON sm.id = mr.serie_id
                JOIN localites l ON l.id = sm.localite_id
                WHERE l.code = ANY(:c) AND sm.code LIKE :pat ESCAPE '\\'
                """
            ),
            {"c": list(_COMMUNES), "pat": _LIKE_DAILY},
        ).all()
    }
    assert len(niveaux_28) == 1, f"plusieurs niveaux derives : {niveaux_28}"

    niveau_pilote = db_session.execute(
        text(
            """
            SELECT DISTINCT mr.niveau_confiance_derive FROM mesures_ressource mr
            JOIN series_metadonnees sm ON sm.id = mr.serie_id
            WHERE sm.code = 'gin_kankan_ghi_nasa_power_2021_2025'
            """
        )
    ).scalar_one()
    assert niveaux_28 == {niveau_pilote}


def test_5_pilotes_intacts(db_session: Session) -> None:
    """Les 5 capitales regionales gardent leurs series daily (zero re-ingestion)."""
    n = db_session.execute(
        text(
            """
            SELECT COUNT(*) FROM series_metadonnees sm
            JOIN localites l ON l.id = sm.localite_id
            WHERE l.code IN ('gin_kankan', 'gin_kindia', 'gin_labe', 'gin_mamou', 'gin_nzerekore')
            AND sm.code LIKE :pat ESCAPE '\\'
            """
        ),
        {"pat": _LIKE_DAILY},
    ).scalar_one()
    # 5 villes x 10 series daily nasa_power : 9 grandeurs (028 / 047) +
    # precipitation (migration 080). 086 ne les touche pas.
    assert n == 50


def test_offline_zero_reseau_et_deterministe(monkeypatch: pytest.MonkeyPatch) -> None:
    """Mode offline : le fetch renvoie le seed (9 params) sans reseau, deterministe."""
    monkeypatch.setenv("KUMA_INGESTION_MODE", "offline")
    monkeypatch.setenv("API_ENVIRONNEMENT", "dev")
    lat, lon = _COMMUNES["gin_boffa"]
    with _client_garde() as garde:
        p1 = _fetch_nasa_daily_raw(
            latitude=lat,
            longitude=lon,
            parameters=list(_PARAMS9),
            periode_debut=date(2021, 1, 1),
            periode_fin=date(2025, 12, 31),
            httpx_client=garde,
        )
        p2 = _fetch_nasa_daily_raw(
            latitude=lat,
            longitude=lon,
            parameters=list(_PARAMS9),
            periode_debut=date(2021, 1, 1),
            periode_fin=date(2025, 12, 31),
            httpx_client=garde,
        )
    # Le client garde n'a pas leve -> aucun appel reseau.
    assert set(p1["properties"]["parameter"]) == set(_PARAMS9)
    assert p1 == p2
