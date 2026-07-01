"""Endpoints de santé.

Deux endpoints :

* ``GET /v1/health``    - public, indique que l'API répond.
* ``GET /v1/health/db`` - authentifié, vérifie la connectivité PostgreSQL.

La vérification Redis est volontairement absente : aucun endpoint de
l'API n'utilise encore Redis. Elle sera ajoutée le jour où le cache
devient critique pour un endpoint métier.
"""

from __future__ import annotations

from typing import Annotated, Literal

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.orm import Session

from kuma_data_core.api.codes_erreur import CodeErreur
from kuma_data_core.api.dependencies import CleApiValidee
from kuma_data_core.api.erreurs import ExceptionKuma
from kuma_data_core.core.config import get_settings
from kuma_data_core.db.session import obtenir_session

routeur = APIRouter(prefix="/health", tags=["sante"])


class ReponseSantePublique(BaseModel):
    """Réponse de l'endpoint public ``/v1/health``."""

    statut: Literal["operationnel"]
    version: str
    environnement: str


class StatutComposant(BaseModel):
    """État d'un composant d'infrastructure (base, cache…)."""

    nom: str
    statut: Literal["operationnel", "degrade", "indisponible"]


class ReponseSanteDetailee(BaseModel):
    """Réponse de l'endpoint authentifié ``/v1/health/db``."""

    statut: Literal["operationnel", "degrade", "indisponible"]
    version: str
    environnement: str
    composants: list[StatutComposant]


@routeur.get(
    "",
    response_model=ReponseSantePublique,
    status_code=status.HTTP_200_OK,
    summary="Santé publique de l'API",
    description="Endpoint non authentifié indiquant que l'API répond.",
)
def sante() -> ReponseSantePublique:
    """Réponse minimale, ne touche aucune dépendance externe."""
    settings = get_settings()
    return ReponseSantePublique(
        statut="operationnel",
        version=settings.api_version,
        environnement=settings.api_environnement,
    )


@routeur.get(
    "/db",
    response_model=ReponseSanteDetailee,
    status_code=status.HTTP_200_OK,
    summary="Santé détaillée (base de données)",
    description=(
        "Endpoint authentifié vérifiant la connectivité à la base "
        "PostgreSQL. La vérification Redis sera ajoutée quand un "
        "endpoint en aura besoin."
    ),
)
def sante_detailee(
    _cle: CleApiValidee,
    session: Annotated[Session, Depends(obtenir_session)],
) -> ReponseSanteDetailee:
    """Vérifie l'état de PostgreSQL via un ``SELECT 1``.

    Si la requête échoue, l'endpoint retourne un statut HTTP 503 avec
    le code ``INFRASTRUCTURE_BASE_INDISPONIBLE``. Le détail des
    composants est inclus dans la charge utile de l'erreur pour
    faciliter le diagnostic côté client.
    """
    settings = get_settings()
    composants: list[StatutComposant] = []

    try:
        session.execute(text("SELECT 1"))
        composants.append(StatutComposant(nom="postgresql", statut="operationnel"))
    except Exception as exc:
        composants.append(StatutComposant(nom="postgresql", statut="indisponible"))
        raise ExceptionKuma(
            code=CodeErreur.INFRASTRUCTURE_BASE_INDISPONIBLE,
            message="Base de données injoignable.",
            statut_http=status.HTTP_503_SERVICE_UNAVAILABLE,
            details={"composants": [c.model_dump() for c in composants]},
        ) from exc

    return ReponseSanteDetailee(
        statut="operationnel",
        version=settings.api_version,
        environnement=settings.api_environnement,
        composants=composants,
    )
