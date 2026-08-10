"""Tests d'integration structure du parc horaire NASA POWER aux 34 points.

Couvre les migrations du volet horaire du chantier profondeur (lots de
communes + pilotes) : 28 communes x 9 grandeurs en 2001-2025, extension
in-place des 36 series pilotes historiques, 18 series pilotes nouvelles
(vents, precipitation).

Discipline heritee des tests de la Vague 3 : **structure seulement**,
invariante sous ``KUMA_SKIP_INGESTION_MASSE_HORAIRE`` (les comptes de
mesures dependent du garde-fou de masse, jamais testes ici).
"""

from __future__ import annotations

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

pytestmark = pytest.mark.integration

_GRANDEURS: tuple[str, ...] = (
    "ghi",
    "dni",
    "dhi",
    "t2m",
    "rh2m",
    "kt",
    "vent_2m",
    "vent_10m",
    "precipitation",
)


def test_252_series_horaires_communes(db_session: Session) -> None:
    """28 communes x 9 grandeurs = 252 series horaires nasa_power 2001-2025."""
    rows = db_session.execute(
        text(
            """
            SELECT sm.code, sm.granularite, sm.methode_collecte,
                   sm.periode_debut, sm.periode_fin, sm.note_publique
            FROM series_metadonnees sm
            JOIN sources s ON s.id = sm.source_id
            JOIN localites l ON l.id = sm.localite_id
            WHERE s.code = 'nasa_power' AND sm.granularite = 'horaire'
              AND l.type_localite = 'commune'
              AND l.code NOT IN ('gin_conakry_kaloum', 'gin_kankan', 'gin_kindia',
                                 'gin_labe', 'gin_mamou', 'gin_nzerekore')
            """
        )
    ).all()
    assert len(rows) == 252
    for r in rows:
        assert r.code.endswith("_nasa_power_2001_2025")
        assert r.methode_collecte == "modele_satellitaire"
        assert str(r.periode_debut) == "2001-01-01"
        assert str(r.periode_fin) == "2025-12-31"
        assert r.note_publique is not None and r.note_publique.strip()


def test_54_series_horaires_pilotes(db_session: Session) -> None:
    """6 pilotes x 9 grandeurs = 54 series horaires : 36 etendues in-place
    (codes repointes _2001_2025, periode_fin 2025) + 18 nouvelles."""
    rows = db_session.execute(
        text(
            """
            SELECT sm.code, sm.grandeur_code, sm.periode_debut, sm.periode_fin,
                   sm.note_publique
            FROM series_metadonnees sm
            JOIN sources s ON s.id = sm.source_id
            JOIN localites l ON l.id = sm.localite_id
            WHERE s.code = 'nasa_power' AND sm.granularite = 'horaire'
              AND l.code IN ('gin_conakry_kaloum', 'gin_kankan', 'gin_kindia',
                             'gin_labe', 'gin_mamou', 'gin_nzerekore')
            """
        )
    ).all()
    assert len(rows) == 54
    for r in rows:
        assert r.code.endswith("_nasa_power_2001_2025")
        assert str(r.periode_debut) == "2001-01-01"
        assert str(r.periode_fin) == "2025-12-31"
        assert r.note_publique is not None and r.note_publique.strip()
    par_grandeur = dict.fromkeys(_GRANDEURS, 0)
    for r in rows:
        par_grandeur[r.grandeur_code] += 1
    assert all(n == 6 for n in par_grandeur.values()), par_grandeur


def test_anciens_codes_2001_2023_disparus(db_session: Session) -> None:
    """L'extension in-place n'a laisse aucun code pilote _2001_2023."""
    n = db_session.execute(
        text(
            "SELECT COUNT(*) FROM series_metadonnees "
            "WHERE code LIKE '%\\_nasa\\_power\\_2001\\_2023' ESCAPE '\\'"
        )
    ).scalar_one()
    assert n == 0


def test_serie_horaire_unique_par_point_grandeur(db_session: Session) -> None:
    """Mono-serie horaire nasa_power par (localite, grandeur) sur les 34 points :
    exigence du routeur horaire (resolution LIMIT 1) et des endpoints F2."""
    rows = db_session.execute(
        text(
            """
            SELECT sm.localite_id, sm.grandeur_code, COUNT(*) AS n
            FROM series_metadonnees sm
            JOIN sources s ON s.id = sm.source_id
            WHERE s.code = 'nasa_power' AND sm.granularite = 'horaire'
            GROUP BY sm.localite_id, sm.grandeur_code
            HAVING COUNT(*) <> 1
            """
        )
    ).all()
    assert rows == []
    total = db_session.execute(
        text(
            """
            SELECT COUNT(*) FROM series_metadonnees sm
            JOIN sources s ON s.id = sm.source_id
            WHERE s.code = 'nasa_power' AND sm.granularite = 'horaire'
            """
        )
    ).scalar_one()
    # 34 points x 9 grandeurs (la fenetre est commune : contrainte compagnes F2).
    assert total == 306


def test_fenetre_commune_par_localite(db_session: Session) -> None:
    """Toutes les series horaires nasa_power d'une localite partagent la meme
    periode_debut (le resolveur de compagnes F2 exige l'egalite stricte)."""
    rows = db_session.execute(
        text(
            """
            SELECT sm.localite_id, COUNT(DISTINCT sm.periode_debut) AS n
            FROM series_metadonnees sm
            JOIN sources s ON s.id = sm.source_id
            WHERE s.code = 'nasa_power' AND sm.granularite = 'horaire'
            GROUP BY sm.localite_id
            HAVING COUNT(DISTINCT sm.periode_debut) <> 1
            """
        )
    ).all()
    assert rows == []
