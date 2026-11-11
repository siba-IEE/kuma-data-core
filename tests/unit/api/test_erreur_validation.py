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
