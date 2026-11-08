"""Endpoint ``GET /v1/edition`` : date de l'édition publiée (ADR-0003).

Non authentifié : le retard sur la base de référence est assumé, donc
affiché. ``edition_metadonnees`` n'existe que dans une édition publiée ;
ailleurs (base de dev), 404 ``RESSOURCE_INTROUVABLE`` est l'état normal.
"""

from __future__ import annotations

from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, status
from sqlalchemy import text
from sqlalchemy.orm import Session

from kuma_data_core.api.codes_erreur import CodeErreur
from kuma_data_core.api.erreurs import ExceptionKuma
from kuma_data_core.api.v1.schemas.edition import CouvertureResumee, ReponseEdition
from kuma_data_core.db.session import obtenir_session

routeur = APIRouter(prefix="/edition", tags=["edition"])


def _lire_edition(session: Session) -> tuple[str, date, str] | None:
    """Lit la ligne unique d'``edition_metadonnees`` si la table existe.

    ``to_regclass`` évite de dépendre d'une exception pour le cas
    « table absente » : ``None`` signifie que ce déploiement ne sert
    pas une édition.
    """
    presente = session.execute(text("SELECT to_regclass('public.edition_metadonnees')")).scalar()
    if presente is None:
        return None
    row = session.execute(
        text(
            """
            SELECT edition_id, date_publication, revision_source
            FROM edition_metadonnees
            LIMIT 1
            """
        )
    ).first()
    if row is None:
        return None
    return str(row.edition_id), row.date_publication, str(row.revision_source)


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
    """Expose les métadonnées de l'édition courante (ADR-0003, D7)."""
    edition = _lire_edition(session)
    if edition is None:
        raise ExceptionKuma(
            code=CodeErreur.RESSOURCE_INTROUVABLE,
            message="Ce deploiement ne sert pas une edition publiee.",
            statut_http=status.HTTP_404_NOT_FOUND,
            details={"raison": "table edition_metadonnees absente ou vide"},
        )
    edition_id, date_publication, revision_source = edition

    localites = session.execute(text("SELECT count(*) FROM localites WHERE actif = TRUE")).scalar()
    series = session.execute(
        text("SELECT count(*) FROM series_metadonnees WHERE actif = TRUE")
    ).scalar()

    return ReponseEdition(
        edition_id=edition_id,
        date_publication=date_publication,
        revision_source=revision_source,
        couverture_resumee=CouvertureResumee(
            localites=int(localites or 0),
            series=int(series or 0),
        ),
    )
