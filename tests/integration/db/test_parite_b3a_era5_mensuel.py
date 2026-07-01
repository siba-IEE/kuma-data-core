"""Tests d'integration de la parite (migration 096).

Porte ERA5-Land mensuel climato 2001-2020 (ghi/t2m/vent_10m) aux 28 communes, meme
traitement que les 6 pilotes (migration 069, moitie mensuelle). ERA5 = raffineur de
resolution HORS axe d'incertitude. Garanties verifiees :

- **Anti-regression pilote** : les 6 pilotes gardent leurs series + mesures ERA5 mensuelles
  (096 n'ingere que des communes) ; somme byte-stable.
- **Brute seulement / hors axe** : ZERO grandeurs_metier (ecart ou calculee) ne reference une
  serie ERA5 ; ERA5 ne vit qu'en mesures_ressource_mensuelles.
- **Caveat ghi DATA-DRIVEN** : une commune recoit le caveat D-29 sur son ghi ssi sa
  degenerescence_pixel(nasa, ghi) > 0 (regle systematique, pas de hardcode).
- **vent_10m** : caveat module sur toutes. Couverture 240 mois/commune/grandeur. Confiance
  B partout, 0 en A. Repli pixel terrestre trace si applique.
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

_MOIS_FENETRE = 240  # 2001-01 -> 2020-12
_N_COMMUNES = 28
_N_GRANDEURS = 3
_TOTAL_COMMUNES = _N_COMMUNES * _N_GRANDEURS * _MOIS_FENETRE  # 20 160
_TOTAL_PILOTES = 6 * _N_GRANDEURS * _MOIS_FENETRE  # 4 320
_CLIM = "s.code = 'ecmwf_era5_land' AND sm.granularite = 'mensuel'"

# Sommes byte-stables (mesurees sur DB fraiche 001->096, seed CDS offline deterministe).
_SOMME_PILOTES = 44702.93279999992
_SOMME_COMMUNES = 212556.90449999875
_SOMME_BOFFA_GHI = 1213.2375999999995


def _scalar(db_session: Session, sql: str) -> float:
    return float(db_session.execute(text(sql)).scalar_one())


def test_pilotes_inchanges(db_session: Session) -> None:
    """Anti-regression : les 6 pilotes gardent 18 series mensuelles + 4 320 mesures ERA5
    (096 n'ajoute que des communes) ; somme byte-stable."""
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
        f"FROM mesures_ressource_mensuelles m JOIN series_metadonnees sm ON sm.id = m.serie_id "
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
    """84 series (28 x 3) + 20 160 mesures (28 x 3 x 240)."""
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
        f"FROM mesures_ressource_mensuelles m JOIN series_metadonnees sm ON sm.id = m.serie_id "
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
    """Chaque (commune, grandeur) couvre 2001-01 -> 2020-12 (240 mois)."""
    rows = db_session.execute(
        text(
            f"""
            SELECT l.code, sm.grandeur_code AS g, COUNT(*) AS n,
                   MIN(m.annee * 100 + m.mois) AS ym_min, MAX(m.annee * 100 + m.mois) AS ym_max
            FROM mesures_ressource_mensuelles m
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
        assert r.n == _MOIS_FENETRE, f"{r.code}/{r.g} : {r.n} mois"
        assert r.ym_min <= 200101 and r.ym_max >= 202012


def test_brute_seulement_hors_axe(db_session: Session) -> None:
    """ERA5 = brute hors axe d'incertitude : AUCUNE grandeurs_metier (ecart/calculee) ne
    reference une serie ERA5. ERA5 ne vit qu'en mesures_ressource_mensuelles."""
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


def test_caveat_ghi_data_driven(db_session: Session) -> None:
    """Regle systematique : une commune a le caveat D-29 sur son ghi ssi degenerescence(nasa,ghi)>0.
    Verifie l'attribution data-driven (pas de hardcode), pour les 28."""
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
    assert len(degenerees) == 14  # 14 des 28 communes co-localisees CERES
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
        a_le_caveat = "Caveat D-29" in r.com
        assert a_le_caveat == (r.code in degenerees), f"{r.code} : caveat ghi != degenerescence"


def test_vent_caveat_module_partout(db_session: Session) -> None:
    """Toutes les series vent_10m communes portent le caveat module u10/v10."""
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
        assert "module des composantes u10/v10" in r.com


def test_confiance_b_communes(db_session: Session) -> None:
    """Toutes les mesures ERA5 mensuelles des communes sont en B ; 0 en A (global ERA5)."""
    niveaux = {
        r[0]
        for r in db_session.execute(
            text(
                f"""
                SELECT DISTINCT m.niveau_confiance_derive FROM mesures_ressource_mensuelles m
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
            SELECT COUNT(*) FROM mesures_ressource_mensuelles m
            JOIN series_metadonnees sm ON sm.id = m.serie_id
            JOIN sources s ON s.id = sm.source_id
            WHERE {_CLIM} AND m.niveau_confiance_derive = 'A'
            """
        )
    ).scalar_one()
    assert n_a == 0


def test_temoin_gin_boffa_ghi(db_session: Session) -> None:
    """Temoin : gin_boffa ghi a 240 mois, valeurs plausibles (0 < ghi < 10 kWh/m2/jour),
    somme stable."""
    rows = db_session.execute(
        text(
            """
            SELECT m.valeur FROM mesures_ressource_mensuelles m
            JOIN series_metadonnees sm ON sm.id = m.serie_id
            WHERE sm.code = 'gin_boffa_ghi_era5_land_2001_2020'
            """
        )
    ).all()
    assert len(rows) == _MOIS_FENETRE
    assert all(0.0 < r[0] < 10.0 for r in rows), "ghi ERA5 hors plage plausible"
    somme = sum(r[0] for r in rows)
    assert float(somme) == pytest.approx(_SOMME_BOFFA_GHI, rel=1e-9)
