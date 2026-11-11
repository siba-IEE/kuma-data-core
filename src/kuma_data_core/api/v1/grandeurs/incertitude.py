"""Fiches d'incertitude inter-source : par localité et en collection."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from kuma_data_core.api.codes_erreur import CodeErreur
from kuma_data_core.api.dependencies import CleApiValidee
from kuma_data_core.api.erreurs import ExceptionKuma
from kuma_data_core.api.v1.grandeurs._commun import _resoudre_coordonnees
from kuma_data_core.api.v1.schemas.grandeurs import (
    DegenerescenceFiche,
    EcartPaireInterSource,
    FichePointIncertitude,
    ReponseIncertitudeInterSource,
    ReponseIncertitudeInterSourceCollection,
)
from kuma_data_core.db.session import obtenir_session
from kuma_data_core.lecture.atlas import (
    lire_degenerescence_pixel,
    lire_ecarts_mensuels,
    lister_points_atlas,
)

routeur = APIRouter()


_AN_DEBUT_ATLAS = 2021
_AN_FIN_ATLAS = 2023
_FENETRE_ATLAS_STR = "2021-2023"
_GRILLE_CERES = "CERES SYN1deg (1 deg / 110 km)"
# (grandeur exposée, grandeur_code de l'écart enregistré, libellé de la paire).
_PAIRES_ECART_ATLAS: tuple[tuple[Literal["ghi", "dni"], str, str], ...] = (
    ("ghi", "ecart_relatif_referentiel", "NASA POWER vs PVGIS-SARAH3"),
    ("dni", "ecart_relatif_dni_cams", "NASA POWER vs CAMS"),
)


def _mediane_abs(valeurs: Sequence[float]) -> float:
    """Médiane des valeurs absolues ; ``valeurs`` ne doit pas être vide."""
    absolues = sorted(abs(v) for v in valeurs)
    n = len(absolues)
    milieu = n // 2
    if n % 2 == 1:
        return absolues[milieu]
    return (absolues[milieu - 1] + absolues[milieu]) / 2.0


def _lire_degenerescence_localite(
    session: Session, code_localite: str
) -> tuple[DegenerescenceFiche | None, list[tuple[str, str | None]]]:
    """Fiche de dégénérescence de pixel de la localité et niveaux de sa ligne.

    Renvoie ``(fiche, niveaux)`` ou ``(None, [])``.
    """
    degenerescence = lire_degenerescence_pixel(session, code_localite)
    if degenerescence is None:
        return None, []
    fiche = DegenerescenceFiche(
        n_jumeaux=degenerescence.n_jumeaux, grille=_GRILLE_CERES, note=degenerescence.note
    )
    return fiche, [(degenerescence.niveau_derive, degenerescence.niveau_override)]


def _assurer_confiance_b(
    niveaux: Sequence[tuple[str, str | None]], code_localite: str
) -> Literal["B"]:
    """Renvoie ``'B'`` si toutes les lignes lues sont en confiance effective B, sinon lève 500.

    La fiche n'affiche ainsi jamais un niveau que ses données ne portent pas.
    """
    effectifs = {(override if override is not None else derive) for derive, override in niveaux}
    if effectifs != {"B"}:
        raise ExceptionKuma(
            code=CodeErreur.SERVEUR_ERREUR_INTERNE,
            message=(
                f"Incohérence de confiance pour {code_localite!r} : la fiche inter-source "
                f"attend des données en confiance B, trouvé {sorted(effectifs)}. "
                "L'atlas compare des sources entre elles (confiance B) ; A est réservée "
                "aux données validées par des mesures au sol."
            ),
            statut_http=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )
    return "B"


def _construire_limite_incertitude_inter_source() -> str:
    """Champ ``limite`` des fiches d'incertitude inter-source."""
    return (
        "Incertitude inter-source, donc relative : divergence entre NASA POWER et les "
        "références satellite (SARAH-3 pour le GHI, CAMS pour le DNI), fenêtre 2021-2023, "
        "confiance B. Ne quantifie pas l'incertitude absolue par rapport à des mesures au "
        "sol : ce n'est pas une barre d'erreur calée au sol."
    )


@routeur.get(
    "/incertitude_inter_source/{code_localite}",
    response_model=ReponseIncertitudeInterSource,
    status_code=status.HTTP_200_OK,
    summary="Fiche d'incertitude inter-source (ecart + degenerescence de pixel)",
    tags=["grandeurs-F1"],
)
def grandeur_incertitude_inter_source(
    code_localite: str,
    _cle: CleApiValidee,
    session: Annotated[Session, Depends(obtenir_session)],
) -> ReponseIncertitudeInterSource:
    """Fiche d'incertitude inter-source d'une localité.

    Assemblée à partir de grandeurs déjà calculées, elle porte deux informations
    distinctes :

    - ``ecarts`` : écart entre NASA POWER et une source de référence, par
      grandeur (GHI : SARAH-3 ; DNI : CAMS), sur 2021-2023. ``ecart_abs_pct``
      (médiane des écarts mensuels absolus) est l'indicateur à retenir ;
      ``ecart_signe_pct`` n'indique qu'un sens.
    - ``degenerescence`` : nombre d'autres localités qui partagent la cellule
      de la grille CERES de NASA POWER.

    Confiance B : la fiche compare des sources entre elles, pas à des mesures au
    sol. 404 ``RESSOURCE_LOCALITE_INCONNUE`` si aucun écart inter-source n'est
    enregistré pour la localité sur la période.
    """
    ecarts: list[EcartPaireInterSource] = []
    niveaux: list[tuple[str, str | None]] = []
    for grandeur, grandeur_ecart, paire in _PAIRES_ECART_ATLAS:
        valeurs, niv = lire_ecarts_mensuels(
            session, code_localite, grandeur_ecart, _AN_DEBUT_ATLAS, _AN_FIN_ATLAS
        )
        if not valeurs:
            continue
        ecarts.append(
            EcartPaireInterSource(
                grandeur=grandeur,
                paire=paire,
                ecart_abs_pct=round(_mediane_abs(valeurs), 4),
                ecart_signe_pct=round(sum(valeurs) / len(valeurs), 4),
                n_mois=len(valeurs),
            )
        )
        niveaux += niv

    if not ecarts:
        raise ExceptionKuma(
            code=CodeErreur.RESSOURCE_LOCALITE_INCONNUE,
            message=(
                f"Localité {code_localite!r} non couverte par l'atlas d'incertitude "
                "inter-source : aucun écart entre sources n'est enregistré pour elle "
                "sur 2021-2023."
            ),
            statut_http=status.HTTP_404_NOT_FOUND,
        )

    degenerescence, niv_degen = _lire_degenerescence_localite(session, code_localite)
    if degenerescence is None:
        raise ExceptionKuma(
            code=CodeErreur.SERVEUR_ERREUR_INTERNE,
            message=(
                f"Incoherence : ecart inter-source present pour {code_localite!r} mais "
                "degenerescence_pixel (NASA/ghi) absente."
            ),
            statut_http=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )
    niveaux += niv_degen

    return ReponseIncertitudeInterSource(
        code_localite=code_localite,
        fenetre=_FENETRE_ATLAS_STR,
        ecarts=ecarts,
        degenerescence=degenerescence,
        niveau_confiance=_assurer_confiance_b(niveaux, code_localite),
        limite=_construire_limite_incertitude_inter_source(),
    )


def _assembler_fiche_point(
    session: Session, localite_id: int, code_localite: str
) -> FichePointIncertitude:
    """Fiche d'un point pour la collection : celle de la route par localité, plus les coordonnées.

    Lève 500 si le point n'a pas d'écart ou pas de dégénérescence.
    """
    ecarts: list[EcartPaireInterSource] = []
    niveaux: list[tuple[str, str | None]] = []
    for grandeur, grandeur_ecart, paire in _PAIRES_ECART_ATLAS:
        valeurs, niv = lire_ecarts_mensuels(
            session, code_localite, grandeur_ecart, _AN_DEBUT_ATLAS, _AN_FIN_ATLAS
        )
        if not valeurs:
            continue
        ecarts.append(
            EcartPaireInterSource(
                grandeur=grandeur,
                paire=paire,
                ecart_abs_pct=round(_mediane_abs(valeurs), 4),
                ecart_signe_pct=round(sum(valeurs) / len(valeurs), 4),
                n_mois=len(valeurs),
            )
        )
        niveaux += niv

    degenerescence, niv_degen = _lire_degenerescence_localite(session, code_localite)
    if not ecarts or degenerescence is None:
        raise ExceptionKuma(
            code=CodeErreur.SERVEUR_ERREUR_INTERNE,
            message=(
                f"Incohérence dans la collection de l'atlas : le point {code_localite!r} "
                "n'a pas d'écart ou pas de dégénérescence enregistrés."
            ),
            statut_http=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )
    niveaux += niv_degen
    latitude, longitude = _resoudre_coordonnees(session, localite_id)
    return FichePointIncertitude(
        code_localite=code_localite,
        fenetre=_FENETRE_ATLAS_STR,
        ecarts=ecarts,
        degenerescence=degenerescence,
        niveau_confiance=_assurer_confiance_b(niveaux, code_localite),
        limite=_construire_limite_incertitude_inter_source(),
        latitude_deg=latitude,
        longitude_deg=longitude,
    )


@routeur.get(
    "/incertitude_inter_source",
    response_model=ReponseIncertitudeInterSourceCollection,
    status_code=status.HTTP_200_OK,
    summary="Collection des fiches d'incertitude inter-source (points de l'atlas)",
    tags=["grandeurs-F1"],
)
def grandeur_incertitude_inter_source_collection(
    _cle: CleApiValidee,
    session: Annotated[Session, Depends(obtenir_session)],
    limit: Annotated[int, Query(ge=1, le=1000)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> ReponseIncertitudeInterSourceCollection:
    """Fiches d'incertitude inter-source de tous les points de l'atlas, paginées.

    Chaque élément est la fiche de
    ``/v1/grandeurs/incertitude_inter_source/{code_localite}``, complétée de la
    latitude et de la longitude du point : un seul appel suffit pour dessiner
    une carte. Les points sont les localités qui ont un écart inter-source
    depuis 2021, triées par code. Même enveloppe paginée que ``/v1/series``
    (``items``, ``total``, ``limit``, ``offset``).
    """
    points = lister_points_atlas(session, _AN_DEBUT_ATLAS)
    total = len(points)
    page = points[offset : offset + limit]
    items = [_assembler_fiche_point(session, loc_id, code) for loc_id, code in page]
    return ReponseIncertitudeInterSourceCollection(
        items=items, total=total, limit=limit, offset=offset
    )
