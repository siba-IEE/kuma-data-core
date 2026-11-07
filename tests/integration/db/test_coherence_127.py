"""Tests d'intégration de la migration 127 (jargon interne des textes publiés).

- Aucune ``description`` ni ``libelle`` de ``grandeurs_referentiel`` (table
  publiée telle quelle) ne porte de vocabulaire de chantier interne.
- Aucun commentaire du catalogue du schéma ``public`` (tables, colonnes,
  vues, fonctions : ``pg_dump`` les emporte dans l'édition) n'en porte.
- Les commentaires des tables et colonnes touchées sont identiques aux
  modèles ORM.
- Corrections de fond : ``periode_type`` documente ``statique`` ;
  ``vent_2m`` n'est plus annoncé comme entrée d'un modèle thermique au vent.
"""

from __future__ import annotations

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

import kuma_data_core.db.models  # noqa: F401  (enregistre toutes les tables)
from kuma_data_core.db.base import Base
from tests.integration.db._jargon import JARGON_INTERNE

pytestmark = pytest.mark.integration

_TABLES_TOUCHEES: tuple[str, ...] = (
    "calage_couverture",
    "grandeurs_metier",
    "mesures_ressource",
    "mesures_ressource_horaires",
    "mesures_ressource_mensuelles",
    "referentiels_calage",
)
_COLONNES_TOUCHEES: tuple[tuple[str, str], ...] = (
    ("grandeurs_metier", "niveau_confiance_derive"),
    ("grandeurs_metier", "periode_type"),
    ("grandeurs_metier", "version_formule"),
    ("grandeurs_referentiel", "code"),
    ("localites", "type_localite"),
    ("mesures_ressource", "niveau_confiance_derive"),
    ("series_metadonnees", "granularite"),
    ("series_metadonnees", "methode_collecte"),
    ("sources", "fiabilite"),
    ("sources", "type_source"),
)


def test_grandeurs_referentiel_sans_jargon(db_session: Session) -> None:
    rows = db_session.execute(
        text("SELECT code, libelle, description FROM grandeurs_referentiel ORDER BY code")
    ).all()
    fautifs = [
        (r.code, champ, m.group(0))
        for r in rows
        for champ, valeur in (("libelle", r.libelle), ("description", r.description))
        if valeur and (m := JARGON_INTERNE.search(valeur))
    ]
    assert fautifs == []


def test_commentaires_catalogue_sans_jargon(db_session: Session) -> None:
    rows = db_session.execute(
        text(
            """
            SELECT pg_describe_object(d.classoid, d.objoid, d.objsubid) AS objet,
                   d.description
            FROM pg_description d
            JOIN pg_class c ON d.classoid = 'pg_class'::regclass AND c.oid = d.objoid
            JOIN pg_namespace n ON n.oid = c.relnamespace
            WHERE n.nspname = 'public'
            UNION ALL
            SELECT pg_describe_object(d.classoid, d.objoid, d.objsubid), d.description
            FROM pg_description d
            JOIN pg_proc p ON d.classoid = 'pg_proc'::regclass AND p.oid = d.objoid
            JOIN pg_namespace n ON n.oid = p.pronamespace
            WHERE n.nspname = 'public'
            """
        )
    ).all()
    assert len(rows) > 30, "catalogue de commentaires anormalement vide"
    fautifs = [(r.objet, m.group(0)) for r in rows if (m := JARGON_INTERNE.search(r.description))]
    assert fautifs == []


@pytest.mark.parametrize("table", _TABLES_TOUCHEES)
def test_commentaire_table_aligne_sur_modele(db_session: Session, table: str) -> None:
    commentaire = db_session.execute(
        text("SELECT obj_description(CAST(:t AS regclass), 'pg_class')"), {"t": table}
    ).scalar_one()
    assert commentaire == Base.metadata.tables[table].comment


@pytest.mark.parametrize(("table", "colonne"), _COLONNES_TOUCHEES)
def test_commentaire_colonne_aligne_sur_modele(
    db_session: Session, table: str, colonne: str
) -> None:
    commentaire = db_session.execute(
        text(
            """
            SELECT col_description(a.attrelid, a.attnum)
            FROM pg_attribute a
            WHERE a.attrelid = CAST(:t AS regclass) AND a.attname = :c
            """
        ),
        {"t": table, "c": colonne},
    ).scalar_one()
    assert commentaire == Base.metadata.tables[table].c[colonne].comment


def test_periode_type_documente_toutes_les_valeurs_du_check(db_session: Session) -> None:
    definition = db_session.execute(
        text(
            "SELECT pg_get_constraintdef(oid) FROM pg_constraint "
            "WHERE conname = 'ck_grandeurs_metier_periode_type_valide'"
        )
    ).scalar_one()
    commentaire = Base.metadata.tables["grandeurs_metier"].c["periode_type"].comment
    assert commentaire is not None
    for valeur in ("annuel", "mensuel", "statique"):
        assert f"'{valeur}'" in definition
        assert valeur in commentaire


def test_vent_2m_pas_annonce_comme_entree_thermique(db_session: Session) -> None:
    description = db_session.execute(
        text("SELECT description FROM grandeurs_referentiel WHERE code = 'vent_2m'")
    ).scalar_one()
    assert "Faiman" not in description
    assert "ne tient pas compte du vent" in description
