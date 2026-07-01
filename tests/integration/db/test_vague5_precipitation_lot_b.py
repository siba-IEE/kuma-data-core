"""Tests d'integration precipitation NASA POWER.

Verifie l'etat apres ``alembic upgrade head`` (migration 080). Deux familles :

- **Structure** (toujours) : unite ``mm_par_jour``, grandeur ``precipitation``
  (F1, stockee), 6 series journalieres seedees, source
  ``nasa_power``, granularite/fenetre/methode.
- **Donnees** (gardees, skip si le seed n'est pas peuple) : volume des mesures,
  positivite (la sentinelle -999 doit etre filtree), et **signal de mousson**
  (Conakry JJAS bien plus humide que DJF) - la verification que c'est de la
  vraie pluie, pas un artefact.

Pattern herite de ``test_vague4_lot_a_era5_land.py``.
"""

from __future__ import annotations

import datetime as dt

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

pytestmark = pytest.mark.integration

_LOCALITES: tuple[str, ...] = (
    "gin_conakry_kaloum",
    "gin_kankan",
    "gin_kindia",
    "gin_labe",
    "gin_mamou",
    "gin_nzerekore",
)
_SOURCE = "nasa_power"


def _alias(localite_code: str) -> str:
    return "gin_conakry" if localite_code == "gin_conakry_kaloum" else localite_code


def _code_serie(localite_code: str) -> str:
    return f"{_alias(localite_code)}_precipitation_nasa_power_2021_2025"


def _tous_les_codes() -> list[str]:
    return [_code_serie(loc) for loc in _LOCALITES]


def _seed_peuple(db_session: Session) -> bool:
    """True si au moins une mesure de precipitation est presente."""
    n = db_session.execute(
        text(
            """
            SELECT COUNT(*) FROM mesures_ressource m
            JOIN series_metadonnees sm ON sm.id = m.serie_id
            WHERE sm.grandeur_code = 'precipitation'
            """
        )
    ).scalar_one()
    return int(n) > 0


# === Structure (toujours) ==================================================


def test_unite_mm_par_jour_seedee(db_session: Session) -> None:
    row = db_session.execute(
        text("SELECT symbole, grandeur, systeme, code_unite_si FROM unites WHERE code = :c"),
        {"c": "mm_par_jour"},
    ).one()
    assert row.symbole == "mm/jour"
    assert row.grandeur == "precipitation"
    assert row.systeme == "composee_mixte"
    assert row.code_unite_si == "metre_par_seconde"


def test_grandeur_precipitation_seedee(db_session: Session) -> None:
    row = db_session.execute(
        text(
            """
            SELECT gr.famille, gr.strategie_calcul, gr.actif, u.code AS unite_code
            FROM grandeurs_referentiel gr JOIN unites u ON u.id = gr.unite_id
            WHERE gr.code = 'precipitation'
            """
        )
    ).one()
    assert row.famille == "F1"
    assert row.strategie_calcul == "stockee"
    assert row.actif is True
    assert row.unite_code == "mm_par_jour"


def test_6_series_seedees(db_session: Session) -> None:
    codes = _tous_les_codes()
    assert len(codes) == 6
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
    assert len(rows) == 6
    for r in rows:
        assert r.source_code == _SOURCE
        assert r.methode_collecte == "modele_satellitaire"
        assert r.granularite == "journalier"
        assert (r.periode_debut, r.periode_fin) == (dt.date(2021, 1, 1), dt.date(2025, 12, 31))


# === Donnees (gardees) =====================================================


def test_volume_mesures(db_session: Session) -> None:
    if not _seed_peuple(db_session):
        pytest.skip("Seed precipitation non peuple (lancer preparer_seed_precipitation.py).")
    n = db_session.execute(
        text(
            """
            SELECT COUNT(*) FROM mesures_ressource m
            JOIN series_metadonnees sm ON sm.id = m.serie_id
            WHERE sm.grandeur_code = 'precipitation' AND sm.code = ANY(:codes)
            """
        ),
        {"codes": _tous_les_codes()},
    ).scalar_one()
    # 6 villes pilotes x 1826 jours (2021-2025) = 10956 (tolerance sur sentinelles -999).
    # migration 094 etend aux 28 communes, scope pilotes ici ; volume communes
    # verifie dans test_parite_b1_precipitation.
    assert 10000 <= int(n) <= 10956, f"mesures precipitation pilotes = {n} (attendu 10956)"


def test_positivite_et_plage(db_session: Session) -> None:
    """Pluie >= 0 (la sentinelle -999 doit etre filtree) et < 1500 mm/jour.

    Le plafond est un garde-fou d'ordre de grandeur (erreur d'unite / sentinelle),
    pas une borne climatique fine. Les pics de mousson du Fouta-Djalon atteignent
    legitimement plusieurs centaines de mm/jour dans le produit NASA POWER PRECTOTCORR.
    La densification (migration 094) ajoute des cellules plus humides : le
    2022-08-20, un meme evenement mousson culmine a Telimele 1021 mm (cellule la plus
    humide, ouest du Fouta), Pita 782, Mamou 608, Labe 564 le meme jour (evenement
    regional coherent, non un artefact). Plafond releve 1000 -> 1500 pour admettre cet
    extreme reel tout en bornant les erreurs grossieres. Source modele (confiance B).
    """
    if not _seed_peuple(db_session):
        pytest.skip("Seed precipitation non peuple.")
    row = db_session.execute(
        text(
            """
            SELECT MIN(m.valeur) AS mn, MAX(m.valeur) AS mx
            FROM mesures_ressource m
            JOIN series_metadonnees sm ON sm.id = m.serie_id
            WHERE sm.grandeur_code = 'precipitation'
            """
        )
    ).one()
    assert float(row.mn) >= 0.0, f"precipitation negative (sentinelle non filtree ?) : {row.mn}"
    assert float(row.mx) < 1500.0, f"precipitation max implausible : {row.mx}"


def test_signal_mousson_conakry(db_session: Session) -> None:
    """Conakry : la mousson (JJAS) est nettement plus humide que la saison seche
    (DJF). Verifie qu'on a bien de la pluie reelle, pas un artefact constant."""
    if not _seed_peuple(db_session):
        pytest.skip("Seed precipitation non peuple.")

    def moyenne_mois(mois: tuple[int, ...]) -> float:
        return float(
            db_session.execute(
                text(
                    """
                    SELECT AVG(m.valeur) FROM mesures_ressource m
                    JOIN series_metadonnees sm ON sm.id = m.serie_id
                    WHERE sm.code = :code
                      AND EXTRACT(MONTH FROM m.instant_mesure) = ANY(:mois)
                    """
                ),
                {"code": _code_serie("gin_conakry_kaloum"), "mois": list(mois)},
            ).scalar_one()
        )

    mousson = moyenne_mois((7, 8, 9))  # juillet-aout-septembre
    seche = moyenne_mois((12, 1, 2))  # decembre-janvier-fevrier
    assert mousson > seche * 5, (
        f"Signal mousson Conakry trop faible : JJAS={mousson:.2f} vs DJF={seche:.2f} mm/jour."
    )
