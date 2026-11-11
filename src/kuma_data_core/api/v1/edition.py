"""Route ``GET /v1/edition`` : fraîcheur affichée (ADR-0003).

Le retard de l'édition publiée sur la base de référence est assumé,
donc affiché : « un retard documenté est une propriété, un retard
silencieux est un défaut ». L'endpoint est **non authentifié** (même
statut public que ``/v1/health``) : la date des données est une
information de confiance, pas une donnée à protéger.

La table ``edition_metadonnees`` n'existe que dans une édition publiée
(elle est injectée par le script d'export, hors schéma de référence et
hors lignée Alembic). Sur un déploiement qui ne sert pas une édition -
typiquement une base de développement - l'endpoint renvoie 404
``RESSOURCE_INTROUVABLE`` : c'est l'état normal du régime local.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from kuma_data_core.api.codes_erreur import CodeErreur
from kuma_data_core.api.erreurs import ExceptionKuma
from kuma_data_core.api.v1.schemas.edition import CouvertureResumee, ReponseEdition
from kuma_data_core.db.session import obtenir_session
from kuma_data_core.lecture.edition import lire_edition
from kuma_data_core.lecture.localites import compter_localites_actives
from kuma_data_core.lecture.series import compter_series_actives

routeur = APIRouter(prefix="/edition", tags=["edition"])


@routeur.get(
    "",
    response_model=ReponseEdition,
    status_code=status.HTTP_200_OK,
    summary="Édition publiée servie par ce déploiement",
    description=(
        "Endpoint non authentifié exposant l'identifiant daté de "
        "l'édition, sa date de publication, la révision git source et "
        "une volumétrie sommaire. Renvoie 404 si le déploiement ne sert "
        "pas une édition publiée (base de développement)."
    ),
)
def edition_courante(
    session: Annotated[Session, Depends(obtenir_session)],
) -> ReponseEdition:
    """Métadonnées de l'édition servie ; 404 si le déploiement n'en sert pas."""
    edition = lire_edition(session)
    if edition is None:
        raise ExceptionKuma(
            code=CodeErreur.RESSOURCE_INTROUVABLE,
            message="Ce deploiement ne sert pas une edition publiee.",
            statut_http=status.HTTP_404_NOT_FOUND,
            details={"raison": "table edition_metadonnees absente ou vide"},
        )
    return ReponseEdition(
        edition_id=edition.edition_id,
        date_publication=edition.date_publication,
        revision_source=edition.revision_source,
        couverture_resumee=CouvertureResumee(
            localites=compter_localites_actives(session),
            series=compter_series_actives(session),
        ),
    )
