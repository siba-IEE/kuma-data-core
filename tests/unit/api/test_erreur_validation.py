"""Une erreur de validation ne renvoie jamais l'entrée fautive au client."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from kuma_data_core.api.main import app

pytestmark = pytest.mark.unit


def test_422_sans_echo_de_l_entree() -> None:
    marqueur = "x" * 5000
    reponse = TestClient(app).post("/v1/cles", json={"email": marqueur, "inconnu": marqueur})
    assert reponse.status_code == 422
    assert marqueur not in reponse.text
    erreurs = reponse.json()["erreur"]["details"]["erreurs"]
    assert erreurs
    assert all(set(erreur) <= {"type", "loc", "msg"} for erreur in erreurs)


def test_periode_inversee_rend_422_et_non_500(cle_solar_valide: str) -> None:
    reponse = TestClient(app, raise_server_exceptions=False).get(
        "/v1/grandeurs/poa_parametrable",
        params={
            "code_serie_source": "x",
            "periode_debut": "2022-02-01",
            "periode_fin": "2022-01-01",
            "inclinaison_deg": 10,
            "orientation_deg": 180,
        },
        headers={"Authorization": f"Bearer {cle_solar_valide}"},
    )
    assert reponse.status_code == 422
    assert reponse.json()["erreur"]["code"] == "VALIDATION_VALEUR_INVALIDE"
