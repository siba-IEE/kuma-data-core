"""Tests d'integration de l'endpoint atlas Temps 2 : fiche d'incertitude inter-source.

``GET /v1/grandeurs/incertitude_inter_source/{code_localite}``. Assemble EN LECTURE les
deux axes d'honnetete deja materialises (ecart inter-source Temps 1 + degenerescence),
**sans les fusionner**. Confiance B (jamais A = terrain).
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from kuma_data_core.api.codes_erreur import CodeErreur

pytestmark = pytest.mark.integration

_URL = "/v1/grandeurs/incertitude_inter_source"


def _get(client: TestClient, headers_auth: dict[str, str], code_localite: str):
    return client.get(f"{_URL}/{code_localite}", headers=headers_auth)


def test_sans_auth_rejete(client: TestClient) -> None:
    assert client.get(f"{_URL}/gin_boffa").status_code == 401


def test_assemblage_commune(client: TestClient, headers_auth: dict[str, str]) -> None:
    """gin_boffa : 200, ecarts (ghi+dni) + degenerescence assembles."""
    r = _get(client, headers_auth, "gin_boffa")
    assert r.status_code == 200
    p = r.json()
    assert p["code_grandeur"] == "incertitude_inter_source"
    assert p["code_localite"] == "gin_boffa"
    assert p["fenetre"] == "2021-2023"
    assert {e["grandeur"] for e in p["ecarts"]} == {"ghi", "dni"}
    assert "n_jumeaux" in p["degenerescence"]


def test_deux_axes_distincts(client: TestClient, headers_auth: dict[str, str]) -> None:
    """Ecart ET degenerescence cote a cote, aucun scalaire unique confle."""
    p = _get(client, headers_auth, "gin_boffa").json()
    assert isinstance(p["ecarts"], list)
    assert isinstance(p["degenerescence"], dict)
    # Aucun champ score / incertitude globale fusionne.
    assert "score" not in p
    assert "incertitude_globale" not in p


def test_dni_recent_pas_climato(client: TestClient, headers_auth: dict[str, str]) -> None:
    """Pilote gin_kankan (climato 2004-2020 + recent en base) : la fiche expose le RECENT."""
    p = _get(client, headers_auth, "gin_kankan").json()
    dni = next(e for e in p["ecarts"] if e["grandeur"] == "dni")
    assert dni["n_mois"] == 36  # 2021-2023 ; pas le climato 2004-2020 (204 mois)


def test_abs_primaire_signe_orientationnel(
    client: TestClient, headers_auth: dict[str, str]
) -> None:
    """|ecart| >= 0 (primaire) ; le signe DNI est negatif (NASA < CAMS, biais all-sky)."""
    p = _get(client, headers_auth, "gin_boffa").json()
    for e in p["ecarts"]:
        assert e["ecart_abs_pct"] >= 0.0
    dni = next(e for e in p["ecarts"] if e["grandeur"] == "dni")
    assert dni["ecart_signe_pct"] < 0.0


def test_anti_survente_b_inter_source(client: TestClient, headers_auth: dict[str, str]) -> None:
    """Confiance B ; 'inter_source' dans code_grandeur ; 'd-67' dans limite."""
    p = _get(client, headers_auth, "gin_boffa").json()
    assert p["niveau_confiance"] == "B"
    assert "inter_source" in p["code_grandeur"]
    assert "inter-source" in p["limite"].lower()
    assert "d-67" in p["limite"].lower()


def test_degenerescence_niveau_localite_d29(
    client: TestClient, headers_auth: dict[str, str]
) -> None:
    """gin_kindia (triplet) : n_jumeaux>=1, note nomme un jumeau ; rendue UNE fois (objet)."""
    p = _get(client, headers_auth, "gin_kindia").json()
    degen = p["degenerescence"]
    assert isinstance(degen, dict)  # rendue une fois, pas par grandeur
    assert degen["n_jumeaux"] >= 1
    assert "gin_mamou" in degen["note"] or "gin_dalaba" in degen["note"]


def test_trou_localite_non_couverte_404(client: TestClient, headers_auth: dict[str, str]) -> None:
    """gin_boke (region, hors des 34 points) : 404 LOCALITE_INCONNUE, message 'non couverte'."""
    r = _get(client, headers_auth, "gin_boke")
    assert r.status_code == 404
    assert r.json()["erreur"]["code"] == CodeErreur.RESSOURCE_LOCALITE_INCONNUE.value
    assert "non couverte" in r.json()["erreur"]["message"].lower()


def test_ghi_dni_partagent_ceres(client: TestClient, headers_auth: dict[str, str]) -> None:
    """Garde de l'hypothese GHI/DNI == grille CERES : la degenerescence (NASA/ghi
    representative) est coherente avec une grille CERES nommee, pour un point degenere."""
    p = _get(client, headers_auth, "gin_kindia").json()
    assert "CERES" in p["degenerescence"]["grille"]
