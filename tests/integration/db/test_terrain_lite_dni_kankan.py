"""Tests d'integration terrain-lite DNI Kankan (calage DNI, confiance A).

Verifie l'etat apres ``alembic upgrade head`` (migrations 077 serie + mesures DNI
sol Kankan, 078 QC BSRN volet DNI). Prerequis du calage DNI : DNI sol mesure en
**confiance A**, en miroir du GHI.

- Source ``esmap_wapp`` REUTILISEE (074, pas de nouvelle source).
- Serie ``gin_kankan_dni_esmap_wapp_2021_2023`` (horaire, mesure_directe, dni).
- 17 520 mesures horaires, **toutes confiance A** (R3), **toutes QC-traitees**.

Pattern herite de ``test_terrain_lite_ghi_kankan.py``.
"""

from __future__ import annotations

import datetime as dt

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

pytestmark = pytest.mark.integration

_SOURCE = "esmap_wapp"
_SERIE = "gin_kankan_dni_esmap_wapp_2021_2023"
_LOCALITE = "gin_kankan"
_N_ATTENDU = 17520


def test_serie_metadonnees(db_session: Session) -> None:
    row = db_session.execute(
        text(
            """
            SELECT sm.granularite, sm.methode_collecte, sm.grandeur_code,
                   sm.periode_debut, sm.periode_fin,
                   s.code AS source_code, loc.code AS localite_code
            FROM series_metadonnees sm
            JOIN sources s ON s.id = sm.source_id
            JOIN localites loc ON loc.id = sm.localite_id
            WHERE sm.code = :code
            """
        ),
        {"code": _SERIE},
    ).first()
    assert row is not None, "Serie DNI sol Kankan absente (migration 077 ?)."
    assert row.granularite == "horaire"
    assert row.methode_collecte == "mesure_directe"  # condition R3 -> A
    assert row.grandeur_code == "dni"
    assert row.source_code == _SOURCE  # source 074 reutilisee
    assert row.localite_code == _LOCALITE
    assert (row.periode_debut, row.periode_fin) == (dt.date(2021, 10, 18), dt.date(2023, 10, 17))


def test_volume_17520(db_session: Session) -> None:
    n = db_session.execute(
        text(
            "SELECT COUNT(*) FROM mesures_ressource_horaires m "
            "JOIN series_metadonnees sm ON sm.id = m.serie_id WHERE sm.code = :code"
        ),
        {"code": _SERIE},
    ).scalar_one()
    assert int(n) == _N_ATTENDU


def test_confiance_a(db_session: Session) -> None:
    """Toutes les mesures en confiance A (R3) - preservee meme apres rejet QC."""
    rows = db_session.execute(
        text(
            "SELECT m.niveau_confiance_derive AS niveau, COUNT(*) AS n "
            "FROM mesures_ressource_horaires m "
            "JOIN series_metadonnees sm ON sm.id = m.serie_id "
            "WHERE sm.code = :code GROUP BY 1"
        ),
        {"code": _SERIE},
    ).all()
    assert [(r.niveau, int(r.n)) for r in rows] == [("A", _N_ATTENDU)]


def test_qc_applique_a_toutes_les_lignes(db_session: Session) -> None:
    """Le QC BSRN volet DNI (migration 078) a traite toutes les lignes."""
    n_non_qc = db_session.execute(
        text(
            "SELECT COUNT(*) FROM mesures_ressource_horaires m "
            "JOIN series_metadonnees sm ON sm.id = m.serie_id "
            "WHERE sm.code = :code "
            "AND (m.commentaire_editorial IS NULL OR m.commentaire_editorial NOT LIKE '[QC %')"
        ),
        {"code": _SERIE},
    ).scalar_one()
    assert int(n_non_qc) == 0
    # Statuts : valide_auto (valide) ou brut (rejet plausibilite DNI). Aucun autre.
    statuts = {
        r.statut
        for r in db_session.execute(
            text(
                "SELECT DISTINCT m.statut FROM mesures_ressource_horaires m "
                "JOIN series_metadonnees sm ON sm.id = m.serie_id WHERE sm.code = :code"
            ),
            {"code": _SERIE},
        ).all()
    }
    assert statuts <= {"valide_auto", "brut"}


def test_coherence_premier_ordre(db_session: Session) -> None:
    row = db_session.execute(
        text(
            "SELECT MIN(m.valeur) AS vmin, MAX(m.valeur) AS vmax, "
            "COUNT(DISTINCT m.instant_mesure) AS n_distinct "
            "FROM mesures_ressource_horaires m "
            "JOIN series_metadonnees sm ON sm.id = m.serie_id WHERE sm.code = :code"
        ),
        {"code": _SERIE},
    ).first()
    assert row is not None
    assert row.vmin >= 0.0  # clamp nuit applique a l'agregation
    assert row.vmax < 1400.0  # DNI horaire moyen sous la constante solaire (1366)
    assert int(row.n_distinct) == _N_ATTENDU
