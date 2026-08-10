"""Tests d'integration des endpoints `/api/v1/series`.

- GET /v1/series sans auth -> 401 AUTH_HEADER_MANQUANT.
- GET /v1/series avec auth -> 200, listing des series (default limit=100).
- GET /v1/series?source=kuma_calculs -> series calculees.
- GET /v1/series?localite=gin_kindia -> series Kindia uniquement.
- GET /v1/series/{code} avec code inexistant -> 404 RESSOURCE_SERIE_INCONNUE.
- GET /v1/series/{code} sur serie brute journalier -> 200 + mesures
  type='journalier'.
- GET /v1/series/{code} sur serie SARAH-3 mensuel -> 200 + mesures
  type='mensuel'.
- GET /v1/series/{code}?format=csv -> 200 text/csv.

TestClient FastAPI synchrone + headers_auth fixture.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from kuma_data_core.api.codes_erreur import CodeErreur

pytestmark = pytest.mark.integration


def test_ti61_listing_sans_auth_rejete(client: TestClient) -> None:
    """GET /v1/series sans header Authorization -> 401."""
    response = client.get("/v1/series")
    assert response.status_code == 401
    payload = response.json()
    assert payload["erreur"]["code"] == CodeErreur.AUTH_HEADER_MANQUANT.value


def test_validation_parametre_invalide_format_erreur_kuma(
    client: TestClient, headers_auth: dict[str, str]
) -> None:
    """Parametre invalide (limit hors bornes) -> 422 au format ErreurKuma.

    Verifie que les erreurs de validation FastAPI passent par le handler
    ``RequestValidationError`` et suivent le contrat ``ErreurKuma``, et non
    le format FastAPI par defaut ``{"detail": [...]}``.
    """
    response = client.get("/v1/series?limit=0", headers=headers_auth)
    assert response.status_code == 422
    payload = response.json()
    assert "detail" not in payload
    assert payload["erreur"]["code"] == CodeErreur.VALIDATION_VALEUR_INVALIDE.value


def test_ti62_listing_avec_auth_retourne_series(
    client: TestClient, headers_auth: dict[str, str]
) -> None:
    """GET /v1/series avec auth -> 200 + envelope paginee SerieListeePaginee.

    Default limit=100 et filtre actif=TRUE par defaut -> envelope avec
    items au max 100 series actives + total reflet du compte filtre.
    Envelope ``{items, total, limit, offset}`` (cf. ADR-0001
    Data Core contrat /v1/series enrichi).

    Verifie aussi la presence des 18 champs catalogue enrichi sur chaque
    entry : id, libelle, localite_*, grandeur_*, source_*, periode_*,
    notes_fr, created_at, updated_at, actif (catalog B.1 de l'audit).
    """
    response = client.get("/v1/series", headers=headers_auth)
    assert response.status_code == 200
    payload = response.json()

    # === Envelope paginee ====================================================
    assert isinstance(payload, dict)
    assert set(payload.keys()) == {"items", "total", "limit", "offset"}
    items = payload["items"]
    assert isinstance(items, list)
    assert payload["limit"] == 100
    assert payload["offset"] == 0
    assert payload["total"] >= 1
    assert len(items) <= payload["limit"]
    assert len(items) <= payload["total"]

    # === Champs catalogue enrichi (18 champs) =================================
    # Serie temoin connue : recuperee par filtre localite (robuste a la pagination ;
    # le catalogue depasse une page apres la densification, et Conakry porte
    # aussi les series mensuelles longues du lot profondeur -> fenetre 60).
    temoin = client.get(
        "/v1/series?localite=gin_conakry_kaloum&limit=60", headers=headers_auth
    ).json()
    assert any(s["code"] == "gin_conakry_ghi_nasa_power_2021_2025" for s in temoin["items"])
    premier = items[0]
    champs_attendus = {
        "id",
        "code",
        "libelle",
        "localite_id",
        "localite_code",
        "localite_nom",
        "localite_iso3",
        "grandeur_code",
        "grandeur_label",
        "grandeur_unit",
        "source_id",
        "source_code",
        "source_label",
        "source_url",
        "periode_debut",
        "periode_fin",
        "methode_collecte",
        "notes_fr",
        "created_at",
        "updated_at",
        "actif",
    }
    assert set(premier.keys()) == champs_attendus
    # Types strictes sur les champs critiques
    assert isinstance(premier["id"], int)
    assert isinstance(premier["localite_id"], int)
    assert isinstance(premier["source_id"], int)
    assert isinstance(premier["localite_nom"], str) and premier["localite_nom"]
    assert isinstance(premier["grandeur_label"], str) and premier["grandeur_label"]
    assert isinstance(premier["grandeur_unit"], str) and premier["grandeur_unit"]
    assert isinstance(premier["source_label"], str) and premier["source_label"]


def test_ti63_filtre_source_kuma_calculs(client: TestClient, headers_auth: dict[str, str]) -> None:
    """?source=kuma_calculs -> series calculees Kuma dans l'envelope.

    Decompte cumule :
    - 48 series sur la fenetre recente 2021-2025 (hep,
      productible_specifique_theorique, fraction_diffuse, humidex,
      variabilite_journaliere, indicateur_qualite_donnees, plus
      ecart_relatif_referentiel + rang_referentiel_temporel +
      rang_referentiel_spatial).
    - 18 series climato (hep 1991-2020,
      productible_specifique_theorique 1991-2020, fraction_diffuse
      2001-2020, x 6 villes, migration 051).
    - 6 series ecart_relatif_dni_cams (migration 072,
      kuma_calculs 2004-2020). Sous-total : 66 + 6 = 72.
    - 62 series calculees atlas (migration 091 : 28 ecart_relatif_referentiel
      communes + 34 ecart_relatif_dni_cams recent 2021-2023). Sous-total : 72 + 62 = 134.
    - 168 series calculees (migration 092 : hep/psp/fd climato+recent aux
      28 communes, 6 series/commune). Total : 134 + 168 = 302.
    - 84 series calculees (migration 093 : humidex + variabilite_journaliere
      + rang_referentiel_temporel aux 28 communes, fenetre recente, 3 series/commune ;
      l'indicateur ne cree pas de serie). Total : 302 + 84 = 386.
    """
    response = client.get(
        "/v1/series?source=kuma_calculs&limit=400",
        headers=headers_auth,
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == 386
    items = payload["items"]
    assert len(items) == 386
    for s in items:
        assert s["source_code"] == "kuma_calculs"


def test_ti64_filtre_localite(client: TestClient, headers_auth: dict[str, str]) -> None:
    """?localite=gin_kindia -> series Kindia uniquement dans l'envelope.

    Kindia a au moins : 5 brutes NASA POWER daily + 1 kt + 1 NASA POWER 1991-2020
    + 1 SARAH-3 + 5 grandeurs Kuma calculs + 3 grandeurs derivees + 6 horaires
    pleine profondeur 2001-2025 + 3 horaires vents/precipitation = 25 series. L'assertion reste
    en >= (le seed horaire est inconditionnel, l'ingestion de masse est gardee).
    """
    response = client.get(
        "/v1/series?localite=gin_kindia&limit=100",
        headers=headers_auth,
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] >= 10
    items = payload["items"]
    assert len(items) >= 10
    for s in items:
        assert s["localite_code"] == "gin_kindia"
        # Localite_nom doit etre coherent avec le code (denormalisation)
        assert s["localite_nom"] != ""


def test_ti65_detail_serie_inconnue_404(client: TestClient, headers_auth: dict[str, str]) -> None:
    """GET /v1/series/{code_inexistant} -> 404 RESSOURCE_SERIE_INCONNUE."""
    response = client.get(
        "/v1/series/code_inexistant_xyz",
        headers=headers_auth,
    )
    assert response.status_code == 404
    payload = response.json()
    assert payload["erreur"]["code"] == CodeErreur.RESSOURCE_SERIE_INCONNUE.value


def test_ti66_detail_serie_brute_journalier(
    client: TestClient, headers_auth: dict[str, str]
) -> None:
    """GET /v1/series/{code} sur serie NASA POWER daily 2021-2025
    -> 200 + 18 champs catalogue enrichi + unite_code + mesures type='journalier'.

    ADR-0001 : le detail herite des 18 champs de SerieListee
    + unite_code + mesures. Verifie que les denormalisations
    grandeur/source/localite sont bien projetees.
    """
    response = client.get(
        "/v1/series/gin_kindia_ghi_nasa_power_2021_2025?limit=10",
        headers=headers_auth,
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["code"] == "gin_kindia_ghi_nasa_power_2021_2025"
    assert payload["source_code"] == "nasa_power"
    assert payload["grandeur_code"] == "ghi"

    # Champs catalogue enrichi
    assert isinstance(payload["id"], int)
    assert payload["localite_code"] == "gin_kindia"
    assert payload["localite_iso3"] == "GIN"
    assert payload["grandeur_label"] != ""
    assert payload["grandeur_unit"] != ""
    assert payload["source_label"] != ""
    # source_url peut etre None ou un URL ; on accepte les deux
    assert payload["source_url"] is None or isinstance(payload["source_url"], str)
    assert "created_at" in payload
    assert "updated_at" in payload

    # Champs specifiques detail
    assert "unite_code" in payload
    assert len(payload["mesures"]) == 10
    for m in payload["mesures"]:
        assert m["type"] == "journalier"
        assert "instant_mesure" in m


def test_ti67_detail_serie_sarah3_mensuel(client: TestClient, headers_auth: dict[str, str]) -> None:
    """GET /v1/series/{code} sur serie SARAH-3 ICDR -> 200 + mesures
    type='mensuel'."""
    response = client.get(
        "/v1/series/gin_conakry_ghi_sarah3_2021_2023?limit=12",
        headers=headers_auth,
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["code"] == "gin_conakry_ghi_sarah3_2021_2023"
    assert payload["source_code"] == "sarah3_monthly"
    assert len(payload["mesures"]) == 12  # 12 mois 2021
    for m in payload["mesures"]:
        assert m["type"] == "mensuel"
        assert "annee" in m
        assert "mois" in m


def test_ti68_detail_format_csv(client: TestClient, headers_auth: dict[str, str]) -> None:
    """GET /v1/series/{code}?format=csv -> 200 text/csv."""
    response = client.get(
        "/v1/series/gin_kindia_ghi_nasa_power_2021_2025?format=csv&limit=5",
        headers=headers_auth,
    )
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/csv")
    body = response.text
    assert "code_serie" in body  # Header CSV
    assert "gin_kindia_ghi_nasa_power_2021_2025" in body
    # 5 lignes de mesures + 1 header
    assert body.strip().count("\n") == 5
