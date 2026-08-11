"""Tests d'integration de la parite (migration 095).

Porte la grandeur brute ``dni`` CAMS Radiation **climato mensuel 2004-2020** aux 28 communes
chef-lieu, meme traitement que les 6 pilotes (migration 071). Capture ADS offline 28-only,
ingestion offline pure. Garanties verifiees :

- **Anti-regression pilote** : les 6 pilotes gardent leurs series + mesures climato CAMS
  (095 n'ingere que des communes) ; somme byte-stable.
- **Couverture par-commune** : chacune des 28 couvre 2004-02 -> 2020-12 (203 mois).
- **Brute seulement (anti-scope-creep)** : aucun ecart climato (`ecart_relatif_dni_cams`
  2004-2020) cree pour les communes ; l'ecart reste une calculee separee (pilotes only, 072).
- Confiance B partout, **0 en A** ; temoin commune recoupe.
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

_MOIS_FENETRE = 203  # fev 2004 -> dec 2020
_N_COMMUNES = 28
_TOTAL_COMMUNES = _N_COMMUNES * _MOIS_FENETRE  # 5 684
_TOTAL_PILOTES = 6 * _MOIS_FENETRE  # 1 218

# Sommes byte-stables (mesurees sur DB fraiche 001->095, seed ADS offline deterministe).
_SOMME_PILOTES = 5232.002700000012
_SOMME_COMMUNES = 25467.646600000007
_SOMME_BOFFA = 795.9168000000003


def _q_scalar(db_session: Session, sql: str) -> float:
    return float(db_session.execute(text(sql)).scalar_one())


def test_pilotes_inchanges(db_session: Session) -> None:
    """Anti-regression : les 6 pilotes gardent 6 series climato + 1 218 mesures (095 n'ajoute
    que des communes) ; somme byte-stable."""
    n_series = db_session.execute(
        text(
            f"""
            SELECT COUNT(*) FROM series_metadonnees sm JOIN localites l ON l.id = sm.localite_id
            JOIN sources s ON s.id = sm.source_id
            WHERE sm.grandeur_code = 'dni' AND s.code = 'cams_radiation'
              AND sm.granularite = 'mensuel' AND sm.periode_debut = '2004-02-01'
              AND l.code IN {_PILOTES_SQL}
            """
        )
    ).scalar_one()
    assert n_series == 6
    n_mesures = db_session.execute(
        text(
            f"""
            SELECT COUNT(*) FROM mesures_ressource_mensuelles m
            JOIN series_metadonnees sm ON sm.id = m.serie_id
            JOIN sources s ON s.id = sm.source_id
            JOIN localites l ON l.id = sm.localite_id
            WHERE sm.grandeur_code = 'dni' AND s.code = 'cams_radiation'
              AND sm.periode_debut = '2004-02-01' AND l.code IN {_PILOTES_SQL}
            """
        )
    ).scalar_one()
    assert n_mesures == _TOTAL_PILOTES
    somme = _q_scalar(
        db_session,
        f"""
        SELECT COALESCE(SUM(m.valeur), 0) FROM mesures_ressource_mensuelles m
        JOIN series_metadonnees sm ON sm.id = m.serie_id
        JOIN sources s ON s.id = sm.source_id
        JOIN localites l ON l.id = sm.localite_id
        WHERE sm.grandeur_code = 'dni' AND s.code = 'cams_radiation'
          AND sm.periode_debut = '2004-02-01' AND l.code IN {_PILOTES_SQL}
        """,
    )
    assert somme == pytest.approx(_SOMME_PILOTES, rel=1e-9)


def test_volume_28_communes(db_session: Session) -> None:
    """28 series climato + 5 684 mesures (= 28 x 203)."""
    n_series = db_session.execute(
        text(
            f"""
            SELECT COUNT(*) FROM series_metadonnees sm JOIN localites l ON l.id = sm.localite_id
            JOIN sources s ON s.id = sm.source_id
            WHERE sm.grandeur_code = 'dni' AND s.code = 'cams_radiation'
              AND sm.granularite = 'mensuel' AND sm.periode_debut = '2004-02-01'
              AND l.code NOT IN {_PILOTES_SQL}
            """
        )
    ).scalar_one()
    assert n_series == _N_COMMUNES
    total = db_session.execute(
        text(
            f"""
            SELECT COUNT(*) FROM mesures_ressource_mensuelles m
            JOIN series_metadonnees sm ON sm.id = m.serie_id
            JOIN sources s ON s.id = sm.source_id
            JOIN localites l ON l.id = sm.localite_id
            WHERE sm.grandeur_code = 'dni' AND s.code = 'cams_radiation'
              AND sm.periode_debut = '2004-02-01' AND l.code NOT IN {_PILOTES_SQL}
            """
        )
    ).scalar_one()
    assert total == _TOTAL_COMMUNES
    somme = _q_scalar(
        db_session,
        f"""
        SELECT COALESCE(SUM(m.valeur), 0) FROM mesures_ressource_mensuelles m
        JOIN series_metadonnees sm ON sm.id = m.serie_id
        JOIN sources s ON s.id = sm.source_id
        JOIN localites l ON l.id = sm.localite_id
        WHERE sm.grandeur_code = 'dni' AND s.code = 'cams_radiation'
          AND sm.periode_debut = '2004-02-01' AND l.code NOT IN {_PILOTES_SQL}
        """,
    )
    assert somme == pytest.approx(_SOMME_COMMUNES, rel=1e-9)


def test_couverture_par_commune(db_session: Session) -> None:
    """Chacune des 28 communes couvre 2004-02 -> 2020-12 (203 mois ; debut <= fev 2004,
    fin >= dec 2020). Attrape une commune vide/tronquee."""
    rows = db_session.execute(
        text(
            f"""
            SELECT l.code AS code, COUNT(*) AS n,
                   MIN(m.annee * 100 + m.mois) AS ym_min, MAX(m.annee * 100 + m.mois) AS ym_max
            FROM mesures_ressource_mensuelles m
            JOIN series_metadonnees sm ON sm.id = m.serie_id
            JOIN sources s ON s.id = sm.source_id
            JOIN localites l ON l.id = sm.localite_id
            WHERE sm.grandeur_code = 'dni' AND s.code = 'cams_radiation'
              AND sm.periode_debut = '2004-02-01' AND l.code NOT IN {_PILOTES_SQL}
            GROUP BY l.code
            """
        )
    ).all()
    assert len(rows) == _N_COMMUNES
    for r in rows:
        assert r.n == _MOIS_FENETRE, f"{r.code} : {r.n} mois != {_MOIS_FENETRE}"
        assert r.ym_min <= 200402, f"{r.code} : debut {r.ym_min}"
        assert r.ym_max >= 202012, f"{r.code} : fin {r.ym_max}"


def test_confiance_b_communes(db_session: Session) -> None:
    """Toutes les mesures climato CAMS des communes sont en B (hardcode mirror 071) ; 0 en A."""
    niveaux = {
        r[0]
        for r in db_session.execute(
            text(
                f"""
                SELECT DISTINCT m.niveau_confiance_derive FROM mesures_ressource_mensuelles m
                JOIN series_metadonnees sm ON sm.id = m.serie_id
                JOIN sources s ON s.id = sm.source_id
                JOIN localites l ON l.id = sm.localite_id
                WHERE sm.grandeur_code = 'dni' AND s.code = 'cams_radiation'
                  AND sm.periode_debut = '2004-02-01' AND l.code NOT IN {_PILOTES_SQL}
                """
            )
        ).all()
    }
    assert niveaux == {"B"}
    n_a = db_session.execute(
        text(
            """
            SELECT COUNT(*) FROM mesures_ressource_mensuelles m
            JOIN series_metadonnees sm ON sm.id = m.serie_id
            JOIN sources s ON s.id = sm.source_id
            WHERE sm.grandeur_code = 'dni' AND s.code = 'cams_radiation'
              AND sm.periode_debut = '2004-02-01' AND m.niveau_confiance_derive = 'A'
            """
        )
    ).scalar_one()
    assert n_a == 0


def test_brute_seulement_aucun_ecart_climato_communes(db_session: Session) -> None:
    """La 095 etait BRUTE seulement : l'ecart climato des communes vient du lot dedie
    (migration 118), jamais de la 095. On verifie que les 5 684 lignes communes (28 x
    203 mois) existent ET qu'elles sont portees par les series kuma_calculs de la 118
    (codes <commune>_ecart_relatif_dni_cams_kuma_calculs_2004_2020), pas par un
    scope-creep du seed brut."""
    n = db_session.execute(
        text(
            f"""
            SELECT COUNT(*) FROM grandeurs_metier gm
            JOIN localites l ON l.id = gm.localite_id
            JOIN series_metadonnees sm ON sm.id = gm.series_metadonnees_id
            WHERE gm.grandeur_code = 'ecart_relatif_dni_cams'
              AND gm.annee_debut <= 2020
              AND l.code NOT IN {_PILOTES_SQL}
              AND sm.code LIKE '%ecart_relatif_dni_cams_kuma_calculs_2004_2020'
            """
        )
    ).scalar_one()
    assert n == 5684, f"ecart climato communes = {n} (attendu 5 684, migration 118)"


def test_temoin_gin_boffa(db_session: Session) -> None:
    """Temoin : gin_boffa a 203 mesures climato DNI, valeurs plausibles (0 < dni < 15
    kWh/m2/jour), somme stable."""
    rows = db_session.execute(
        text(
            """
            SELECT m.valeur FROM mesures_ressource_mensuelles m
            JOIN series_metadonnees sm ON sm.id = m.serie_id
            WHERE sm.code = 'gin_boffa_dni_cams_2004_2020'
            """
        )
    ).all()
    assert len(rows) == _MOIS_FENETRE
    assert all(0.0 < r[0] < 15.0 for r in rows), "DNI climato hors plage plausible"
    somme = sum(r[0] for r in rows)
    assert float(somme) == pytest.approx(_SOMME_BOFFA, rel=1e-9)
