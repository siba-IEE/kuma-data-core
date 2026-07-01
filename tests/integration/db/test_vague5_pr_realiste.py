"""Tests d'integration PR realiste : grandeur + resolveur PM cross-source.

La grandeur ``pr_realiste`` (F1 ``calculee_volee``) ne stocke rien ; on verifie son
referentiel + le **resolveur PM cross-source dedie** (``_chercher_serie_pm_cams``)
qui epingle ``cams_eac4`` (les PM sont une source differente du GHI source
``nasa_power`` ; symetrique du resolveur pluie, sens inverse).
"""

from __future__ import annotations

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

from kuma_data_core.api.v1.grandeurs import _chercher_serie_pm_cams

pytestmark = pytest.mark.integration


def test_grandeur_pr_realiste_referentiel(db_session: Session) -> None:
    """Grandeur F1 calculee_volee, unite sans_unite, aucune serie/mesure stockee."""
    row = db_session.execute(
        text(
            """
            SELECT gr.famille, gr.strategie_calcul, gr.actif, u.code AS unite
            FROM grandeurs_referentiel gr JOIN unites u ON u.id = gr.unite_id
            WHERE gr.code = 'pr_realiste'
            """
        )
    ).one()
    assert row.famille == "F1"
    assert row.strategie_calcul == "calculee_volee"
    assert row.actif is True
    assert row.unite == "sans_unite"
    n_series = db_session.execute(
        text("SELECT COUNT(*) FROM series_metadonnees WHERE grandeur_code = 'pr_realiste'")
    ).scalar_one()
    assert int(n_series) == 0


@pytest.mark.parametrize("grandeur", ["pm2_5", "pm10"])
def test_resolveur_pm_cross_source_epingle_cams_eac4(db_session: Session, grandeur: str) -> None:
    """Le resolveur dedie renvoie la serie PM cams_eac4 (PAS une compagne nasa_power)."""
    conakry_id = db_session.execute(
        text("SELECT id FROM localites WHERE code = 'gin_conakry_kaloum'")
    ).scalar_one()
    serie_id = _chercher_serie_pm_cams(db_session, int(conakry_id), grandeur)
    assert serie_id is not None
    row = db_session.execute(
        text(
            """
            SELECT s.code AS source, sm.grandeur_code, sm.granularite
            FROM series_metadonnees sm JOIN sources s ON s.id = sm.source_id
            WHERE sm.id = :id
            """
        ),
        {"id": serie_id},
    ).one()
    assert row.source == "cams_eac4"  # cross-source : surtout PAS nasa_power
    assert row.grandeur_code == grandeur
    assert row.granularite == "journalier"


def test_resolveur_pm_none_si_absente(db_session: Session) -> None:
    """Localite sans serie PM (pays Guinee) -> None ; branche du 400 endpoint."""
    gin_id = db_session.execute(text("SELECT id FROM localites WHERE code = 'gin'")).scalar_one()
    assert _chercher_serie_pm_cams(db_session, int(gin_id), "pm2_5") is None
