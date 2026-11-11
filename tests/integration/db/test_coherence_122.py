"""Commentaires du catalogue : sans vocabulaire de chantier, renvois vérifiables.

Les commentaires de tables, colonnes, vues et fonctions partent avec l'édition
publique. Lecture seule.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

from tests.jargon import correspondances

pytestmark = pytest.mark.integration

_RACINE = Path(__file__).resolve().parents[3]
_URL_DEPOT = "https://github.com/siba-IEE/kuma-data-core/blob/main/"

# Tables, colonnes et vues (pg_class), puis fonctions (pg_proc) du schéma public.
_SQL_COMMENTAIRES = text(
    """
    SELECT c.relname || COALESCE('.' || a.attname, '') AS objet, d.description
    FROM pg_description d
    JOIN pg_class c ON c.oid = d.objoid AND d.classoid = 'pg_class'::regclass
    JOIN pg_namespace n ON n.oid = c.relnamespace
    LEFT JOIN pg_attribute a ON a.attrelid = c.oid AND a.attnum = d.objsubid AND d.objsubid > 0
    WHERE n.nspname = 'public'
    UNION ALL
    SELECT p.proname || '()', d.description
    FROM pg_description d
    JOIN pg_proc p ON p.oid = d.objoid AND d.classoid = 'pg_proc'::regclass
    JOIN pg_namespace n ON n.oid = p.pronamespace
    WHERE n.nspname = 'public'
    ORDER BY 1
    """
)


def _commentaires(db_session: Session) -> dict[str, str]:
    return dict(db_session.execute(_SQL_COMMENTAIRES).tuples().all())


def test_le_catalogue_est_commente(db_session: Session) -> None:
    """Garde contre un test vide : tables, colonnes, vues et fonction sont bien lues."""
    commentaires = _commentaires(db_session)
    for objet in (
        "series_metadonnees",
        "series_metadonnees.granularite",
        "v_grandeurs_metier_courantes",
        "valider_hierarchie_localites()",
    ):
        assert objet in commentaires


def test_aucun_commentaire_ne_porte_de_vocabulaire_de_chantier(db_session: Session) -> None:
    fautifs = {
        objet: trouves
        for objet, description in _commentaires(db_session).items()
        if (trouves := correspondances(description))
    }
    assert not fautifs


def test_les_renvois_au_depot_designent_des_fichiers_existants(db_session: Session) -> None:
    """Un commentaire qui cite un document du dépôt donne son URL, et le fichier existe."""
    renvois = {
        (objet, url)
        for objet, description in _commentaires(db_session).items()
        for url in re.findall(r"https?://\S+", description)
    }
    assert any(url.startswith(_URL_DEPOT) for _, url in renvois)
    absents = sorted(
        (objet, url)
        for objet, url in renvois
        if url.startswith(_URL_DEPOT) and not (_RACINE / url.removeprefix(_URL_DEPOT)).is_file()
    )
    assert not absents
