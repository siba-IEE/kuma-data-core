"""Tests d'integration soiling : grandeur + resolveur bi-source pluie.

La grandeur ``taux_salissure_proxy`` (F1 ``calculee_volee``) ne stocke aucune serie
ni mesure ; on verifie son referentiel + le **resolveur de pluie bi-source dedie**
(``_chercher_serie_pluie_nasa``) qui epingle ``nasa_power`` (la pluie est une source
differente des PM ``cams_eac4``, le helper standard ``_chercher_serie_compagne`` la
raterait car il filtre sur ``source_id``).
"""

from __future__ import annotations

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

from kuma_data_core.api.v1.grandeurs import _chercher_serie_pluie_nasa

pytestmark = pytest.mark.integration


def test_grandeur_taux_salissure_proxy_referentiel(db_session: Session) -> None:
    """Grandeur F1 calculee_volee, unite pourcent, aucune serie/mesure stockee."""
    row = db_session.execute(
        text(
            """
            SELECT gr.famille, gr.strategie_calcul, gr.actif, u.code AS unite
            FROM grandeurs_referentiel gr JOIN unites u ON u.id = gr.unite_id
            WHERE gr.code = 'taux_salissure_proxy'
            """
        )
    ).one()
    assert row.famille == "F1"
    assert row.strategie_calcul == "calculee_volee"
    assert row.actif is True
    assert row.unite == "pourcent"
    n_series = db_session.execute(
        text("SELECT COUNT(*) FROM series_metadonnees WHERE grandeur_code = 'taux_salissure_proxy'")
    ).scalar_one()
    assert int(n_series) == 0


def test_resolveur_pluie_bisource_epingle_nasa_power(db_session: Session) -> None:
    """Le resolveur dedie renvoie la serie precipitation nasa_power (PAS une compagne
    PM cams_eac4) : c'est l'assertion centrale de la resolution bi-source."""
    conakry_id = db_session.execute(
        text("SELECT id FROM localites WHERE code = 'gin_conakry_kaloum'")
    ).scalar_one()
    serie_id = _chercher_serie_pluie_nasa(db_session, int(conakry_id))
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
    assert row.source == "nasa_power"  # bi-source : surtout PAS cams_eac4
    assert row.grandeur_code == "precipitation"
    assert row.granularite == "journalier"


def test_resolveur_pluie_none_si_absente(db_session: Session) -> None:
    """Localite sans serie de pluie (pays Guinee) -> None ; c'est la branche qui
    declenche le 400 ``INCOMPATIBILITE_SOURCE_GRANDEUR`` cote endpoint."""
    gin_id = db_session.execute(text("SELECT id FROM localites WHERE code = 'gin'")).scalar_one()
    assert _chercher_serie_pluie_nasa(db_session, int(gin_id)) is None
