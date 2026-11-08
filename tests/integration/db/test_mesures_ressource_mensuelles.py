"""Volumes et décomptes de ``mesures_ressource_mensuelles`` et des tables liées."""

from __future__ import annotations

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from kuma_data_core.db.models.mesures_ressource_mensuelles import MesureRessourceMensuelle

pytestmark = pytest.mark.integration


_CODES_SERIES_SARAH3_1_7A: tuple[str, ...] = (
    "gin_conakry_ghi_sarah3_2021_2023",
    "gin_kankan_ghi_sarah3_2021_2023",
    "gin_kindia_ghi_sarah3_2021_2023",
    "gin_labe_ghi_sarah3_2021_2023",
    "gin_mamou_ghi_sarah3_2021_2023",
    "gin_nzerekore_ghi_sarah3_2021_2023",
)

_CODES_SERIES_POWER_1991_2020: tuple[str, ...] = (
    "gin_conakry_ghi_power_1991_2020",
    "gin_kankan_ghi_power_1991_2020",
    "gin_kindia_ghi_power_1991_2020",
    "gin_labe_ghi_power_1991_2020",
    "gin_mamou_ghi_power_1991_2020",
    "gin_nzerekore_ghi_power_1991_2020",
)


def test_ti47_decompte_mesures_ressource_mensuelles(db_session: Session) -> None:
    """Décompte total et par source de ``mesures_ressource_mensuelles``."""
    total = db_session.scalar(select(func.count()).select_from(MesureRessourceMensuelle))
    # Pilotes (6 villes) : 216 SARAH-3 + 2 160 NASA GHI + 8 640 MERRA-2 (4 x 360)
    #   + 5 760 CERES (4 x 240) + 4 320 ERA5-Land + 1 218 + 216 CAMS DNI = 22 530
    # 28 communes : 77 280 NASA (28 x 2 760) + 1 008 SARAH-3 + 1 008 + 5 684 CAMS DNI
    #   + 20 160 ERA5-Land (28 x 3 x 240) = 105 140
    # 34 points en profondeur : 156 672 NASA (34 x 4 608) + 17 884 CAMS GHI/DHI
    #   (34 x 2 x 263) + 15 504 SARAH-3 GHI/DNI (34 x 2 x 228) = 190 060
    assert total == 317730

    n_sarah3 = db_session.execute(
        text(
            """
            SELECT COUNT(*) FROM mesures_ressource_mensuelles m
            JOIN series_metadonnees sm ON sm.id = m.serie_id
            WHERE sm.code LIKE '%sarah3%'
            """
        )
    ).scalar_one()
    # 216 (6 x 36) + 1 008 (28 x 36) + 15 504 (34 x 2 x 228)
    assert n_sarah3 == 16728

    n_cams = db_session.execute(
        text(
            """
            SELECT COUNT(*) FROM mesures_ressource_mensuelles m
            JOIN series_metadonnees sm ON sm.id = m.serie_id
            JOIN sources s ON s.id = sm.source_id
            WHERE s.code = 'cams_radiation'
            """
        )
    ).scalar_one()
    # DNI : 1 218 (6 x 203) + 216 (6 x 36) + 1 008 (28 x 36) + 5 684 (28 x 203)
    # + GHI/DHI : 17 884 (34 x 2 x 263)
    assert n_cams == 26010

    n_power_1991 = db_session.execute(
        text(
            """
            SELECT COUNT(*) FROM mesures_ressource_mensuelles m
            JOIN series_metadonnees sm ON sm.id = m.serie_id
            WHERE sm.code LIKE '%power_1991%'
            """
        )
    ).scalar_one()
    # (6 + 28) localités x 5 grandeurs x 360 mois
    assert n_power_1991 == 61200

    # Fenêtre 2001-2020 : CERES SYN1deg pur, sans le biais composite SRB/CERES du DHI.
    n_power_2001 = db_session.execute(
        text(
            """
            SELECT COUNT(*) FROM mesures_ressource_mensuelles m
            JOIN series_metadonnees sm ON sm.id = m.serie_id
            WHERE sm.code LIKE '%power_2001%'
            """
        )
    ).scalar_one()
    # (6 + 28) localités x 4 grandeurs (dhi, dni, kt, albedo) x 240 mois
    assert n_power_2001 == 32640


def test_ti48_source_sarah3_monthly_inseree(db_session: Session) -> None:
    """Source ``sarah3_monthly`` présente (CM SAF/EUMETSAT, fiabilité haute)."""
    row = db_session.execute(
        text(
            """
            SELECT code, type_source, fiabilite, organisation
            FROM sources WHERE code = 'sarah3_monthly'
            """
        )
    ).first()
    assert row is not None
    assert row.type_source == "base_donnees"
    assert row.fiabilite == "haute"
    assert "CM SAF" in row.organisation
    assert "EUMETSAT" in row.organisation


def test_ti49_12_series_brutes_1_7a_inserees(db_session: Session) -> None:
    """Les 12 séries brutes SARAH-3 et NASA POWER 1991-2020 des villes pilotes existent."""
    codes_1_7a = list(_CODES_SERIES_SARAH3_1_7A) + list(_CODES_SERIES_POWER_1991_2020)
    rows = db_session.execute(
        text("SELECT code FROM series_metadonnees WHERE code = ANY(:codes) ORDER BY code"),
        {"codes": codes_1_7a},
    ).all()
    codes_trouves = {r.code for r in rows}
    assert len(codes_trouves) == 12
    assert codes_trouves == set(codes_1_7a)


def test_ti50_exception_conakry_appliquee(db_session: Session) -> None:
    """Les séries de Conakry-Kaloum sont préfixées ``gin_conakry``, sans ``_kaloum``."""
    for code_attendu in (
        "gin_conakry_ghi_sarah3_2021_2023",
        "gin_conakry_ghi_power_1991_2020",
    ):
        n = db_session.execute(
            text("SELECT COUNT(*) FROM series_metadonnees WHERE code = :c"),
            {"c": code_attendu},
        ).scalar_one()
        assert n == 1, f"Code {code_attendu!r} attendu une fois, trouve {n}"

    for code_interdit in (
        "gin_conakry_kaloum_ghi_sarah3_2021_2023",
        "gin_conakry_kaloum_ghi_power_1991_2020",
    ):
        n = db_session.execute(
            text("SELECT COUNT(*) FROM series_metadonnees WHERE code = :c"),
            {"c": code_interdit},
        ).scalar_one()
        assert n == 0, f"Code {code_interdit!r} ne devrait pas exister (exception D-32)"


# === Decompte mesures_ressource derive du seed =============================
# Part NASA daily dérivée du seed (robuste à un re-seed) ; le reste vient de seeds
# dédiés, hors NASA_DAILY_PAYLOADS, donc figé ici :
# 64 272 (pilotes) + 51 128 précipitation (28 x 1 826) + 153 384 ERA5-Land
# (3 x 28 x 1 826) + 95 424 PM EAC4 (2 x 28 x 1 704) + 4 147 830 NASA profondeur
# (34 points, 10 grandeurs) + 815 796 CAMS GHI/DHI/DNI (102 x 7 998)
# + 1 088 680 AOD et ozone EAC4 (136 x 8 005)
_MESURES_NON_NASA_DAILY: int = 6416514


def _mesures_ressource_attendu() -> int:
    """Compte attendu de ``mesures_ressource`` : non-sentinelles du seed NASA + part non NASA."""
    from kuma_data_core.db.seeds.nasa_power_daily_seed_data import NASA_DAILY_PAYLOADS

    nasa = sum(
        1
        for payload in NASA_DAILY_PAYLOADS.values()
        for vals in payload["properties"]["parameter"].values()
        for v in vals.values()
        if v != -999.0
    )
    return _MESURES_NON_NASA_DAILY + nasa


def test_ti51_mesures_ressource_journalier_inchange(db_session: Session) -> None:
    """Décompte de ``mesures_ressource``, déterministe en mode offline."""
    n_ressource = db_session.execute(text("SELECT COUNT(*) FROM mesures_ressource")).scalar_one()
    assert n_ressource == _mesures_ressource_attendu()


def test_ti52_decomptes_cumules_post_1_7a(db_session: Session) -> None:
    """Décomptes de sources, séries brutes et mesures.

    Les grandeurs calculées référentielles (écarts et rangs inter-source) sont
    exclues du compte de séries.
    """
    n_sources = db_session.execute(text("SELECT COUNT(*) FROM sources")).scalar_one()
    n_series_hors_calculees_ref = db_session.execute(
        text(
            """
            SELECT COUNT(*) FROM series_metadonnees
            WHERE grandeur_code NOT IN ('ecart_relatif_referentiel',
                                        'rang_referentiel_temporel',
                                        'rang_referentiel_spatial',
                                        'ecart_relatif_dni_cams')
            """
        )
    ).scalar_one()
    n_ressource = db_session.execute(text("SELECT COUNT(*) FROM mesures_ressource")).scalar_one()
    n_mens = db_session.execute(
        text("SELECT COUNT(*) FROM mesures_ressource_mensuelles")
    ).scalar_one()
    assert n_sources == 15
    # 770 (pilotes et NASA des 28 communes)
    # 28 communes : 28 SARAH-3 + 28 + 28 CAMS DNI + 168 calculées (6 par commune)
    #   + 56 humidex et variabilité + 28 précipitation + 84 + 84 ERA5-Land + 56 PM = 560
    # 34 points : 340 + 340 NASA profondeur + 238 CAMS + 68 SARAH-3 + 136 EAC4 = 1 122
    # horaire : 252 (28 communes) + 18 (pilotes) = 270
    assert n_series_hors_calculees_ref == 2722
    assert n_ressource == _mesures_ressource_attendu()
    # Voir test_ti47.
    assert n_mens == 317730
