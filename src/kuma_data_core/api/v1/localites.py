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
from sqlalchemy import text
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

routeur = APIRouter(prefix="/localites", tags=["localites"])


_LIMIT_DEFAUT_LISTING: int = 100
_LIMIT_MAX_LISTING: int = 1000


def _to_float_optional(valeur: object) -> float | None:
    """``Decimal | None`` -> ``float | None``, JSON n'ayant pas de type décimal.

    Un float64 garde les 8 décimales des colonnes ``latitude`` et ``longitude``.
    """
    if valeur is None:
        return None
    return float(valeur)  # type: ignore[arg-type]


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
        Query(description="Filtre pays ISO 3166-1 alpha-3 (ex. GIN, SEN)"),
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
        Query(description="Filtre code de la localite parente (ex. gin pour villes guineennes)"),
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
    clauses: list[str] = []
    params: dict[str, object] = {"limit": limit, "offset": offset}

    if pays_iso3 is not None:
        clauses.append("L.pays_iso3 = :pays_iso3")
        params["pays_iso3"] = pays_iso3
    if type_localite is not None:
        clauses.append("L.type_localite = :type_localite")
        params["type_localite"] = type_localite
    if parent_code is not None:
        clauses.append("P.code = :parent_code")
        params["parent_code"] = parent_code
    if actif is not None:
        clauses.append("L.actif = :actif")
        params["actif"] = actif

    where_sql = ("WHERE " + " AND ".join(clauses)) if clauses else ""

    total = session.execute(
        text(
            f"""
            SELECT COUNT(*) AS n
            FROM localites L
            LEFT JOIN localites P ON L.parent_id = P.id
            {where_sql}
            """
        ),
        {k: v for k, v in params.items() if k not in ("limit", "offset")},
    ).scalar_one()

    rows = session.execute(
        text(
            f"""
            SELECT
                L.id,
                L.code,
                L.nom,
                L.type_localite,
                L.parent_id,
                P.code AS parent_code,
                L.pays_iso3,
                L.latitude,
                L.longitude,
                L.altitude_metres,
                L.population_estimee,
                L.annee_population,
                L.fuseau_horaire,
                L.cree_le AS created_at,
                L.modifie_le AS updated_at,
                L.actif
            FROM localites L
            LEFT JOIN localites P ON L.parent_id = P.id
            {where_sql}
            ORDER BY L.code
            LIMIT :limit OFFSET :offset
            """
        ),
        params,
    ).all()

    items = [
        LocaliteListee(
            id=int(r.id),
            code=r.code,
            nom=r.nom,
            type_localite=r.type_localite,
            parent_id=int(r.parent_id) if r.parent_id is not None else None,
            parent_code=r.parent_code,
            pays_iso3=r.pays_iso3,
            latitude=_to_float_optional(r.latitude),
            longitude=_to_float_optional(r.longitude),
            altitude_metres=int(r.altitude_metres) if r.altitude_metres is not None else None,
            population_estimee=(
                int(r.population_estimee) if r.population_estimee is not None else None
            ),
            annee_population=int(r.annee_population) if r.annee_population is not None else None,
            fuseau_horaire=r.fuseau_horaire,
            created_at=r.created_at,
            updated_at=r.updated_at,
            actif=r.actif,
        )
        for r in rows
    ]
    return LocaliteListeePaginee(items=items, total=int(total), limit=limit, offset=offset)


# Déclarée avant ``/{code}`` : FastAPI teste les routes dans l'ordre de
# déclaration et ``resolution`` serait sinon pris pour un code.


@routeur.get(
    "/resolution",
    response_model=ReponseResolution,
    status_code=status.HTTP_200_OK,
    summary="Resolution d'un point quelconque vers la localite qui l'echantillonne",
    description=(
        "Pour un point (lat, lon), retourne la localite du referentiel "
        "dont la climatologie mensuelle echantillonne la cellule de "
        "grille contenant le point. Le plus-proche-voisin naif est "
        "faux : la localite la plus proche peut appartenir a une autre "
        "cellule (cas demontre : Tokounou est plus proche de Kankan "
        "mais dans la cellule de Kerouane)."
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
    rows = session.execute(
        text(
            """
            SELECT l.code, l.nom, l.latitude, l.longitude,
                   MIN(sm.code) AS serie_code
            FROM localites l
            JOIN series_metadonnees sm ON sm.localite_id = l.id
            WHERE l.actif = TRUE
              AND l.latitude IS NOT NULL AND l.longitude IS NOT NULL
              AND sm.actif = TRUE
              AND sm.granularite = 'mensuel'
              AND sm.grandeur_code = :grandeur
              AND sm.periode_debut = '1991-01-01'
              AND sm.periode_fin = '2020-12-31'
            GROUP BY l.code, l.nom, l.latitude, l.longitude
            """
        ),
        {"grandeur": grandeur},
    ).all()
    if not rows:
        raise ExceptionKuma(
            code=CodeErreur.RESSOURCE_INTROUVABLE,
            message="Aucun point d'ingestion de climatologie pour cette grandeur.",
            statut_http=status.HTTP_404_NOT_FOUND,
        )

    cellule_lat = math.floor(lat)
    cellule_lon = math.floor(lon)

    candidates = [
        (str(r.code), str(r.nom), float(r.latitude), float(r.longitude), str(r.serie_code))
        for r in rows
    ]
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

    assert meilleure is not None  # rows non vide, vérifié plus haut
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
    row = session.execute(
        text(
            """
            SELECT
                L.id,
                L.code,
                L.nom,
                L.type_localite,
                L.parent_id,
                P.code AS parent_code,
                L.pays_iso3,
                L.latitude,
                L.longitude,
                L.altitude_metres,
                L.population_estimee,
                L.annee_population,
                L.fuseau_horaire,
                L.cree_le AS created_at,
                L.modifie_le AS updated_at,
                L.actif
            FROM localites L
            LEFT JOIN localites P ON L.parent_id = P.id
            WHERE L.code = :code
            """
        ),
        {"code": code},
    ).first()

    if row is None:
        raise ExceptionKuma(
            code=CodeErreur.RESSOURCE_LOCALITE_INCONNUE,
            message=f"Localite {code!r} introuvable.",
            statut_http=status.HTTP_404_NOT_FOUND,
        )

    return LocaliteDetail(
        id=int(row.id),
        code=row.code,
        nom=row.nom,
        type_localite=row.type_localite,
        parent_id=int(row.parent_id) if row.parent_id is not None else None,
        parent_code=row.parent_code,
        pays_iso3=row.pays_iso3,
        latitude=_to_float_optional(row.latitude),
        longitude=_to_float_optional(row.longitude),
        altitude_metres=int(row.altitude_metres) if row.altitude_metres is not None else None,
        population_estimee=(
            int(row.population_estimee) if row.population_estimee is not None else None
        ),
        annee_population=(int(row.annee_population) if row.annee_population is not None else None),
        fuseau_horaire=row.fuseau_horaire,
        created_at=row.created_at,
        updated_at=row.updated_at,
        actif=row.actif,
    )
