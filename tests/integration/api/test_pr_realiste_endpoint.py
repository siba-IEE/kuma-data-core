"""Tests d'integration de l'endpoint ``/v1/grandeurs/pr_realiste``.

PR realiste = PR_fourni x ratio_T x (1 - salissure) selon le mode. Source = serie
GHI. Couvre : auth, succes par mode, **divergence de fenetre par mode** (preuve de la
resolution bi-source : un mode salissure borne a 2025-08-31 par les PM EAC4, un mode
sans salissure va plus loin), saisonnalite Harmattan (mensuel), et les rejets.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from kuma_data_core.api.codes_erreur import CodeErreur

pytestmark = pytest.mark.integration

_BASE = "/v1/grandeurs/pr_realiste"
_SERIE_GHI_CONAKRY = "gin_conakry_ghi_nasa_power_2021_2025"
_SERIE_PM25_CONAKRY = "gin_conakry_pm2_5_cams_eac4_2021_2025"
_SERIE_INCONNUE = "serie_inexistante_xxx"
_PR = "0.80"
_NOCT = "45"
_COEFF = "-0.4"


def _params(correction: str, thermique: bool = True) -> dict[str, str]:
    p = {"pr_fourni": _PR, "correction": correction}
    if thermique:
        p |= {"noct_degc": _NOCT, "coeff_temp_pourcent_par_degc": _COEFF}
    return p


def test_pr_realiste_sans_auth_rejete(client: TestClient) -> None:
    response = client.get(
        f"{_BASE}/{_SERIE_GHI_CONAKRY}", params=_params("aucune", thermique=False)
    )
    assert response.status_code == 401


def test_pr_realiste_aucune_echo(client: TestClient, headers_auth: dict[str, str]) -> None:
    """Mode 'aucune' -> pr_realiste == PR_fourni ; fenetre GHI (au-dela de la salissure)."""
    response = client.get(
        f"{_BASE}/{_SERIE_GHI_CONAKRY}",
        params=_params("aucune", thermique=False),
        headers=headers_auth,
    )
    assert response.status_code == 200
    p = response.json()
    assert p["code_grandeur"] == "pr_realiste"
    assert p["correction"] == "aucune"
    assert all(abs(m["pr_realiste"] - 0.80) < 1e-9 for m in p["mesures_journalier"])
    # Fenetre GHI : va plus loin que l'overlap PM (2025-08-31), pas borne par la salissure.
    assert p["periode"].split("/")[1] > "2025-08-31"


def test_pr_realiste_temperature_salissure_fenetre_pm(
    client: TestClient, headers_auth: dict[str, str]
) -> None:
    """Mode complet -> fenetre bornee a l'overlap PM EAC4 (2021-01-01/2025-08-31) :
    preuve que PM (cross-source) + pluie ont ete resolues et intersectees."""
    response = client.get(
        f"{_BASE}/{_SERIE_GHI_CONAKRY}",
        params=_params("temperature_salissure"),
        headers=headers_auth,
    )
    assert response.status_code == 200
    p = response.json()
    assert p["periode"] == "2021-01-01/2025-08-31"
    assert p["correction"] == "temperature_salissure"
    assert len(p["mesures_journalier"]) == 1704
    assert len(p["mesures_mensuel"]) > 0
    for m in p["mesures_journalier"]:
        assert 0.0 <= m["pr_realiste"] <= 1.0
        assert m["niveau_confiance"] == "B"
    assert "PR-reference" in p["limite"]
    assert "L-TR-6" in p["limite"]  # caveat thermique optimiste
    assert "spin-up" in p["limite"]  # caveat salissure


def test_pr_realiste_saisonnalite_harmattan(
    client: TestClient, headers_auth: dict[str, str]
) -> None:
    """Mensuel : le PR plonge en saison seche Harmattan (Dec-Fev) vs mousson (Jul-Sep)."""
    response = client.get(
        f"{_BASE}/{_SERIE_GHI_CONAKRY}",
        params=_params("temperature_salissure"),
        headers=headers_auth,
    )
    assert response.status_code == 200
    mensuel = response.json()["mesures_mensuel"]
    seche = [m["pr_realiste"] for m in mensuel if m["instant"][5:7] in ("12", "01", "02")]
    mousson = [m["pr_realiste"] for m in mensuel if m["instant"][5:7] in ("07", "08", "09")]
    assert seche and mousson
    assert sum(seche) / len(seche) < sum(mousson) / len(mousson), (
        "creux Harmattan attendu : PR Dec-Fev < PR Jul-Sep"
    )


def test_pr_realiste_grandeur_incompatible_rejete(
    client: TestClient, headers_auth: dict[str, str]
) -> None:
    """Serie source non-GHI (PM2.5) -> 400 INCOMPATIBILITE_SOURCE_GRANDEUR."""
    response = client.get(
        f"{_BASE}/{_SERIE_PM25_CONAKRY}",
        params=_params("aucune", thermique=False),
        headers=headers_auth,
    )
    assert response.status_code == 400
    assert response.json()["erreur"]["code"] == CodeErreur.INCOMPATIBILITE_SOURCE_GRANDEUR.value


def test_pr_realiste_thermique_sans_noct_rejete(
    client: TestClient, headers_auth: dict[str, str]
) -> None:
    """Mode thermique sans noct/coeff -> 422 (validation Pydantic)."""
    response = client.get(
        f"{_BASE}/{_SERIE_GHI_CONAKRY}",
        params={"pr_fourni": _PR, "correction": "temperature"},
        headers=headers_auth,
    )
    assert response.status_code == 422


def test_pr_realiste_serie_inconnue(client: TestClient, headers_auth: dict[str, str]) -> None:
    """Serie source inconnue -> 404."""
    response = client.get(
        f"{_BASE}/{_SERIE_INCONNUE}",
        params=_params("aucune", thermique=False),
        headers=headers_auth,
    )
    assert response.status_code == 404
