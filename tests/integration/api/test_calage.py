"""Tests d'integration de l'endpoint ``/api/v1/calage`` (ADR-0004).

Le referentiel de calage satellite/sol est une donnee editoriale
seedee par la migration 101 : la premiere entree est le GHI de la
station de Kankan (3 saisons).
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from kuma_data_core.api.codes_erreur import CodeErreur

pytestmark = pytest.mark.integration


def test_ti113_calage_sans_auth_rejete(client: TestClient) -> None:
    """GET /v1/calage/... sans auth : 401."""
    r = client.get("/v1/calage/gin_kankan/ghi")
    assert r.status_code == 401


def test_ti114_calage_kankan_ghi_sert_le_referentiel(
    client: TestClient, headers_auth: dict[str, str]
) -> None:
    """(gin_kankan, ghi) : 3 saisons, biais mesures, facteurs derives.

    Les chiffres contractuels sont ceux de la note de calage et de la
    methode d'etude mini-reseau v1 : harmattan +4,4 % (k 0,9579),
    mousson +1,5 % (k 0,9852), intersaison +1,9 % (k 0,9814).
    """
    r = client.get("/v1/calage/gin_kankan/ghi", headers=headers_auth)
    assert r.status_code == 200
    payload = r.json()
    assert payload["localite"] == "gin_kankan"
    assert payload["grandeur"] == "ghi"
    assert payload["code"] == "gin_kankan_ghi_calage_saisonnier"
    assert payload["version"] == "v1"
    assert payload["provenance"]
    assert payload["portee"]

    saisons = {s["nom"]: s for s in payload["saisons"]}
    assert set(saisons) == {"harmattan", "mousson", "intersaison"}
    attendus = {
        "harmattan": (0.044, 0.9579, [11, 12, 1, 2, 3]),
        "mousson": (0.015, 0.9852, [6, 7, 8, 9]),
        "intersaison": (0.019, 0.9814, [4, 5, 10]),
    }
    for nom, (biais, k, mois) in attendus.items():
        saison = saisons[nom]
        assert saison["mois"] == mois
        assert abs(saison["biais"] - biais) <= 1e-9
        assert abs(saison["k"] - k) <= 5e-5

    # Les 12 mois sont couverts exactement une fois.
    tous_mois = sorted(m for s in payload["saisons"] for m in s["mois"])
    assert tous_mois == list(range(1, 13))


def test_ti121_calage_porte_le_domaine_de_couverture(
    client: TestClient, headers_auth: dict[str, str]
) -> None:
    """Le referentiel sert son domaine de couverture (migration 102).

    Domaine initial arrete par le fondateur le 2026-07-20 : les 5
    communes points d'ingestion de la region administrative de Kankan.
    C'est la donnee qui pilote la couverture geographique des
    consommateurs (couverture progressive, ADR-0004).
    """
    r = client.get("/v1/calage/gin_kankan/ghi", headers=headers_auth)
    assert r.status_code == 200
    payload = r.json()
    assert payload["localites_couvertes"] == [
        "gin_kankan",
        "gin_kerouane",
        "gin_kouroussa",
        "gin_mandiana",
        "gin_siguiri",
    ]
    assert payload["justification_couverture"]
    assert "2026-07-20" in payload["justification_couverture"]
    # Serie sol de fondation, machine-lisible (migration 103).
    assert payload["serie_sol"] == "gin_kankan_ghi_esmap_wapp_2021_2023"


def test_ti122_listing_des_referentiels_publies(
    client: TestClient, headers_auth: dict[str, str]
) -> None:
    """GET /v1/calage : l'endpoint de decouverte des consommateurs.

    Une entree par referentiel : station, grandeur, serie sol de
    fondation, domaine de couverture. Ajouter une station = publier
    son referentiel, aucun changement cote consommateurs (genericite
    pays, residu 3).
    """
    r = client.get("/v1/calage", headers=headers_auth)
    assert r.status_code == 200
    payload = r.json()
    assert payload["total"] == 1
    referentiel = payload["items"][0]
    assert referentiel["code"] == "gin_kankan_ghi_calage_saisonnier"
    assert referentiel["localite"] == "gin_kankan"
    assert referentiel["grandeur"] == "ghi"
    assert referentiel["serie_sol"] == "gin_kankan_ghi_esmap_wapp_2021_2023"
    assert referentiel["localites_couvertes"] == [
        "gin_kankan",
        "gin_kerouane",
        "gin_kouroussa",
        "gin_mandiana",
        "gin_siguiri",
    ]


def test_ti123_listing_sans_auth_rejete(client: TestClient) -> None:
    """GET /v1/calage sans auth : 401."""
    r = client.get("/v1/calage")
    assert r.status_code == 401


def test_ti115_calage_absent_erreur_honnete(
    client: TestClient, headers_auth: dict[str, str]
) -> None:
    """Couple sans referentiel publie : 404 RESSOURCE_INTROUVABLE."""
    r = client.get("/v1/calage/gin_kindia/ghi", headers=headers_auth)
    assert r.status_code == 404
    assert r.json()["erreur"]["code"] == CodeErreur.RESSOURCE_INTROUVABLE.value
