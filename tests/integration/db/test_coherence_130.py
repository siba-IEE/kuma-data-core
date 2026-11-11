"""Notes publiques du rang spatial : elles nomment les localités classées. Lecture seule."""

from __future__ import annotations

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

from tests.jargon import correspondances

pytestmark = pytest.mark.integration


def _notes(db_session: Session) -> list[tuple[str, str, str]]:
    """(code de série, nom de la localité, note publique) des séries du rang spatial."""
    lignes = (
        db_session.execute(
            text(
                """
                SELECT sm.code, l.nom, sm.note_publique
                FROM series_metadonnees sm JOIN localites l ON l.id = sm.localite_id
                WHERE sm.grandeur_code = 'rang_referentiel_spatial'
                """
            )
        )
        .tuples()
        .all()
    )
    assert lignes
    return list(lignes)


def test_aucune_note_ne_porte_de_vocabulaire_de_chantier(db_session: Session) -> None:
    fautives = {
        code: trouves for code, _, note in _notes(db_session) if (trouves := correspondances(note))
    }
    assert not fautives


def test_chaque_note_nomme_toutes_les_localites_classees(db_session: Session) -> None:
    """Le rang n'a de sens que par rapport à l'ensemble classé : la note le donne en entier."""
    lignes = _notes(db_session)
    noms = {nom for _, nom, _ in lignes}
    incompletes = {code: sorted(nom for nom in noms if nom not in note) for code, _, note in lignes}
    assert not {code: absents for code, absents in incompletes.items() if absents}
    # Le rang maximal annoncé est le nombre de localités classées.
    assert all(f"de 1 (irradiation la plus faible) à {len(noms)} " in n for _, _, n in lignes)
