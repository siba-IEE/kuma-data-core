"""Libellés des séries : sans vocabulaire de chantier, tous distincts. Lecture seule."""

from __future__ import annotations

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

from tests.jargon import correspondances

pytestmark = pytest.mark.integration


def _libelles(db_session: Session) -> list[tuple[str, str]]:
    lignes = db_session.execute(text("SELECT code, libelle FROM series_metadonnees")).tuples().all()
    assert lignes
    return list(lignes)


def test_aucun_libelle_ne_porte_de_vocabulaire_de_chantier(db_session: Session) -> None:
    fautifs = {
        code: trouves
        for code, libelle in _libelles(db_session)
        if (trouves := correspondances(libelle))
    }
    assert not fautifs


def test_les_libelles_sont_distincts(db_session: Session) -> None:
    libelles = [libelle for _, libelle in _libelles(db_session)]
    assert len(set(libelles)) == len(libelles)


def test_les_series_d_ecart_suivent_un_seul_modele_de_libelle(db_session: Session) -> None:
    """« <grandeur> mensuel <localité> <début>-<fin> », sans mention ajoutée."""
    hors_modele = db_session.execute(
        text(
            """
            SELECT code, libelle FROM series_metadonnees
            WHERE grandeur_code IN ('ecart_relatif_referentiel', 'ecart_relatif_dni_cams')
              AND libelle !~ ('^' || grandeur_code || ' mensuel \\S+ \\d{4}-\\d{4}$')
            """
        )
    ).all()
    assert not hors_modele
