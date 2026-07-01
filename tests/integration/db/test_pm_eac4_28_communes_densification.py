"""Tests d'integration PM2.5/PM10 EAC4 densification 28 communes.

Verifie l'etat apres ``alembic upgrade head`` (migration 098). Mirror du test pilote
(``test_vague5_pm_eac4_lot_a.py``) etendu aux 28 communes chef-lieu :

- **Structure** (toujours) : 56 series journalieres seedees (28 x 2),
  source ``cams_eac4`` / granularite / methode, ``periode_fin = 2025-08-31``, caveat
  L-SOIL-4 (grille grossiere) porte sur les 28, confiance B.
- **Donnees** (gardees, skip si le seed n'est pas peuple) : volume 95 424, mesures
  confiance B, plage plausible, invariant physique PM10 >= PM2.5 par (commune, date).
- **Anti-ecart** (toujours) : aucune ``grandeur_metier`` ne reference ``cams_eac4``
  (PM = BRUTE seulement ; le caveat L-SOIL-4 n'est PAS materialise en grandeur).

Le **deverrouillage soiling** (commune temoin) est verifie cote API dans
``tests/integration/api/test_soiling_endpoint.py``.
"""

from __future__ import annotations

import datetime as dt

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

pytestmark = pytest.mark.integration

# Enumeration exhaustive des 28 communes chef-lieu (codes = localites.code,
# disjoints des 6 pilotes). Hardcodee pour figer le perimetre et detecter tout drift.
_COMMUNES_28: tuple[str, ...] = (
    "gin_beyla",
    "gin_boffa",
    "gin_boke_centre",
    "gin_coyah",
    "gin_dabola",
    "gin_dalaba",
    "gin_dinguiraye",
    "gin_dubreka",
    "gin_faranah_centre",
    "gin_forecariah",
    "gin_fria",
    "gin_gaoual",
    "gin_gueckedou",
    "gin_kerouane",
    "gin_kissidougou",
    "gin_koubia",
    "gin_koundara",
    "gin_kouroussa",
    "gin_lelouma",
    "gin_lola",
    "gin_macenta",
    "gin_mali",
    "gin_mandiana",
    "gin_pita",
    "gin_siguiri",
    "gin_telimele",
    "gin_tougue",
    "gin_yomou",
)
_GRANDEURS: tuple[str, ...] = ("pm2_5", "pm10")
_SOURCE = "cams_eac4"
_JOURS_FENETRE = 1704  # 2021-01-01 -> 2025-08-31
_VOLUME_ATTENDU = len(_COMMUNES_28) * len(_GRANDEURS) * _JOURS_FENETRE  # 95 424


def _code_serie(commune: str, grandeur: str) -> str:
    return f"{commune}_{grandeur}_cams_eac4_2021_2025"


def _tous_les_codes() -> list[str]:
    return [_code_serie(c, g) for c in _COMMUNES_28 for g in _GRANDEURS]


def _seed_peuple(db_session: Session) -> bool:
    n = db_session.execute(
        text(
            "SELECT COUNT(*) FROM mesures_ressource m "
            "JOIN series_metadonnees sm ON sm.id = m.serie_id "
            "WHERE sm.code = ANY(:codes)"
        ),
        {"codes": _tous_les_codes()},
    ).scalar_one()
    return int(n) > 0


# === Structure (toujours) ==================================================


def test_56_series_seedees(db_session: Session) -> None:
    codes = _tous_les_codes()
    assert len(codes) == 56
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
    assert len(rows) == 56
    for r in rows:
        assert r.source_code == _SOURCE
        assert r.methode_collecte == "modele_satellitaire"
        assert r.granularite == "journalier"
        # Couverture reelle EAC4 : 2021-01-01 a 2025-08-31 (latence reanalyse).
        assert (r.periode_debut, r.periode_fin) == (dt.date(2021, 1, 1), dt.date(2025, 8, 31))


def test_caveat_l_soil_4_porte_sur_les_28(db_session: Session) -> None:
    """Caveat generique L-SOIL-4 (grille grossiere 0,75 deg) present dans les 56
    commentaires editoriaux, mention de la confiance B."""
    rows = db_session.execute(
        text("SELECT code, commentaire_editorial FROM series_metadonnees WHERE code = ANY(:codes)"),
        {"codes": _tous_les_codes()},
    ).all()
    assert len(rows) == 56
    for r in rows:
        assert "L-SOIL-4" in r.commentaire_editorial, f"caveat absent : {r.code}"
        assert "0,75" in r.commentaire_editorial
        assert "Confiance B" in r.commentaire_editorial


# === Anti-ecart (toujours) : PM = BRUTE seulement ==========================


def test_aucune_grandeur_metier_reference_cams_eac4(db_session: Session) -> None:
    """Garde anti-ecart : zero ``grandeur_metier`` adossee a une serie ``cams_eac4``
    (les PM restent brutes ; le caveat L-SOIL-4 n'est PAS materialise en grandeur,
    pas d'equivalent ERA5-ghi invente). Invariant global (pilotes + densification)."""
    n = db_session.execute(
        text(
            """
            SELECT COUNT(*) FROM grandeurs_metier gm
            JOIN series_metadonnees sm ON sm.id = gm.series_metadonnees_id
            JOIN sources s ON s.id = sm.source_id
            WHERE s.code = 'cams_eac4'
            """
        )
    ).scalar_one()
    assert int(n) == 0, f"{n} grandeur(s)_metier reference(nt) cams_eac4 (attendu 0, BRUTE)"


# === Donnees (gardees) =====================================================


def test_volume_mesures(db_session: Session) -> None:
    if not _seed_peuple(db_session):
        pytest.skip("Seed EAC4 densification non peuple (lancer --densification).")
    n = db_session.execute(
        text(
            "SELECT COUNT(*) FROM mesures_ressource m "
            "JOIN series_metadonnees sm ON sm.id = m.serie_id "
            "WHERE sm.code = ANY(:codes)"
        ),
        {"codes": _tous_les_codes()},
    ).scalar_one()
    # 28 communes x 1704 jours (2021-01-01 -> 2025-08-31) x 2 grandeurs = 95 424.
    assert int(n) == _VOLUME_ATTENDU, f"mesures PM EAC4 densif = {n} (attendu {_VOLUME_ATTENDU})"


def test_confiance_b_et_plage(db_session: Session) -> None:
    """Toutes les mesures en B ; concentrations >= 0 et < 2000 ug/m3."""
    if not _seed_peuple(db_session):
        pytest.skip("Seed EAC4 densification non peuple.")
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
    assert int(row.non_b) == 0, "mesures PM densif hors confiance B"
    assert float(row.mn) >= 0.0
    assert float(row.mx) < 2000.0, f"concentration PM implausible : {row.mx}"


def test_invariant_pm10_superieur_pm2_5(db_session: Session) -> None:
    """Invariant physique : PM10 >= PM2.5 par (commune, date) (PM10 inclut PM2.5)."""
    if not _seed_peuple(db_session):
        pytest.skip("Seed EAC4 densification non peuple.")
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
        {"codes": [_code_serie(c, "pm2_5") for c in _COMMUNES_28]},
    ).scalar_one()
    assert int(violations) == 0, f"{violations} (commune, date) avec PM2.5 > PM10"
