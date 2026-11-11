"""Lecture des localités : liste, détail, coordonnées et candidates à la résolution d'un point."""

from __future__ import annotations

from datetime import datetime
from typing import Any, NamedTuple

from sqlalchemy import Row, text
from sqlalchemy.orm import Session


class Localite(NamedTuple):
    """Localité, avec le code de sa localité parente.

    ``created_at`` et ``updated_at`` sont les colonnes ``cree_le`` et
    ``modifie_le``. Latitude et longitude, décimales en base, sont rendues en
    ``float`` : un float64 garde leurs 8 décimales.
    """

    id: int
    code: str
    nom: str
    type_localite: str
    parent_id: int | None
    parent_code: str | None
    pays_iso3: str | None
    latitude: float | None
    longitude: float | None
    altitude_metres: int | None
    population_estimee: int | None
    annee_population: int | None
    fuseau_horaire: str | None
    created_at: datetime
    updated_at: datetime
    actif: bool


class CandidateResolution(NamedTuple):
    """Localité candidate à la résolution d'un point, avec sa série de climatologie."""

    code: str
    nom: str
    latitude: float
    longitude: float
    serie_code: str


def _localite(r: Row[Any]) -> Localite:
    """Convertit une ligne de la liste ou du détail, qui sélectionnent les mêmes colonnes."""
    return Localite(
        id=int(r.id),
        code=r.code,
        nom=r.nom,
        type_localite=r.type_localite,
        parent_id=int(r.parent_id) if r.parent_id is not None else None,
        parent_code=r.parent_code,
        pays_iso3=r.pays_iso3,
        latitude=float(r.latitude) if r.latitude is not None else None,
        longitude=float(r.longitude) if r.longitude is not None else None,
        altitude_metres=int(r.altitude_metres) if r.altitude_metres is not None else None,
        population_estimee=int(r.population_estimee) if r.population_estimee is not None else None,
        annee_population=int(r.annee_population) if r.annee_population is not None else None,
        fuseau_horaire=r.fuseau_horaire,
        created_at=r.created_at,
        updated_at=r.updated_at,
        actif=r.actif,
    )


def lire_page_localites(
    session: Session,
    *,
    pays_iso3: str | None,
    type_localite: str | None,
    parent_code: str | None,
    actif: bool | None,
    limit: int,
    offset: int,
) -> tuple[int, list[Localite]]:
    """``(total, page)`` des localités qui passent les filtres, triées par code.

    Un filtre à ``None`` n'est pas appliqué. ``total`` compte toutes les pages.
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
    return int(total), [_localite(r) for r in rows]


def lire_localite(session: Session, code: str) -> Localite | None:
    """Localité de ce code, active ou non, ou ``None``."""
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
    return _localite(row) if row is not None else None


def localite_active_existe(session: Session, code: str) -> bool:
    """Vrai si une localité active porte ce code."""
    existe = session.execute(
        text("SELECT 1 FROM localites WHERE code = :code AND actif = TRUE"),
        {"code": code},
    ).first()
    return existe is not None


def lister_localites_de_code_court(session: Session, code_court: str) -> list[str]:
    """Codes, triés, des localités actives nommées ``<code d'un pays>_<code_court>``.

    Le préfixe est le code d'une localité de type ``pays`` du référentiel : le
    même code court peut désigner une localité dans plusieurs pays.
    """
    rows = session.execute(
        text(
            """
            SELECT l.code
            FROM localites l
            JOIN localites p
              ON p.type_localite = 'pays' AND l.code = p.code || '_' || :code_court
            WHERE l.actif = TRUE
            ORDER BY l.code
            """
        ),
        {"code_court": code_court},
    ).all()
    return [str(r.code) for r in rows]


def compter_localites_actives(session: Session) -> int:
    """Nombre de localités actives."""
    total = session.execute(text("SELECT count(*) FROM localites WHERE actif = TRUE")).scalar()
    return int(total or 0)


def lire_coordonnees(session: Session, localite_id: int) -> tuple[float, float] | None:
    """``(latitude, longitude)`` de la localité, en degrés, ou ``None`` si elle n'en a pas."""
    row = session.execute(
        text("SELECT latitude, longitude FROM localites WHERE id = :id"),
        {"id": localite_id},
    ).first()
    if row is None or row.latitude is None or row.longitude is None:
        return None
    return float(row.latitude), float(row.longitude)


def lister_candidates_resolution(session: Session, grandeur: str) -> list[CandidateResolution]:
    """Localités actives géolocalisées qui portent une série mensuelle 1991-2020 de la grandeur.

    Une ligne par localité ; si elle porte plusieurs séries, celle du plus petit code.
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
    return [
        CandidateResolution(
            code=str(r.code),
            nom=str(r.nom),
            latitude=float(r.latitude),
            longitude=float(r.longitude),
            serie_code=str(r.serie_code),
        )
        for r in rows
    ]
