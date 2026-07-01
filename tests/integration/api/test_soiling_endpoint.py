"""Tests d'integration de l'endpoint ``/v1/grandeurs/taux_salissure_proxy``.

Proxy de salissure (modele HSU). Entree = serie PM2.5 (EAC4) ; compagnes PM10
(cams_eac4) + precipitation (nasa_power, resolveur bi-source). Couvre : auth,
succes 200 + structure, et les rejets (grandeur incompatible -> 400, serie
inconnue -> 404).

La ``periode`` retournee (``2021-01-01/2025-08-31``, bornee par les PM) **prouve**
au passage que la pluie ``nasa_power`` a bien ete resolue et intersectee : sans
elle, l'intersection des 3 series serait vide. La resolution bi-source explicite
est verifiee dans ``tests/integration/db/test_vague5_soiling_lot_c.py``.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from kuma_data_core.api.codes_erreur import CodeErreur

pytestmark = pytest.mark.integration

_BASE = "/v1/grandeurs/taux_salissure_proxy"
_SERIE_PM25_CONAKRY = "gin_conakry_pm2_5_cams_eac4_2021_2025"
_SERIE_PM25_BOFFA = "gin_boffa_pm2_5_cams_eac4_2021_2025"  # commune densification
_SERIE_GHI_CONAKRY = "gin_conakry_ghi_nasa_power_2021_2025"
_SERIE_INCONNUE = "serie_inexistante_xxx"


def test_soiling_sans_auth_rejete(client: TestClient) -> None:
    """Sans Bearer -> 401."""
    response = client.get(f"{_BASE}/{_SERIE_PM25_CONAKRY}")
    assert response.status_code == 401


def test_soiling_succes(client: TestClient, headers_auth: dict[str, str]) -> None:
    """Serie PM2.5 Conakry -> 200 ; structure, fenetre PM-bornee, pertes bornees."""
    response = client.get(f"{_BASE}/{_SERIE_PM25_CONAKRY}", headers=headers_auth)
    assert response.status_code == 200
    p = response.json()
    assert p["code_grandeur"] == "taux_salissure_proxy"
    assert p["code_serie_source"] == _SERIE_PM25_CONAKRY
    assert p["code_localite"] == "gin_conakry_kaloum"
    # Fenetre effective = intersection PM ∩ pluie, bornee par les PM (2025-08-31).
    # Sa presence prouve que la pluie nasa_power a ete resolue et intersectee.
    assert p["periode"] == "2021-01-01/2025-08-31"
    assert p["unite"] == "%"
    assert p["surface_tilt_deg"] == 10.0
    assert p["cleaning_threshold_mm"] == 1.0
    assert len(p["mesures"]) == 1704
    for m in p["mesures"]:
        assert 0.0 <= m["perte_pct"] <= 100.0
        assert m["niveau_confiance"] == "B"
    assert "spin-up" in p["limite"]


def test_soiling_deverrouille_densification_boffa(
    client: TestClient, headers_auth: dict[str, str]
) -> None:
    """Deverrouillage densification : une commune SANS
    aucune modif d'endpoint. gin_boffa a desormais PM2.5/PM10 (migration 098) ; le
    proxy resout la compagne PM10 (meme source EAC4) + la pluie nasa_power
    (resolveur data-driven) par localite_id -> 200, fenetre PM-bornee, pertes bornees.
    Prouve que la densification ouvre le soiling aux 28 sans toucher l'API."""
    response = client.get(f"{_BASE}/{_SERIE_PM25_BOFFA}", headers=headers_auth)
    assert response.status_code == 200
    p = response.json()
    assert p["code_grandeur"] == "taux_salissure_proxy"
    assert p["code_serie_source"] == _SERIE_PM25_BOFFA
    assert p["code_localite"] == "gin_boffa"
    # Fenetre effective = intersection PM ∩ pluie, bornee par les PM (2025-08-31).
    # Sa presence prouve que la pluie nasa_power gin_boffa a ete resolue et intersectee.
    assert p["periode"] == "2021-01-01/2025-08-31"
    assert p["unite"] == "%"
    assert len(p["mesures"]) == 1704
    for m in p["mesures"]:
        assert 0.0 <= m["perte_pct"] <= 100.0
        assert m["niveau_confiance"] == "B"


def test_soiling_grandeur_incompatible_rejete(
    client: TestClient, headers_auth: dict[str, str]
) -> None:
    """Serie GHI (pas PM2.5) -> 400 INCOMPATIBILITE_SOURCE_GRANDEUR."""
    response = client.get(f"{_BASE}/{_SERIE_GHI_CONAKRY}", headers=headers_auth)
    assert response.status_code == 400
    assert response.json()["erreur"]["code"] == CodeErreur.INCOMPATIBILITE_SOURCE_GRANDEUR.value


def test_soiling_serie_inconnue(client: TestClient, headers_auth: dict[str, str]) -> None:
    """Serie source inconnue -> 404."""
    response = client.get(f"{_BASE}/{_SERIE_INCONNUE}", headers=headers_auth)
    assert response.status_code == 404
