"""Tests d'integration du backfill Conakry.

Ce backfill etend la serie pilote Conakry a la pleine profondeur
2001-2023 par renommage in-place (``_2021_2023`` -> ``_2001_2023``, puis
``_2001_2025`` a l'extension pilote,
``periode_debut=2001``) + ingestion 2001-2020 dans le meme ``serie_id``.
L'ingestion de masse est court-circuitee en CI (``KUMA_SKIP_INGESTION_MASSE_HORAIRE``) ;
le renommage + ``periode_debut`` sont inconditionnels (verifies ici).

Point de surete (le coeur du backfill) : le QC est scope a 2001-2020, donc les
decisions precedentes sur 2021-2023 sont preservees. Le test de
non-regression verifie que les **29 rejets DHI 2021-2023** restent
``brut`` apres le backfill (invariant CI / local).
"""

from __future__ import annotations

import datetime as dt

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

pytestmark = pytest.mark.integration


_GRANDEURS_HORAIRES: tuple[str, ...] = ("ghi", "dni", "dhi", "t2m", "rh2m", "kt")


def _code_nouveau(grandeur: str) -> str:
    return f"gin_conakry_{grandeur}_nasa_power_2001_2025"


def _code_ancien(grandeur: str) -> str:
    return f"gin_conakry_{grandeur}_nasa_power_2021_2023"


def test_3d_series_conakry_renommees_pleine_profondeur(db_session: Session) -> None:
    """Les 6 series Conakry horaire portent le code _2001_2025 et periode_debut=2001."""
    rows = db_session.execute(
        text(
            """
            SELECT code, periode_debut, periode_fin, granularite
            FROM series_metadonnees
            WHERE code = ANY(:codes)
            """
        ),
        {"codes": [_code_nouveau(g) for g in _GRANDEURS_HORAIRES]},
    ).all()
    assert len(rows) == 6, "6 series Conakry _2001_2025 attendues"
    for r in rows:
        assert r.granularite == "horaire"
        assert r.periode_debut == dt.date(2001, 1, 1)
        assert r.periode_fin == dt.date(2025, 12, 31)


def test_3d_ancien_code_2021_2023_disparu(db_session: Session) -> None:
    """L'ancien code pilote _2021_2023 n'existe plus (renomme in-place)."""
    n = db_session.execute(
        text("SELECT COUNT(*) FROM series_metadonnees WHERE code = ANY(:codes)"),
        {"codes": [_code_ancien(g) for g in _GRANDEURS_HORAIRES]},
    ).scalar_one()
    assert n == 0, "l'ancien code _2021_2023 ne doit plus exister apres le renommage"


def test_3d_non_regression_rejets_dhi_2021_2023_preserves(db_session: Session) -> None:
    """Non-regression : les 29 rejets DHI 2021-2023 restent brut apres le backfill.

    Scope explicite instant >= 2021-01-01 pour etre invariant que le
    backfill 2001-2020 ait tourne (local) ou non (CI). La migration
    055 avait conserve 29 lignes DHI Conakry 2021-2023 en ``brut`` (rejet
    plausibilite hors borne) ; le QC scope du backfill ne doit pas les toucher.
    """
    n_brut_dhi_2021 = db_session.execute(
        text(
            """
            SELECT COUNT(*)
            FROM mesures_ressource_horaires mh
            JOIN series_metadonnees sm ON sm.id = mh.serie_id
            WHERE sm.code = :code
              AND mh.statut = 'brut'
              AND mh.valide_au IS NULL
              AND (mh.instant_mesure AT TIME ZONE 'UTC')::date >= :borne
            """
        ),
        {"code": _code_nouveau("dhi"), "borne": dt.date(2021, 1, 1)},
    ).scalar_one()
    assert n_brut_dhi_2021 == 29, (
        f"29 rejets DHI 2021-2023 (lot 2) attendus preserves, trouve {n_brut_dhi_2021}"
    )

    # Les autres grandeurs n'avaient aucun rejet 2021-2023 : inchange.
    for grandeur in ("ghi", "dni", "t2m", "rh2m", "kt"):
        n_brut = db_session.execute(
            text(
                """
                SELECT COUNT(*)
                FROM mesures_ressource_horaires mh
                JOIN series_metadonnees sm ON sm.id = mh.serie_id
                WHERE sm.code = :code
                  AND mh.statut = 'brut'
                  AND mh.valide_au IS NULL
                  AND (mh.instant_mesure AT TIME ZONE 'UTC')::date >= :borne
                """
            ),
            {"code": _code_nouveau(grandeur), "borne": dt.date(2021, 1, 1)},
        ).scalar_one()
        assert n_brut == 0, f"{grandeur} 2021-2023 : {n_brut} brut (attendu 0, lot 2 inchange)"
