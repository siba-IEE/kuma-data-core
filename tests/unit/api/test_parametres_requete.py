"""Dépendance ``parametres_requete`` : contrainte entre champs en 422, OpenAPI inchangé."""

from __future__ import annotations

from typing import Any

import pytest
from fastapi import Depends, FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.testclient import TestClient
from pydantic import BaseModel, Field, model_validator

from kuma_data_core.api.dependencies import parametres_requete
from kuma_data_core.api.erreurs import handler_validation_requete

pytestmark = pytest.mark.unit


class _Fenetre(BaseModel):
    debut: int = Field(..., ge=0, description="Début.")
    fin: int
    format_sortie: str = Field("json", alias="format")

    @model_validator(mode="after")
    def _ordonnee(self) -> _Fenetre:
        if self.fin < self.debut:
            raise ValueError("fin avant debut")
        return self


def _application(dependance: Any) -> FastAPI:
    app = FastAPI()
    app.add_exception_handler(RequestValidationError, handler_validation_requete)

    @app.get("/f/{debut}")
    def route(params: _Fenetre = dependance) -> dict[str, object]:
        return params.model_dump(by_alias=True)

    return app


def test_contrainte_entre_champs_en_422() -> None:
    client = TestClient(_application(Depends(parametres_requete(_Fenetre))))
    reponse = client.get("/f/5", params={"fin": 1})
    assert reponse.status_code == 422
    [detail] = reponse.json()["erreur"]["details"]["erreurs"]
    assert detail["loc"] == ["query"]
    assert detail["msg"] == "Value error, fin avant debut"


def test_valeurs_valides_et_alias_transmis() -> None:
    client = TestClient(_application(Depends(parametres_requete(_Fenetre))))
    reponse = client.get("/f/1", params={"fin": 5, "format": "csv"})
    assert reponse.status_code == 200
    assert reponse.json() == {"debut": 1, "fin": 5, "format": "csv"}


def test_openapi_identique_a_depends_du_modele() -> None:
    avec_modele = _application(Depends()).openapi()
    avec_dependance = _application(Depends(parametres_requete(_Fenetre))).openapi()
    assert avec_dependance == avec_modele
