"""Endpoint ``GET /api/v1/calage/{localite}/{grandeur}``.

Sert le référentiel de calage satellite/sol d'une station de
référence (ADR-0004) : biais saisonniers mesurés, facteur dérivé
k = 1/(1+biais), provenance et portée de transport. Donnée
éditoriale de l'édition, lue telle quelle - aucun calcul amont,
conforme au profil édition figée (D6).

Codes localité complets (``gin_kankan``), alignés sur ``/v1/series``
et ``/v1/localites``. 404 ``RESSOURCE_INTROUVABLE`` si aucun
référentiel actif n'existe pour le couple.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, status
from sqlalchemy import text
from sqlalchemy.orm import Session

from kuma_data_core.api.codes_erreur import CodeErreur
from kuma_data_core.api.dependencies import CleApiValidee
from kuma_data_core.api.erreurs import ExceptionKuma
from kuma_data_core.api.v1.schemas.calage import ReponseCalage, SaisonCalage
from kuma_data_core.db.session import obtenir_session

routeur = APIRouter(prefix="/calage", tags=["calage"])


@routeur.get(
    "/{localite}/{grandeur}",
    response_model=ReponseCalage,
    status_code=status.HTTP_200_OK,
    summary="Referentiel de calage satellite/sol d'une station de reference",
)
def referentiel_calage(
    localite: str,
    grandeur: str,
    _cle: CleApiValidee,
    session: Annotated[Session, Depends(obtenir_session)],
) -> ReponseCalage:
    """Retourne les biais saisonniers publiés pour (station, grandeur).

    Chaque saison porte le biais mesuré (satellite moins sol, relatif)
    et le facteur dérivé ``k = 1 / (1 + biais)``. La provenance
    (note de calage, script reproductible, série sol de référence) et
    la portée de transport accompagnent les chiffres : jamais un
    nombre nu.
    """
    rows = session.execute(
        text(
            """
            SELECT rc.code, rc.saison, rc.mois, rc.biais, rc.provenance,
                   rc.portee, rc.version
            FROM referentiels_calage rc
            JOIN localites l ON l.id = rc.localite_id
            WHERE l.code = :localite
              AND rc.grandeur_code = :grandeur
              AND rc.actif = TRUE
            ORDER BY rc.id
            """
        ),
        {"localite": localite, "grandeur": grandeur},
    ).all()
    if not rows:
        raise ExceptionKuma(
            code=CodeErreur.RESSOURCE_INTROUVABLE,
            message=("Aucun referentiel de calage publie pour cette station et cette grandeur."),
            statut_http=status.HTTP_404_NOT_FOUND,
        )

    premiere = rows[0]
    return ReponseCalage(
        localite=localite,
        grandeur=grandeur,
        code=str(premiere.code),
        version=str(premiere.version),
        saisons=[
            SaisonCalage(
                nom=str(row.saison),
                mois=[int(m) for m in row.mois],
                biais=float(row.biais),
                k=1.0 / (1.0 + float(row.biais)),
            )
            for row in rows
        ],
        provenance=str(premiere.provenance),
        portee=str(premiere.portee),
    )
