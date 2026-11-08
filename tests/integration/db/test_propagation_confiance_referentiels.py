"""Écart et rang référentiels prennent le niveau de leurs entrées (règle P, plafond B).

Une mesure NASA POWER journalière de Conakry passe en C dans une transaction
annulée ; l'écart et le rang recalculés pour son mois passent en C.
"""

from __future__ import annotations

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

from kuma_data_core.services.grandeurs.referentiels import (
    calculer_et_inserer_ecart_inter_source,
    calculer_et_inserer_rang_temporel,
)

pytestmark = pytest.mark.integration

_GHI_JOUR = "gin_conakry_ghi_nasa_power_2021_2025"


def _id(session: Session, code: str) -> int:
    return int(
        session.execute(
            text("SELECT id FROM series_metadonnees WHERE code = :c"), {"c": code}
        ).scalar_one()
    )


def _preparer(session: Session, code_serie_calculee: str) -> int:
    """Passe le 2022-03-15 en C et clôt les lignes courantes de la série calculée."""
    n = session.execute(
        text(
            "UPDATE mesures_ressource SET niveau_confiance_override = 'C', "
            "commentaire_editorial = 'test propagation' "
            "WHERE serie_id = :s AND instant_mesure = '2022-03-15' AND valide_au IS NULL"
        ),
        {"s": _id(session, _GHI_JOUR)},
    ).rowcount  # type: ignore[attr-defined]
    assert n == 1
    serie_id = _id(session, code_serie_calculee)
    session.execute(
        text(
            "UPDATE grandeurs_metier SET valide_au = now() "
            "WHERE series_metadonnees_id = :s AND valide_au IS NULL"
        ),
        {"s": serie_id},
    )
    return serie_id


def _niveaux(session: Session, serie_id: int) -> dict[tuple[int, int], str]:
    rows = session.execute(
        text(
            "SELECT annee_debut, mois, niveau_confiance_derive FROM grandeurs_metier "
            "WHERE series_metadonnees_id = :s AND valide_au IS NULL"
        ),
        {"s": serie_id},
    ).all()
    return {(int(r.annee_debut), int(r.mois)): r.niveau_confiance_derive for r in rows}


def test_ecart_mois_en_c(db_session: Session) -> None:
    serie_id = _preparer(db_session, "gin_conakry_ecart_relatif_referentiel_kuma_calculs_2021_2023")
    calculer_et_inserer_ecart_inter_source(
        session=db_session,
        contextes=[
            {
                "localite_id": int(
                    db_session.execute(
                        text("SELECT id FROM localites WHERE code = 'gin_conakry_kaloum'")
                    ).scalar_one()
                ),
                "code_serie_nasa_daily": _GHI_JOUR,
                "code_serie_reference": "gin_conakry_ghi_sarah3_2021_2023",
                "series_metadonnees_id": serie_id,
            }
        ],
        grandeur_code="ecart_relatif_referentiel",
        annee_debut=2021,
        annee_fin=2023,
    )
    niveaux = _niveaux(db_session, serie_id)
    assert len(niveaux) == 36
    assert niveaux.pop((2022, 3)) == "C"
    assert set(niveaux.values()) == {"B"}


def test_rang_temporel_mois_en_c(db_session: Session) -> None:
    serie_id = _preparer(db_session, "gin_conakry_rang_referentiel_temporel_kuma_calculs_2021_2025")
    calculer_et_inserer_rang_temporel(
        session=db_session,
        contextes=[
            {
                "localite_id": int(
                    db_session.execute(
                        text("SELECT id FROM localites WHERE code = 'gin_conakry_kaloum'")
                    ).scalar_one()
                ),
                "code_serie_kuma_daily": _GHI_JOUR,
                "code_serie_power_1991_2020": "gin_conakry_ghi_power_1991_2020",
                "series_metadonnees_id": serie_id,
            }
        ],
    )
    niveaux = _niveaux(db_session, serie_id)
    assert len(niveaux) == 60
    assert niveaux.pop((2022, 3)) == "C"
    assert set(niveaux.values()) == {"B"}
