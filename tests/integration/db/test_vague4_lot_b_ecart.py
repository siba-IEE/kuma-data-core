"""Tests d'integration ecart_relatif_dni_cams.

Verifie l'etat apres ``alembic upgrade head`` (migration 072 : grandeur +
6 series kuma_calculs + 1 218 lignes grandeurs_metier).

Calcul deterministe depuis la base (aucun reseau) -> les donnees sont
toujours presentes (pas de seed-gating). Assertions :

- **Structure** : grandeur ``ecart_relatif_dni_cams`` enregistree (F1,
  calculee_volee, unite pourcent) ; 6 series calculees kuma_calculs.
- **Volume** : 1 218 lignes (203 mois communs x 6 villes).
- **Signe (temoin, valeurs reelles)** : Labe 2010-01, ecart relu et
  recalcule depuis les DNI bruts NASA/CAMS (PAS un signe suppose).
- **Orientation globale** : ecart moyen < 0 (NASA < CAMS).
- Unite %, confiance B, aucun NULL.
"""

from __future__ import annotations

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

pytestmark = pytest.mark.integration

_GRANDEUR = "ecart_relatif_dni_cams"
_LOCALITES: tuple[str, ...] = (
    "gin_conakry_kaloum",
    "gin_kankan",
    "gin_kindia",
    "gin_labe",
    "gin_mamou",
    "gin_nzerekore",
)


def _alias(localite_code: str) -> str:
    return "gin_conakry" if localite_code == "gin_conakry_kaloum" else localite_code


def _code_serie(localite_code: str) -> str:
    return f"{_alias(localite_code)}_{_GRANDEUR}_kuma_calculs_2004_2020"


# === Structure =============================================================


def test_grandeur_enregistree(db_session: Session) -> None:
    row = db_session.execute(
        text(
            """
            SELECT gr.famille, gr.strategie_calcul, u.code AS unite_code
            FROM grandeurs_referentiel gr JOIN unites u ON u.id = gr.unite_id
            WHERE gr.code = :g
            """
        ),
        {"g": _GRANDEUR},
    ).one()
    assert row.famille == "F1"
    assert row.strategie_calcul == "calculee_volee"
    assert row.unite_code == "pourcent"


def test_6_series_calculees(db_session: Session) -> None:
    codes = [_code_serie(loc) for loc in _LOCALITES]
    rows = db_session.execute(
        text(
            """
            SELECT sm.code, sm.methode_collecte, s.code AS source_code
            FROM series_metadonnees sm JOIN sources s ON s.id = sm.source_id
            WHERE sm.code = ANY(:codes)
            """
        ),
        {"codes": codes},
    ).all()
    assert {r.code for r in rows} == set(codes)
    for r in rows:
        assert r.source_code == "kuma_calculs"
        assert r.methode_collecte == "calcul_derive"


# === Volume / données ======================================================


def test_volume_1218(db_session: Session) -> None:
    # Scope au climato 2004-2020 : l'atlas Temps 1 (091)
    # ajoute un ecart DNI recent 2021-2023 sous la meme grandeur, fenetre distincte.
    n = db_session.execute(
        text(
            "SELECT COUNT(*) FROM grandeurs_metier WHERE grandeur_code = :g AND annee_debut <= 2020"
        ),
        {"g": _GRANDEUR},
    ).scalar_one()
    assert int(n) == 1218, f"ecart_relatif_dni_cams climato 2004-2020 = {n} (attendu 1218)"


def test_aucun_null_et_confiance_b(db_session: Session) -> None:
    n_null = db_session.execute(
        text("SELECT COUNT(*) FROM grandeurs_metier WHERE grandeur_code = :g AND valeur IS NULL"),
        {"g": _GRANDEUR},
    ).scalar_one()
    assert int(n_null) == 0, f"{n_null} lignes NULL inattendues (pas de seuil applique)"

    niveaux = {
        r[0]
        for r in db_session.execute(
            text(
                "SELECT DISTINCT niveau_confiance_derive FROM grandeurs_metier "
                "WHERE grandeur_code = :g"
            ),
            {"g": _GRANDEUR},
        ).all()
    }
    assert niveaux == {"B"}, f"Niveaux inattendus : {niveaux}"


def test_orientation_globale_negative(db_session: Session) -> None:
    """NASA lit moins de DNI que CAMS -> ecart moyen franchement negatif."""
    # Scope au climato 2004-2020 (l'atlas Temps 1 ajoute le recent).
    moyenne = db_session.execute(
        text(
            "SELECT AVG(valeur) FROM grandeurs_metier "
            "WHERE grandeur_code = :g AND annee_debut <= 2020"
        ),
        {"g": _GRANDEUR},
    ).scalar_one()
    assert float(moyenne) < -5.0, f"ecart moyen = {moyenne} (attendu < -5 %, -25.7 observe)"


def test_signe_temoin_labe_2010_01_valeurs_reelles(db_session: Session) -> None:
    """Temoin Labe 2010-01 : ecart relu == recalcule depuis les DNI bruts.

    Verifie le SIGNE sur des valeurs reelles (NASA 5.1242 / CAMS 7.4900 ->
    -31.5861 %), pas un signe suppose. L'orientation est (nasa - cams)/cams.
    """
    loc_id = db_session.execute(
        text("SELECT id FROM localites WHERE code = 'gin_labe'")
    ).scalar_one()

    ecart_stocke = db_session.execute(
        text(
            """
            SELECT valeur FROM grandeurs_metier
            WHERE grandeur_code = :g AND localite_id = :loc
              AND annee_debut = 2010 AND mois = 1
            """
        ),
        {"g": _GRANDEUR, "loc": loc_id},
    ).scalar_one()

    nasa = db_session.execute(
        text(
            """
            SELECT m.valeur FROM mesures_ressource_mensuelles m
            JOIN series_metadonnees sm ON sm.id = m.serie_id
            WHERE sm.code = 'gin_labe_dni_power_2001_2020' AND m.annee = 2010 AND m.mois = 1
            """
        )
    ).scalar_one()
    cams = db_session.execute(
        text(
            """
            SELECT m.valeur FROM mesures_ressource_mensuelles m
            JOIN series_metadonnees sm ON sm.id = m.serie_id
            WHERE sm.code = 'gin_labe_dni_cams_2004_2020' AND m.annee = 2010 AND m.mois = 1
            """
        )
    ).scalar_one()

    # Valeurs brutes attendues (documentees, tolerance d'arrondi).
    assert abs(float(nasa) - 5.1242) < 1e-3
    assert abs(float(cams) - 7.4900) < 1e-3

    ecart_recalcule = (float(nasa) - float(cams)) / float(cams) * 100.0
    assert float(ecart_stocke) < 0.0, "Signe attendu negatif (NASA < CAMS)"
    assert abs(float(ecart_stocke) - ecart_recalcule) < 1e-9, "Valeur stockee != recalcul brut"
    assert abs(float(ecart_stocke) - (-31.5861)) < 1e-3, (
        f"Temoin Labe 2010-01 = {ecart_stocke} (attendu -31.5861)"
    )
