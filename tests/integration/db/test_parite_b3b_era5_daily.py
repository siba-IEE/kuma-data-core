"""Tests d'integration de la parite (migration 097).

Porte ERA5-Land DAILY 2021-2025 (ghi/t2m/vent_10m) aux 28 communes, meme traitement que les
6 pilotes (migration 069, moitie journaliere ; meme dataset timeseries). ERA5 = raffineur HORS
axe d'incertitude. Garanties verifiees :

- **Anti-regression pilote** : les 6 pilotes gardent leurs series + mesures ERA5 daily
  (097 n'ingere que des communes) ; somme byte-stable.
- **Brute seulement / hors axe** : ZERO grandeurs_metier ne reference une serie ERA5.
- **Caveat ghi DATA-DRIVEN** : memes 14 communes (degenerescence stable cross-fenetre) ;
  **vent_10m sans caveat en daily** (le caveat module ne concerne que le mensuel).
- Couverture 1826 j/commune/grandeur. Confiance B partout, 0 en A.
"""

from __future__ import annotations

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

pytestmark = pytest.mark.integration

_PILOTES_SQL = (
    "('gin_conakry_kaloum','gin_kankan','gin_kindia','gin_labe','gin_mamou','gin_nzerekore')"
)
_COMMUNE = "gin_boffa"

_JOURS_FENETRE = 1826  # 2021-2025 calendrier complet
_N_COMMUNES = 28
_N_GRANDEURS = 3
_TOTAL_COMMUNES = _N_COMMUNES * _N_GRANDEURS * _JOURS_FENETRE  # 153 384
_TOTAL_PILOTES = 6 * _N_GRANDEURS * _JOURS_FENETRE  # 32 868
_CLIM = "s.code = 'ecmwf_era5_land' AND sm.granularite = 'journalier'"

# Sommes byte-stables (mesurees sur DB fraiche 001->097, seed CDS offline deterministe).
_SOMME_PILOTES = 353598.6010999996
_SOMME_COMMUNES = 1679453.8345999683
_SOMME_BOFFA_GHI = 9253.304000000015


def _scalar(db_session: Session, sql: str) -> float:
    return float(db_session.execute(text(sql)).scalar_one())


def test_pilotes_inchanges(db_session: Session) -> None:
    """Anti-regression : les 6 pilotes gardent 18 series daily + 32 868 mesures ERA5 ; somme
    byte-stable."""
    n_series = db_session.execute(
        text(
            f"""
            SELECT COUNT(*) FROM series_metadonnees sm JOIN sources s ON s.id = sm.source_id
            JOIN localites l ON l.id = sm.localite_id
            WHERE {_CLIM} AND l.code IN {_PILOTES_SQL}
            """
        )
    ).scalar_one()
    assert n_series == 18
    base = (
        f"FROM mesures_ressource m JOIN series_metadonnees sm ON sm.id = m.serie_id "
        f"JOIN sources s ON s.id = sm.source_id JOIN localites l ON l.id = sm.localite_id "
        f"WHERE {_CLIM}"
    )
    n_mes = int(_scalar(db_session, f"SELECT COUNT(*) {base} AND l.code IN {_PILOTES_SQL}"))
    assert n_mes == _TOTAL_PILOTES
    somme = _scalar(
        db_session, f"SELECT COALESCE(SUM(m.valeur),0) {base} AND l.code IN {_PILOTES_SQL}"
    )
    assert somme == pytest.approx(_SOMME_PILOTES, rel=1e-9)


def test_volume_28_communes(db_session: Session) -> None:
    """84 series (28 x 3) + 153 384 mesures (28 x 3 x 1826)."""
    n_series = db_session.execute(
        text(
            f"""
            SELECT COUNT(*) FROM series_metadonnees sm JOIN sources s ON s.id = sm.source_id
            JOIN localites l ON l.id = sm.localite_id
            WHERE {_CLIM} AND l.code NOT IN {_PILOTES_SQL}
            """
        )
    ).scalar_one()
    assert n_series == _N_COMMUNES * _N_GRANDEURS
    base = (
        f"FROM mesures_ressource m JOIN series_metadonnees sm ON sm.id = m.serie_id "
        f"JOIN sources s ON s.id = sm.source_id JOIN localites l ON l.id = sm.localite_id "
        f"WHERE {_CLIM}"
    )
    total = int(_scalar(db_session, f"SELECT COUNT(*) {base} AND l.code NOT IN {_PILOTES_SQL}"))
    assert total == _TOTAL_COMMUNES
    somme = _scalar(
        db_session, f"SELECT COALESCE(SUM(m.valeur),0) {base} AND l.code NOT IN {_PILOTES_SQL}"
    )
    assert somme == pytest.approx(_SOMME_COMMUNES, rel=1e-9)


def test_couverture_par_commune_grandeur(db_session: Session) -> None:
    """Chaque (commune, grandeur) couvre 2021-2025 (1826 jours, debut <= 2021-01-31,
    fin >= 2025-12-01)."""
    rows = db_session.execute(
        text(
            f"""
            SELECT l.code, sm.grandeur_code AS g, COUNT(*) AS n,
                   MIN(m.instant_mesure) AS dmin, MAX(m.instant_mesure) AS dmax
            FROM mesures_ressource m
            JOIN series_metadonnees sm ON sm.id = m.serie_id
            JOIN sources s ON s.id = sm.source_id
            JOIN localites l ON l.id = sm.localite_id
            WHERE {_CLIM} AND l.code NOT IN {_PILOTES_SQL}
            GROUP BY l.code, sm.grandeur_code
            """
        )
    ).all()
    assert len(rows) == _N_COMMUNES * _N_GRANDEURS
    for r in rows:
        assert r.n == _JOURS_FENETRE, f"{r.code}/{r.g} : {r.n} jours"
        assert str(r.dmin) <= "2021-01-31" and str(r.dmax) >= "2025-12-01"


def test_brute_seulement_hors_axe(db_session: Session) -> None:
    """ERA5 = brute hors axe : AUCUNE grandeurs_metier (ecart/calculee) ne reference ERA5."""
    n = db_session.execute(
        text(
            """
            SELECT COUNT(*) FROM grandeurs_metier gm
            JOIN series_metadonnees sm ON sm.id = gm.series_metadonnees_id
            JOIN sources s ON s.id = sm.source_id
            WHERE s.code = 'ecmwf_era5_land'
            """
        )
    ).scalar_one()
    assert n == 0, "une grandeurs_metier reference ERA5 (ecart/calculee = scope-creep hors axe)"


def test_caveat_ghi_data_driven_14(db_session: Session) -> None:
    """Memes 14 communes : caveat D-29 sur ghi ssi degenerescence(nasa,ghi)>0."""
    degenerees = {
        r[0]
        for r in db_session.execute(
            text(
                f"""
                SELECT l.code FROM grandeurs_metier gm
                JOIN localites l ON l.id = gm.localite_id
                JOIN series_metadonnees sm ON sm.id = gm.series_metadonnees_id
                JOIN sources s ON s.id = sm.source_id
                WHERE gm.grandeur_code = 'degenerescence_pixel' AND s.code = 'nasa_power'
                  AND sm.grandeur_code = 'ghi' AND gm.valeur > 0 AND l.code NOT IN {_PILOTES_SQL}
                """
            )
        ).all()
    }
    assert len(degenerees) == 14
    rows = db_session.execute(
        text(
            f"""
            SELECT l.code, sm.commentaire_editorial AS com
            FROM series_metadonnees sm JOIN sources s ON s.id = sm.source_id
            JOIN localites l ON l.id = sm.localite_id
            WHERE {_CLIM} AND sm.grandeur_code = 'ghi' AND l.code NOT IN {_PILOTES_SQL}
            """
        )
    ).all()
    assert len(rows) == _N_COMMUNES
    for r in rows:
        assert ("Caveat D-29" in r.com) == (r.code in degenerees), f"{r.code} : caveat ghi"


def test_vent_sans_caveat_en_daily(db_session: Session) -> None:
    """En daily, vent_10m n'a PAS de caveat module (mirror 069 : le caveat ne concerne que
    le mensuel = module des moyennes ; le daily est moyenne des modules horaires)."""
    rows = db_session.execute(
        text(
            f"""
            SELECT sm.commentaire_editorial AS com
            FROM series_metadonnees sm JOIN sources s ON s.id = sm.source_id
            JOIN localites l ON l.id = sm.localite_id
            WHERE {_CLIM} AND sm.grandeur_code = 'vent_10m' AND l.code NOT IN {_PILOTES_SQL}
            """
        )
    ).all()
    assert len(rows) == _N_COMMUNES
    for r in rows:
        assert "module des composantes u10/v10" not in r.com


def test_confiance_b_communes(db_session: Session) -> None:
    """Toutes les mesures ERA5 daily des communes sont en B ; 0 en A (global ERA5 daily)."""
    niveaux = {
        r[0]
        for r in db_session.execute(
            text(
                f"""
                SELECT DISTINCT m.niveau_confiance_derive FROM mesures_ressource m
                JOIN series_metadonnees sm ON sm.id = m.serie_id
                JOIN sources s ON s.id = sm.source_id
                JOIN localites l ON l.id = sm.localite_id
                WHERE {_CLIM} AND l.code NOT IN {_PILOTES_SQL}
                """
            )
        ).all()
    }
    assert niveaux == {"B"}
    n_a = db_session.execute(
        text(
            f"""
            SELECT COUNT(*) FROM mesures_ressource m
            JOIN series_metadonnees sm ON sm.id = m.serie_id
            JOIN sources s ON s.id = sm.source_id
            WHERE {_CLIM} AND m.niveau_confiance_derive = 'A'
            """
        )
    ).scalar_one()
    assert n_a == 0


def test_temoin_gin_boffa_ghi(db_session: Session) -> None:
    """Temoin : gin_boffa ghi daily a 1826 jours, valeurs plausibles (0 <= ghi < 12), somme
    stable."""
    rows = db_session.execute(
        text(
            """
            SELECT m.valeur FROM mesures_ressource m
            JOIN series_metadonnees sm ON sm.id = m.serie_id
            WHERE sm.code = 'gin_boffa_ghi_era5_land_2021_2025'
            """
        )
    ).all()
    assert len(rows) == _JOURS_FENETRE
    assert all(0.0 <= r[0] < 12.0 for r in rows), "ghi ERA5 daily hors plage plausible"
    somme = sum(r[0] for r in rows)
    assert float(somme) == pytest.approx(_SOMME_BOFFA_GHI, rel=1e-9)
