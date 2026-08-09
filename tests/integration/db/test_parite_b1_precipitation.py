"""Tests d'integration de la parite (migration 094).

Porte la grandeur brute ``precipitation`` (NASA POWER PRECTOTCORR, mm/jour, journalier,
2021-2025, confiance B) aux 28 communes chef-lieu, meme traitement que les 6 pilotes
(migration 080). Capture offline 28-only, ingestion offline pure. Garanties verifiees :

- **Anti-regression pilote** : les 6 pilotes gardent leurs series + mesures precip
  (094 n'ingere que des communes) ; somme byte-stable.
- **Couverture par-commune** : chacune des 28 couvre toute la fenetre
  (1826 jours, calendrier complet sans sentinelle) -> une commune vide/tronquee echoue.
- **Plage bornee** : total communes dans [46 600, 51 128] (cap = 28 x 1826) ;
  ici exact 51 128 (donnee NASA pluie sentinelle-free, comme les pilotes).
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

_JOURS_FENETRE = 1826  # 2021-2025 calendrier complet
_N_COMMUNES = 28
_TOTAL_COMMUNES = _N_COMMUNES * _JOURS_FENETRE  # 51 128 (sentinelle-free)
_CAP = 28 * _JOURS_FENETRE  # 51 128
_PLANCHER = 46600  # 91 % du cap (mirror taux sentinelle pilote), borne basse non triviale

# Sommes byte-stables (mesurees sur DB fraiche 001->094, seed offline deterministe).
_SOMME_PILOTES = 96311.20999999967
_SOMME_COMMUNES = 395961.239999999
_SOMME_BOFFA = 19749.930000000004


def test_pilotes_inchanges(db_session: Session) -> None:
    """Anti-regression : les 6 pilotes gardent 6 series + 10 956 mesures precip (094 n'ajoute
    que des communes) ; somme byte-stable."""
    n_series = db_session.execute(
        text(
            f"""
            SELECT COUNT(*) FROM series_metadonnees sm JOIN localites l ON l.id = sm.localite_id
            WHERE sm.grandeur_code = 'precipitation' AND sm.granularite = 'journalier'
              AND l.code IN {_PILOTES_SQL}
            """
        )
    ).scalar_one()
    assert n_series == 6
    n_mesures = db_session.execute(
        text(
            f"""
            SELECT COUNT(*) FROM mesures_ressource mr
            JOIN series_metadonnees sm ON sm.id = mr.serie_id
            JOIN localites l ON l.id = sm.localite_id
            WHERE sm.grandeur_code = 'precipitation' AND l.code IN {_PILOTES_SQL}
            """
        )
    ).scalar_one()
    assert n_mesures == 6 * _JOURS_FENETRE  # 10 956
    somme = db_session.execute(
        text(
            f"""
            SELECT COALESCE(SUM(mr.valeur), 0) FROM mesures_ressource mr
            JOIN series_metadonnees sm ON sm.id = mr.serie_id
            JOIN localites l ON l.id = sm.localite_id
            WHERE sm.grandeur_code = 'precipitation' AND l.code IN {_PILOTES_SQL}
            """
        )
    ).scalar_one()
    assert float(somme) == pytest.approx(_SOMME_PILOTES, rel=1e-9)


def test_volume_28_communes(db_session: Session) -> None:
    """28 series, total 51 128 mesures (= 28 x 1826), borne par [plancher, cap]."""
    n_series = db_session.execute(
        text(
            f"""
            SELECT COUNT(*) FROM series_metadonnees sm JOIN localites l ON l.id = sm.localite_id
            WHERE sm.grandeur_code = 'precipitation' AND sm.granularite = 'journalier'
              AND l.code NOT IN {_PILOTES_SQL}
            """
        )
    ).scalar_one()
    assert n_series == _N_COMMUNES
    total = db_session.execute(
        text(
            f"""
            SELECT COUNT(*) FROM mesures_ressource mr
            JOIN series_metadonnees sm ON sm.id = mr.serie_id
            JOIN localites l ON l.id = sm.localite_id
            WHERE sm.grandeur_code = 'precipitation' AND l.code NOT IN {_PILOTES_SQL}
            """
        )
    ).scalar_one()
    assert _PLANCHER <= total <= _CAP, f"total precip communes {total} hors [{_PLANCHER}, {_CAP}]"
    assert total == _TOTAL_COMMUNES  # exact (sentinelle-free)
    somme = db_session.execute(
        text(
            f"""
            SELECT COALESCE(SUM(mr.valeur), 0) FROM mesures_ressource mr
            JOIN series_metadonnees sm ON sm.id = mr.serie_id
            JOIN localites l ON l.id = sm.localite_id
            WHERE sm.grandeur_code = 'precipitation' AND l.code NOT IN {_PILOTES_SQL}
            """
        )
    ).scalar_one()
    assert float(somme) == pytest.approx(_SOMME_COMMUNES, rel=1e-9)


def test_couverture_par_commune(db_session: Session) -> None:
    """Chacune des 28 communes couvre toute la fenetre 2021-2025 (1826 jours,
    premiere date <= 2021-01-31, derniere >= 2025-12-01). Attrape une commune vide/tronquee
    qu'une plage globale seule masquerait."""
    rows = db_session.execute(
        text(
            f"""
            SELECT l.code AS code, COUNT(*) AS n,
                   MIN(mr.instant_mesure) AS dmin, MAX(mr.instant_mesure) AS dmax
            FROM mesures_ressource mr
            JOIN series_metadonnees sm ON sm.id = mr.serie_id
            JOIN localites l ON l.id = sm.localite_id
            WHERE sm.grandeur_code = 'precipitation' AND l.code NOT IN {_PILOTES_SQL}
            GROUP BY l.code
            """
        )
    ).all()
    assert len(rows) == _N_COMMUNES
    for r in rows:
        assert r.n == _JOURS_FENETRE, f"{r.code} : {r.n} mesures != {_JOURS_FENETRE}"
        assert str(r.dmin) <= "2021-01-31", f"{r.code} : debut {r.dmin}"
        assert str(r.dmax) >= "2025-12-01", f"{r.code} : fin {r.dmax}"


def test_confiance_b_communes(db_session: Session) -> None:
    """Toutes les mesures precip des communes sont en B (hardcode mirror 080) ; 0 en A."""
    niveaux = {
        r[0]
        for r in db_session.execute(
            text(
                f"""
                SELECT DISTINCT mr.niveau_confiance_derive FROM mesures_ressource mr
                JOIN series_metadonnees sm ON sm.id = mr.serie_id
                JOIN localites l ON l.id = sm.localite_id
                WHERE sm.grandeur_code = 'precipitation' AND l.code NOT IN {_PILOTES_SQL}
                """
            )
        ).all()
    }
    assert niveaux == {"B"}
    n_a = db_session.execute(
        text(
            """
            SELECT COUNT(*) FROM mesures_ressource mr
            JOIN series_metadonnees sm ON sm.id = mr.serie_id
            WHERE sm.grandeur_code = 'precipitation' AND mr.niveau_confiance_derive = 'A'
            """
        )
    ).scalar_one()
    assert n_a == 0


def test_series_structure_communes(db_session: Session) -> None:
    """Les 28 series precip communes : nasa_power, journalier, modele_satellitaire, 2021-2025."""
    rows = db_session.execute(
        text(
            f"""
            SELECT s.code AS src, sm.granularite, sm.methode_collecte,
                   sm.periode_debut, sm.periode_fin
            FROM series_metadonnees sm JOIN sources s ON s.id = sm.source_id
            JOIN localites l ON l.id = sm.localite_id
            WHERE sm.grandeur_code = 'precipitation' AND sm.granularite = 'journalier'
              AND l.code NOT IN {_PILOTES_SQL}
            """
        )
    ).all()
    assert len(rows) == _N_COMMUNES
    for r in rows:
        assert r.src == "nasa_power"
        assert r.granularite == "journalier"
        assert r.methode_collecte == "modele_satellitaire"
        assert str(r.periode_debut) == "2021-01-01"
        assert str(r.periode_fin) == "2025-12-31"


def test_temoin_gin_boffa(db_session: Session) -> None:
    """Temoin : gin_boffa a 1826 mesures precip, valeurs >= 0 (pluie tropicale), somme stable."""
    rows = db_session.execute(
        text(
            """
            SELECT mr.valeur FROM mesures_ressource mr
            JOIN series_metadonnees sm ON sm.id = mr.serie_id
            WHERE sm.code = 'gin_boffa_precipitation_nasa_power_2021_2025'
            """
        )
    ).all()
    assert len(rows) == _JOURS_FENETRE
    assert all(r[0] >= 0.0 for r in rows), "precipitation negative (sentinelle non filtree ?)"
    somme = sum(r[0] for r in rows)
    assert float(somme) == pytest.approx(_SOMME_BOFFA, rel=1e-9)
