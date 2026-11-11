"""Format d'erreur de l'API et handlers associés.

Toute erreur suit la structure ``ErreurKuma`` :

.. code-block:: json

   {
     "erreur": {
       "code": "AUTH_CLE_INVALIDE",
       "message": "Clé API invalide ou révoquée.",
       "details": null
     }
   }

``code`` est un identifiant stable (``codes_erreur.CodeErreur``), ``message``
un texte français pour un humain, ``details`` des informations structurées
facultatives.
"""

from __future__ import annotations

from typing import Any

from fastapi import Request, status
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from kuma_data_core.api.codes_erreur import CodeErreur
from kuma_data_core.core.logging import obtenir_logger


class DetailErreur(BaseModel):
    """Détail d'une erreur Kuma."""

    code: CodeErreur = Field(description="Code stable de l'erreur")
    message: str = Field(description="Message lisible en français")
    details: dict[str, Any] | None = Field(
        default=None,
        description="Informations supplémentaires structurées",
    )


class ErreurKuma(BaseModel):
    """Réponse d'erreur standardisée."""

    erreur: DetailErreur


class ExceptionKuma(Exception):
    """Erreur applicative (code, message, statut HTTP) rendue par ``handler_exception_kuma``."""

    def __init__(
        self,
        code: CodeErreur,
        message: str,
        statut_http: int,
        details: dict[str, Any] | None = None,
    ) -> None:
        self.code = code
        self.message = message
        self.statut_http = statut_http
        self.details = details
        super().__init__(message)


async def handler_exception_kuma(request: Request, exc: Exception) -> JSONResponse:
    """Convertit une ``ExceptionKuma`` en réponse JSON.

    ``exc`` est typé ``Exception`` parce que
    ``FastAPI.add_exception_handler`` l'exige.
    """
    assert isinstance(exc, ExceptionKuma)
    erreur = ErreurKuma(
        erreur=DetailErreur(
            code=exc.code,
            message=exc.message,
            details=exc.details,
        )
    )
    return JSONResponse(
        status_code=exc.statut_http,
        content=erreur.model_dump(exclude_none=True),
    )


async def handler_validation_requete(request: Request, exc: Exception) -> JSONResponse:
    """Convertit une erreur de validation d'entrée en réponse ``ErreurKuma``.

    FastAPI lève ``RequestValidationError`` avant d'atteindre le code du
    routeur lorsqu'un paramètre viole son type, ses bornes ou un
    ``model_validator``. Sans ce handler, la réponse sortirait au format
    FastAPI par défaut (``{"detail": [...]}``), hors contrat Kuma.
    """
    # ``input`` et ``ctx`` sont retirés : renvoyer l'entrée fautive doublerait le
    # coût d'un corps volumineux et peut refléter des données non maîtrisées.
    details = (
        jsonable_encoder(
            [
                {cle: erreur[cle] for cle in ("type", "loc", "msg") if cle in erreur}
                for erreur in exc.errors()
            ]
        )
        if isinstance(exc, RequestValidationError)
        else None
    )
    erreur = ErreurKuma(
        erreur=DetailErreur(
            code=CodeErreur.VALIDATION_VALEUR_INVALIDE,
            message="Une ou plusieurs valeurs de la requête sont invalides.",
            details={"erreurs": details} if details is not None else None,
        )
    )
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content=erreur.model_dump(exclude_none=True),
    )


async def handler_exception_generique(request: Request, exc: Exception) -> JSONResponse:
    """Toute exception non gérée devient un 500 au format ``ErreurKuma``.

    Rien du détail technique ne part au client (trace, chemin interne,
    version de dépendance) : la trace complète va dans le journal serveur.
    """
    log = obtenir_logger("kuma.api.erreur_non_geree")
    log.error(
        "exception_non_geree",
        methode=request.method,
        chemin=request.url.path,
        type_exception=type(exc).__name__,
        exc_info=exc,
    )
    erreur = ErreurKuma(
        erreur=DetailErreur(
            code=CodeErreur.SERVEUR_ERREUR_INTERNE,
            message="Une erreur interne est survenue.",
            details=None,
        )
    )
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content=erreur.model_dump(exclude_none=True),
    )
