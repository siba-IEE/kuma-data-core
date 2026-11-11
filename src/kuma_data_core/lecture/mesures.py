"""Lecture des mesures journalières, mensuelles et horaires, et des valeurs de grandeur calculée.

Chaque lecteur nomme la règle de sélection qu'il applique ; les règles sont
définies dans ``editorial.selection``.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, time, timedelta
from typing import Literal, NamedTuple
from zoneinfo import ZoneInfo

from sqlalchemy import text
from sqlalchemy.orm import Session

from kuma_data_core.editorial.niveaux_confiance import NiveauxEntrees
from kuma_data_core.editorial.selection import (
    VUE_GRANDEURS_EN_VIGUEUR,
    StatutValide,
    lignes_en_vigueur,
    lignes_en_vigueur_validees,
)


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
    """Valeur horaire à son instant, tel qu'enregistré (avec fuseau), et statut de sa ligne."""

    instant_mesure: datetime
    valeur: float
    statut: StatutValide


def lire_page_journaliere(
    session: Session,
    serie_id: int,
    bornes: tuple[date | None, date | None],
    limit: int,
    offset: int,
) -> list[LigneJournaliere]:
    """Page des mesures journalières en vigueur de la série, bornes incluses, triée par date."""
    from_d, to_d = bornes
    clauses = ["mr.serie_id = :serie_id", lignes_en_vigueur("mr")]
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
    """Page des mesures mensuelles en vigueur de la série, triée par mois.

    Seuls l'année et le mois des bornes comptent ; mois bornes inclus.
    """
    from_d, to_d = bornes
    clauses = ["m.serie_id = :serie_id", lignes_en_vigueur("m")]
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
    """Page des valeurs de grandeur calculée de la série, lues dans la vue des valeurs en vigueur.

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
            FROM {VUE_GRANDEURS_EN_VIGUEUR} v
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
    """Valeurs journalières en vigueur d'une série sur la fenêtre, indexées par date.

    Range le niveau de confiance effectif de chaque valeur lue dans ``niveaux``.
    """
    rows = session.execute(
        text(
            f"""
            SELECT instant_mesure, valeur,
                   coalesce(niveau_confiance_override, niveau_confiance_derive) AS niveau
            FROM mesures_ressource
            WHERE serie_id = :serie_id
              AND {lignes_en_vigueur()}
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
    fuseau: str,
    niveaux: NiveauxEntrees,
) -> dict[datetime, float]:
    """Valeurs horaires en vigueur et validées d'une série, indexées par instant local.

    Les lignes rejetées par le contrôle qualité (statut ``brut``) sont exclues.
    ``fuseau`` est le nom IANA du fuseau de la localité de la série : la fenêtre
    porte sur la date locale, les instants sont rendus dans ce fuseau, et le
    niveau effectif de chaque valeur lue est rangé sous son jour local dans
    ``niveaux``.
    """
    rows = session.execute(
        text(
            f"""
            SELECT instant_mesure, valeur,
                   coalesce(niveau_confiance_override, niveau_confiance_derive) AS niveau
            FROM mesures_ressource_horaires
            WHERE serie_id = :serie_id
              AND {lignes_en_vigueur_validees()}
              AND instant_mesure >= :borne_debut
              AND instant_mesure < :borne_fin
              AND (instant_mesure AT TIME ZONE :fuseau)::date >= :debut
              AND (instant_mesure AT TIME ZONE :fuseau)::date <= :fin
            ORDER BY instant_mesure
            """
        ),
        {
            "serie_id": serie_id,
            "fuseau": fuseau,
            "debut": periode_debut,
            "fin": periode_fin,
            # Bornes larges en UTC, pour que l'index serve : aucun fuseau n'est
            # décalé de plus de 14 h, le filtre sur la date locale fait le tri exact.
            "borne_debut": datetime.combine(periode_debut, time.min, UTC) - timedelta(days=1),
            "borne_fin": datetime.combine(periode_fin, time.min, UTC) + timedelta(days=2),
        },
    ).all()
    zone = ZoneInfo(fuseau)
    valeurs: dict[datetime, float] = {}
    for r in rows:
        instant = r.instant_mesure.astimezone(zone)
        niveaux.ajouter(instant.date(), r.niveau)
        valeurs[instant] = float(r.valeur)
    return valeurs


def lire_points_horaires(
    session: Session, serie_id: int, periode_debut: date, periode_fin: date
) -> list[PointHoraire]:
    """Points horaires en vigueur et validés d'une série sur la fenêtre, triés par instant.

    Les lignes rejetées par le contrôle qualité (statut ``brut``) sont exclues.
    La fenêtre porte sur la date UTC.
    """
    rows = session.execute(
        text(
            f"""
            SELECT instant_mesure, valeur, statut
            FROM mesures_ressource_horaires
            WHERE serie_id = :serie_id
              AND {lignes_en_vigueur_validees()}
              AND (instant_mesure AT TIME ZONE 'UTC')::date >= :debut
              AND (instant_mesure AT TIME ZONE 'UTC')::date <= :fin
            ORDER BY instant_mesure
            """
        ),
        {"serie_id": serie_id, "debut": periode_debut, "fin": periode_fin},
    ).all()
    return [
        PointHoraire(instant_mesure=r.instant_mesure, valeur=float(r.valeur), statut=r.statut)
        for r in rows
    ]


def lire_valeurs_mensuelles(
    session: Session,
    serie_id: int,
    periode_debut: date,
    periode_fin: date,
    *,
    niveaux: NiveauxEntrees,
) -> dict[tuple[int, int], float]:
    """Valeurs mensuelles en vigueur d'une série, indexées par ``(annee, mois)``, bornes incluses.

    Range le niveau effectif de chaque valeur lue sous son mois dans ``niveaux``.
    """
    rows = session.execute(
        text(
            f"""
            SELECT annee, mois, valeur,
                   coalesce(niveau_confiance_override, niveau_confiance_derive) AS niveau
            FROM mesures_ressource_mensuelles
            WHERE serie_id = :serie_id
              AND {lignes_en_vigueur()}
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
    """Mesures mensuelles en vigueur d'une série, en tuples ``(annee, mois, valeur)`` triés.

    Tout est chargé d'un coup (360 lignes pour une série 1991-2020 complète).
    Range le niveau effectif de chaque valeur lue dans ``niveaux``.
    """
    rows = session.execute(
        text(
            f"""
            SELECT annee, mois, valeur,
                   coalesce(niveau_confiance_override, niveau_confiance_derive) AS niveau
            FROM mesures_ressource_mensuelles
            WHERE serie_id = :serie_id AND {lignes_en_vigueur()}
            ORDER BY annee, mois
            """
        ),
        {"serie_id": serie_id},
    ).all()
    for r in rows:
        niveaux.ajouter((int(r.annee), int(r.mois)), r.niveau)
    return [(int(r.annee), int(r.mois), float(r.valeur)) for r in rows]


def lister_localites_de_meme_serie_mensuelle(session: Session, serie_id: int) -> list[str]:
    """Codes, triés, des autres localités dont une série mensuelle égale cette série.

    Sont comparées les séries actives de même source, même grandeur et même
    ``periode_debut``. Deux séries sont égales quand leurs valeurs en vigueur,
    ordonnées par année puis mois, sont identiques : PostgreSQL compare les
    tableaux, aucune valeur n'est rapatriée. C'est le cas de deux localités
    d'une même cellule, quand la grille de la source est plus large que leur
    écart.
    """
    rows = session.execute(
        text(
            f"""
            WITH reference AS (
                SELECT id, localite_id, source_id, grandeur_code, periode_debut
                FROM series_metadonnees
                WHERE id = :serie_id
            ),
            vecteurs AS (
                SELECT m.serie_id, array_agg(m.valeur ORDER BY m.annee, m.mois) AS valeurs
                FROM mesures_ressource_mensuelles m
                WHERE {lignes_en_vigueur("m")}
                  AND m.serie_id IN (
                      SELECT sm.id
                      FROM series_metadonnees sm
                      JOIN reference r
                        ON sm.source_id = r.source_id
                       AND sm.grandeur_code = r.grandeur_code
                       AND sm.periode_debut = r.periode_debut
                      WHERE sm.actif = TRUE
                  )
                GROUP BY m.serie_id
            )
            SELECT DISTINCT l.code
            FROM reference r
            JOIN vecteurs v_ref ON v_ref.serie_id = r.id
            JOIN vecteurs v ON v.valeurs = v_ref.valeurs
            JOIN series_metadonnees sm ON sm.id = v.serie_id
            JOIN localites l ON l.id = sm.localite_id
            WHERE sm.localite_id <> r.localite_id
            ORDER BY l.code
            """
        ),
        {"serie_id": serie_id},
    ).all()
    return [str(r.code) for r in rows]
