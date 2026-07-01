"""Tests d'integration de la densification CAMS Radiation DNI (migration 089).

Les 28 nouvelles communes chef-lieu recoivent la reference CAMS Radiation DNI
all-sky (mensuel 2021-2023), seedee offline (seed densification separe). C'est la
2e reference d'ecart inter-source aux nouveaux points (apres SARAH-3 GHI) :
avec NASA daily DNI deja en base, l'ecart DNI NASA vs CAMS est calculable aux
33 sur 2021-2023 = couche atlas (triptyque NASA / SARAH-3 / CAMS).

- 28 series (gin_<commune>_dni_cams_2021_2023), granularite mensuel, source
  cams_radiation ;
- 1 008 mesures = 28 x 36 mois (jeu CAMS fige, deterministe) ;
- 6 pilotes intacts (071/073, zero retrofit) ; climato 2004-2020 inchangee ;
- overlap NASA daily DNI + CAMS DNI sur 2021-2023 (ecart DNI calculable).

Fixture ``db_session`` (conftest.py). Base d'integration a head (089).
"""

from __future__ import annotations

import datetime as dt

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

from kuma_data_core.db.seeds.localites_prefectures_seed_data import PREFECTURES_GUINEE

pytestmark = pytest.mark.integration

_SOURCE = "cams_radiation"
_COMMUNES: tuple[str, ...] = tuple(
    p["commune_code"] for p in PREFECTURES_GUINEE if p["existante"] is None
)


def _codes_series() -> list[str]:
    return [f"{c}_dni_cams_2021_2023" for c in _COMMUNES]


def _seed_peuple(db_session: Session) -> bool:
    n = db_session.execute(
        text(
            """
            SELECT COUNT(*) FROM mesures_ressource_mensuelles m
            JOIN series_metadonnees sm ON sm.id = m.serie_id
            WHERE sm.code = ANY(:codes)
            """
        ),
        {"codes": _codes_series()},
    ).scalar_one()
    return int(n) > 0


def test_28_series_cams(db_session: Session) -> None:
    rows = db_session.execute(
        text(
            """
            SELECT sm.granularite, sm.grandeur_code, sm.periode_debut, sm.periode_fin,
                   sm.methode_collecte, s.code AS source_code
            FROM series_metadonnees sm
            JOIN sources s ON s.id = sm.source_id
            WHERE sm.code = ANY(:codes)
            """
        ),
        {"codes": _codes_series()},
    ).all()
    assert len(rows) == 28
    for r in rows:
        assert r.source_code == _SOURCE
        assert r.grandeur_code == "dni"
        assert r.granularite == "mensuel"
        assert r.methode_collecte == "modele_satellitaire"
        assert (r.periode_debut, r.periode_fin) == (dt.date(2021, 1, 1), dt.date(2023, 12, 31))


def test_volume_1008_mesures(db_session: Session) -> None:
    if not _seed_peuple(db_session):
        pytest.skip(
            "Seed CAMS densification non peuple "
            "(lancer scripts/preparer_seed_cams.py 2021 2023 --densification)."
        )
    n = db_session.execute(
        text(
            """
            SELECT COUNT(*) FROM mesures_ressource_mensuelles m
            JOIN series_metadonnees sm ON sm.id = m.serie_id
            WHERE sm.code = ANY(:codes)
            """
        ),
        {"codes": _codes_series()},
    ).scalar_one()
    assert int(n) == 1008  # 28 communes x 36 mois (2021-2023)


def test_confiance_b_et_plage_physique(db_session: Session) -> None:
    if not _seed_peuple(db_session):
        pytest.skip("Seed CAMS densification non peuple.")
    niveaux = {
        r[0]
        for r in db_session.execute(
            text(
                "SELECT DISTINCT m.niveau_confiance_derive FROM mesures_ressource_mensuelles m "
                "JOIN series_metadonnees sm ON sm.id = m.serie_id WHERE sm.code = ANY(:codes)"
            ),
            {"codes": _codes_series()},
        ).all()
    }
    assert niveaux == {"B"}
    row = db_session.execute(
        text(
            "SELECT MIN(m.valeur) AS mn, MAX(m.valeur) AS mx FROM mesures_ressource_mensuelles m "
            "JOIN series_metadonnees sm ON sm.id = m.serie_id WHERE sm.code = ANY(:codes)"
        ),
        {"codes": _codes_series()},
    ).one()
    # Plage physique DNI (attrape un oubli du /1000 ou du /nb_jours).
    assert float(row.mn) >= 1.0 and float(row.mx) <= 9.0, f"DNI hors plage : {row.mn}..{row.mx}"


def test_6_pilotes_et_climato_intacts(db_session: Session) -> None:
    """Series CAMS DNI : 34 recentes (073 + 089) et 34 climato (071 + 095). Les
    6 pilotes restent intacts (zero retrofit) ; la densification n'AJOUTE que des communes."""
    n_recent = db_session.execute(
        text("SELECT COUNT(*) FROM series_metadonnees WHERE code LIKE '%_dni_cams_2021_2023'")
    ).scalar_one()
    # 6 pilotes + 28 communes = 34 series recentes (les pilotes intacts).
    assert int(n_recent) == 34
    n_climato = db_session.execute(
        text("SELECT COUNT(*) FROM series_metadonnees WHERE code LIKE '%_dni_cams_2004_2020'")
    ).scalar_one()
    # 6 pilotes (071) + 28 communes (migration 095) = 34 ; pilotes intacts.
    assert int(n_climato) == 34


def test_overlap_nasa_cams_dni_ecart_calculable(db_session: Session) -> None:
    """Aux nouveaux points, NASA daily DNI ET CAMS DNI couvrent 2021-2023 -> ecart calculable."""
    if not _seed_peuple(db_session):
        pytest.skip("Seed CAMS densification non peuple.")
    n_nasa = db_session.execute(
        text(
            """
            SELECT COUNT(*) FROM mesures_ressource mr
            JOIN series_metadonnees sm ON sm.id = mr.serie_id
            JOIN localites l ON l.id = sm.localite_id
            WHERE l.code = 'gin_boffa' AND sm.grandeur_code = 'dni'
            AND sm.granularite = 'journalier'
            AND mr.instant_mesure BETWEEN '2021-01-01' AND '2023-12-31'
            """
        )
    ).scalar_one()
    n_cams = db_session.execute(
        text(
            """
            SELECT COUNT(*) FROM mesures_ressource_mensuelles m
            JOIN series_metadonnees sm ON sm.id = m.serie_id
            WHERE sm.code = 'gin_boffa_dni_cams_2021_2023'
            """
        )
    ).scalar_one()
    assert n_nasa > 0 and int(n_cams) == 36  # overlap DNI reel -> ecart inter-source calculable
