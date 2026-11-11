"""Lecture des mesures journalières, mensuelles et horaires, et des valeurs de grandeur calculée.

Trois règles décident des lignes qu'une lecture retient. Chacune est définie
une seule fois, ci-dessous, et chaque lecteur nomme celle qu'il applique.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Literal, NamedTuple

from sqlalchemy import text
from sqlalchemy.orm import Session

from kuma_data_core.editorial.niveaux_confiance import NiveauxEntrees
from kuma_data_core.editorial.statuts import STATUTS_VALIDES

# Version en vigueur de chaque mesure, quel que soit son statut éditorial.
_LIGNES_COURANTES = "valide_au IS NULL"

# Version en vigueur de statut validé : une ligne ``brut`` ou ``deprecie`` est écartée.
_LIGNES_COURANTES_VALIDEES = (
    "statut IN (" + ", ".join(f"'{statut}'" for statut in STATUTS_VALIDES) + ")"
    f" AND {_LIGNES_COURANTES}"
)

# Vue des valeurs en vigueur, de la version de formule actuelle, hors statut ``deprecie``.
_GRANDEURS_METIER_COURANTES = "v_grandeurs_metier_courantes"


class LigneJournaliere(NamedTuple):
    """Mesure journalière, avec ses niveaux de confiance et son statut éditorial."""

    instant_mesure: date
    valeur: float
    niveau_confiance_derive: str
    niveau_confiance_override: str | None
    niveau_effectif: str
    statut: str


class LigneMensuelle(NamedTuple):
    """Mesure mensuelle, avec ses niveaux de confiance et son statut éditorial."""

    annee: int
    mois: int
    valeur: float
    niveau_confiance_derive: str
    niveau_confiance_override: str | None
    niveau_effectif: str
    statut: str


class LigneGrandeurMetier(NamedTuple):
    """Valeur de grandeur calculée, avec sa période, sa version de formule et ses niveaux."""

    periode_type: Literal["annuel", "mensuel", "statique"]
    annee_debut: int
    annee_fin: int
    mois: int | None
    version_formule: int
    valeur: float
    niveau_confiance_derive: str
    niveau_confiance_override: str | None
    niveau_effectif: str
    statut: str


class PointHoraire(NamedTuple):
    """Valeur horaire à son instant, tel qu'enregistré (avec fuseau)."""

    instant_mesure: datetime
    valeur: float


def lire_page_journaliere(
    session: Session,
    serie_id: int,
    bornes: tuple[date | None, date | None],
    limit: int,
    offset: int,
) -> list[LigneJournaliere]:
    """Page des mesures journalières courantes de la série, bornes incluses, triée par date."""
    from_d, to_d = bornes
    clauses = ["mr.serie_id = :serie_id", _LIGNES_COURANTES]
    params: dict[str, object] = {"serie_id": serie_id, "limit": limit, "offset": offset}
    if from_d is not None:
        clauses.append("mr.instant_mesure >= :from_d")
        params["from_d"] = from_d
    if to_d is not None:
        clauses.append("mr.instant_mesure <= :to_d")
        params["to_d"] = to_d

    rows = session.execute(
        text(
            f"""
            SELECT
                mr.instant_mesure, mr.valeur,
                mr.niveau_confiance_derive, mr.niveau_confiance_override,
                COALESCE(mr.niveau_confiance_override, mr.niveau_confiance_derive)
                  AS niveau_effectif,
                mr.statut
            FROM mesures_ressource mr
            WHERE {" AND ".join(clauses)}
            ORDER BY mr.instant_mesure
            LIMIT :limit OFFSET :offset
            """
        ),
        params,
    ).all()
    return [
        LigneJournaliere(
            instant_mesure=r.instant_mesure,
            valeur=float(r.valeur),
            niveau_confiance_derive=r.niveau_confiance_derive,
            niveau_confiance_override=r.niveau_confiance_override,
            niveau_effectif=r.niveau_effectif,
            statut=r.statut,
        )
        for r in rows
    ]


def lire_page_mensuelle(
    session: Session,
    serie_id: int,
    bornes: tuple[date | None, date | None],
    limit: int,
    offset: int,
) -> list[LigneMensuelle]:
    """Page des mesures mensuelles courantes de la série, triée par mois.

    Seuls l'année et le mois des bornes comptent ; mois bornes inclus.
    """
    from_d, to_d = bornes
    clauses = ["m.serie_id = :serie_id", _LIGNES_COURANTES]
    params: dict[str, object] = {"serie_id": serie_id, "limit": limit, "offset": offset}
    if from_d is not None:
        clauses.append("(m.annee, m.mois) >= (:from_y, :from_m)")
        params["from_y"] = from_d.year
        params["from_m"] = from_d.month
    if to_d is not None:
        clauses.append("(m.annee, m.mois) <= (:to_y, :to_m)")
        params["to_y"] = to_d.year
        params["to_m"] = to_d.month

    rows = session.execute(
        text(
            f"""
            SELECT
                m.annee, m.mois, m.valeur,
                m.niveau_confiance_derive, m.niveau_confiance_override,
                COALESCE(m.niveau_confiance_override, m.niveau_confiance_derive)
                  AS niveau_effectif,
                m.statut
            FROM mesures_ressource_mensuelles m
            WHERE {" AND ".join(clauses)}
            ORDER BY m.annee, m.mois
            LIMIT :limit OFFSET :offset
            """
        ),
        params,
    ).all()
    return [
        LigneMensuelle(
            annee=int(r.annee),
            mois=int(r.mois),
            valeur=float(r.valeur),
            niveau_confiance_derive=r.niveau_confiance_derive,
            niveau_confiance_override=r.niveau_confiance_override,
            niveau_effectif=r.niveau_effectif,
            statut=r.statut,
        )
        for r in rows
    ]


def lire_page_grandeurs_metier(
    session: Session,
    serie_id: int,
    bornes: tuple[date | None, date | None],
    limit: int,
    offset: int,
) -> list[LigneGrandeurMetier]:
    """Page des valeurs de grandeur calculée de la série, lues dans la vue des valeurs courantes.

    Seuls l'année et le mois des bornes comptent ; une valeur sans mois vaut
    janvier pour la borne basse et décembre pour la borne haute.
    """
    from_d, to_d = bornes
    clauses = ["v.series_metadonnees_id = :serie_id"]
    params: dict[str, object] = {"serie_id": serie_id, "limit": limit, "offset": offset}
    if from_d is not None:
        clauses.append("(v.annee_debut, COALESCE(v.mois, 1)) >= (:from_y, :from_m)")
        params["from_y"] = from_d.year
        params["from_m"] = from_d.month
    if to_d is not None:
        clauses.append("(v.annee_fin, COALESCE(v.mois, 12)) <= (:to_y, :to_m)")
        params["to_y"] = to_d.year
        params["to_m"] = to_d.month

    rows = session.execute(
        text(
            f"""
            SELECT
                v.periode_type, v.annee_debut, v.annee_fin, v.mois,
                v.version_formule, v.valeur,
                v.niveau_confiance_derive, v.niveau_confiance_override,
                v.niveau_effectif, v.statut
            FROM {_GRANDEURS_METIER_COURANTES} v
            WHERE {" AND ".join(clauses)}
            ORDER BY v.annee_debut, v.mois NULLS FIRST
            LIMIT :limit OFFSET :offset
            """
        ),
        params,
    ).all()
    return [
        LigneGrandeurMetier(
            periode_type=r.periode_type,
            annee_debut=int(r.annee_debut),
            annee_fin=int(r.annee_fin),
            mois=int(r.mois) if r.mois is not None else None,
            version_formule=int(r.version_formule),
            valeur=float(r.valeur),
            niveau_confiance_derive=r.niveau_confiance_derive,
            niveau_confiance_override=r.niveau_confiance_override,
            niveau_effectif=r.niveau_effectif,
            statut=r.statut,
        )
        for r in rows
    ]


def lire_valeurs_journalieres(
    session: Session,
    serie_id: int,
    periode_debut: date,
    periode_fin: date,
    *,
    niveaux: NiveauxEntrees,
) -> dict[date, float]:
    """Valeurs journalières courantes d'une série sur la fenêtre, indexées par date.

    Range le niveau de confiance effectif de chaque valeur lue dans ``niveaux``.
    """
    rows = session.execute(
        text(
            f"""
            SELECT instant_mesure, valeur,
                   coalesce(niveau_confiance_override, niveau_confiance_derive) AS niveau
            FROM mesures_ressource
            WHERE serie_id = :serie_id
              AND {_LIGNES_COURANTES}
              AND instant_mesure >= :debut
              AND instant_mesure <= :fin
            ORDER BY instant_mesure
            """
        ),
        {"serie_id": serie_id, "debut": periode_debut, "fin": periode_fin},
    ).all()
    for r in rows:
        niveaux.ajouter(r.instant_mesure, r.niveau)
    return {r.instant_mesure: float(r.valeur) for r in rows}


def lire_valeurs_horaires(
    session: Session,
    serie_id: int,
    periode_debut: date,
    periode_fin: date,
    *,
    niveaux: NiveauxEntrees,
) -> dict[datetime, float]:
    """Valeurs horaires validées et courantes d'une série, indexées par instant.

    Les lignes rejetées par le contrôle qualité (statut ``brut``) sont exclues.
    La fenêtre porte sur la date UTC. Range le niveau effectif de chaque valeur
    lue sous son jour UTC dans ``niveaux``.
    """
    rows = session.execute(
        text(
            f"""
            SELECT instant_mesure, valeur,
                   coalesce(niveau_confiance_override, niveau_confiance_derive) AS niveau
            FROM mesures_ressource_horaires
            WHERE serie_id = :serie_id
              AND {_LIGNES_COURANTES_VALIDEES}
              AND (instant_mesure AT TIME ZONE 'UTC')::date >= :debut
              AND (instant_mesure AT TIME ZONE 'UTC')::date <= :fin
            ORDER BY instant_mesure
            """
        ),
        {"serie_id": serie_id, "debut": periode_debut, "fin": periode_fin},
    ).all()
    for r in rows:
        niveaux.ajouter(r.instant_mesure.astimezone(UTC).date(), r.niveau)
    return {r.instant_mesure: float(r.valeur) for r in rows}


def lire_points_horaires(
    session: Session, serie_id: int, periode_debut: date, periode_fin: date
) -> list[PointHoraire]:
    """Points horaires validés et courants d'une série sur la fenêtre, triés par instant.

    Les lignes rejetées par le contrôle qualité (statut ``brut``) sont exclues.
    La fenêtre porte sur la date UTC.
    """
    rows = session.execute(
        text(
            f"""
            SELECT instant_mesure, valeur
            FROM mesures_ressource_horaires
            WHERE serie_id = :serie_id
              AND {_LIGNES_COURANTES_VALIDEES}
              AND (instant_mesure AT TIME ZONE 'UTC')::date >= :debut
              AND (instant_mesure AT TIME ZONE 'UTC')::date <= :fin
            ORDER BY instant_mesure
            """
        ),
        {"serie_id": serie_id, "debut": periode_debut, "fin": periode_fin},
    ).all()
    return [PointHoraire(instant_mesure=r.instant_mesure, valeur=float(r.valeur)) for r in rows]


def lire_valeurs_mensuelles(
    session: Session,
    serie_id: int,
    periode_debut: date,
    periode_fin: date,
    *,
    niveaux: NiveauxEntrees,
) -> dict[tuple[int, int], float]:
    """Valeurs mensuelles courantes d'une série, indexées par ``(annee, mois)``, bornes incluses.

    Range le niveau effectif de chaque valeur lue sous son mois dans ``niveaux``.
    """
    rows = session.execute(
        text(
            f"""
            SELECT annee, mois, valeur,
                   coalesce(niveau_confiance_override, niveau_confiance_derive) AS niveau
            FROM mesures_ressource_mensuelles
            WHERE serie_id = :serie_id
              AND {_LIGNES_COURANTES}
              AND (annee, mois) >= (:from_y, :from_m)
              AND (annee, mois) <= (:to_y, :to_m)
            ORDER BY annee, mois
            """
        ),
        {
            "serie_id": serie_id,
            "from_y": periode_debut.year,
            "from_m": periode_debut.month,
            "to_y": periode_fin.year,
            "to_m": periode_fin.month,
        },
    ).all()
    for r in rows:
        niveaux.ajouter((int(r.annee), int(r.mois)), r.niveau)
    return {(int(r.annee), int(r.mois)): float(r.valeur) for r in rows}


def lire_serie_mensuelle_entiere(
    session: Session, serie_id: int, *, niveaux: NiveauxEntrees
) -> list[tuple[int, int, float]]:
    """Mesures mensuelles courantes d'une série, en tuples ``(annee, mois, valeur)`` triés.

    Tout est chargé d'un coup (360 lignes pour une série 1991-2020 complète).
    Range le niveau effectif de chaque valeur lue dans ``niveaux``.
    """
    rows = session.execute(
        text(
            f"""
            SELECT annee, mois, valeur,
                   coalesce(niveau_confiance_override, niveau_confiance_derive) AS niveau
            FROM mesures_ressource_mensuelles
            WHERE serie_id = :serie_id AND {_LIGNES_COURANTES}
            ORDER BY annee, mois
            """
        ),
        {"serie_id": serie_id},
    ).all()
    for r in rows:
        niveaux.ajouter((int(r.annee), int(r.mois)), r.niveau)
    return [(int(r.annee), int(r.mois), float(r.valeur)) for r in rows]
