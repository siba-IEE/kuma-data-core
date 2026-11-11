"""Point d'entrée de l'API : ``creer_application()`` et l'instance ``app`` pour ``uvicorn``.

.. code-block:: bash

    uv run uvicorn kuma_data_core.api.main:app --reload --host 127.0.0.1 --port 8000

Chaque requête est journalisée (``methode``, ``chemin``, ``statut``,
``duree_ms``).
"""

from __future__ import annotations

import time
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware

from kuma_data_core.api.erreurs import (
    ExceptionKuma,
    handler_exception_generique,
    handler_exception_kuma,
    handler_validation_requete,
)
from kuma_data_core.api.v1.routeur import routeur_v1
from kuma_data_core.core.config import get_settings
from kuma_data_core.core.logging import configurer_logging, obtenir_logger


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Configure la journalisation au démarrage et trace ``api_demarrage`` / ``api_arret``."""
    configurer_logging()
    settings = get_settings()
    log = obtenir_logger("kuma.api.lifespan")
    log.info(
        "api_demarrage",
        environnement=settings.api_environnement,
        version=settings.api_version,
    )
    yield
    log.info("api_arret")


def creer_application() -> FastAPI:
    """Construit l'application FastAPI selon la configuration courante.

    La documentation OpenAPI n'est servie que si ``Settings.api_docs_actives``
    (interdit en production par le validateur de configuration).
    """
    settings = get_settings()

    docs_url = "/docs" if settings.api_docs_actives else None
    redoc_url = "/redoc" if settings.api_docs_actives else None
    openapi_url = "/openapi.json" if settings.api_docs_actives else None

    app = FastAPI(
        title=settings.api_titre,
        version=settings.api_version,
        docs_url=docs_url,
        redoc_url=redoc_url,
        openapi_url=openapi_url,
        lifespan=lifespan,
    )
    # La console web envoie ses requêtes depuis le navigateur avec la clé de
    # l'utilisateur : POST pour l'émission de clé, GET pour tout le reste.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origines,
        # Authentification par jeton Bearer, sans cookie de session : rien à
        # transmettre entre origines, donc pas d'en-tête Allow-Credentials.
        allow_credentials=False,
        allow_methods=["GET", "POST"],
        allow_headers=["Authorization", "Content-Type"],
    )
    app.add_exception_handler(ExceptionKuma, handler_exception_kuma)
    app.add_exception_handler(RequestValidationError, handler_validation_requete)
    app.add_exception_handler(Exception, handler_exception_generique)

    @app.middleware("http")
    async def journaliser_requete(
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        log = obtenir_logger("kuma.api.requete")
        debut = time.perf_counter()
        response = await call_next(request)
        duree_ms = (time.perf_counter() - debut) * 1000
        log.info(
            "requete_traitee",
            methode=request.method,
            chemin=request.url.path,
            statut=response.status_code,
            duree_ms=round(duree_ms, 2),
        )
        return response

    app.include_router(routeur_v1)

    return app


app = creer_application()
