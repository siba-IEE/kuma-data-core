"""Provenance des référentiels de calage : en clair, renvois vérifiables. Lecture seule."""

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


def _provenances(db_session: Session) -> list[tuple[str, str, str]]:
    lignes = (
        db_session.execute(text("SELECT code, saison, provenance FROM referentiels_calage"))
        .tuples()
        .all()
    )
    assert lignes
    return list(lignes)


def test_aucune_provenance_ne_porte_de_vocabulaire_de_chantier(db_session: Session) -> None:
    fautives = {
        (code, saison): trouves
        for code, saison, provenance in _provenances(db_session)
        if (trouves := correspondances(provenance))
    }
    assert not fautives


def test_les_renvois_au_depot_designent_des_fichiers_existants(db_session: Session) -> None:
    renvois = {
        url.rstrip(".,;")
        for _, _, provenance in _provenances(db_session)
        for url in re.findall(r"https?://\S+", provenance)
    }
    assert any(url.startswith(_URL_DEPOT) for url in renvois)
    absents = sorted(
        url
        for url in renvois
        if url.startswith(_URL_DEPOT) and not (_RACINE / url.removeprefix(_URL_DEPOT)).is_file()
    )
    assert not absents


def test_la_serie_sol_citee_est_celle_du_referentiel(db_session: Session) -> None:
    ecarts = db_session.execute(
        text(
            "SELECT code, saison FROM referentiels_calage "
            "WHERE position(serie_sol IN provenance) = 0"
        )
    ).all()
    assert not ecarts
