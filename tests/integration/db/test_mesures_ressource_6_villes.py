"""Tests d'integration cohérence cross-localités 6 villes pilotes.

Couvre :
- 30 series au total dans series_metadonnees (5 Conakry + 25 nouvelles)
- compte par serie dans [1820, 1826] pour les 25 nouvelles series
- total mesures_ressource 54 768 (6 villes x 9128)
- plages physiques par localite (positivite solaire, T2M elargi
  pour altitude, RH2M [0, 100])
- lapse rate altitude (T2M_moy_Labe 1025m < T2M_moy_Conakry 6m
  avec difference dans [4, 12] degC)
- niveau_confiance_derive uniforme 'B' sur les 6 villes
- DHI <= GHI avec tolerance epsilon 10% sur les 5 nouvelles villes
- roundtrip Alembic regression (downgrade 021 -> upgrade head)

Pattern avec extension multi-localites.
"""

from __future__ import annotations

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from kuma_data_core.db.models.mesures_ressource import MesureRessource

pytestmark = pytest.mark.integration


_LOCALITES_1_4: tuple[str, ...] = (
    "gin_kankan",
    "gin_kindia",
    "gin_labe",
    "gin_mamou",
    "gin_nzerekore",
)
_LOCALITE_CONAKRY: str = "gin_conakry_kaloum"
_GRANDEURS: tuple[str, ...] = ("ghi", "dni", "dhi", "t2m", "rh2m")

# Tolerance lapse rate altitude Labe (1025m) vs Conakry (6m)
# Plage [4, 12] degC absorbe variance saisonniere + effet maritime/continental.
_LAPSE_RATE_MIN_DEGC: float = 4.0
_LAPSE_RATE_MAX_DEGC: float = 12.0

_TOLERANCE_EPSILON_DHI_GHI: float = 0.10  # 10%


def _code_serie(localite_code: str, grandeur_code: str) -> str:
    """Convention naming."""
    if localite_code == _LOCALITE_CONAKRY:
        # Conakry historique : code court 'gin_conakry_<grandeur>'
        return f"gin_conakry_{grandeur_code}_nasa_power_2021_2025"
    return f"{localite_code}_{grandeur_code}_nasa_power_2021_2025"


def _id_localite(db_session: Session, code: str) -> int:
    return int(
        db_session.execute(
            text("SELECT id FROM localites WHERE code = :code"),
            {"code": code},
        ).scalar_one()
    )


# ---------------------------------------------------------------------------
# Comptes
# ---------------------------------------------------------------------------


def test_t37_30_series_brutes_au_total(db_session: Session) -> None:
    """30 series brutes dans series_metadonnees (5 Conakry
    + 25 nouvelles) sur les 5 grandeurs brutes initiales (ghi/dni/dhi/t2m/rh2m).

    Comptage filtre sur les 5 grandeurs brutes initiales pour rester stable
    face aux ajouts ulterieurs (6 series HEP, 6 series kt, 24 series
    kuma_calculs, 12 series brutes SARAH-3 + NASA POWER 1991-2020). Le filtre
    additionnel ``periode_debut = '2021-01-01'`` preserve la semantique du test.
    Filtre source ``nasa_power`` ajoute : les series ERA5-Land journalier
    2021-2025 (ghi/t2m, modele_satellitaire) partagent le profil de filtre
    des brutes et doivent etre exclues de ce comptage scopé NASA.

    Densification (migration 086) : 28 communes ajoutent ces memes 5
    grandeurs daily NASA POWER. Scope localite aux 6 villes pilotes ajoute pour
    preserver la semantique « 6 villes » de ce test (les 28 sont couvertes par
    test_densification_daily_b1).
    """
    n = db_session.scalar(
        select(func.count())
        .select_from(text("series_metadonnees"))
        .where(text("source_id = (SELECT id FROM sources WHERE code = 'nasa_power')"))
        .where(text("methode_collecte = 'modele_satellitaire'"))
        .where(text("grandeur_code IN ('ghi', 'dni', 'dhi', 't2m', 'rh2m')"))
        .where(text("periode_debut = '2021-01-01'"))
        .where(text("periode_fin = '2025-12-31'"))
        .where(
            text(
                "localite_id IN (SELECT id FROM localites WHERE code IN "
                "('gin_conakry_kaloum', 'gin_kankan', 'gin_kindia', 'gin_labe', "
                "'gin_mamou', 'gin_nzerekore'))"
            )
        )
    )
    assert n == 30


def test_t38_25_nouvelles_series_1_4_compte_par_serie(db_session: Session) -> None:
    """Chacune des 25 nouvelles series a 1820-1826 lignes."""
    codes_1_4 = [_code_serie(loc, gr) for loc in _LOCALITES_1_4 for gr in _GRANDEURS]
    rows = db_session.execute(
        text(
            """
            SELECT sm.code, count(mr.id) AS nb
            FROM series_metadonnees sm
            JOIN mesures_ressource mr ON mr.serie_id = sm.id
            WHERE sm.code = ANY(:codes)
            GROUP BY sm.code
            ORDER BY sm.code
            """
        ),
        {"codes": codes_1_4},
    ).all()
    assert len(rows) == 25
    for r in rows:
        assert 1820 <= r.nb <= 1826, f"{r.code} : {r.nb} lignes"


def test_t39_total_mesures_5_nouvelles_villes(db_session: Session) -> None:
    """Total mesures 5 grandeurs brutes initiales sur les
    5 nouvelles villes 45 640 lignes.

    Comptage filtre sur les 5 grandeurs brutes initiales pour rester stable
    face aux ajouts ulterieurs (kt ajoute 5 villes * 1825 = 9125
    lignes additionnelles dans mesures_ressource). Filtre
    source ``nasa_power`` ajoute : ERA5-Land journalier
    2021-2025 (ghi/t2m) partage le profil grandeur/ville des brutes."""
    rows = db_session.execute(
        text(
            """
            SELECT count(mr.id) AS nb
            FROM mesures_ressource mr
            JOIN series_metadonnees sm ON sm.id = mr.serie_id
            JOIN localites l ON l.id = sm.localite_id
            WHERE l.code = ANY(:codes)
              AND sm.grandeur_code IN ('ghi', 'dni', 'dhi', 't2m', 'rh2m')
              AND sm.source_id = (SELECT id FROM sources WHERE code = 'nasa_power')
            """
        ),
        {"codes": list(_LOCALITES_1_4)},
    ).all()
    assert len(rows) == 1
    n = rows[0].nb
    assert 45550 <= n <= 45650, f"Total 5 nouvelles villes : {n} (attendu 45550-45650)"


# ---------------------------------------------------------------------------
# Plages physiques par localité
# ---------------------------------------------------------------------------


def test_t40_positivite_solaire_5_nouvelles_villes(db_session: Session) -> None:
    """0 valeur negative sur les grandeurs solaires (GHI/DNI/DHI)
    pour les 5 nouvelles villes.
    """
    n_negatifs = db_session.scalar(
        text(
            """
            SELECT count(mr.id)
            FROM mesures_ressource mr
            JOIN series_metadonnees sm ON sm.id = mr.serie_id
            JOIN localites l ON l.id = sm.localite_id
            WHERE l.code = ANY(:codes)
              AND sm.grandeur_code IN ('ghi', 'dni', 'dhi')
              AND mr.valeur < 0
            """
        ).bindparams(codes=list(_LOCALITES_1_4))
    )
    assert n_negatifs == 0


def test_t40_t2m_plage_elargie_par_altitude(db_session: Session) -> None:
    """T2M des 5 nouvelles villes ∈ [10, 40] °C (plage elargie pour
    Labe altitude 1025m vs Conakry 6m).
    """
    rows = db_session.execute(
        text(
            """
            SELECT l.code AS loc, MIN(mr.valeur) AS t_min, MAX(mr.valeur) AS t_max
            FROM mesures_ressource mr
            JOIN series_metadonnees sm ON sm.id = mr.serie_id
            JOIN localites l ON l.id = sm.localite_id
            WHERE l.code = ANY(:codes) AND sm.grandeur_code = 't2m'
            GROUP BY l.code
            """
        ).bindparams(codes=list(_LOCALITES_1_4))
    ).all()
    assert len(rows) == 5
    for r in rows:
        assert 10.0 <= r.t_min <= 40.0, f"{r.loc} T2M min={r.t_min}"
        assert 10.0 <= r.t_max <= 40.0, f"{r.loc} T2M max={r.t_max}"


def test_t40_rh2m_plage_valide(db_session: Session) -> None:
    """RH2M ∈ [0, 100] % sur les 5 nouvelles villes."""
    rows = db_session.execute(
        text(
            """
            SELECT MIN(mr.valeur) AS rh_min, MAX(mr.valeur) AS rh_max
            FROM mesures_ressource mr
            JOIN series_metadonnees sm ON sm.id = mr.serie_id
            JOIN localites l ON l.id = sm.localite_id
            WHERE l.code = ANY(:codes) AND sm.grandeur_code = 'rh2m'
            """
        ).bindparams(codes=list(_LOCALITES_1_4))
    ).all()
    assert len(rows) == 1
    rh_min, rh_max = rows[0].rh_min, rows[0].rh_max
    assert 0.0 <= rh_min <= 100.0
    assert 0.0 <= rh_max <= 100.0


# ---------------------------------------------------------------------------
# Lapse rate altitude Labé < Conakry de [4, 12] degC
# ---------------------------------------------------------------------------


def test_t41a_lapse_rate_direction_labe_conakry(db_session: Session) -> None:
    """Direction physique correcte - T2M_moy_Labe < T2M_moy_Conakry.

    Sanity check minimal : Labe (1025m altitude) doit etre plus fraiche que
    Conakry (6m, cotier). Direction physique attendue.
    """
    rows = db_session.execute(
        text(
            """
            SELECT l.code AS loc, AVG(mr.valeur) AS t_moy
            FROM mesures_ressource mr
            JOIN series_metadonnees sm ON sm.id = mr.serie_id
            JOIN localites l ON l.id = sm.localite_id
            WHERE l.code IN ('gin_labe', 'gin_conakry_kaloum')
              AND sm.grandeur_code = 't2m'
            GROUP BY l.code
            """
        )
    ).all()
    t_moy = {r.loc: float(r.t_moy) for r in rows}
    assert t_moy["gin_labe"] < t_moy["gin_conakry_kaloum"], (
        f"Labe ({t_moy['gin_labe']:.2f}) doit etre plus fraiche que Conakry "
        f"({t_moy['gin_conakry_kaloum']:.2f})."
    )


@pytest.mark.xfail(
    reason=(
        "Finding 1-4 (dette D-24) : NASA POWER MERRA-2 sous-estime le "
        "gradient altitude Labe (1025m) - Conakry (6m). Delta observe 2.97 "
        "degC vs plage theorique [4, 12] (lapse rate atmospherique standard "
        "6.5 degC/km). Cause probable : resolution MERRA-2 0.5deg x 0.625deg "
        "(55 km) lisse le massif du Fouta-Djalon. La direction physique "
        "(Labe < Conakry) est preservee (cf. T41a). A investiguer en passe "
        "ulterieure : confronter ANM Guinee station 61809 Labe (1025m WMO) "
        "+ ERA5-Land 9km natif si activation phase 2+."
    ),
    strict=True,
)
def test_t41b_lapse_rate_magnitude_labe_conakry_xfail(db_session: Session) -> None:
    """Magnitude lapse rate [4, 12] degC. xfail acte du drift.

    Test conserve pour acter le constat factuel : NASA POWER MERRA-2
    montre un delta Conakry-Labe inferieur a la fourchette theorique.
    Le test passera (`xpass` = `strict=True` echoue) si NASA POWER
    corrige la resolution ou si on switch vers ERA5-Land.
    """
    rows = db_session.execute(
        text(
            """
            SELECT l.code AS loc, AVG(mr.valeur) AS t_moy
            FROM mesures_ressource mr
            JOIN series_metadonnees sm ON sm.id = mr.serie_id
            JOIN localites l ON l.id = sm.localite_id
            WHERE l.code IN ('gin_labe', 'gin_conakry_kaloum')
              AND sm.grandeur_code = 't2m'
            GROUP BY l.code
            """
        )
    ).all()
    t_moy = {r.loc: float(r.t_moy) for r in rows}
    delta = t_moy["gin_conakry_kaloum"] - t_moy["gin_labe"]
    assert _LAPSE_RATE_MIN_DEGC <= delta <= _LAPSE_RATE_MAX_DEGC, (
        f"Delta T2M Conakry-Labe = {delta:.2f} degC "
        f"(attendu [{_LAPSE_RATE_MIN_DEGC}, {_LAPSE_RATE_MAX_DEGC}])"
    )


# ---------------------------------------------------------------------------
# Niveau de confiance derive uniforme B
# ---------------------------------------------------------------------------


def test_t42_niveau_confiance_uniforme_6_villes(db_session: Session) -> None:
    """Toutes les lignes des 6 villes ont niveau_confiance_derive = 'B'
    (R4 catch-all sur methode_collecte='modele_satellitaire').
    """
    rows = db_session.execute(
        select(MesureRessource.niveau_confiance_derive, func.count()).group_by(
            MesureRessource.niveau_confiance_derive
        )
    ).all()
    distribution = {r.niveau_confiance_derive: r.count for r in rows}
    assert set(distribution.keys()) == {"B"}


# ---------------------------------------------------------------------------
# DHI <= GHI avec tolerance epsilon par localite
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("localite_code", list(_LOCALITES_1_4))
def test_t43_dhi_inferieur_ghi_par_ville(db_session: Session, localite_code: str) -> None:
    """DHI <= GHI * (1 + epsilon) sur les 5 nouvelles villes.

    Tolerance epsilon = 10%. Au plus 5% des jours en
    violation par ville.
    """
    rows = db_session.execute(
        text(
            """
            SELECT ghi.instant_mesure, ghi.valeur AS ghi, dhi.valeur AS dhi
            FROM mesures_ressource ghi
            JOIN series_metadonnees sm_ghi ON sm_ghi.id = ghi.serie_id
            JOIN mesures_ressource dhi
                 ON dhi.instant_mesure = ghi.instant_mesure
            JOIN series_metadonnees sm_dhi ON sm_dhi.id = dhi.serie_id
            JOIN localites l ON l.id = sm_ghi.localite_id
            WHERE l.code = :loc
              AND sm_ghi.grandeur_code = 'ghi'
              AND sm_dhi.grandeur_code = 'dhi'
              AND sm_dhi.localite_id = sm_ghi.localite_id
              AND ghi.valide_au IS NULL
              AND dhi.valide_au IS NULL
            """
        ),
        {"loc": localite_code},
    ).all()

    assert len(rows) >= 1820, f"{localite_code} : {len(rows)} jours communs"

    seuil = 1.0 + _TOLERANCE_EPSILON_DHI_GHI
    violations = [r for r in rows if r.dhi > r.ghi * seuil]
    pct_violations = len(violations) / len(rows) * 100.0
    assert pct_violations <= 5.0, (
        f"{localite_code} : {pct_violations:.2f}% violent DHI <= GHI*{seuil}"
    )


# ---------------------------------------------------------------------------
# Roundtrip Alembic regression
# ---------------------------------------------------------------------------


@pytest.mark.regression
def test_t44_roundtrip_alembic_022() -> None:
    """Downgrade 022 -> 021 (supprime 45 640 lignes, Conakry
    preservee) puis upgrade head re-ingere et revérifie.
    """
    from kuma_data_core.db.session import get_engine

    cfg = Config("alembic.ini")
    engine = get_engine()

    codes_1_4 = [_code_serie(loc, gr) for loc in _LOCALITES_1_4 for gr in _GRANDEURS]
    with Session(engine) as s:
        n_initial = s.scalar(
            text(
                """
                SELECT count(mr.id)
                FROM mesures_ressource mr
                JOIN series_metadonnees sm ON sm.id = mr.serie_id
                WHERE sm.code = ANY(:codes)
                """
            ).bindparams(codes=codes_1_4)
        )
    assert 45550 <= n_initial <= 45650

    command.downgrade(cfg, "021")
    with Session(engine) as s:
        n_apres_down = s.scalar(
            text(
                """
                SELECT count(mr.id)
                FROM mesures_ressource mr
                JOIN series_metadonnees sm ON sm.id = mr.serie_id
                WHERE sm.code = ANY(:codes)
                """
            ).bindparams(codes=codes_1_4)
        )
    assert n_apres_down == 0

    command.upgrade(cfg, "head")
    with Session(engine) as s:
        n_final = s.scalar(
            text(
                """
                SELECT count(mr.id)
                FROM mesures_ressource mr
                JOIN series_metadonnees sm ON sm.id = mr.serie_id
                WHERE sm.code = ANY(:codes)
                """
            ).bindparams(codes=codes_1_4)
        )
    assert 45550 <= n_final <= 45650
