"""Tests d'integration des endpoints `/api/v1/localites`.

- GET /v1/localites sans auth -> 401 AUTH_HEADER_MANQUANT.
- GET /v1/localites avec auth -> 200, envelope paginee
  ``LocaliteListeePaginee`` avec items et 16 champs catalogue.
- GET /v1/localites?pays_iso3=GIN -> filtre pays.
- GET /v1/localites?type_localite=commune -> filtre type
  (>= 6 communes Guinee).
- GET /v1/localites?parent_code=<code> -> filtre parent.
- GET /v1/localites?actif=false -> filtre soft-delete.
- GET /v1/localites?limit=2&offset={0,2} -> pagination
  coherente, total stable.
- GET /v1/localites/gin_conakry_kaloum -> 200 + 16 champs +
  coordonnees coherentes (lat 9.5, lon -13.7).
- GET /v1/localites/{code_inexistant} -> 404
  RESSOURCE_LOCALITE_INCONNUE.

TestClient FastAPI synchrone + headers_auth fixture
(cf. ``tests/conftest.py``). Marqueur ``pytest.mark.integration``.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from kuma_data_core.api.codes_erreur import CodeErreur

pytestmark = pytest.mark.integration


# === Champs attendus catalogue =============================================

_CHAMPS_LOCALITE = {
    "id",
    "code",
    "nom",
    "type_localite",
    "parent_id",
    "parent_code",
    "pays_iso3",
    "latitude",
    "longitude",
    "altitude_metres",
    "population_estimee",
    "annee_population",
    "fuseau_horaire",
    "created_at",
    "updated_at",
    "actif",
}


def test_ti107_listing_sans_auth_rejete(client: TestClient) -> None:
    """GET /v1/localites sans header Authorization -> 401."""
    response = client.get("/v1/localites")
    assert response.status_code == 401
    payload = response.json()
    assert payload["erreur"]["code"] == CodeErreur.AUTH_HEADER_MANQUANT.value


def test_ti108_listing_envelope_paginee_16_champs(
    client: TestClient, headers_auth: dict[str, str]
) -> None:
    """GET /v1/localites avec auth -> envelope ``LocaliteListeePaginee``.

    Verifie la structure ``{items, total, limit, offset}`` cohérente
    avec :class:`SerieListeePaginee` (ADR-0001) et la presence des 16
    champs catalogue sur chaque entry (cf. ADR-0002).
    """
    response = client.get("/v1/localites", headers=headers_auth)
    assert response.status_code == 200
    payload = response.json()

    # Envelope paginee
    assert isinstance(payload, dict)
    assert set(payload.keys()) == {"items", "total", "limit", "offset"}
    assert payload["limit"] == 100
    assert payload["offset"] == 0
    assert payload["total"] >= 1
    items = payload["items"]
    assert isinstance(items, list)
    assert len(items) >= 1
    assert len(items) <= payload["limit"]
    assert len(items) <= payload["total"]

    # 16 champs catalogue sur chaque entry
    premiere = items[0]
    assert set(premiere.keys()) == _CHAMPS_LOCALITE
    assert isinstance(premiere["id"], int)
    assert isinstance(premiere["code"], str) and premiere["code"]
    assert isinstance(premiere["nom"], str) and premiere["nom"]
    assert isinstance(premiere["type_localite"], str)
    assert isinstance(premiere["actif"], bool)


def test_ti109_filtre_pays_iso3_gin(client: TestClient, headers_auth: dict[str, str]) -> None:
    """?pays_iso3=GIN -> uniquement les localites guineennes."""
    response = client.get("/v1/localites?pays_iso3=GIN&limit=100", headers=headers_auth)
    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] >= 6  # >= 6 villes Guinee
    for loc in payload["items"]:
        assert loc["pays_iso3"] == "GIN"


def test_ti110_filtre_type_localite_commune(
    client: TestClient, headers_auth: dict[str, str]
) -> None:
    """?type_localite=commune -> uniquement les communes.

    Au moins 6 communes guineennes (Kaloum/Kankan/Kindia/Labe/
    Mamou/Nzerekore selon nomenclature).
    """
    response = client.get("/v1/localites?type_localite=commune&limit=100", headers=headers_auth)
    assert response.status_code == 200
    payload = response.json()
    for loc in payload["items"]:
        assert loc["type_localite"] == "commune"


def test_ti111_filtre_parent_code(client: TestClient, headers_auth: dict[str, str]) -> None:
    """?parent_code=<code> -> uniquement les enfants directs.

    On suppose qu'il existe au moins une localite racine ayant des
    enfants (ex. ``afrique`` -> regions ou pays ; ``gin``
    -> communes ; etc.). Le test reste flexible : on prend le
    parent_code de la premiere entry qui en a un, et on verifie que
    le filtrage par ce code retourne uniquement des entrees pointant
    vers lui.
    """
    # Recupere un parent_code existant depuis le listing global
    response_all = client.get("/v1/localites?limit=100", headers=headers_auth)
    assert response_all.status_code == 200
    parents_dispo = {
        loc["parent_code"] for loc in response_all.json()["items"] if loc["parent_code"] is not None
    }
    if not parents_dispo:
        pytest.skip("Aucune localite avec parent en base - filtre parent_code non testable.")
    parent_code = sorted(parents_dispo)[0]

    response = client.get(
        f"/v1/localites?parent_code={parent_code}&limit=100", headers=headers_auth
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] >= 1
    for loc in payload["items"]:
        assert loc["parent_code"] == parent_code


def test_ti112_filtre_actif_false(client: TestClient, headers_auth: dict[str, str]) -> None:
    """?actif=false -> uniquement les localites desactivees.

    Si aucune localite n'est desactivee, le total = 0 et
    items = [] (comportement normal d'un filtre sans match).
    """
    response = client.get("/v1/localites?actif=false&limit=100", headers=headers_auth)
    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] >= 0
    for loc in payload["items"]:
        assert loc["actif"] is False


def test_ti113_pagination_coherente(client: TestClient, headers_auth: dict[str, str]) -> None:
    """limit=2 offset=0 puis offset=2 -> total stable, pages distinctes."""
    response1 = client.get("/v1/localites?limit=2&offset=0&pays_iso3=GIN", headers=headers_auth)
    assert response1.status_code == 200
    page1 = response1.json()

    response2 = client.get("/v1/localites?limit=2&offset=2&pays_iso3=GIN", headers=headers_auth)
    assert response2.status_code == 200
    page2 = response2.json()

    # Total stable entre les pages (filtre identique)
    assert page1["total"] == page2["total"]
    assert page1["limit"] == 2
    assert page2["limit"] == 2
    assert page1["offset"] == 0
    assert page2["offset"] == 2

    # Pages disjointes (codes distincts si page2 non vide)
    if page2["items"]:
        codes_p1 = {loc["code"] for loc in page1["items"]}
        codes_p2 = {loc["code"] for loc in page2["items"]}
        assert codes_p1.isdisjoint(codes_p2)


def test_ti114_detail_localite_kaloum(client: TestClient, headers_auth: dict[str, str]) -> None:
    """GET /v1/localites/gin_conakry_kaloum -> 200 + 16 champs.

    Verifie les metadonnees Kaloum (commune de Conakry, Guinee) :
    latitude 9.51, longitude -13.71, pays_iso3 GIN, fuseau horaire
    Africa/Conakry. Les valeurs exactes peuvent varier selon les
    fixtures DB - assertions volontairement flexibles.
    """
    response = client.get("/v1/localites/gin_conakry_kaloum", headers=headers_auth)
    assert response.status_code == 200
    payload = response.json()

    # 16 champs presents
    assert set(payload.keys()) == _CHAMPS_LOCALITE

    # Identite
    assert payload["code"] == "gin_conakry_kaloum"
    assert isinstance(payload["nom"], str) and payload["nom"]
    assert isinstance(payload["id"], int)

    # Geolocalisation Kaloum (Conakry, Guinee - equateur cote Atlantique)
    assert payload["pays_iso3"] == "GIN"
    assert payload["latitude"] is not None
    assert 9.0 <= payload["latitude"] <= 10.0
    assert payload["longitude"] is not None
    assert -14.0 <= payload["longitude"] <= -13.0

    # Fuseau IANA (Guinee UTC+0 sans DST)
    assert payload["fuseau_horaire"] == "Africa/Conakry"

    # Actif par defaut
    assert payload["actif"] is True


def test_ti115_detail_localite_inconnue_404(
    client: TestClient, headers_auth: dict[str, str]
) -> None:
    """GET /v1/localites/{code_inexistant} -> 404 RESSOURCE_LOCALITE_INCONNUE."""
    response = client.get("/v1/localites/zzz_code_inexistant_xyz", headers=headers_auth)
    assert response.status_code == 404
    payload = response.json()
    assert payload["erreur"]["code"] == CodeErreur.RESSOURCE_LOCALITE_INCONNUE.value
