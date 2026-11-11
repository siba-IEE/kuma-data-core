"""Routes ``/v1/localites`` : liste, résolution d'un point et détail.

- ``GET /v1/localites`` : liste paginée des localités (filtres ``pays_iso3``,
  ``type_localite``, ``parent_code``, ``actif`` ; 100 par page, 1000 au plus).
- ``GET /v1/localites/resolution`` : localité qui représente la cellule de
  grille d'un point (ADR-0004).
- ``GET /v1/localites/{code}`` : détail d'une localité (code en slug ASCII, ou
  ``<code_pays>_<slug>`` pour une entité administrative).

Même enveloppe paginée et mêmes conventions que ``/v1/series`` (ADR-0001,
ADR-0002). ``parent_code`` est obtenu par jointure de ``localites`` sur
elle-même, ce qui évite un second appel pour connaître le parent.
"""

from __future__ import annotations

import math
from typing import Annotated

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from kuma_data_core.api.codes_erreur import CodeErreur
from kuma_data_core.api.dependencies import CleApiValidee
from kuma_data_core.api.erreurs import ExceptionKuma
from kuma_data_core.api.v1.schemas.localites import (
    CelluleResolution,
    LocaliteDetail,
    LocaliteListee,
    LocaliteListeePaginee,
    LocaliteResolue,
    PointGeographique,
    ReponseResolution,
)
from kuma_data_core.db.session import obtenir_session
from kuma_data_core.lecture.localites import (
    Localite,
    lire_localite,
    lire_page_localites,
    lister_candidates_resolution,
)

routeur = APIRouter(prefix="/localites", tags=["localites"])


_LIMIT_DEFAUT_LISTING: int = 100
_LIMIT_MAX_LISTING: int = 1000


def _vers_localite_listee(localite: Localite) -> LocaliteListee:
    """Schéma de réponse d'une localité lue, le même pour la liste et pour le détail."""
    return LocaliteListee(
        id=localite.id,
        code=localite.code,
        nom=localite.nom,
        type_localite=localite.type_localite,
        parent_id=localite.parent_id,
        parent_code=localite.parent_code,
        pays_iso3=localite.pays_iso3,
        latitude=localite.latitude,
        longitude=localite.longitude,
        altitude_metres=localite.altitude_metres,
        population_estimee=localite.population_estimee,
        annee_population=localite.annee_population,
        fuseau_horaire=localite.fuseau_horaire,
        created_at=localite.created_at,
        updated_at=localite.updated_at,
        actif=localite.actif,
    )


_RAYON_TERRE_KM = 6371.0


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Distance du grand cercle entre deux points WGS84, en km (formule de haversine)."""
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return 2 * _RAYON_TERRE_KM * math.asin(math.sqrt(a))


@routeur.get(
    "",
    response_model=LocaliteListeePaginee,
    status_code=status.HTTP_200_OK,
    summary="Listing des localites disponibles",
    description=(
        "Retourne la liste paginée des localités, triée par code, dans une "
        "enveloppe `{items, total, limit, offset}`. Filtrage optionnel par "
        "pays_iso3, type_localite, parent_code ou statut actif ; par défaut, "
        "seules les localités actives sont listées."
    ),
)
def lister_localites(
    _cle: CleApiValidee,
    session: Annotated[Session, Depends(obtenir_session)],
    pays_iso3: Annotated[
        str | None,
        Query(
            description=(
                "Filtre sur le pays : code ISO 3166-1 alpha-3 en majuscules, tel que "
                "rendu dans le champ pays_iso3 des localités."
            ),
        ),
    ] = None,
    type_localite: Annotated[
        str | None,
        Query(
            description=(
                "Filtre type : continent, region_supranationale, pays, "
                "region_administrative, commune, site"
            ),
        ),
    ] = None,
    parent_code: Annotated[
        str | None,
        Query(
            description=(
                "Filtre sur le code de la localité parente directe, tel que rendu dans "
                "le champ parent_code des localités."
            ),
        ),
    ] = None,
    actif: Annotated[
        bool | None, Query(description="Filtre actif (TRUE/FALSE), defaut TRUE")
    ] = True,
    limit: Annotated[int, Query(ge=1, le=_LIMIT_MAX_LISTING)] = _LIMIT_DEFAUT_LISTING,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> LocaliteListeePaginee:
    """Liste paginée des localités, triée par code.

    ``actif`` vaut TRUE par défaut : passer ``actif=false`` pour voir les
    localités désactivées.
    """
    total, localites = lire_page_localites(
        session,
        pays_iso3=pays_iso3,
        type_localite=type_localite,
        parent_code=parent_code,
        actif=actif,
        limit=limit,
        offset=offset,
    )
    return LocaliteListeePaginee(
        items=[_vers_localite_listee(localite) for localite in localites],
        total=total,
        limit=limit,
        offset=offset,
    )


# Déclarée avant ``/{code}`` : FastAPI teste les routes dans l'ordre de
# déclaration et ``resolution`` serait sinon pris pour un code.


@routeur.get(
    "/resolution",
    response_model=ReponseResolution,
    status_code=status.HTTP_200_OK,
    summary="Resolution d'un point quelconque vers la localite qui l'echantillonne",
    description=(
        "Pour un point (lat, lon), retourne la localité du référentiel "
        "dont la climatologie mensuelle échantillonne la cellule de "
        "grille contenant le point. Ce n'est pas toujours la localité "
        "la plus proche : celle-ci peut appartenir à une autre cellule, "
        "dont la climatologie n'est pas celle du point."
    ),
)
def resoudre_point(
    _cle: CleApiValidee,
    session: Annotated[Session, Depends(obtenir_session)],
    lat: Annotated[float, Query(ge=-90, le=90, description="Latitude WGS84 du point.")],
    lon: Annotated[float, Query(ge=-180, le=180, description="Longitude WGS84 du point.")],
    grandeur: Annotated[str, Query(pattern="^ghi$")] = "ghi",
) -> ReponseResolution:
    """Résout un point vers la localité qui représente sa cellule de grille.

    Candidates : les localités actives qui portent une série mensuelle active
    de la grandeur sur 1991-2020. La cellule est celle de la grille de la
    source de climatologie, 1° x 1°, frontières aux degrés entiers. Si aucune
    candidate n'est dans la cellule du point, ``meme_cellule`` vaut ``false``
    et la plus proche est renvoyée avec sa distance. Lève 404
    ``RESSOURCE_INTROUVABLE`` si aucune localité ne porte de série de ce type.
    """
    candidates = lister_candidates_resolution(session, grandeur)
    if not candidates:
        raise ExceptionKuma(
            code=CodeErreur.RESSOURCE_INTROUVABLE,
            message="Aucun point d'ingestion de climatologie pour cette grandeur.",
            statut_http=status.HTTP_404_NOT_FOUND,
        )

    cellule_lat = math.floor(lat)
    cellule_lon = math.floor(lon)

    meilleure: tuple[float, int] | None = None
    meilleure_meme_cellule: tuple[float, int] | None = None
    for indice, (_code, _nom, r_lat, r_lon, _serie) in enumerate(candidates):
        distance = _haversine_km(lat, lon, r_lat, r_lon)
        if meilleure is None or distance < meilleure[0]:
            meilleure = (distance, indice)
        dans_cellule = math.floor(r_lat) == cellule_lat and math.floor(r_lon) == cellule_lon
        if dans_cellule and (
            meilleure_meme_cellule is None or distance < meilleure_meme_cellule[0]
        ):
            meilleure_meme_cellule = (distance, indice)

    assert meilleure is not None  # candidates non vide, vérifié plus haut
    meme_cellule = meilleure_meme_cellule is not None
    distance_km, indice_retenu = (
        meilleure_meme_cellule if meilleure_meme_cellule is not None else meilleure
    )
    code, nom, retenue_lat, retenue_lon, serie_climatologie = candidates[indice_retenu]

    return ReponseResolution(
        point=PointGeographique(latitude_deg=lat, longitude_deg=lon),
        grandeur=grandeur,
        cellule=CelluleResolution(
            lat_min=float(cellule_lat),
            lat_max=float(cellule_lat + 1),
            lon_min=float(cellule_lon),
            lon_max=float(cellule_lon + 1),
        ),
        localite=LocaliteResolue(
            code=code,
            nom=nom,
            latitude_deg=retenue_lat,
            longitude_deg=retenue_lon,
        ),
        distance_km=round(distance_km, 1),
        meme_cellule=meme_cellule,
        serie_climatologie=serie_climatologie,
    )


@routeur.get(
    "/{code}",
    response_model=LocaliteDetail,
    status_code=status.HTTP_200_OK,
    summary="Detail d'une localite",
    description=(
        "Retourne le detail d'une localite identifiee par son code "
        "(slug ASCII pour racines, `<code_pays>_<slug>` pour entites "
        "administratives)."
    ),
)
def detailler_localite(
    code: str,
    _cle: CleApiValidee,
    session: Annotated[Session, Depends(obtenir_session)],
) -> LocaliteDetail:
    """Détail d'une localité, active ou non.

    Lève 404 ``RESSOURCE_LOCALITE_INCONNUE`` si le code est inconnu.
    """
    localite = lire_localite(session, code)
    if localite is None:
        raise ExceptionKuma(
            code=CodeErreur.RESSOURCE_LOCALITE_INCONNUE,
            message=f"Localite {code!r} introuvable.",
            statut_http=status.HTTP_404_NOT_FOUND,
        )
    return _vers_localite_listee(localite)
