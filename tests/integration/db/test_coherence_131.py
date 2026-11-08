"""Tests d'integration de la migration 131 (nom de localite dans les libelles).

Les libelles publies des series designent leur localite par son nom
(``localites.nom``), jamais par son code. Un code de localite peut figurer
dans un code de serie cite en provenance (``derive de gin_labe_ghi_power_...``) :
la garde ne vise que le code employe comme mot entier.
"""

from __future__ import annotations

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

pytestmark = pytest.mark.integration


def test_aucun_libelle_ne_porte_un_code_de_localite(db_session: Session) -> None:
    rows = db_session.execute(
        text(
            """
            SELECT s.code, s.libelle, l.code AS localite FROM series_metadonnees s
            JOIN localites l
              ON s.libelle ~ ('(^|[^a-z0-9_])' || l.code || '($|[^a-z0-9_])')
            ORDER BY s.code
            """
        )
    ).all()
    assert rows == []


def test_series_calculees_nommees_par_localites_nom(db_session: Session) -> None:
    """Les 9 gabarits « (calcul Kuma) » des 28 communes emploient localites.nom."""
    n = db_session.execute(
        text(
            """
            SELECT COUNT(*) FROM series_metadonnees s
            JOIN localites l ON l.id = s.localite_id
            WHERE s.libelle = s.grandeur_code || ' ' || l.nom || ' '
                  || extract(year FROM s.periode_debut)::int || '-'
                  || extract(year FROM s.periode_fin)::int || ' (calcul Kuma)'
            """
        )
    ).scalar_one()
    assert n == 252


def test_libelles_restent_uniques(db_session: Session) -> None:
    total, distincts = db_session.execute(
        text("SELECT COUNT(*), COUNT(DISTINCT libelle) FROM series_metadonnees")
    ).one()
    assert total == distincts
