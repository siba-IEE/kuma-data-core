"""Séries ``rang_referentiel_temporel`` : aucun lien de documentation. Lecture seule.

La grandeur n'a pas de fiche méthodologique dans le dépôt : ses séries ne
citent rien plutôt qu'un chemin qui ne mène nulle part.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

pytestmark = pytest.mark.integration

_RACINE = Path(__file__).resolve().parents[3]
_FICHE = "docs/methodologie/grandeurs/rang_referentiel_temporel.md"


def test_les_series_sans_fiche_ne_citent_aucun_lien(db_session: Session) -> None:
    lignes = db_session.execute(
        text(
            "SELECT code, methode_collecte_doc, url_documentation FROM series_metadonnees "
            "WHERE grandeur_code = 'rang_referentiel_temporel'"
        )
    ).all()
    assert lignes
    assert not (_RACINE / _FICHE).is_file(), (
        "La fiche existe désormais : ses séries peuvent citer son URL, ce test est à revoir."
    )
    avec_lien = [code for code, methode, url in lignes if methode is not None or url is not None]
    assert not avec_lien


def test_plus_aucune_serie_ne_cite_le_chemin_de_la_fiche_absente(db_session: Session) -> None:
    n = db_session.execute(
        text(
            "SELECT count(*) FROM series_metadonnees "
            "WHERE methode_collecte_doc LIKE :motif OR url_documentation LIKE :motif"
        ),
        {"motif": f"%{_FICHE}"},
    ).scalar_one()
    assert n == 0
