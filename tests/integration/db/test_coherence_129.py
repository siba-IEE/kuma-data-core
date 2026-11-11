"""Descriptions des grandeurs : présentes, sans vocabulaire de chantier. Lecture seule."""

from __future__ import annotations

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

from tests.jargon import correspondances

pytestmark = pytest.mark.integration


def _descriptions(db_session: Session) -> dict[str, str | None]:
    descriptions = dict(
        db_session.execute(text("SELECT code, description FROM grandeurs_referentiel"))
        .tuples()
        .all()
    )
    assert descriptions
    return descriptions


def test_toutes_les_grandeurs_ont_une_description(db_session: Session) -> None:
    sans = [code for code, d in _descriptions(db_session).items() if not (d or "").strip()]
    assert not sans


def test_aucune_description_ne_porte_de_vocabulaire_de_chantier(db_session: Session) -> None:
    fautives = {
        code: trouves
        for code, description in _descriptions(db_session).items()
        if (trouves := correspondances(description or ""))
    }
    assert not fautives
