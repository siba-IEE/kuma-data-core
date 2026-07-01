"""Tests d'integration de la parite (migration 092).

Etend hep / productible_specifique_theorique / fraction_diffuse aux 28 communes,
fenetres climato (1991-2020 / 2001-2020) + recente (2021-2025), meme traitement que
les 6 pilotes. Migration seule (climato = helpers 051 dupliques verbatim ; recent =
orchestrateurs). Garanties verifiees :

- **Anti-regression pilote** : les 6 pilotes gardent exactement leurs lignes (la
  migration n'INSERE que des series communes, ne touche jamais les pilotes).
- **Fidelite climato** : sur une commune temoin, hep_climato == application directe de
  la formule (garde anti-erreur de copie des helpers dupliques) ; psp == hep x 0.8.
- Volume commune == volume pilote ; confiance B ; fraction_diffuse dans [0, 1].
"""

from __future__ import annotations

import calendar

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

pytestmark = pytest.mark.integration

_A1 = ("hep", "productible_specifique_theorique", "fraction_diffuse")
_PILOTES = (
    "gin_conakry_kaloum",
    "gin_kankan",
    "gin_kindia",
    "gin_labe",
    "gin_mamou",
    "gin_nzerekore",
)
_COMMUNE = "gin_boffa"


def _n_a1(db_session: Session, code_localite: str, where: str = "") -> int:
    return db_session.execute(
        text(
            f"""
            SELECT COUNT(*) FROM grandeurs_metier gm
            JOIN localites l ON l.id = gm.localite_id
            WHERE l.code = :loc AND gm.grandeur_code = ANY(:g) {where}
            """
        ),
        {"loc": code_localite, "g": list(_A1)},
    ).scalar_one()


def test_pilotes_inchanges(db_session: Session) -> None:
    """Anti-regression : chaque pilote garde 1235 lignes hep/psp/fd (la migration n'ajoute que des
    communes) ; somme temoin gin_kankan byte-stable."""
    for code in _PILOTES:
        assert _n_a1(db_session, code) == 1235, f"{code} : pilote modifie par A1"
    somme = db_session.execute(
        text(
            """
            SELECT COALESCE(SUM(gm.valeur), 0) FROM grandeurs_metier gm
            JOIN localites l ON l.id = gm.localite_id
            WHERE l.code = 'gin_kankan' AND gm.grandeur_code = ANY(:g)
            """
        ),
        {"g": list(_A1)},
    ).scalar_one()
    assert float(somme) == pytest.approx(256901.629590, rel=1e-9)


def test_commune_meme_volume_que_pilote(db_session: Session) -> None:
    """gin_boffa : 1235 lignes (climato 1040 + recent 195) = meme traitement que pilote."""
    assert _n_a1(db_session, _COMMUNE) == 1235
    assert _n_a1(db_session, _COMMUNE, "AND gm.annee_debut <= 2020") == 1040  # climato
    assert _n_a1(db_session, _COMMUNE, "AND gm.annee_debut >= 2021") == 195  # recent


def test_confiance_b_communes(db_session: Session) -> None:
    """Toutes les lignes des communes sont en B (climato hardcode + recent derive)."""
    niveaux = {
        r[0]
        for r in db_session.execute(
            text(
                """
                SELECT DISTINCT gm.niveau_confiance_derive FROM grandeurs_metier gm
                JOIN localites l ON l.id = gm.localite_id
                JOIN series_metadonnees sm ON sm.id = gm.series_metadonnees_id
                JOIN sources s ON s.id = sm.source_id
                WHERE gm.grandeur_code = ANY(:g) AND s.code = 'kuma_calculs'
                  AND l.code NOT IN ('gin_conakry_kaloum','gin_kankan','gin_kindia',
                                     'gin_labe','gin_mamou','gin_nzerekore')
                """
            ),
            {"g": list(_A1)},
        ).all()
    }
    assert niveaux == {"B"}


def test_fidelite_climato_hep_temoin(db_session: Session) -> None:
    """Garde anti-erreur de copie : hep climato de gin_boffa == application DIRECTE de la
    formule (GHI mensuel x nb_jours), et psp == hep x 0.8."""
    ghi = db_session.execute(
        text(
            """
            SELECT m.annee, m.mois, m.valeur FROM mesures_ressource_mensuelles m
            JOIN series_metadonnees sm ON sm.id = m.serie_id
            WHERE sm.code = 'gin_boffa_ghi_power_1991_2020' AND m.valide_au IS NULL
            """
        )
    ).all()
    assert len(ghi) == 360  # 30 ans x 12 mois
    hep_stocke = {
        (int(r.annee), int(r.mois)): float(r.valeur)
        for r in db_session.execute(
            text(
                """
                SELECT gm.annee_debut AS annee, gm.mois, gm.valeur FROM grandeurs_metier gm
                JOIN series_metadonnees sm ON sm.id = gm.series_metadonnees_id
                WHERE sm.code = 'gin_boffa_hep_kuma_calculs_1991_2020'
                  AND gm.periode_type = 'mensuel'
                """
            )
        ).all()
    }
    psp_stocke = {
        (int(r.annee), int(r.mois)): float(r.valeur)
        for r in db_session.execute(
            text(
                """
                SELECT gm.annee_debut AS annee, gm.mois, gm.valeur FROM grandeurs_metier gm
                JOIN series_metadonnees sm ON sm.id = gm.series_metadonnees_id
                WHERE sm.code = 'gin_boffa_productible_specifique_theorique_kuma_calculs_1991_2020'
                  AND gm.periode_type = 'mensuel'
                """
            )
        ).all()
    }
    assert len(hep_stocke) == 360
    for r in ghi:
        y, m, ghi_v = int(r.annee), int(r.mois), float(r.valeur)
        attendu = ghi_v * calendar.monthrange(y, m)[1]
        assert hep_stocke[(y, m)] == pytest.approx(attendu, rel=1e-9), f"hep climato {y}-{m}"
        assert psp_stocke[(y, m)] == pytest.approx(attendu * 0.8, rel=1e-9), f"psp climato {y}-{m}"


def test_fraction_diffuse_communes_dans_01(db_session: Session) -> None:
    """fraction_diffuse des 28 communes (climato + recent) dans [0, 1] (invariant physique)."""
    row = db_session.execute(
        text(
            """
            SELECT MIN(gm.valeur) mn, MAX(gm.valeur) mx FROM grandeurs_metier gm
            JOIN localites l ON l.id = gm.localite_id
            WHERE gm.grandeur_code = 'fraction_diffuse'
              AND l.code NOT IN ('gin_conakry_kaloum','gin_kankan','gin_kindia',
                                 'gin_labe','gin_mamou','gin_nzerekore')
            """
        )
    ).one()
    assert float(row.mn) >= 0.0 and float(row.mx) <= 1.0
