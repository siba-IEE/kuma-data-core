"""Endpoints ``/v1/contributions`` - les fiches d'études partagées par SolClim-3.

``POST /v1/contributions/{etude_uid}`` dépose la fiche d'une étude, ou
remplace celle que la même clé avait déposée : le logiciel l'envoie à chaque
enregistrement, sans compter les envois. Il faut une clé porteuse d'une
licence SolClim-3 active, comme pour le bail.

``POST /v1/contributions/{etude_uid}/retrait`` retire la fiche : l'auteur
d'une étude passée en « confidentielle » la reprend. Le retrait ne demande
que la clé, pas la licence, pour rester possible après la fin de celle-ci.

Les deux routes sont en ``POST`` : le CORS de l'API n'ouvre aux navigateurs
que ``GET`` et ``POST``, et le logiciel appelle depuis sa vue web.

La fiche est validée strictement (``schemas.contributions``) : elle ne
porte ni le nom de l'étude, ni le chemin du fichier, ni les coordonnées
exactes d'un point (ADR-0006).
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from fastapi import APIRouter, Response, status
from sqlalchemy.orm import Session

from kuma_data_core.api.codes_erreur import CodeErreur
from kuma_data_core.api.dependencies import CleApiValidee
from kuma_data_core.api.erreurs import ExceptionKuma
from kuma_data_core.api.v1.schemas.contributions import DemandeContribution, ReponseContribution
from kuma_data_core.core.config import get_settings
from kuma_data_core.services import contributions
from kuma_data_core.services.licences import licence_valide_pour_cle

routeur = APIRouter(prefix="/contributions", tags=["contributions"])


def _base_de_service() -> None:
    if get_settings().meta_db is None:
        raise ExceptionKuma(
            code=CodeErreur.CONTRIBUTIONS_NON_ACTIVEES,
            message="La reception des contributions n'est pas activee sur ce deploiement.",
            statut_http=status.HTTP_404_NOT_FOUND,
        )


@routeur.post(
    "/{etude_uid}",
    response_model=ReponseContribution,
    summary="Déposer ou remplacer la fiche d'une étude",
    description=(
        "Dépose la fiche d'une étude SolClim-3, ou remplace celle que la même "
        "clé avait déposée pour cette étude. Réservé aux clés porteuses d'une "
        "licence active. Réponse 201 au premier envoi, 200 ensuite."
    ),
    responses={201: {"model": ReponseContribution, "description": "Fiche créée."}},
)
def deposer(
    etude_uid: UUID,
    demande: DemandeContribution,
    cle: CleApiValidee,
    response: Response,
) -> ReponseContribution:
    """Dépose la fiche de l'étude ``etude_uid``."""
    _base_de_service()
    from kuma_data_core.db.session import get_engine_meta

    maintenant = datetime.now(tz=UTC)
    with Session(get_engine_meta()) as session:
        trouve = licence_valide_pour_cle(session, cle, maintenant)
        if trouve is None:
            raise ExceptionKuma(
                code=CodeErreur.LICENCE_ABSENTE,
                message="Aucune licence SolClim-3 active n'est attachee a cette cle.",
                statut_http=status.HTTP_403_FORBIDDEN,
            )
        _, cle_api = trouve
        depot = contributions.deposer(session, cle_api, str(etude_uid), demande, maintenant)

    response.status_code = status.HTTP_201_CREATED if depot.creee else status.HTTP_200_OK
    return ReponseContribution(
        etude_uid=str(etude_uid),
        recue_le=depot.recue_le,
        mise_a_jour_le=depot.mise_a_jour_le,
        nombre_envois=depot.nombre_envois,
    )


@routeur.post(
    "/{etude_uid}/retrait",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Retirer la fiche d'une étude",
    description="Supprime la fiche que cette clé avait déposée pour l'étude.",
)
def retirer(etude_uid: UUID, cle: CleApiValidee) -> Response:
    """Retire la fiche de l'étude ``etude_uid`` déposée par cette clé."""
    _base_de_service()
    from kuma_data_core.db.session import get_engine_meta

    with Session(get_engine_meta()) as session:
        cle_api = contributions.cle_active(session, cle)
        if cle_api is None or not contributions.retirer(session, cle_api, str(etude_uid)):
            raise ExceptionKuma(
                code=CodeErreur.CONTRIBUTION_INCONNUE,
                message="Aucune fiche de cette etude n'a ete deposee avec cette cle.",
                statut_http=status.HTTP_404_NOT_FOUND,
            )
    return Response(status_code=status.HTTP_204_NO_CONTENT)
