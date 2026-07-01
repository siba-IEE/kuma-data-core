"""Tests d'integration terrain-lite GHI Kankan (confiance A).

Verifie l'etat apres ``alembic upgrade head`` (migrations 074 source esmap_wapp,
075 serie + mesures GHI sol Kankan, 076 QC BSRN). Premiere grandeur Kuma en
**confiance A** (mesure sol directe).

- Source ``esmap_wapp`` (base de donnees, fiabilite haute, licence CC-BY-4.0).
- Serie ``gin_kankan_ghi_esmap_wapp_2021_2023`` (horaire, mesure_directe, ghi).
- 17 520 mesures horaires, **toutes confiance A** (R3), **toutes QC-traitees**.

Pattern herite de ``test_vague4_cams_2021_2023.py``.
"""

from __future__ import annotations

import datetime as dt

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

pytestmark = pytest.mark.integration

_SOURCE = "esmap_wapp"
_SERIE = "gin_kankan_ghi_esmap_wapp_2021_2023"
_LOCALITE = "gin_kankan"
_N_ATTENDU = 17520


# === Source ================================================================


def test_source_esmap_wapp(db_session: Session) -> None:
    row = db_session.execute(
        text(
            "SELECT type_source, fiabilite, metadonnees->>'licence' AS licence "
            "FROM sources WHERE code = :code"
        ),
        {"code": _SOURCE},
    ).first()
    assert row is not None, "Source esmap_wapp absente (migration 074 ?)."
    assert row.type_source == "base_donnees"
    assert row.fiabilite == "haute"  # indispensable pour R3 -> A
    assert row.licence == "CC-BY-4.0"


# === Serie =================================================================


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
    assert row is not None, "Serie GHI sol Kankan absente (migration 075 ?)."
    assert row.granularite == "horaire"
    assert row.methode_collecte == "mesure_directe"  # condition R3 -> A
    assert row.grandeur_code == "ghi"
    assert row.source_code == _SOURCE
    assert row.localite_code == _LOCALITE
    assert (row.periode_debut, row.periode_fin) == (dt.date(2021, 10, 18), dt.date(2023, 10, 17))


# === Volume + confiance A ==================================================


def test_volume_17520(db_session: Session) -> None:
    n = db_session.execute(
        text(
            "SELECT COUNT(*) FROM mesures_ressource_horaires m "
            "JOIN series_metadonnees sm ON sm.id = m.serie_id WHERE sm.code = :code"
        ),
        {"code": _SERIE},
    ).scalar_one()
    assert int(n) == _N_ATTENDU  # 2 ans pleins horaires (2 x 8760)


def test_confiance_a(db_session: Session) -> None:
    """Toutes les mesures en confiance A (R3) - coeur du lot terrain-lite."""
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


# === QC ====================================================================


def test_qc_applique_a_toutes_les_lignes(db_session: Session) -> None:
    """Le QC BSRN (migration 076) a traite toutes les lignes (aucune brut non commentee)."""
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
    # Statuts : valide_auto (valide) ou brut (rejet plausibilite). Aucun autre.
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


# === Coherence physique ====================================================


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
    assert row.vmax < 1500.0  # GHI horaire moyen dans le plausible (BSRN possible 2100)
    assert int(row.n_distinct) == _N_ATTENDU  # pas de doublon d'instant (1 serie horaire)
