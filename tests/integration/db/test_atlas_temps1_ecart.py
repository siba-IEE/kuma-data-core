"""Tests d'integration de l'atlas Temps 1 : ecart inter-source etendu aux 33
(migration 091).

L'ecart inter-source (donnee-coeur de l'atlas) est materialise aux 34 points sur la
fenetre commune 2021-2023, pairwise par grandeur :

- GHI : ``ecart_relatif_referentiel`` = NASA vs SARAH-3 ; 6 pilotes (1-7b, 216) + 28
  communes (atlas, 1 008) = 1 224 lignes, 34 localites.
- DNI : ``ecart_relatif_dni_cams`` fenetre RECENTE 2021-2023 = NASA vs CAMS ; 34 points
  x 36 = 1 224 lignes (le climato 2004-2020, 1 218, reste un artefact pilote distinct).

Confiance B (inter-source, pas terrain : A reste terrain). Fenetre commune 2021-2023.

Fixture ``db_session`` (conftest.py). Base d'integration a head (091).
"""

from __future__ import annotations

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

pytestmark = pytest.mark.integration

_COMMUNE = "gin_boffa"  # une nouvelle commune temoin


def test_ecart_ghi_etendu_aux_34(db_session: Session) -> None:
    """ecart_relatif_referentiel : 34 localites, 1 224 lignes (216 pilotes + 1 008 communes)."""
    n_loc = db_session.execute(
        text(
            "SELECT COUNT(DISTINCT localite_id) FROM grandeurs_metier "
            "WHERE grandeur_code = 'ecart_relatif_referentiel'"
        )
    ).scalar_one()
    n = db_session.execute(
        text(
            "SELECT COUNT(*) FROM grandeurs_metier "
            "WHERE grandeur_code = 'ecart_relatif_referentiel'"
        )
    ).scalar_one()
    assert n_loc == 34
    assert n == 1224


def test_ecart_dni_recent_34_climato_intact(db_session: Session) -> None:
    """ecart_relatif_dni_cams : recent 2021-2023 = 34 x 36 = 1 224 ; climato 2004-2020 = 1 218."""
    recent = db_session.execute(
        text(
            "SELECT COUNT(*) FROM grandeurs_metier "
            "WHERE grandeur_code = 'ecart_relatif_dni_cams' AND annee_debut >= 2021"
        )
    ).scalar_one()
    climato = db_session.execute(
        text(
            "SELECT COUNT(*) FROM grandeurs_metier "
            "WHERE grandeur_code = 'ecart_relatif_dni_cams' AND annee_debut <= 2020"
        )
    ).scalar_one()
    assert recent == 1224
    assert climato == 1218  # inchange (anti-melange de fenetres)


def test_62_series_calculees_creees(db_session: Session) -> None:
    """62 series calculees creees par 091 (28 GHI communes + 34 DNI recent)."""
    n = db_session.execute(
        text(
            """
            SELECT COUNT(*) FROM series_metadonnees sm
            JOIN sources s ON s.id = sm.source_id
            WHERE s.code = 'kuma_calculs'
              AND sm.code LIKE '%_kuma_calculs_2021_2023'
              AND sm.libelle LIKE '%(atlas Temps 1)'
            """
        )
    ).scalar_one()
    assert n == 62


def test_confiance_b_jamais_a(db_session: Session) -> None:
    """L'ecart est B (inter-source). Aucune ligne grandeurs_metier en A (A = terrain)."""
    niveaux = {
        r[0]
        for r in db_session.execute(
            text(
                "SELECT DISTINCT niveau_confiance_derive FROM grandeurs_metier "
                "WHERE grandeur_code IN ('ecart_relatif_referentiel','ecart_relatif_dni_cams')"
            )
        ).all()
    }
    assert niveaux == {"B"}
    n_a = db_session.execute(
        text("SELECT COUNT(*) FROM grandeurs_metier WHERE niveau_confiance_derive = 'A'")
    ).scalar_one()
    assert n_a == 0


def test_bornes_physiques_recent(db_session: Session) -> None:
    """L'ecart recent reste dans la borne physique [-100, +100] (regression bug 045)."""
    row = db_session.execute(
        text(
            """
            SELECT MIN(valeur) AS mn, MAX(valeur) AS mx FROM grandeurs_metier
            WHERE grandeur_code IN ('ecart_relatif_referentiel','ecart_relatif_dni_cams')
              AND annee_debut >= 2021 AND valeur IS NOT NULL
            """
        )
    ).one()
    assert float(row.mn) >= -100.0 and float(row.mx) <= 100.0


def test_commune_temoin_ghi_et_dni_calculables(db_session: Session) -> None:
    """A gin_boffa, GHI et DNI ont chacun 36 mois d'ecart (fiche d'atlas assemblable)."""
    for grandeur in ("ecart_relatif_referentiel", "ecart_relatif_dni_cams"):
        n = db_session.execute(
            text(
                """
                SELECT COUNT(*) FROM grandeurs_metier gm
                JOIN localites l ON l.id = gm.localite_id
                WHERE gm.grandeur_code = :g AND l.code = :loc AND gm.annee_debut >= 2021
                """
            ),
            {"g": grandeur, "loc": _COMMUNE},
        ).scalar_one()
        assert n == 36, f"{_COMMUNE}/{grandeur} attendu 36 mois, obtenu {n}"
