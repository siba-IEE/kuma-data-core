"""Fiches des sources : notes et métadonnées sans vocabulaire de chantier. Lecture seule."""

from __future__ import annotations

import json

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

from tests.jargon import correspondances

pytestmark = pytest.mark.integration


def _fiches(db_session: Session) -> list[tuple[str, str | None, object]]:
    lignes = db_session.execute(text("SELECT code, notes, metadonnees FROM sources")).tuples().all()
    assert lignes
    return list(lignes)


def test_toutes_les_sources_ont_une_note(db_session: Session) -> None:
    sans_note = [code for code, notes, _ in _fiches(db_session) if not (notes or "").strip()]
    assert not sans_note


def test_aucune_note_ne_porte_de_vocabulaire_de_chantier(db_session: Session) -> None:
    fautives = {
        code: trouves
        for code, notes, _ in _fiches(db_session)
        if (trouves := correspondances(notes or ""))
    }
    assert not fautives


def test_aucune_metadonnee_ne_porte_de_vocabulaire_de_chantier(db_session: Session) -> None:
    """Clés et valeurs comprises : l'objet est balayé sous sa forme JSON."""
    fiches = [(code, meta) for code, _, meta in _fiches(db_session) if meta is not None]
    assert fiches
    fautives = {
        code: trouves
        for code, meta in fiches
        if (trouves := correspondances(json.dumps(meta, ensure_ascii=False)))
    }
    assert not fautives
