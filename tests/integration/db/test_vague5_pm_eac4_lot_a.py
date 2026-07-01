"""Tests d'integration PM2.5/PM10 EAC4.

Verifie l'etat apres ``alembic upgrade head`` (migration 081). Deux familles :

- **Structure** (toujours) : source ``cams_eac4`` (fiabilite haute), unite
  ``microgramme_par_metre_cube``, grandeurs ``pm2_5``/``pm10`` (F1, stockee), 12
  series journalieres seedees, source/granularite/methode,
  ``periode_fin = 2025-08-31`` (couverture reelle EAC4).
- **Donnees** (gardees, skip si le seed n'est pas peuple) : volume 20 448, mesures
  confiance B, et **invariant physique PM10 >= PM2.5** par (ville, date) - l'assertion
  centrale (PM10 inclut les PM2.5).

Pattern herite de ``test_vague5_precipitation_lot_b.py`` / ``test_vague4_lot_a_era5_land.py``.
"""

from __future__ import annotations

import datetime as dt

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

pytestmark = pytest.mark.integration

_LOCALITES: tuple[str, ...] = (
    "gin_conakry_kaloum",
    "gin_kankan",
    "gin_kindia",
    "gin_labe",
    "gin_mamou",
    "gin_nzerekore",
)
_GRANDEURS: tuple[str, ...] = ("pm2_5", "pm10")
_SOURCE = "cams_eac4"


def _alias(localite_code: str) -> str:
    return "gin_conakry" if localite_code == "gin_conakry_kaloum" else localite_code


def _code_serie(localite_code: str, grandeur: str) -> str:
    return f"{_alias(localite_code)}_{grandeur}_cams_eac4_2021_2025"


def _tous_les_codes() -> list[str]:
    return [_code_serie(loc, g) for loc in _LOCALITES for g in _GRANDEURS]


def _seed_peuple(db_session: Session) -> bool:
    # Scope aux 12 series pilotes : la densification (migration 098) ajoute du PM
    # pour 28 communes ; ce test reste cantonne aux pilotes (les 28 -> test dedie).
    n = db_session.execute(
        text(
            """
            SELECT COUNT(*) FROM mesures_ressource m
            JOIN series_metadonnees sm ON sm.id = m.serie_id
            WHERE sm.code = ANY(:codes)
            """
        ),
        {"codes": _tous_les_codes()},
    ).scalar_one()
    return int(n) > 0


# === Structure (toujours) ==================================================


def test_source_cams_eac4_seedee(db_session: Session) -> None:
    row = db_session.execute(
        text("SELECT type_source, fiabilite, langue, doi FROM sources WHERE code = :c"),
        {"c": _SOURCE},
    ).one()
    assert row.type_source == "base_donnees"
    assert row.fiabilite == "haute"
    assert row.langue == "en"
    assert row.doi is None  # non confirme, non invente


def test_unite_microgramme_seedee(db_session: Session) -> None:
    row = db_session.execute(
        text(
            "SELECT symbole, grandeur, code_unite_si, facteur_conversion_si "
            "FROM unites WHERE code = 'microgramme_par_metre_cube'"
        )
    ).one()
    assert row.symbole == "µg/m³"
    assert row.grandeur == "concentration_massique"
    assert row.code_unite_si == "kilogramme_par_metre_cube"
    assert float(row.facteur_conversion_si) == 1e-9


def test_grandeurs_pm_seedees(db_session: Session) -> None:
    rows = db_session.execute(
        text(
            """
            SELECT gr.code, gr.famille, gr.strategie_calcul, gr.actif, u.code AS unite
            FROM grandeurs_referentiel gr JOIN unites u ON u.id = gr.unite_id
            WHERE gr.code IN ('pm2_5', 'pm10') ORDER BY gr.code
            """
        )
    ).all()
    assert {r.code for r in rows} == {"pm2_5", "pm10"}
    for r in rows:
        assert r.famille == "F1"
        assert r.strategie_calcul == "stockee"
        assert r.actif is True
        assert r.unite == "microgramme_par_metre_cube"


def test_12_series_seedees(db_session: Session) -> None:
    codes = _tous_les_codes()
    assert len(codes) == 12
    trouves = {
        r.code
        for r in db_session.execute(
            text("SELECT code FROM series_metadonnees WHERE code = ANY(:codes)"),
            {"codes": codes},
        ).all()
    }
    assert trouves == set(codes), f"Series manquantes : {set(codes) - trouves}"


def test_metadonnees_series(db_session: Session) -> None:
    rows = db_session.execute(
        text(
            """
            SELECT sm.granularite, sm.periode_debut, sm.periode_fin,
                   sm.methode_collecte, s.code AS source_code
            FROM series_metadonnees sm JOIN sources s ON s.id = sm.source_id
            WHERE sm.code = ANY(:codes)
            """
        ),
        {"codes": _tous_les_codes()},
    ).all()
    assert len(rows) == 12
    for r in rows:
        assert r.source_code == _SOURCE
        assert r.methode_collecte == "modele_satellitaire"
        assert r.granularite == "journalier"
        # Couverture reelle EAC4 : 2021-01-01 a 2025-08-31 (latence reanalyse).
        assert (r.periode_debut, r.periode_fin) == (dt.date(2021, 1, 1), dt.date(2025, 8, 31))


# === Donnees (gardees) =====================================================


def test_volume_mesures(db_session: Session) -> None:
    if not _seed_peuple(db_session):
        pytest.skip("Seed EAC4 non peuple (lancer preparer_seed_cams_eac4.py).")
    n = db_session.execute(
        text(
            """
            SELECT COUNT(*) FROM mesures_ressource m
            JOIN series_metadonnees sm ON sm.id = m.serie_id
            WHERE sm.code = ANY(:codes)
            """
        ),
        {"codes": _tous_les_codes()},
    ).scalar_one()
    # 6 villes x 1704 jours (2021-01-01 -> 2025-08-31) x 2 grandeurs = 20 448.
    # Scope pilotes (la densification ajoute 95 424 mesures PM aux 28, test dedie).
    assert int(n) == 20_448, f"mesures PM EAC4 pilotes = {n} (attendu 20 448)"


def test_confiance_b_et_plage(db_session: Session) -> None:
    """Toutes les mesures en B ; concentrations > 0 et < 2000 ug/m3."""
    if not _seed_peuple(db_session):
        pytest.skip("Seed EAC4 non peuple.")
    row = db_session.execute(
        text(
            """
            SELECT MIN(m.valeur) AS mn, MAX(m.valeur) AS mx,
                   COUNT(*) FILTER (WHERE m.niveau_confiance_derive <> 'B') AS non_b
            FROM mesures_ressource m
            JOIN series_metadonnees sm ON sm.id = m.serie_id
            WHERE sm.code = ANY(:codes)
            """
        ),
        {"codes": _tous_les_codes()},
    ).one()
    assert int(row.non_b) == 0, "mesures PM hors confiance B"
    assert float(row.mn) >= 0.0
    assert float(row.mx) < 2000.0, f"concentration PM implausible : {row.mx}"


def test_invariant_pm10_superieur_pm2_5(db_session: Session) -> None:
    """Invariant physique : PM10 >= PM2.5 par (ville, date) (PM10 inclut PM2.5)."""
    if not _seed_peuple(db_session):
        pytest.skip("Seed EAC4 non peuple.")
    violations = db_session.execute(
        text(
            """
            SELECT COUNT(*) FROM mesures_ressource m25
            JOIN series_metadonnees s25 ON s25.id = m25.serie_id AND s25.grandeur_code = 'pm2_5'
            JOIN series_metadonnees s10 ON s10.localite_id = s25.localite_id
                                       AND s10.grandeur_code = 'pm10'
                                       AND s10.source_id = s25.source_id
            JOIN mesures_ressource m10 ON m10.serie_id = s10.id
                                      AND m10.instant_mesure = m25.instant_mesure
            WHERE s25.code = ANY(:codes) AND m25.valeur > m10.valeur * 1.0001
            """
        ),
        {"codes": [_code_serie(loc, "pm2_5") for loc in _LOCALITES]},
    ).scalar_one()
    assert int(violations) == 0, f"{violations} (ville, date) avec PM2.5 > PM10"
