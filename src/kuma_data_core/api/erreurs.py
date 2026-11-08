"""Format d'erreur ``ErreurKuma`` (``{"erreur": {code, message, details}}``) et ses handlers.

``code`` est stable (``CodeErreur``), ``message`` en français. Une exception
non gérée devient un 500 normalisé, sans fuite de trace côté client.
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
    """Exception interne portant ``(code, message, statut HTTP)``."""

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
    """``ExceptionKuma`` -> réponse JSON normalisée.

    ``exc`` est typée ``Exception`` pour la signature de ``add_exception_handler``.
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
    """``RequestValidationError`` -> ``ErreurKuma`` au lieu du ``{"detail": [...]}`` de FastAPI."""
    details = jsonable_encoder(exc.errors()) if isinstance(exc, RequestValidationError) else None
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
    """Exception non gérée -> 500 normalisé ; la trace part dans les logs, jamais au client."""
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
