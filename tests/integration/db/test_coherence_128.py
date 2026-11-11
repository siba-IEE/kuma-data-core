"""Notes des localités : sans vocabulaire de chantier. Lecture seule."""

from __future__ import annotations

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

from tests.jargon import correspondances

pytestmark = pytest.mark.integration


def test_aucune_note_de_localite_ne_porte_de_vocabulaire_de_chantier(db_session: Session) -> None:
    notes = dict(
        db_session.execute(text("SELECT code, notes FROM localites WHERE notes IS NOT NULL"))
        .tuples()
        .all()
    )
    assert notes
    fautives = {code: trouves for code, note in notes.items() if (trouves := correspondances(note))}
    assert not fautives
