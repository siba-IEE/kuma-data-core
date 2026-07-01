"""Tests d'integration CAMS Radiation DNI recent 2021-2023.

Verifie l'etat apres ``alembic upgrade head`` (migration 073). Series recentes
**separees** ``*_dni_cams_2021_2023`` (pas de fusion avec la climato 2004-2020) ;
meme source ``cams_radiation``, grandeur ``dni``, mensuel, confiance B.

- Structure (toujours) : 6 series, fenetre 2021-01->2023-12.
- Donnees (gardees, skip si seed non peuple) : 216 mesures, confiance B, plage
  physique.

Pattern herite de ``test_vague4_lot_b_cams.py``.
"""

from __future__ import annotations

import datetime as dt

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

pytestmark = pytest.mark.integration

_LOCALITES: tuple[str, ...] = (
    "gin_conakry_kaloum",
    "gin_kankan",
    "gin_kindia",
    "gin_labe",
    "gin_mamou",
    "gin_nzerekore",
)
_SOURCE = "cams_radiation"


def _alias(localite_code: str) -> str:
    return "gin_conakry" if localite_code == "gin_conakry_kaloum" else localite_code


def _code(localite_code: str) -> str:
    return f"{_alias(localite_code)}_dni_cams_2021_2023"


def _tous_les_codes() -> list[str]:
    return [_code(loc) for loc in _LOCALITES]


def _seed_peuple(db_session: Session) -> bool:
    n = db_session.execute(
        text(
            """
            SELECT COUNT(*) FROM mesures_ressource_mensuelles m
            JOIN series_metadonnees sm ON sm.id = m.serie_id
            WHERE sm.code = ANY(:codes)
            """
        ),
        {"codes": _tous_les_codes()},
    ).scalar_one()
    return int(n) > 0


# === Structure (toujours) ==================================================


def test_6_series_recentes_seedees(db_session: Session) -> None:
    codes = _tous_les_codes()
    assert len(codes) == 6
    trouves = {
        r.code
        for r in db_session.execute(
            text("SELECT code FROM series_metadonnees WHERE code = ANY(:codes)"),
            {"codes": codes},
        ).all()
    }
    assert trouves == set(codes), f"Series manquantes : {set(codes) - trouves}"


def test_metadonnees_series(db_session: Session) -> None:
    rows = db_session.execute(
        text(
            """
            SELECT sm.granularite, sm.periode_debut, sm.periode_fin,
                   sm.methode_collecte, sm.grandeur_code, s.code AS source_code
            FROM series_metadonnees sm JOIN sources s ON s.id = sm.source_id
            WHERE sm.code = ANY(:codes)
            """
        ),
        {"codes": _tous_les_codes()},
    ).all()
    assert len(rows) == 6
    for r in rows:
        assert r.source_code == _SOURCE
        assert r.grandeur_code == "dni"
        assert r.methode_collecte == "modele_satellitaire"
        assert r.granularite == "mensuel"
        assert (r.periode_debut, r.periode_fin) == (dt.date(2021, 1, 1), dt.date(2023, 12, 31))


def test_climato_2004_2020_distincte_du_recent(db_session: Session) -> None:
    """Les series climato 2004-2020 restent distinctes des recentes 2021-2023 (pas de fusion
    de fenetres). Densifiees aux 28 communes (migration 095) : 6 pilotes
    (071) + 28 communes = 34."""
    n = db_session.execute(
        text("SELECT COUNT(*) FROM series_metadonnees WHERE code LIKE '%_dni_cams_2004_2020'")
    ).scalar_one()
    assert int(n) == 34


# === Données (gardées) =====================================================


def test_volume_216(db_session: Session) -> None:
    if not _seed_peuple(db_session):
        pytest.skip(
            "Seed CAMS 2021-2023 non peuple (lancer scripts/preparer_seed_cams.py 2021 2023)."
        )
    n = db_session.execute(
        text(
            "SELECT COUNT(*) FROM mesures_ressource_mensuelles m "
            "JOIN series_metadonnees sm ON sm.id = m.serie_id WHERE sm.code = ANY(:codes)"
        ),
        {"codes": _tous_les_codes()},
    ).scalar_one()
    # 6 series x 36 mois (2021-01 -> 2023-12) = 216.
    assert int(n) == 216, f"mensuelles CAMS 2021-2023 = {n} (attendu 216)"


def test_confiance_b(db_session: Session) -> None:
    if not _seed_peuple(db_session):
        pytest.skip("Seed CAMS 2021-2023 non peuple.")
    niveaux = {
        r[0]
        for r in db_session.execute(
            text(
                "SELECT DISTINCT m.niveau_confiance_derive FROM mesures_ressource_mensuelles m "
                "JOIN series_metadonnees sm ON sm.id = m.serie_id WHERE sm.code = ANY(:codes)"
            ),
            {"codes": _tous_les_codes()},
        ).all()
    }
    assert niveaux == {"B"}, f"Niveaux inattendus : {niveaux}"


def test_coherence_premier_ordre(db_session: Session) -> None:
    """Plage physique DNI (attrape un oubli du /1000 ou du /nb_jours)."""
    if not _seed_peuple(db_session):
        pytest.skip("Seed CAMS 2021-2023 non peuple.")
    row = db_session.execute(
        text(
            "SELECT MIN(m.valeur) AS mn, MAX(m.valeur) AS mx FROM mesures_ressource_mensuelles m "
            "JOIN series_metadonnees sm ON sm.id = m.serie_id WHERE sm.code = ANY(:codes)"
        ),
        {"codes": _tous_les_codes()},
    ).one()
    assert float(row.mn) >= 1.0 and float(row.mx) <= 9.0, (
        f"DNI CAMS 2021-2023 hors plage [1.0, 9.0] : min={row.mn}, max={row.mx}"
    )
