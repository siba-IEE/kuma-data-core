"""Tests d'integration : indicateur de degenerescence de pixel (migration 090).

Verifie l'etat apres ``alembic upgrade head``. La grandeur F1 ``degenerescence_pixel``
est materialisee dans ``grandeurs_metier`` (1 ligne statique par localite x source x
parametre, valeur = nombre de jumeaux-pixel).

Verite-terrain (sondee en base) :

- NASA radiation (CERES 1deg) : 8 groupes de jumeaux -> distribution valeur
  0 x14, 1 x10, 2 x6, 3 x4 (5 paires, 2 triplets, 1 quadruplet cotier, 14 resolus).
- NASA meteo (MERRA 0.5deg) : 5 groupes (toutes paires) -> 0 x24, 1 x10.
- SARAH-3 / CAMS (interpoles 5 km) : 0 partout.
- {Dalaba, Kindia, Mamou} co-pixel radiatif (valeur 2 chacun).

Fixture ``db_session`` (conftest.py). Base d'integration a head (090).
"""

from __future__ import annotations

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

pytestmark = pytest.mark.integration

_GRANDEUR = "degenerescence_pixel"


def _distribution(db_session: Session, source: str, grandeur: str) -> dict[int, int]:
    """Distribution {valeur: nb_localites} de degenerescence_pixel pour (source, parametre)."""
    rows = db_session.execute(
        text(
            """
            SELECT gm.valeur, COUNT(*) AS n
            FROM grandeurs_metier gm
            JOIN series_metadonnees sm ON sm.id = gm.series_metadonnees_id
            JOIN sources s ON s.id = sm.source_id
            WHERE gm.grandeur_code = :gr AND s.code = :src AND sm.grandeur_code = :g
            GROUP BY gm.valeur
            """
        ),
        {"gr": _GRANDEUR, "src": source, "g": grandeur},
    ).all()
    return {int(r.valeur): int(r.n) for r in rows}


def test_grandeur_declaree(db_session: Session) -> None:
    """La grandeur est cataloguee F1 calculee_volee, unite sans_unite."""
    row = db_session.execute(
        text(
            """
            SELECT gr.famille, gr.strategie_calcul, u.code AS unite
            FROM grandeurs_referentiel gr
            JOIN unites u ON u.id = gr.unite_id
            WHERE gr.code = :c
            """
        ),
        {"c": _GRANDEUR},
    ).first()
    assert row is not None
    assert row.famille == "F1"
    assert row.strategie_calcul == "calculee_volee"
    assert row.unite == "sans_unite"


def test_volume_374_lignes(db_session: Session) -> None:
    """34 points x 11 (source x parametre) = 374 lignes materialisees."""
    n = db_session.execute(
        text("SELECT COUNT(*) FROM grandeurs_metier WHERE grandeur_code = :c"),
        {"c": _GRANDEUR},
    ).scalar_one()
    assert n == 374


def test_metadonnees_uniformes(db_session: Session) -> None:
    """Toutes les lignes : confiance B (B3-6 : A reservee terrain), statique, mois NULL."""
    rows = db_session.execute(
        text(
            """
            SELECT DISTINCT niveau_confiance_derive, periode_type,
                   (mois IS NULL) AS mois_null
            FROM grandeurs_metier WHERE grandeur_code = :c
            """
        ),
        {"c": _GRANDEUR},
    ).all()
    assert len(rows) == 1
    assert rows[0].niveau_confiance_derive == "B"
    assert rows[0].periode_type == "statique"
    assert rows[0].mois_null is True


def test_confiance_b_avec_caveat_exactitude(db_session: Session) -> None:
    """Reste en B (A = terrain) mais le commentaire nomme l'exactitude (caveat B3-6)."""
    comm = db_session.execute(
        text(
            """
            SELECT gm.commentaire_editorial
            FROM grandeurs_metier gm
            JOIN localites l ON l.id = gm.localite_id
            JOIN series_metadonnees sm ON sm.id = gm.series_metadonnees_id
            WHERE gm.grandeur_code = :c AND l.code = 'gin_kindia'
              AND sm.grandeur_code = 'ghi' AND sm.granularite = 'mensuel'
              AND sm.periode_debut = '1991-01-01'
            """
        ),
        {"c": _GRANDEUR},
    ).scalar_one()
    assert "exact" in comm.lower()
    assert "terrain" in comm.lower()  # le caveat dit pourquoi B et pas A


def test_radiation_ceres_8_groupes(db_session: Session) -> None:
    """NASA radiation (CERES 1deg) : ghi -> 0 x14, 1 x10, 2 x6, 3 x4 (8 groupes)."""
    assert _distribution(db_session, "nasa_power", "ghi") == {0: 14, 1: 10, 2: 6, 3: 4}


def test_meteo_merra_plus_fine(db_session: Session) -> None:
    """NASA meteo (MERRA 0.5deg) : t2m -> 0 x24, 1 x10. Grille plus fine = moins degenere."""
    assert _distribution(db_session, "nasa_power", "t2m") == {0: 24, 1: 10}


def test_degenerescence_par_parametre(db_session: Session) -> None:
    """La radiation (CERES) est plus degeneree que la meteo (MERRA) ; dni suit ghi,
    vent_10m suit t2m (meme grille par classe de parametre)."""
    assert _distribution(db_session, "nasa_power", "dni") == _distribution(
        db_session, "nasa_power", "ghi"
    )
    assert _distribution(db_session, "nasa_power", "vent_10m") == _distribution(
        db_session, "nasa_power", "t2m"
    )
    # Strictement plus de points degeneres en radiation qu'en meteo.
    n_radiation = 34 - _distribution(db_session, "nasa_power", "ghi")[0]
    n_meteo = 34 - _distribution(db_session, "nasa_power", "t2m")[0]
    assert n_radiation > n_meteo  # 20 > 10


def test_sources_interpolees_zero(db_session: Session) -> None:
    """SARAH-3 / CAMS (interpoles 5 km) : compte 0 partout (valeurs distinctes)."""
    assert _distribution(db_session, "sarah3_monthly", "ghi") == {0: 34}
    assert _distribution(db_session, "cams_radiation", "dni") == {0: 34}


def test_caveat_resolution_sur_interpolees(db_session: Session) -> None:
    """Les lignes interpolees portent un caveat de resolution, pas un compte de jumeaux."""
    comm = db_session.execute(
        text(
            """
            SELECT gm.commentaire_editorial
            FROM grandeurs_metier gm
            JOIN series_metadonnees sm ON sm.id = gm.series_metadonnees_id
            JOIN sources s ON s.id = sm.source_id
            JOIN localites l ON l.id = gm.localite_id
            WHERE gm.grandeur_code = :gr AND s.code = 'sarah3_monthly'
              AND l.code = 'gin_boffa'
            """
        ),
        {"gr": _GRANDEUR},
    ).scalar_one()
    assert "interpolee" in comm.lower()
    assert "resolution" in comm.lower()


def test_d29_kindia_mamou_dalaba_co_pixel(db_session: Session) -> None:
    """Dalaba, Kindia, Mamou co-pixel radiatif (valeur 2, jumeaux nommes)."""
    for loc in ("gin_kindia", "gin_mamou", "gin_dalaba"):
        row = db_session.execute(
            text(
                """
                SELECT gm.valeur, gm.commentaire_editorial AS comm
                FROM grandeurs_metier gm
                JOIN series_metadonnees sm ON sm.id = gm.series_metadonnees_id
                JOIN localites l ON l.id = gm.localite_id
                WHERE gm.grandeur_code = :gr AND l.code = :loc
                  AND sm.grandeur_code = 'ghi' AND sm.granularite = 'mensuel'
                  AND sm.periode_debut = '1991-01-01'
                """
            ),
            {"gr": _GRANDEUR, "loc": loc},
        ).first()
        assert row is not None
        assert int(row.valeur) == 2, f"{loc} attendu valeur=2, obtenu {row.valeur}"
        # Le commentaire nomme les deux autres jumeaux du triplet.
        autres = {"gin_dalaba", "gin_kindia", "gin_mamou"} - {loc}
        for jumeau in autres:
            assert jumeau in row.comm, f"{loc} doit nommer {jumeau} dans son commentaire"


def test_ghi_dni_partagent_grille_ceres(db_session: Session) -> None:
    """Garde de l'hypothese atlas Temps 2 : la degenerescence NASA ``ghi`` == NASA ``dni``
    pour chaque point (memes pixels CERES). L'endpoint inter-source prend la ligne ``ghi``
    comme representative du DNI ; si une grille future casse l'egalite, ce test l'attrape."""
    rows = db_session.execute(
        text(
            """
            SELECT l.code AS loc, sm.grandeur_code AS g, gm.valeur
            FROM grandeurs_metier gm
            JOIN localites l ON l.id = gm.localite_id
            JOIN series_metadonnees sm ON sm.id = gm.series_metadonnees_id
            JOIN sources s ON s.id = sm.source_id
            WHERE gm.grandeur_code = 'degenerescence_pixel'
              AND s.code = 'nasa_power' AND sm.grandeur_code IN ('ghi', 'dni')
            """
        )
    ).all()
    par_loc: dict[str, dict[str, int]] = {}
    for r in rows:
        par_loc.setdefault(r.loc, {})[r.g] = int(r.valeur)
    assert par_loc, "aucune ligne degenerescence NASA ghi/dni"
    for code, d in par_loc.items():
        assert d.get("ghi") == d.get("dni"), f"{code}: ghi={d.get('ghi')} != dni={d.get('dni')}"
