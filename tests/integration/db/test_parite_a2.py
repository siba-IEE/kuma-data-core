"""Tests d'integration de la parite (migration 093).

Etend humidex / variabilite_journaliere / rang_referentiel_temporel /
indicateur_qualite_donnees aux 28 communes, meme traitement que les 6 pilotes.
Migration seule (humidex/variabilite = orchestrateurs derivant la confiance ;
rang_temporel = fonction FOCALISEE calculer_et_inserer_rang_temporel ; indicateur =
orchestrateur sur les series brutes daily). Garanties verifiees :

- **Anti-regression pilote** : les 6 pilotes gardent exactement leurs lignes des 4
  grandeurs (la migration n'INSERE que des communes) ; somme temoin byte-stable.
- **Garde anti-corruption rang_spatial (obligatoire)** : (a) zero ligne
  rang_referentiel_spatial creee par 093 (total inchange, aucune commune) ; (b) les
  rang_spatial des 6 pilotes byte-identiques.
- **Fidelite rang_temporel** : sur une commune temoin, chaque percentile stocke ==
  recalcul direct via le helper pur _calcul_rang_temporel (garde anti-erreur de cablage
  de la fonction focalisee).
- Volume commune == volume pilote ; confiance B ; 0 en A ; indicateur 6 grandeurs (parite).
"""

from __future__ import annotations

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

from kuma_data_core.services.grandeurs.referentiels import _calcul_rang_temporel

pytestmark = pytest.mark.integration

_A2 = (
    "humidex",
    "variabilite_journaliere",
    "rang_referentiel_temporel",
    "indicateur_qualite_donnees",
)
_PILOTES = (
    "gin_conakry_kaloum",
    "gin_kankan",
    "gin_kindia",
    "gin_labe",
    "gin_mamou",
    "gin_nzerekore",
)
_PILOTES_SQL = (
    "('gin_conakry_kaloum','gin_kankan','gin_kindia','gin_labe','gin_mamou','gin_nzerekore')"
)
_COMMUNE = "gin_boffa"

# Volumes attendus par localite (pilote == commune, meme traitement) :
# humidex 65 (5 annuel + 60 mensuel) + variabilite 5 (annuel) + rang_temporel 60 (mensuel)
# + indicateur 6 (statique, 6 grandeurs daily) = 136.
_N_HUMIDEX = 65
_N_VARIAB = 5
_N_RANG_TEMP = 60
_N_INDIC = 6
_N_PAR_LOCALITE = _N_HUMIDEX + _N_VARIAB + _N_RANG_TEMP + _N_INDIC  # 136

# Somme temoin gin_kankan sur les 4 grandeurs (byte-stable, valeur deterministe du
# seed offline). Mesuree sur DB fraiche 001->093.
_SOMME_KANKAN_A2 = 4868.157741460751
# Somme rang_spatial des 6 pilotes (byte-identite, inchangee par 093). 360 lignes de rang
# ordinal 1-6, soit 60 groupes mensuels x (1+2+3+4+5+6) = 60 x 21 = 1260.
_SOMME_RANG_SPATIAL_PILOTES = 1260.0


def _n_a2(db_session: Session, code_localite: str, where: str = "") -> int:
    return db_session.execute(
        text(
            f"""
            SELECT COUNT(*) FROM grandeurs_metier gm
            JOIN localites l ON l.id = gm.localite_id
            WHERE l.code = :loc AND gm.grandeur_code = ANY(:g) {where}
            """
        ),
        {"loc": code_localite, "g": list(_A2)},
    ).scalar_one()


def test_pilotes_inchanges(db_session: Session) -> None:
    """Anti-regression : chaque pilote garde 136 lignes des 4 grandeurs (65+5+60+6) ;
    somme temoin gin_kankan byte-stable."""
    for code in _PILOTES:
        assert _n_a2(db_session, code) == _N_PAR_LOCALITE, f"{code} : pilote modifie par A2"
        assert _n_a2(db_session, code, "AND gm.grandeur_code = 'humidex'") == _N_HUMIDEX
        assert (
            _n_a2(db_session, code, "AND gm.grandeur_code = 'variabilite_journaliere'") == _N_VARIAB
        )
        assert (
            _n_a2(db_session, code, "AND gm.grandeur_code = 'rang_referentiel_temporel'")
            == _N_RANG_TEMP
        )
        assert (
            _n_a2(db_session, code, "AND gm.grandeur_code = 'indicateur_qualite_donnees'")
            == _N_INDIC
        )
    somme = db_session.execute(
        text(
            """
            SELECT COALESCE(SUM(gm.valeur), 0) FROM grandeurs_metier gm
            JOIN localites l ON l.id = gm.localite_id
            WHERE l.code = 'gin_kankan' AND gm.grandeur_code = ANY(:g)
            """
        ),
        {"g": list(_A2)},
    ).scalar_one()
    assert float(somme) == pytest.approx(_SOMME_KANKAN_A2, rel=1e-9)


def test_commune_meme_volume_que_pilote(db_session: Session) -> None:
    """gin_boffa : 136 lignes (65 humidex + 5 variabilite + 60 rang_temporel +
    6 indicateur) = meme traitement que pilote."""
    assert _n_a2(db_session, _COMMUNE) == _N_PAR_LOCALITE
    assert _n_a2(db_session, _COMMUNE, "AND gm.grandeur_code = 'humidex'") == _N_HUMIDEX
    assert (
        _n_a2(db_session, _COMMUNE, "AND gm.grandeur_code = 'variabilite_journaliere'") == _N_VARIAB
    )
    assert (
        _n_a2(db_session, _COMMUNE, "AND gm.grandeur_code = 'rang_referentiel_temporel'")
        == _N_RANG_TEMP
    )
    assert (
        _n_a2(db_session, _COMMUNE, "AND gm.grandeur_code = 'indicateur_qualite_donnees'")
        == _N_INDIC
    )


def test_volumes_a2_totaux_communes(db_session: Session) -> None:
    """Decompte total sur les 28 communes (hors pilotes)."""
    rows = db_session.execute(
        text(
            f"""
            SELECT gm.grandeur_code, COUNT(*) FROM grandeurs_metier gm
            JOIN localites l ON l.id = gm.localite_id
            WHERE gm.grandeur_code = ANY(:g) AND l.code NOT IN {_PILOTES_SQL}
            GROUP BY gm.grandeur_code
            """
        ),
        {"g": list(_A2)},
    ).all()
    decompte = {r[0]: r[1] for r in rows}
    assert decompte["humidex"] == 28 * _N_HUMIDEX  # 1820
    assert decompte["variabilite_journaliere"] == 28 * _N_VARIAB  # 140
    assert decompte["rang_referentiel_temporel"] == 28 * _N_RANG_TEMP  # 1680
    assert decompte["indicateur_qualite_donnees"] == 28 * _N_INDIC  # 168


def test_garde_zero_rang_spatial(db_session: Session) -> None:
    """Garde anti-corruption (a) : 093 ne cree AUCUNE ligne rang_referentiel_spatial.

    Total rang_spatial inchange (360 = pool pilote migration 043) ; aucune commune n'a
    de ligne rang_spatial."""
    total = db_session.execute(
        text(
            "SELECT COUNT(*) FROM grandeurs_metier WHERE grandeur_code = 'rang_referentiel_spatial'"
        )
    ).scalar_one()
    assert total == 360, "093 a cree des lignes rang_referentiel_spatial (pool pilote corrompu)"
    n_communes = db_session.execute(
        text(
            f"""
            SELECT COUNT(*) FROM grandeurs_metier gm
            JOIN localites l ON l.id = gm.localite_id
            WHERE gm.grandeur_code = 'rang_referentiel_spatial' AND l.code NOT IN {_PILOTES_SQL}
            """
        )
    ).scalar_one()
    assert n_communes == 0, "une commune porte du rang_referentiel_spatial (interdit lot A2)"


def test_rang_spatial_pilotes_byte_identique(db_session: Session) -> None:
    """Garde anti-corruption (b) : les rang_spatial des 6 pilotes sont byte-identiques
    (360 lignes, somme stable). 093 ne doit pas les avoir touches."""
    n_pilotes = db_session.execute(
        text(
            f"""
            SELECT COUNT(*) FROM grandeurs_metier gm
            JOIN localites l ON l.id = gm.localite_id
            WHERE gm.grandeur_code = 'rang_referentiel_spatial' AND l.code IN {_PILOTES_SQL}
            """
        )
    ).scalar_one()
    assert n_pilotes == 360
    somme = db_session.execute(
        text(
            "SELECT COALESCE(SUM(valeur), 0) FROM grandeurs_metier "
            "WHERE grandeur_code = 'rang_referentiel_spatial'"
        )
    ).scalar_one()
    assert float(somme) == pytest.approx(_SOMME_RANG_SPATIAL_PILOTES, rel=1e-12)


def test_confiance_b_communes(db_session: Session) -> None:
    """Toutes les lignes des communes sont en B (humidex/variabilite derivent R4->B ;
    rang_temporel 'B' ; indicateur 'B'). 0 en A."""
    niveaux = {
        r[0]
        for r in db_session.execute(
            text(
                f"""
                SELECT DISTINCT gm.niveau_confiance_derive FROM grandeurs_metier gm
                JOIN localites l ON l.id = gm.localite_id
                WHERE gm.grandeur_code = ANY(:g) AND l.code NOT IN {_PILOTES_SQL}
                """
            ),
            {"g": list(_A2)},
        ).all()
    }
    assert niveaux == {"B"}


def test_indicateur_communes_parite_6_grandeurs(db_session: Session) -> None:
    """L'indicateur des communes couvre les MEMES 6 grandeurs daily que les pilotes
    (ghi/t2m/rh2m/dni/dhi/kt), pointe une serie brute nasa_power journaliere, statique."""
    rows = db_session.execute(
        text(
            f"""
            SELECT sm.grandeur_code AS g_pointee, sm.granularite, s.code AS src,
                   gm.periode_type, gm.mois, gm.niveau_confiance_derive
            FROM grandeurs_metier gm
            JOIN localites l ON l.id = gm.localite_id
            JOIN series_metadonnees sm ON sm.id = gm.series_metadonnees_id
            JOIN sources s ON s.id = sm.source_id
            WHERE gm.grandeur_code = 'indicateur_qualite_donnees' AND l.code NOT IN {_PILOTES_SQL}
            """
        )
    ).all()
    assert len(rows) == 168
    grandeurs_pointees = {r.g_pointee for r in rows}
    grandeurs_pilote = {
        r[0]
        for r in db_session.execute(
            text(
                f"""
                SELECT DISTINCT sm.grandeur_code FROM grandeurs_metier gm
                JOIN localites l ON l.id = gm.localite_id
                JOIN series_metadonnees sm ON sm.id = gm.series_metadonnees_id
                WHERE gm.grandeur_code = 'indicateur_qualite_donnees' AND l.code IN {_PILOTES_SQL}
                """
            )
        ).all()
    }
    assert grandeurs_pointees == grandeurs_pilote, "indicateur communes != 6 grandeurs pilotes"
    for r in rows:
        assert r.granularite == "journalier"
        assert r.src == "nasa_power"
        assert r.periode_type == "statique"
        assert r.mois is None
        assert r.niveau_confiance_derive == "B"


def test_fidelite_rang_temporel_temoin(db_session: Session) -> None:
    """Garde anti-erreur de cablage : chaque percentile rang_temporel de gin_boffa ==
    recalcul direct via _calcul_rang_temporel (NASA daily agrege mensuel vs distribution
    climato 1991-2020 stratifiee par mois)."""
    kuma_mensuel = {
        (int(r.annee), int(r.mois)): float(r.moyenne)
        for r in db_session.execute(
            text(
                """
                SELECT EXTRACT(YEAR FROM mr.instant_mesure)::int AS annee,
                       EXTRACT(MONTH FROM mr.instant_mesure)::int AS mois,
                       AVG(mr.valeur) AS moyenne
                FROM mesures_ressource mr JOIN series_metadonnees sm ON sm.id = mr.serie_id
                WHERE sm.code = 'gin_boffa_ghi_nasa_power_2021_2025'
                  AND mr.valide_au IS NULL AND mr.statut <> 'deprecie'
                GROUP BY annee, mois
                """
            )
        ).all()
    }
    distribution_par_mois: dict[int, list[float]] = {m: [] for m in range(1, 13)}
    for r in db_session.execute(
        text(
            """
            SELECT m.annee, m.mois, m.valeur FROM mesures_ressource_mensuelles m
            JOIN series_metadonnees sm ON sm.id = m.serie_id
            WHERE sm.code = 'gin_boffa_ghi_power_1991_2020' AND m.valide_au IS NULL
            """
        )
    ).all():
        if 1991 <= int(r.annee) <= 2020:
            distribution_par_mois[int(r.mois)].append(float(r.valeur))

    stocke = db_session.execute(
        text(
            """
            SELECT gm.annee_debut AS annee, gm.mois, gm.valeur FROM grandeurs_metier gm
            JOIN series_metadonnees sm ON sm.id = gm.series_metadonnees_id
            WHERE sm.code = 'gin_boffa_rang_referentiel_temporel_kuma_calculs_2021_2025'
              AND gm.periode_type = 'mensuel'
            """
        )
    ).all()
    assert len(stocke) == _N_RANG_TEMP
    for r in stocke:
        y, m, valeur = int(r.annee), int(r.mois), float(r.valeur)
        attendu = _calcul_rang_temporel(kuma_mensuel[(y, m)], distribution_par_mois[m])
        assert valeur == pytest.approx(attendu, rel=1e-12), f"rang_temporel {y}-{m}"
        assert 0.0 <= valeur <= 100.0
