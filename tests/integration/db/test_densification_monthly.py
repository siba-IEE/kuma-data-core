"""Tests d'intégration de la densification monthly (migration 087).

Les 28 nouvelles communes chef-lieu sont seedées en NASA POWER monthly (climato
long-terme) depuis le seed offline committé :

- 252 séries (28 communes x 9 grandeurs), ``granularite='mensuel'``, source
  ``nasa_power``, deux fenêtres (1991-2020 MERRA-2 / 2001-2020 CERES) ;
- mesures dérivées du seed committé (volume = 28 x 2760, pas un littéral) ;
- ingestion offline : 0 appel réseau (client garde) + tranchage correct des deux
  fenêtres + déterministe ;
- retrofit : le seed couvre aussi les 6 pilotes (041/050 immuables les lisent en
  offline, count-preserving).

Fixture ``db_session`` (conftest.py). Base d'intégration à head (087).
"""

from __future__ import annotations

import httpx
import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

from kuma_data_core.db.seeds.localites_prefectures_seed_data import PREFECTURES_GUINEE
from kuma_data_core.db.seeds.nasa_power_monthly_seed_data import NASA_MONTHLY_PAYLOADS
from kuma_data_core.external.nasa_power import SENTINELLE_VALEUR_MANQUANTE
from kuma_data_core.ingestion.nasa_power_monthly import _cle_ville_offline, _fetch_nasa_monthly_raw

pytestmark = pytest.mark.integration


# Mapping grandeur -> (parametre NASA, annee_debut), fenetre fin = 2020.
_GRANDEURS: dict[str, tuple[str, int]] = {
    "ghi": ("ALLSKY_SFC_SW_DWN", 1991),
    "t2m": ("T2M", 1991),
    "rh2m": ("RH2M", 1991),
    "vent_2m": ("WS2M", 1991),
    "vent_10m": ("WS10M", 1991),
    "dhi": ("ALLSKY_SFC_SW_DIFF", 2001),
    "dni": ("ALLSKY_SFC_SW_DNI", 2001),
    "kt": ("ALLSKY_KT", 2001),
    "albedo_surface": ("ALLSKY_SRF_ALB", 2001),
}
_ANNEE_FIN = 2020

_COMMUNES: dict[str, tuple[float, float]] = {
    p["commune_code"]: (float(p["lat"]), float(p["lon"]))
    for p in PREFECTURES_GUINEE
    if p["existante"] is None
}


def _client_garde() -> httpx.Client:
    """Client httpx qui leve sur tout appel reseau (preuve 0-reseau en offline)."""

    def _interdit(request: httpx.Request) -> httpx.Response:
        raise AssertionError(f"Appel reseau interdit en mode offline : {request.url}")

    return httpx.Client(transport=httpx.MockTransport(_interdit))


def _est_mensuel(cle: str) -> bool:
    return len(cle) == 6 and cle.isdigit() and 1 <= int(cle[4:]) <= 12


def test_252_series_mensuelles(db_session: Session) -> None:
    """28 communes x 9 grandeurs = 252 series mensuelles."""
    n = db_session.execute(
        text(
            """
            SELECT COUNT(*) FROM series_metadonnees sm
            JOIN localites l ON l.id = sm.localite_id
            WHERE l.code = ANY(:c) AND sm.granularite = 'mensuel'
            AND sm.source_id = (SELECT id FROM sources WHERE code = 'nasa_power')
            AND sm.periode_fin = '2020-12-31'
            """
        ),
        {"c": list(_COMMUNES)},
    ).scalar_one()
    assert n == 252


def test_volume_mesures_derive_du_seed(db_session: Session) -> None:
    """Volume mensuel des 28 = compte non-sentinelles du seed (28 x 2760 = 77 280)."""
    db_n = db_session.execute(
        text(
            """
            SELECT COUNT(*) FROM mesures_ressource_mensuelles m
            JOIN series_metadonnees sm ON sm.id = m.serie_id
            JOIN localites l ON l.id = sm.localite_id
            WHERE l.code = ANY(:c) AND sm.granularite = 'mensuel'
            AND sm.source_id = (SELECT id FROM sources WHERE code = 'nasa_power')
            AND sm.periode_fin = '2020-12-31'
            """
        ),
        {"c": list(_COMMUNES)},
    ).scalar_one()

    seed_n = 0
    for lat, lon in _COMMUNES.values():
        params = NASA_MONTHLY_PAYLOADS[_cle_ville_offline(lat, lon)]["properties"]["parameter"]
        for _grandeur, (param, annee_debut) in _GRANDEURS.items():
            seed_n += sum(
                1
                for cle, v in params[param].items()
                if _est_mensuel(cle)
                and annee_debut <= int(cle[:4]) <= _ANNEE_FIN
                and v != SENTINELLE_VALEUR_MANQUANTE
            )

    assert db_n == seed_n == 77280


def test_offline_zero_reseau_deux_fenetres(monkeypatch: pytest.MonkeyPatch) -> None:
    """Offline : tranchage correct des 2 fenetres + 0 reseau + deterministe."""
    monkeypatch.setenv("KUMA_INGESTION_MODE", "offline")
    monkeypatch.setenv("API_ENVIRONNEMENT", "dev")
    lat, lon = _COMMUNES["gin_boffa"]
    with _client_garde() as garde:
        # CERES DNI : fenetre 2001-2020 (pas de 1991).
        dni = _fetch_nasa_monthly_raw(
            latitude=lat,
            longitude=lon,
            parameters=["ALLSKY_SFC_SW_DNI"],
            annee_debut=2001,
            annee_fin=2020,
            httpx_client=garde,
        )["properties"]["parameter"]["ALLSKY_SFC_SW_DNI"]
        # MERRA-2 GHI : fenetre pleine 1991-2020.
        ghi = _fetch_nasa_monthly_raw(
            latitude=lat,
            longitude=lon,
            parameters=["ALLSKY_SFC_SW_DWN"],
            annee_debut=1991,
            annee_fin=2020,
            httpx_client=garde,
        )["properties"]["parameter"]["ALLSKY_SFC_SW_DWN"]
        dni2 = _fetch_nasa_monthly_raw(
            latitude=lat,
            longitude=lon,
            parameters=["ALLSKY_SFC_SW_DNI"],
            annee_debut=2001,
            annee_fin=2020,
            httpx_client=garde,
        )["properties"]["parameter"]["ALLSKY_SFC_SW_DNI"]
    annees_dni = {int(k[:4]) for k in dni if _est_mensuel(k)}
    annees_ghi = {int(k[:4]) for k in ghi if _est_mensuel(k)}
    assert min(annees_dni) == 2001 and max(annees_dni) == 2020  # 1991 exclu
    assert min(annees_ghi) == 1991 and max(annees_ghi) == 2020  # fenetre pleine
    assert dni == dni2  # deterministe (le garde n'a pas leve -> 0 reseau)


def test_confiance_coherente_avec_pilotes(db_session: Session) -> None:
    """Niveau derive des 28 = un seul niveau, identique aux pilotes monthly."""
    niveaux = {
        r[0]
        for r in db_session.execute(
            text(
                """
                SELECT DISTINCT m.niveau_confiance_derive FROM mesures_ressource_mensuelles m
                JOIN series_metadonnees sm ON sm.id = m.serie_id
                JOIN localites l ON l.id = sm.localite_id
                WHERE l.code = ANY(:c) AND sm.granularite = 'mensuel'
                """
            ),
            {"c": list(_COMMUNES)},
        ).all()
    }
    assert len(niveaux) == 1
    niveau_pilote = db_session.execute(
        text(
            "SELECT DISTINCT m.niveau_confiance_derive FROM mesures_ressource_mensuelles m "
            "JOIN series_metadonnees sm ON sm.id = m.serie_id "
            "WHERE sm.code = 'gin_kankan_t2m_power_1991_2020'"
        )
    ).scalar_one()
    assert niveaux == {niveau_pilote}


def test_6_pilotes_intacts(db_session: Session) -> None:
    """Les 6 pilotes gardent leurs series monthly (041/050, zero re-seed par 087)."""
    n = db_session.execute(
        text(
            """
            SELECT COUNT(*) FROM series_metadonnees sm
            JOIN localites l ON l.id = sm.localite_id
            WHERE l.code IN ('gin_conakry_kaloum', 'gin_kankan', 'gin_kindia',
                             'gin_labe', 'gin_mamou', 'gin_nzerekore')
            AND sm.granularite = 'mensuel'
            AND sm.source_id = (SELECT id FROM sources WHERE code = 'nasa_power')
            AND sm.periode_fin = '2020-12-31'
            """
        )
    ).scalar_one()
    # 6 villes x 9 grandeurs monthly NASA (ghi 041 + 8 grandeurs 050).
    # Filtre periode_fin 2020-12-31 : perimetre normales climato (les series
    # mensuelles longues 1981/1984/2001-2025 sont un lot distinct).
    assert n == 54
