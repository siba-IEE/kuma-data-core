"""Tests d'integration de ``GET /api/v1/localites/resolution`` (ADR-0004).

Resolution d'un point quelconque vers la localite du referentiel qui
echantillonne sa cellule de climatologie. Le cas contractuel est
celui qui a demontre le piege du plus-proche-voisin : Tokounou
(9,8459 N / -9,7115 O) est plus proche de Kankan (~74 km) mais dans
la cellule echantillonnee par Kerouane (~99 km).
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

pytestmark = pytest.mark.integration

_TOKOUNOU = {"lat": 9.8459, "lon": -9.7115}


def test_ti116_resolution_sans_auth_rejete(client: TestClient) -> None:
    """GET /v1/localites/resolution sans auth : 401."""
    r = client.get("/v1/localites/resolution", params=_TOKOUNOU)
    assert r.status_code == 401


def test_ti117_resolution_tokounou_cellule_de_kerouane(
    client: TestClient, headers_auth: dict[str, str]
) -> None:
    """Tokounou est resolu vers Kerouane (meme cellule), pas Kankan.

    Verification empirique du 2026-07-20 : la moyenne 1991-2020 de
    gin_kerouane_ghi_power_1991_2020 reproduit le releve NASA POWER
    au point de Tokounou, ecart nul sur les 12 mois.
    """
    r = client.get("/v1/localites/resolution", params=_TOKOUNOU, headers=headers_auth)
    assert r.status_code == 200
    payload = r.json()
    assert payload["localite"]["code"] == "gin_kerouane"
    assert payload["meme_cellule"] is True
    assert payload["cellule"] == {
        "lat_min": 9.0,
        "lat_max": 10.0,
        "lon_min": -10.0,
        "lon_max": -9.0,
    }
    # Kerouane est plus loin que Kankan : la distance prouve que la
    # resolution n'est pas un plus-proche-voisin.
    assert 90 <= payload["distance_km"] <= 110
    # Le Core dit quelle serie consommer (genericite pays, residu 2).
    assert payload["serie_climatologie"] == "gin_kerouane_ghi_power_1991_2020"


def test_ti118_resolution_point_dans_la_cellule_de_kankan(
    client: TestClient, headers_auth: dict[str, str]
) -> None:
    """Un point a cote de Kankan ville est resolu vers Kankan."""
    r = client.get(
        "/v1/localites/resolution",
        params={"lat": 10.4, "lon": -9.3},
        headers=headers_auth,
    )
    assert r.status_code == 200
    payload = r.json()
    assert payload["localite"]["code"] == "gin_kankan"
    assert payload["meme_cellule"] is True


def test_ti119_resolution_cellule_non_echantillonnee(
    client: TestClient, headers_auth: dict[str, str]
) -> None:
    """Cellule sans point d'ingestion : plus proche candidate, drapeau faux.

    Point en mer au large de la Guinee : aucune commune du referentiel
    ne partage sa cellule. La reponse est honnete (meme_cellule faux)
    et porte la distance pour l'affichage de l'hypothese de transport.
    """
    r = client.get(
        "/v1/localites/resolution",
        params={"lat": 8.0, "lon": -16.0},
        headers=headers_auth,
    )
    assert r.status_code == 200
    payload = r.json()
    assert payload["meme_cellule"] is False
    assert payload["distance_km"] > 100
    assert payload["localite"]["code"].startswith("gin_")
    assert payload["serie_climatologie"].endswith("_ghi_power_1991_2020")


def test_ti120_resolution_parametres_hors_bornes(
    client: TestClient, headers_auth: dict[str, str]
) -> None:
    """Latitude hors bornes : 422 de validation."""
    r = client.get(
        "/v1/localites/resolution",
        params={"lat": 91.0, "lon": 0.0},
        headers=headers_auth,
    )
    assert r.status_code == 422
