"""Tests d'intégration de la migration 133 (rang spatial sur toutes les localités).

- Version de formule 2 en vigueur ; les 360 lignes de la version 1 sont closes
  à l'instant où commencent les 2 040 lignes de la version 2.
- Chaque mois courant est une permutation de 1 à 34, identique à un recalcul
  direct (moyenne mensuelle du GHI journalier, ex-aequo par code de localité).
- Les ex-aequo forment chaque mois les mêmes groupes, à rangs consécutifs, et la
  note publique de chaque série concernée nomme ses jumelles.
- Textes : description sans couverture chiffrée, libellés au nom de la
  localité ; l'API sert la version 2.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session

pytestmark = pytest.mark.integration

_G = "rang_referentiel_spatial"
_N_LOCALITES = 34
_N_MOIS = 60

_GROUPES_EGAUX: frozenset[frozenset[str]] = frozenset(
    frozenset(g)
    for g in (
        ("gin_boffa", "gin_boke_centre"),
        ("gin_conakry_kaloum", "gin_coyah", "gin_dubreka", "gin_forecariah"),
        ("gin_dalaba", "gin_kindia", "gin_mamou"),
        ("gin_fria", "gin_telimele"),
        ("gin_kankan", "gin_kouroussa"),
        ("gin_koubia", "gin_tougue"),
        ("gin_labe", "gin_lelouma", "gin_pita"),
        ("gin_lola", "gin_nzerekore"),
    )
)

# Moyenne mensuelle du GHI NASA POWER journalier 2021-2025, par localité.
_SQL_GHI_MENSUEL = """
    SELECT l.code, sm.localite_id,
           EXTRACT(YEAR FROM mr.instant_mesure)::int AS annee,
           EXTRACT(MONTH FROM mr.instant_mesure)::int AS mois,
           AVG(mr.valeur) AS v
    FROM mesures_ressource mr
    JOIN series_metadonnees sm ON sm.id = mr.serie_id
    JOIN localites l ON l.id = sm.localite_id
    JOIN sources s ON s.id = sm.source_id
    WHERE s.code = 'nasa_power' AND sm.grandeur_code = 'ghi'
      AND sm.granularite = 'journalier' AND sm.code LIKE '%\\_ghi\\_nasa\\_power\\_2021\\_2025'
      AND mr.valide_au IS NULL AND mr.statut <> 'deprecie'
    GROUP BY l.code, sm.localite_id, annee, mois
"""


def test_version_2_en_vigueur(db_session: Session) -> None:
    version = db_session.execute(
        text("SELECT version_formule_actuelle FROM grandeurs_referentiel WHERE code = :g"),
        {"g": _G},
    ).scalar_one()
    assert version == 2
    rows = db_session.execute(
        text(
            """
            SELECT version_formule, count(*) AS n,
                   count(*) FILTER (WHERE valide_au IS NULL) AS courantes,
                   count(DISTINCT localite_id) AS n_loc, min(valeur) AS vmin, max(valeur) AS vmax,
                   count(DISTINCT niveau_confiance_derive) AS n_niv,
                   min(niveau_confiance_derive) AS niveau
            FROM grandeurs_metier WHERE grandeur_code = :g
            GROUP BY version_formule ORDER BY version_formule
            """
        ),
        {"g": _G},
    ).all()
    assert [tuple(r) for r in rows] == [
        (1, 360, 0, 6, 1, 6, 1, "B"),
        (2, 2040, 2040, 34, 1, 34, 1, "B"),
    ]


def test_version_1_close_a_l_ouverture_de_la_version_2(db_session: Session) -> None:
    row = db_session.execute(
        text(
            """
            SELECT
                (SELECT count(DISTINCT valide_au) FROM grandeurs_metier
                 WHERE grandeur_code = :g AND version_formule = 1) AS n_fin,
                (SELECT count(DISTINCT valide_du) FROM grandeurs_metier
                 WHERE grandeur_code = :g AND version_formule = 2) AS n_debut,
                (SELECT max(valide_au) FROM grandeurs_metier
                 WHERE grandeur_code = :g AND version_formule = 1)
                = (SELECT min(valide_du) FROM grandeurs_metier
                   WHERE grandeur_code = :g AND version_formule = 2) AS contigu
            """
        ),
        {"g": _G},
    ).one()
    assert (row.n_fin, row.n_debut, row.contigu) == (1, 1, True)


def test_chaque_mois_permutation_1_34(db_session: Session) -> None:
    rows = db_session.execute(
        text(
            """
            SELECT annee_debut, mois, array_agg(valeur::int ORDER BY valeur) AS rangs,
                   count(DISTINCT localite_id) AS n_loc
            FROM v_grandeurs_metier_courantes WHERE grandeur_code = :g
            GROUP BY annee_debut, mois
            """
        ),
        {"g": _G},
    ).all()
    assert len(rows) == _N_MOIS
    for r in rows:
        assert r.rangs == list(range(1, _N_LOCALITES + 1)), (r.annee_debut, r.mois)
        assert r.n_loc == _N_LOCALITES


def test_rangs_egaux_au_recalcul_direct(db_session: Session) -> None:
    """Rang = position par GHI mensuel croissant, ex-aequo dans l'ordre des codes."""
    n_total, n_egaux = db_session.execute(
        text(
            f"""
            WITH m AS ({_SQL_GHI_MENSUEL}),
            r AS (
                SELECT localite_id, annee, mois,
                       row_number() OVER (PARTITION BY annee, mois ORDER BY v, code) AS rang
                FROM m
            )
            SELECT count(*), count(*) FILTER (WHERE gm.valeur = r.rang)
            FROM grandeurs_metier gm
            JOIN r ON r.localite_id = gm.localite_id AND r.annee = gm.annee_debut
                  AND r.mois = gm.mois
            WHERE gm.grandeur_code = :g AND gm.valide_au IS NULL
            """
        ),
        {"g": _G},
    ).one()
    assert (n_total, n_egaux) == (2040, 2040)


def test_ex_aequo_groupes_stables_et_rangs_consecutifs(db_session: Session) -> None:
    rows = db_session.execute(
        text(
            f"""
            WITH m AS ({_SQL_GHI_MENSUEL})
            SELECT m.annee, m.mois, array_agg(m.code ORDER BY m.code) AS codes,
                   max(gm.valeur) - min(gm.valeur) AS etendue
            FROM m
            JOIN grandeurs_metier gm ON gm.localite_id = m.localite_id
                 AND gm.annee_debut = m.annee AND gm.mois = m.mois
                 AND gm.grandeur_code = :g AND gm.valide_au IS NULL
            GROUP BY m.annee, m.mois, m.v
            HAVING count(*) > 1
            """
        ),
        {"g": _G},
    ).all()
    par_mois: dict[tuple[int, int], set[frozenset[str]]] = {}
    for r in rows:
        par_mois.setdefault((r.annee, r.mois), set()).add(frozenset(r.codes))
        assert r.etendue == len(r.codes) - 1, (r.annee, r.mois, r.codes)
    assert len(par_mois) == _N_MOIS
    assert all(groupes == _GROUPES_EGAUX for groupes in par_mois.values())


def test_series_et_notes(db_session: Session) -> None:
    rows = db_session.execute(
        text(
            """
            SELECT s.code, s.libelle, s.note_publique, s.methode_collecte, s.periode_debut,
                   s.periode_fin, src.code AS source, l.code AS loc, l.nom
            FROM series_metadonnees s
            JOIN sources src ON src.id = s.source_id
            JOIN localites l ON l.id = s.localite_id
            WHERE s.grandeur_code = :g
            """
        ),
        {"g": _G},
    ).all()
    assert len(rows) == _N_LOCALITES
    noms = {r.loc: r.nom for r in rows}
    jumelles = {code: groupe - {code} for groupe in _GROUPES_EGAUX for code in groupe}
    assert len(jumelles) == 20
    for r in rows:
        assert r.code.endswith("_rang_referentiel_spatial_kuma_calculs_2021_2025")
        assert r.libelle == f"rang_referentiel_spatial mensuel {r.nom} 2021-2025"
        assert (r.source, r.methode_collecte) == ("kuma_calculs", "calcul_derive")
        assert (str(r.periode_debut), str(r.periode_fin)) == ("2021-01-01", "2025-12-31")
        assert "parmi les 34 localités couvertes" in r.note_publique
        assert "pilote" not in r.note_publique.lower()
        if r.loc in jumelles:
            assert "lit la même cellule de la grille NASA POWER" in r.note_publique
            for autre in jumelles[r.loc]:
                assert noms[autre] in r.note_publique, (r.code, autre)
        else:
            assert "même cellule" not in r.note_publique


def test_description(db_session: Session) -> None:
    description = db_session.execute(
        text("SELECT description FROM grandeurs_referentiel WHERE code = :g"), {"g": _G}
    ).scalar_one()
    assert "de 1 au nombre de localités classées" in description
    assert "même cellule de la grille NASA POWER" in description
    assert "pilote" not in description.lower()
    assert "Niveau de confiance B" in description


def test_api_sert_la_version_2(
    client: TestClient, headers_auth: dict[str, str], db_session: Session
) -> None:
    """Une série reprise (Kindia) et une série nouvelle (Beyla) : 60 mois, version 2."""
    for code in (
        "gin_kindia_rang_referentiel_spatial_kuma_calculs_2021_2025",
        "gin_beyla_rang_referentiel_spatial_kuma_calculs_2021_2025",
    ):
        r = client.get(f"/v1/series/{code}?limit=100", headers=headers_auth)
        assert r.status_code == 200, code
        payload = r.json()
        mesures = payload["mesures"]
        assert len(mesures) == _N_MOIS, code
        assert {m["version_formule"] for m in mesures} == {2}
        assert all(1 <= m["valeur"] <= _N_LOCALITES for m in mesures)
        assert "parmi les 34 localités couvertes" in payload["notes_fr"]
