"""HEP : la série amont doit être GHI ; les appels des migrations 027 et 092 le sont.

Les deux migrations appellent ``calculer_et_inserer_hep`` avec, pour chaque
série ``<commune>_hep_kuma_calculs_2021_2025``, la série
``<commune>_ghi_nasa_power_2021_2025``. Le recalcul de ces 34 paires sur la
base courante redonne les lignes stockées, contrôle de grandeur compris.
"""

from __future__ import annotations

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

from kuma_data_core.services.grandeurs.hep import calculer_et_inserer_hep

pytestmark = pytest.mark.integration

_SQL_PAIRES = text(
    r"""
    SELECT h.code AS code_hep,
           replace(h.code, '_hep_kuma_calculs_2021_2025', '_ghi_nasa_power_2021_2025') AS code_ghi
    FROM series_metadonnees h
    WHERE h.code LIKE '%\_hep\_kuma\_calculs\_2021\_2025'
    ORDER BY h.code
    """
)

_SQL_LIGNES = text(
    """
    SELECT periode_type, annee_debut, annee_fin, mois, version_formule, valeur,
           niveau_confiance_derive
    FROM grandeurs_metier
    WHERE series_metadonnees_id = (SELECT id FROM series_metadonnees WHERE code = :code)
      AND valide_au IS NULL
    ORDER BY periode_type, annee_debut, annee_fin, mois
    """
)


def test_amont_non_ghi_rejete(db_session: Session) -> None:
    """Une série T2M de la même localité en amont : ``RuntimeError`` avant toute insertion."""
    with pytest.raises(RuntimeError, match=r"grandeur_code='t2m', attendu 'ghi'"):
        calculer_et_inserer_hep(
            session=db_session,
            code_serie_hep="gin_conakry_hep_kuma_calculs_2021_2025",
            code_serie_ghi_amont="gin_conakry_t2m_nasa_power_2021_2025",
        )


def test_appels_des_migrations_recalcules_a_l_identique(db_session: Session) -> None:
    """Les 34 paires (6 villes de 027, 28 de 092) passent le contrôle et redonnent leurs lignes."""
    paires = db_session.execute(_SQL_PAIRES).all()
    assert len(paires) == 34
    for code_hep, code_ghi in paires:
        avant = [tuple(r) for r in db_session.execute(_SQL_LIGNES, {"code": code_hep})]
        assert len(avant) == 65, code_hep
        db_session.execute(
            text(
                "DELETE FROM grandeurs_metier WHERE series_metadonnees_id = "
                "(SELECT id FROM series_metadonnees WHERE code = :code)"
            ),
            {"code": code_hep},
        )
        calculer_et_inserer_hep(
            session=db_session, code_serie_hep=code_hep, code_serie_ghi_amont=code_ghi
        )
        apres = [tuple(r) for r in db_session.execute(_SQL_LIGNES, {"code": code_hep})]
        assert apres == avant, code_hep
