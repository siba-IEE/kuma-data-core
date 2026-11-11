"""Routes ``/v1/calage``.

Servent le référentiel de calage satellite/sol d'une station de référence
(ADR-0004) : biais saisonniers mesurés, facteur dérivé k = 1/(1+biais),
provenance et portée de transport. Donnée éditoriale de l'édition, lue telle
quelle, sans appel sortant.

Codes de localité complets (``gin_kankan``), comme ``/v1/series`` et
``/v1/localites``. 404 ``RESSOURCE_INTROUVABLE`` si aucun référentiel actif
n'existe pour le couple.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from kuma_data_core.api.codes_erreur import CodeErreur
from kuma_data_core.api.dependencies import CleApiValidee
from kuma_data_core.api.erreurs import ExceptionKuma
from kuma_data_core.api.v1.schemas.calage import (
    ReferentielListe,
    ReponseCalage,
    ReponseCalageListe,
    SaisonCalage,
)
from kuma_data_core.db.session import obtenir_session
from kuma_data_core.lecture.calage import (
    lire_couverture_referentiel,
    lire_couvertures_par_referentiel,
    lire_saisons_referentiel,
    lister_referentiels,
)

routeur = APIRouter(prefix="/calage", tags=["calage"])


@routeur.get(
    "",
    response_model=ReponseCalageListe,
    status_code=status.HTTP_200_OK,
    summary="Listing des referentiels de calage publies",
)
def lister_referentiels_calage(
    _cle: CleApiValidee,
    session: Annotated[Session, Depends(obtenir_session)],
) -> ReponseCalageListe:
    """Référentiels de calage publiés, avec leur domaine de couverture.

    Une entrée par référentiel : station, grandeur, version, série sol sur
    laquelle il est fondé et localités couvertes. La liste permet de découvrir
    les stations disponibles sans les connaître d'avance.
    """
    referentiels = lister_referentiels(session)
    par_referentiel = lire_couvertures_par_referentiel(session)

    items = [
        ReferentielListe(
            code=r.code,
            localite=r.localite,
            grandeur=r.grandeur_code,
            version=r.version,
            serie_sol=r.serie_sol,
            localites_couvertes=par_referentiel.get(r.code, []),
        )
        for r in referentiels
    ]
    return ReponseCalageListe(items=items, total=len(items))


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
    saisons = lire_saisons_referentiel(session, localite, grandeur)
    if not saisons:
        raise ExceptionKuma(
            code=CodeErreur.RESSOURCE_INTROUVABLE,
            message=("Aucun referentiel de calage publie pour cette station et cette grandeur."),
            statut_http=status.HTTP_404_NOT_FOUND,
        )

    premiere = saisons[0]
    couverture = lire_couverture_referentiel(session, premiere.code)

    return ReponseCalage(
        localite=localite,
        grandeur=grandeur,
        code=premiere.code,
        version=premiere.version,
        saisons=[
            SaisonCalage(
                nom=saison.saison,
                mois=saison.mois,
                biais=saison.biais,
                k=1.0 / (1.0 + saison.biais),
            )
            for saison in saisons
        ],
        provenance=premiere.provenance,
        portee=premiere.portee,
        localites_couvertes=[c.code for c in couverture],
        justification_couverture=couverture[0].justification if couverture else None,
        serie_sol=premiere.serie_sol,
    )
