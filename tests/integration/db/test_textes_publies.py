"""Garde globale : aucun texte publié ne porte de vocabulaire de chantier. Lecture seule.

Périmètre : toutes les colonnes non numériques des tables de l'édition publique
(manifeste de publication), hors colonnes neutralisées avant le dump, et tous
les commentaires du catalogue du schéma ``public``. Aucune exception : une
correspondance est soit un texte à corriger, soit un défaut du motif.
"""

from __future__ import annotations

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

from kuma_data_core.publication.manifeste import (
    ASSAINISSEMENTS,
    TABLES_HORS_ORM_PUBLIEES,
    tables_dumpees,
)
from tests.jargon import correspondances

pytestmark = pytest.mark.integration

# Types sans texte. Toute colonne d'un autre type est balayée sous sa forme texte
# (tableaux et JSON compris) : un type nouveau n'échappe pas à la garde.
_TYPES_SANS_TEXTE = (
    "bigint",
    "integer",
    "smallint",
    "numeric",
    "double precision",
    "real",
    "boolean",
    "date",
    "timestamp with time zone",
    "timestamp without time zone",
)
_SQL_COLONNES = text(
    """
    SELECT table_name, column_name FROM information_schema.columns
    WHERE table_schema = 'public' AND table_name = ANY(:tables)
      AND data_type <> ALL(:types_sans_texte)
    ORDER BY table_name, ordinal_position
    """
)
_SQL_COMMENTAIRES = text(
    """
    SELECT o.type || ' ' || o.identity, d.description
    FROM pg_description d
    CROSS JOIN LATERAL pg_identify_object(d.classoid, d.objoid, d.objsubid) AS o
    WHERE o.schema = 'public' OR (o.type = 'schema' AND o.name = 'public')
    """
)


def _colonnes(db_session: Session) -> list[tuple[str, str]]:
    """Colonnes publiées susceptibles de porter du texte."""
    tables = sorted(tables_dumpees() | TABLES_HORS_ORM_PUBLIEES)
    return [
        (table, colonne)
        for table, colonne in db_session.execute(
            _SQL_COLONNES, {"tables": tables, "types_sans_texte": list(_TYPES_SANS_TEXTE)}
        ).tuples()
        if colonne not in ASSAINISSEMENTS.get(table, {})
    ]


def test_le_balayage_couvre_toutes_les_tables_publiees(db_session: Session) -> None:
    """Garde contre un test vide : chaque table publiée a des colonnes balayées."""
    colonnes = _colonnes(db_session)
    assert {table for table, _ in colonnes} == tables_dumpees() | TABLES_HORS_ORM_PUBLIEES
    for attendue in (
        ("sources", "metadonnees"),
        ("sources", "auteurs"),
        ("localites", "notes"),
        ("grandeurs_metier", "commentaire_editorial"),
        ("mesures_ressource_horaires", "commentaire_editorial"),
        ("series_metadonnees", "note_publique"),
        ("unites", "references_normatives"),
    ):
        assert attendue in colonnes
    assert ("series_metadonnees", "commentaire_editorial") not in colonnes
    assert ("contributeurs", "notes_internes") not in colonnes


def test_aucune_valeur_publiee_ne_porte_de_vocabulaire_de_chantier(db_session: Session) -> None:
    fautives: dict[str, dict[str, list[str]]] = {}
    for table, colonne in _colonnes(db_session):
        # Valeurs distinctes : les tables de mesures ont des millions de lignes.
        # Les identifiants viennent du catalogue, pas d'une entrée extérieure.
        valeurs = db_session.execute(
            text(f'SELECT DISTINCT "{colonne}"::text FROM "{table}" WHERE "{colonne}" IS NOT NULL')
        ).scalars()
        trouvees = {v[:200]: c for v in valeurs if (c := correspondances(v))}
        if trouvees:
            fautives[f"{table}.{colonne}"] = trouvees
    assert not fautives


def test_aucun_commentaire_du_catalogue_ne_porte_de_vocabulaire_de_chantier(
    db_session: Session,
) -> None:
    commentaires = db_session.execute(_SQL_COMMENTAIRES).tuples().all()
    objets = {objet for objet, _ in commentaires}
    assert {
        "table public.series_metadonnees",
        "table column public.sources.doi",
        "view public.v_grandeurs_metier_courantes",
        "function public.valider_hierarchie_localites()",
    } <= objets
    fautifs = {
        objet: trouves
        for objet, description in commentaires
        if (trouves := correspondances(description))
    }
    assert not fautifs
