"""Tests d'integration du seed horaire Kindia.

Ce seed ingere la profondeur 2001-2023 (6 grandeurs) pour Kindia en
serie **unique pleine profondeur** par grandeur. L'ingestion de masse
(138 appels NASA, 1,1 M lignes) est court-circuitee en CI par
``KUMA_SKIP_INGESTION_MASSE_HORAIRE`` : le **seed des
6 series est inconditionnel**, c'est lui qui est verifie ici. Les
assertions portent donc sur la **structure** (codes, granularite,
fenetre, source, methode), invariantes que l'ingestion ait tourne ou
non. La distribution QC reelle sur Kindia (pixel interieur) est le
livrable humain, inspecte hors CI.

Pattern herite de ``test_mesures_ressource_mensuelles.py`` (fixture
``db_session`` conftest.py, assertions sur l'etat post-``upgrade head``).
"""

from __future__ import annotations

import datetime as dt

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

pytestmark = pytest.mark.integration


_GRANDEURS_HORAIRES: tuple[str, ...] = ("ghi", "dni", "dhi", "t2m", "rh2m", "kt")
_LOCALITE_CODE: str = "gin_kindia"


def _code_serie(grandeur: str) -> str:
    return f"{_LOCALITE_CODE}_{grandeur}_nasa_power_2001_2025"


def test_3b_six_series_kindia_seedees(db_session: Session) -> None:
    """Les 6 series horaires Kindia 2001-2025 sont seedees (fenetre etendue
    in-place, extension pilote)."""
    codes = [_code_serie(g) for g in _GRANDEURS_HORAIRES]
    rows = db_session.execute(
        text("SELECT code FROM series_metadonnees WHERE code = ANY(:codes) ORDER BY code"),
        {"codes": codes},
    ).all()
    codes_trouves = {r.code for r in rows}
    assert codes_trouves == set(codes), (
        f"6 series Kindia attendues, manquantes : {set(codes) - codes_trouves}"
    )


def test_3b_metadonnees_series_kindia(db_session: Session) -> None:
    """Chaque serie Kindia : granularite horaire, fenetre 2001-2025, source/methode."""
    rows = db_session.execute(
        text(
            """
            SELECT sm.grandeur_code, sm.granularite, sm.periode_debut, sm.periode_fin,
                   sm.methode_collecte, s.code AS source_code, l.code AS localite_code
            FROM series_metadonnees sm
            JOIN sources s ON s.id = sm.source_id
            JOIN localites l ON l.id = sm.localite_id
            WHERE sm.code = ANY(:codes)
            """
        ),
        {"codes": [_code_serie(g) for g in _GRANDEURS_HORAIRES]},
    ).all()

    assert len(rows) == 6
    grandeurs_vues = set()
    for r in rows:
        grandeurs_vues.add(r.grandeur_code)
        assert r.granularite == "horaire", f"{r.grandeur_code} : granularite={r.granularite!r}"
        assert r.periode_debut == dt.date(2001, 1, 1)
        assert r.periode_fin == dt.date(2025, 12, 31)
        assert r.source_code == "nasa_power"
        assert r.methode_collecte == "modele_satellitaire"
        assert r.localite_code == _LOCALITE_CODE
    assert grandeurs_vues == set(_GRANDEURS_HORAIRES)


def test_3b_serie_unique_par_grandeur(db_session: Session) -> None:
    """Serie unique pleine profondeur : pas de variante segmentee par fenetre.

    Garantit la forme exigee par le lever passe-plat
    (``_chercher_serie_horaire_stockee`` : LIMIT 1 + couverture
    mono-serie). Aucune serie horaire Kindia ``_2001_2020`` /
    ``_2021_2023`` ne doit coexister avec la serie pleine profondeur.
    """
    for grandeur in _GRANDEURS_HORAIRES:
        n = db_session.execute(
            text(
                """
                SELECT COUNT(*) FROM series_metadonnees sm
                JOIN localites l ON l.id = sm.localite_id
                WHERE l.code = :loc
                  AND sm.grandeur_code = :grandeur
                  AND sm.granularite = 'horaire'
                """
            ),
            {"loc": _LOCALITE_CODE, "grandeur": grandeur},
        ).scalar_one()
        assert n == 1, f"{grandeur} : {n} series horaires Kindia (attendu 1, serie unique)"
