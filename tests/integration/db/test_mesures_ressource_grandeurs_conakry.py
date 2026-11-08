"""Tests d'intégration cohérence cross-grandeurs Conakry.

Couvre :
- Compte par série pour les 5 séries Conakry
- Plages physiques (positivité, bornes tropicales sur T2M / RH2M)
- Inégalité physique DHI ≤ GHI avec tolérance ε ≈ 5-10 %
- Niveau de confiance dérivé identique pour les 5 séries (R4 catch-all)
- Aller-retour Alembic 019 → 020 → 019 → 020 (regression, base éphémère)

Pattern ``db_session`` fixture conftest.py.
"""

from __future__ import annotations

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from kuma_data_core.db.models.mesures_ressource import MesureRessource
from tests._migrations import BaseEphemere, verifier_aller_retour

pytestmark = pytest.mark.integration


_CODES_SERIES_1_3: tuple[str, ...] = (
    "gin_conakry_dni_nasa_power_2021_2025",
    "gin_conakry_dhi_nasa_power_2021_2025",
    "gin_conakry_t2m_nasa_power_2021_2025",
    "gin_conakry_rh2m_nasa_power_2021_2025",
)

_CODE_SERIE_GHI: str = "gin_conakry_ghi_nasa_power_2021_2025"

# Tolérance ε sur DHI ≤ GHI : 5-10% absorbe les
# artefacts de moyennes daily NASA POWER (CERES SYN1deg agrégé séparément).
_TOLERANCE_EPSILON_DHI_GHI: float = 0.10  # 10%


def _ids_series(db_session: Session, codes: tuple[str, ...]) -> dict[str, int]:
    """Mapping code_serie -> serie_id."""
    rows = db_session.execute(
        text("SELECT id, code FROM series_metadonnees WHERE code = ANY(:codes)"),
        {"codes": list(codes)},
    ).all()
    return {r.code: int(r.id) for r in rows}


# ---------------------------------------------------------------------------
# Compte par série
# ---------------------------------------------------------------------------


def test_t27_5_series_conakry_existent(db_session: Session) -> None:
    """5 séries Conakry seedées (4 nouvelles + 1 GHI)."""
    tous_codes = (*_CODES_SERIES_1_3, _CODE_SERIE_GHI)
    ids = _ids_series(db_session, tous_codes)
    assert len(ids) == 5


def test_t28_compte_par_serie(db_session: Session) -> None:
    """Pour chaque série Conakry, 1825-1826 lignes
    (1826 jours moins sentinelles éventuelles).
    """
    tous_codes = (*_CODES_SERIES_1_3, _CODE_SERIE_GHI)
    ids = _ids_series(db_session, tous_codes)
    for code, serie_id in ids.items():
        n = db_session.scalar(
            select(func.count())
            .select_from(MesureRessource)
            .where(MesureRessource.serie_id == serie_id)
        )
        assert 1820 <= n <= 1826, f"{code} : {n} lignes (attendu 1820-1826)"


def test_t29_total_mesures_conakry(db_session: Session) -> None:
    """Total mesures Conakry 9128 (5 séries, sentinelles filtrées)."""
    tous_codes = (*_CODES_SERIES_1_3, _CODE_SERIE_GHI)
    ids = _ids_series(db_session, tous_codes)
    n = db_session.scalar(
        select(func.count())
        .select_from(MesureRessource)
        .where(MesureRessource.serie_id.in_(ids.values()))
    )
    assert 9100 <= n <= 9130, f"Total Conakry : {n} lignes (attendu 9100-9130)"


# ---------------------------------------------------------------------------
# Plages physiques
# ---------------------------------------------------------------------------


def test_t30_positivite_solaire(db_session: Session) -> None:
    """Toutes valeurs solaires (GHI, DNI, DHI) ≥ 0."""
    codes_solaires = (
        _CODE_SERIE_GHI,
        "gin_conakry_dni_nasa_power_2021_2025",
        "gin_conakry_dhi_nasa_power_2021_2025",
    )
    ids = _ids_series(db_session, codes_solaires)
    n_negatifs = db_session.scalar(
        select(func.count())
        .select_from(MesureRessource)
        .where(MesureRessource.serie_id.in_(ids.values()))
        .where(MesureRessource.valeur < 0)
    )
    assert n_negatifs == 0


def test_t31_t2m_plage_tropicale(db_session: Session) -> None:
    """T2M Conakry ∈ [15, 40] °C (climat tropical côtier)."""
    ids = _ids_series(db_session, ("gin_conakry_t2m_nasa_power_2021_2025",))
    rows = db_session.execute(
        select(func.min(MesureRessource.valeur), func.max(MesureRessource.valeur)).where(
            MesureRessource.serie_id == next(iter(ids.values()))
        )
    ).first()
    assert rows is not None
    t_min, t_max = rows
    assert 15.0 <= t_min <= 40.0, f"T2M min={t_min}"
    assert 15.0 <= t_max <= 40.0, f"T2M max={t_max}"


def test_t32_rh2m_plage_valide(db_session: Session) -> None:
    """RH2M ∈ [0, 100] %."""
    ids = _ids_series(db_session, ("gin_conakry_rh2m_nasa_power_2021_2025",))
    rows = db_session.execute(
        select(func.min(MesureRessource.valeur), func.max(MesureRessource.valeur)).where(
            MesureRessource.serie_id == next(iter(ids.values()))
        )
    ).first()
    assert rows is not None
    rh_min, rh_max = rows
    assert 0.0 <= rh_min <= 100.0, f"RH2M min={rh_min}"
    assert 0.0 <= rh_max <= 100.0, f"RH2M max={rh_max}"


# ---------------------------------------------------------------------------
# Cohérence cross-grandeurs DHI ≤ GHI avec tolérance ε (Q2)
# ---------------------------------------------------------------------------


def test_t33_dhi_inferieur_ghi_avec_tolerance(db_session: Session) -> None:
    """Pour chaque jour avec GHI ET DHI, DHI <= GHI * (1 + epsilon).

    Tolerance epsilon = 10% pour absorber les artefacts de moyennes daily
    NASA POWER (CERES SYN1deg agrege separement GHI et DHI).
    """
    ids = _ids_series(
        db_session,
        (_CODE_SERIE_GHI, "gin_conakry_dhi_nasa_power_2021_2025"),
    )
    id_ghi = ids[_CODE_SERIE_GHI]
    id_dhi = ids["gin_conakry_dhi_nasa_power_2021_2025"]

    # JOIN sur instant_mesure (les 2 séries ont les mêmes jours, modulo sentinelles)
    rows = db_session.execute(
        text(
            """
            SELECT ghi.instant_mesure, ghi.valeur AS ghi, dhi.valeur AS dhi
            FROM mesures_ressource ghi
            JOIN mesures_ressource dhi
                 ON dhi.instant_mesure = ghi.instant_mesure
                 AND dhi.serie_id = :id_dhi
            WHERE ghi.serie_id = :id_ghi
              AND ghi.valide_au IS NULL
              AND dhi.valide_au IS NULL
            """
        ),
        {"id_ghi": id_ghi, "id_dhi": id_dhi},
    ).all()

    assert len(rows) >= 1820, f"Trop peu de jours communs : {len(rows)}"

    seuil = 1.0 + _TOLERANCE_EPSILON_DHI_GHI
    violations = [r for r in rows if r.dhi > r.ghi * seuil]
    pct_violations = len(violations) / len(rows) * 100.0
    # Tolerance globale : au plus 5% de jours violent DHI <= GHI*1.1
    assert pct_violations <= 5.0, (
        f"{pct_violations:.2f}% de jours violent DHI <= GHI*{seuil} "
        f"(au plus 5% admis). Echantillon : "
        f"{[(str(r.instant_mesure), r.ghi, r.dhi) for r in violations[:3]]}"
    )


# ---------------------------------------------------------------------------
# Niveau de confiance dérivé identique
# ---------------------------------------------------------------------------


def test_t34_niveau_confiance_derive_uniforme_b(db_session: Session) -> None:
    """Les 5 séries Conakry ont toutes niveau_confiance_derive = 'B'
    (R4 catch-all sur methode_collecte='modele_satellitaire').
    """
    tous_codes = (*_CODES_SERIES_1_3, _CODE_SERIE_GHI)
    ids = _ids_series(db_session, tous_codes)
    rows = db_session.execute(
        select(MesureRessource.niveau_confiance_derive, func.count())
        .where(MesureRessource.serie_id.in_(ids.values()))
        .group_by(MesureRessource.niveau_confiance_derive)
    ).all()
    distribution = {r.niveau_confiance_derive: r.count for r in rows}
    assert set(distribution.keys()) == {"B"}, (
        f"Niveaux trouvés : {distribution}, attendu uniquement 'B'."
    )


# ---------------------------------------------------------------------------
# Aucune ligne sentinelle
# ---------------------------------------------------------------------------


def test_t35_aucune_ligne_sentinelle_1_3(db_session: Session) -> None:
    """Aucune ligne valeur = -999.0 dans les 4 nouvelles séries."""
    ids = _ids_series(db_session, _CODES_SERIES_1_3)
    n = db_session.scalar(
        select(func.count())
        .select_from(MesureRessource)
        .where(MesureRessource.serie_id.in_(ids.values()))
        .where(MesureRessource.valeur == -999.0)
    )
    assert n == 0


# ---------------------------------------------------------------------------
# Roundtrip Alembic regression
# ---------------------------------------------------------------------------


_SQL_N_MESURES_SERIES = """
    SELECT count(mr.id)
    FROM mesures_ressource mr
    JOIN series_metadonnees sm ON sm.id = mr.serie_id
    WHERE sm.code = ANY(:codes)
"""


@pytest.mark.regression
def test_t36_roundtrip_alembic_020(base_ephemere: BaseEphemere) -> None:
    """019 → 020 → 019 → 020 sur base éphémère : 4 séries x 1826 jours partent puis reviennent.

    Le GHI Conakry (migration 018) est préservé par le downgrade de 020.
    """

    def controler_019(base: BaseEphemere) -> None:
        assert base.scalar(_SQL_N_MESURES_SERIES, codes=list(_CODES_SERIES_1_3)) == 0
        assert base.scalar(_SQL_N_MESURES_SERIES, codes=[_CODE_SERIE_GHI]) == 1826

    def controler_020(base: BaseEphemere) -> None:
        for code in _CODES_SERIES_1_3:
            assert base.scalar(_SQL_N_MESURES_SERIES, codes=[code]) == 1826, code
        assert base.scalar(_SQL_N_MESURES_SERIES, codes=list(_CODES_SERIES_1_3)) == 7304
        assert base.scalar(_SQL_N_MESURES_SERIES, codes=[_CODE_SERIE_GHI]) == 1826
        assert base.scalar("SELECT count(*) FROM mesures_ressource") == 9130

    verifier_aller_retour(
        base_ephemere,
        cible="019",
        testee="020",
        controler_cible=controler_019,
        controler_testee=controler_020,
    )
