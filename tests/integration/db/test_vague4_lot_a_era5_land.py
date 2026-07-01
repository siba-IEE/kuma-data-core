"""Tests d'integration ERA5-Land.

Verifie l'etat apres ``alembic upgrade head`` (migrations 068 source +
069 series/mesures). Deux familles d'assertions :

- **Structure** (toujours executees) : 36 series ERA5-Land seedees,
  source ``ecmwf_era5_land``, granularites, fenetres, methode.
- **Donnees** (gardees, skip si le seed n'est pas peuple) : volume des
  mesures, coherence physique de 1er ordre (dont le controle K->C qui
  attrape tout bug de conversion), et **separation Kindia/Mamou** -
  l'assertion centrale : sous ERA5-Land les deux villes ne sont plus
  bit-identiques comme sous CERES 1deg.

Pattern : fixture ``db_session`` (conftest.py), assertions post-upgrade head
(herite de ``test_horaire_kindia_vague3_lot3b.py``).
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
_GRANDEURS: tuple[str, ...] = ("ghi", "t2m", "vent_10m")
_SOURCE = "ecmwf_era5_land"


def _alias(localite_code: str) -> str:
    return "gin_conakry" if localite_code == "gin_conakry_kaloum" else localite_code


def _code_mensuel(localite_code: str, grandeur: str) -> str:
    return f"{_alias(localite_code)}_{grandeur}_era5_land_2001_2020"


def _code_journalier(localite_code: str, grandeur: str) -> str:
    return f"{_alias(localite_code)}_{grandeur}_era5_land_2021_2025"


def _tous_les_codes() -> list[str]:
    codes: list[str] = []
    for loc in _LOCALITES:
        for g in _GRANDEURS:
            codes.append(_code_mensuel(loc, g))
            codes.append(_code_journalier(loc, g))
    return codes


def _seed_peuple(db_session: Session) -> bool:
    """True si au moins une mesure ERA5-Land mensuelle est presente."""
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


# === Structure (toujours) ==================================================


def test_source_ecmwf_era5_land_seedee(db_session: Session) -> None:
    row = db_session.execute(
        text("SELECT type_source, fiabilite, doi FROM sources WHERE code = :c"),
        {"c": _SOURCE},
    ).one()
    assert row.type_source == "base_donnees"
    assert row.fiabilite == "haute"
    assert row.doi == "10.24381/cds.68d2bb30"


def test_36_series_seedees(db_session: Session) -> None:
    codes = _tous_les_codes()
    assert len(codes) == 36
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
    assert len(rows) == 36
    for r in rows:
        assert r.source_code == _SOURCE
        assert r.methode_collecte == "modele_satellitaire"
        if r.granularite == "mensuel":
            assert (r.periode_debut, r.periode_fin) == (dt.date(2001, 1, 1), dt.date(2020, 12, 31))
        else:
            assert r.granularite == "journalier"
            assert (r.periode_debut, r.periode_fin) == (dt.date(2021, 1, 1), dt.date(2025, 12, 31))


# === Données (gardées) =====================================================


def test_volume_mesures(db_session: Session) -> None:
    if not _seed_peuple(db_session):
        pytest.skip("Seed ERA5-Land non peuple (lancer scripts/preparer_seed_era5_land.py).")
    # Scope aux 36 codes pilotes (migration 096 etend l'ERA5 mensuel aux 28 ;
    # le volume communes est verifie dans test_parite_b3a_era5_mensuel).
    n_mens = db_session.execute(
        text(
            "SELECT COUNT(*) FROM mesures_ressource_mensuelles m "
            "JOIN series_metadonnees sm ON sm.id = m.serie_id "
            "JOIN sources s ON s.id = sm.source_id WHERE s.code = :src AND sm.code = ANY(:codes)"
        ),
        {"src": _SOURCE, "codes": _tous_les_codes()},
    ).scalar_one()
    # 18 series mensuelles pilotes x 240 mois = 4320 (tolerance sur sentinelles eventuelles).
    assert 4200 <= int(n_mens) <= 4320, f"mensuelles ERA5-Land pilotes = {n_mens} (attendu 4320)"

    n_jour = db_session.execute(
        text(
            "SELECT COUNT(*) FROM mesures_ressource m "
            "JOIN series_metadonnees sm ON sm.id = m.serie_id "
            "JOIN sources s ON s.id = sm.source_id WHERE s.code = :src AND sm.code = ANY(:codes)"
        ),
        {"src": _SOURCE, "codes": _tous_les_codes()},
    ).scalar_one()
    # 18 series journalieres pilotes x 1826 jours 32868.
    assert 30000 <= int(n_jour) <= 33000, (
        f"journalieres ERA5-Land pilotes = {n_jour} (attendu 32868)"
    )


def test_coherence_premier_ordre(db_session: Session) -> None:
    """Plages physiques par grandeur (le borne T2M attrape un bug K->C)."""
    if not _seed_peuple(db_session):
        pytest.skip("Seed ERA5-Land non peuple.")
    bornes = {"ghi": (0.0, 9.0), "t2m": (10.0, 40.0), "vent_10m": (0.0, 25.0)}
    for grandeur, (lo, hi) in bornes.items():
        row = db_session.execute(
            text(
                """
                SELECT MIN(m.valeur) AS mn, MAX(m.valeur) AS mx
                FROM mesures_ressource_mensuelles m
                JOIN series_metadonnees sm ON sm.id = m.serie_id
                JOIN sources s ON s.id = sm.source_id
                WHERE s.code = :src AND sm.grandeur_code = :g
                """
            ),
            {"src": _SOURCE, "g": grandeur},
        ).one()
        assert lo <= float(row.mn) and float(row.mx) <= hi, (
            f"{grandeur} hors plage [{lo}, {hi}] : min={row.mn}, max={row.mx}"
        )


def test_d29_separation_kindia_mamou(db_session: Session) -> None:
    """Sous ERA5-Land, le GHI Kindia n'est plus bit-identique a Mamou.

    Contraste avec CERES SYN1deg (meme cellule 1deg -> series identiques).
    """
    if not _seed_peuple(db_session):
        pytest.skip("Seed ERA5-Land non peuple.")

    def ghi_mensuel(localite_code: str) -> list[tuple[int, int, float]]:
        return [
            (int(r.annee), int(r.mois), float(r.valeur))
            for r in db_session.execute(
                text(
                    """
                    SELECT m.annee, m.mois, m.valeur
                    FROM mesures_ressource_mensuelles m
                    JOIN series_metadonnees sm ON sm.id = m.serie_id
                    WHERE sm.code = :code ORDER BY m.annee, m.mois
                    """
                ),
                {"code": _code_mensuel(localite_code, "ghi")},
            ).all()
        ]

    kindia = ghi_mensuel("gin_kindia")
    mamou = ghi_mensuel("gin_mamou")
    assert kindia and mamou, "Series GHI Kindia/Mamou attendues peuplees."
    assert kindia != mamou, (
        "GHI ERA5-Land Kindia == Mamou : la separation spatiale D-29 attendue "
        "n'est pas observee (pixels 0.1deg distincts attendus)."
    )
