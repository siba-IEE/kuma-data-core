"""Tests d'integration CAMS Radiation DNI.

Verifie l'etat apres ``alembic upgrade head`` (migrations 070 source +
071 series/mesures). Deux familles d'assertions :

- **Structure** (toujours executees) : 6 series CAMS DNI seedees,
  ``*_dni_cams_2004_2020``, source ``cams_radiation`` (doi NULL),
  granularite mensuel, fenetre 2004-02 -> 2020-12, methode satellitaire.
- **Donnees** (gardees, skip si le seed n'est pas peuple) : volume exact
  (1 218 = 203 x 6), confiance B, coherence physique de 1er ordre (plage
  DNI qui attrape tout bug de conversion Wh->kWh ou oubli du /jours), et
  **signal Harmattan** : DNI Labe (altitude, sec) > Conakry (cotier humide).

Chiffres figes apres verification du seed reel genere par
``scripts/preparer_seed_cams.py`` (constat : 1 218 mesures, plage observee
1.54-8.28 kWh/m2/jour, moyennes Labe 5.26 vs Conakry 3.70).

Pattern : fixture ``db_session`` (conftest.py), assertions post-upgrade head
(herite de ``test_vague4_lot_a_era5_land.py``).
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
_SOURCE = "cams_radiation"


def _alias(localite_code: str) -> str:
    return "gin_conakry" if localite_code == "gin_conakry_kaloum" else localite_code


def _code(localite_code: str) -> str:
    return f"{_alias(localite_code)}_dni_cams_2004_2020"


def _tous_les_codes() -> list[str]:
    return [_code(loc) for loc in _LOCALITES]


def _seed_peuple(db_session: Session) -> bool:
    """True si au moins une mesure CAMS mensuelle est presente."""
    n = db_session.execute(
        text(
            """
            SELECT COUNT(*) FROM mesures_ressource_mensuelles m
            JOIN series_metadonnees sm ON sm.id = m.serie_id
            JOIN sources s ON s.id = sm.source_id
            WHERE s.code = :src
            """
        ),
        {"src": _SOURCE},
    ).scalar_one()
    return int(n) > 0


def _moyenne_dni(db_session: Session, localite_code: str) -> float:
    return float(
        db_session.execute(
            text(
                """
                SELECT AVG(m.valeur)
                FROM mesures_ressource_mensuelles m
                JOIN series_metadonnees sm ON sm.id = m.serie_id
                WHERE sm.code = :code
                """
            ),
            {"code": _code(localite_code)},
        ).scalar_one()
    )


# === Structure (toujours) ==================================================


def test_source_cams_radiation_seedee(db_session: Session) -> None:
    row = db_session.execute(
        text("SELECT type_source, fiabilite, doi FROM sources WHERE code = :c"),
        {"c": _SOURCE},
    ).one()
    assert row.type_source == "base_donnees"
    assert row.fiabilite == "haute"
    # DOI de catalogue ADS Copernicus (section citation de la page dataset).
    assert row.doi == "10.24381/5cab0912"


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
                   sm.methode_collecte, sm.grandeur_code, s.code AS source_code
            FROM series_metadonnees sm JOIN sources s ON s.id = sm.source_id
            WHERE sm.code = ANY(:codes)
            """
        ),
        {"codes": _tous_les_codes()},
    ).all()
    assert len(rows) == 6
    for r in rows:
        assert r.source_code == _SOURCE
        assert r.grandeur_code == "dni"
        assert r.methode_collecte == "modele_satellitaire"
        assert r.granularite == "mensuel"
        assert (r.periode_debut, r.periode_fin) == (dt.date(2004, 2, 1), dt.date(2020, 12, 31))


# === Données (gardées) =====================================================


def test_volume_mesures(db_session: Session) -> None:
    if not _seed_peuple(db_session):
        pytest.skip("Seed CAMS non peuple (lancer scripts/preparer_seed_cams.py).")
    # Scopé aux 6 séries climato 2004-2020 (pas à la source : l'extension
    # récente 2021-2023, migration 073, partage la source cams_radiation).
    n_mens = db_session.execute(
        text(
            "SELECT COUNT(*) FROM mesures_ressource_mensuelles m "
            "JOIN series_metadonnees sm ON sm.id = m.serie_id "
            "WHERE sm.code = ANY(:codes)"
        ),
        {"codes": _tous_les_codes()},
    ).scalar_one()
    # 6 series x 203 mois (2004-02 -> 2020-12) = 1 218.
    assert int(n_mens) == 1218, f"mensuelles CAMS 2004-2020 = {n_mens} (attendu 1218)"


def test_confiance_b(db_session: Session) -> None:
    if not _seed_peuple(db_session):
        pytest.skip("Seed CAMS non peuple.")
    niveaux = {
        r.niveau_confiance_derive
        for r in db_session.execute(
            text(
                """
                SELECT DISTINCT m.niveau_confiance_derive
                FROM mesures_ressource_mensuelles m
                JOIN series_metadonnees sm ON sm.id = m.serie_id
                JOIN sources s ON s.id = sm.source_id
                WHERE s.code = :src
                """
            ),
            {"src": _SOURCE},
        ).all()
    }
    assert niveaux == {"B"}, f"Niveaux de confiance CAMS inattendus : {niveaux}"


def test_coherence_premier_ordre(db_session: Session) -> None:
    """Plage physique DNI (attrape un oubli du /1000 Wh->kWh ou du /nb_jours)."""
    if not _seed_peuple(db_session):
        pytest.skip("Seed CAMS non peuple.")
    row = db_session.execute(
        text(
            """
            SELECT MIN(m.valeur) AS mn, MAX(m.valeur) AS mx
            FROM mesures_ressource_mensuelles m
            JOIN series_metadonnees sm ON sm.id = m.serie_id
            JOIN sources s ON s.id = sm.source_id
            WHERE s.code = :src
            """
        ),
        {"src": _SOURCE},
    ).one()
    # Plage observee 1.54-8.28 kWh/m2/jour ; bornes physiques avec marge.
    assert float(row.mn) >= 1.0 and float(row.mx) <= 9.0, (
        f"DNI CAMS hors plage [1.0, 9.0] : min={row.mn}, max={row.mx}"
    )


def test_signal_harmattan_labe_gt_conakry(db_session: Session) -> None:
    """Signal Harmattan : DNI moyen Labe (altitude, air sec) > Conakry (cotier).

    Assertion directionnelle (seuil documente non fige a priori) : l'ecart
    observe est 1.56 kWh/m2/jour (Labe 5.26 vs Conakry 3.70). On exige un
    ecart franc (> 0.5) pour distinguer du bruit.
    """
    if not _seed_peuple(db_session):
        pytest.skip("Seed CAMS non peuple.")
    labe = _moyenne_dni(db_session, "gin_labe")
    conakry = _moyenne_dni(db_session, "gin_conakry_kaloum")
    assert labe - conakry > 0.5, (
        f"Signal Harmattan attendu (Labe > Conakry) non observe : "
        f"Labe={labe:.3f}, Conakry={conakry:.3f}"
    )
