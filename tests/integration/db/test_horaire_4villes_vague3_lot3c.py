"""Tests d'integration du seed horaire 4 villes.

Ce seed etend le rollout horaire (apres Kindia) aux 4 villes neuves
restantes (Mamou, Labe, Kankan, Nzerekore) en serie unique pleine
profondeur 2001-2023. L'ingestion de masse est court-circuitee en CI par
``KUMA_SKIP_INGESTION_MASSE_HORAIRE`` ; le seed des 24
series est inconditionnel. Les assertions portent sur la **structure**
(invariante que l'ingestion ait tourne ou non).

Cas particulier Mamou (dette D-29) : co-pixel CERES avec Kindia. Le
radiatif (ghi/dni/dhi/kt) est ingere quand meme (symetrie catalogue) avec
un ``commentaire_editorial`` documentant l'identite - verifie ici.
"""

from __future__ import annotations

import datetime as dt

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

pytestmark = pytest.mark.integration


_GRANDEURS_HORAIRES: tuple[str, ...] = ("ghi", "dni", "dhi", "t2m", "rh2m", "kt")
_VILLES_3C: tuple[str, ...] = ("gin_mamou", "gin_labe", "gin_kankan", "gin_nzerekore")
_GRANDEURS_COPIXEL_MAMOU: frozenset[str] = frozenset({"ghi", "dni", "dhi", "kt"})


def _code_serie(localite: str, grandeur: str) -> str:
    return f"{localite}_{grandeur}_nasa_power_2001_2023"


def test_3c_24_series_seedees(db_session: Session) -> None:
    """Les 24 series horaires (4 villes x 6 grandeurs) 2001-2023 sont seedees."""
    codes = [_code_serie(loc, g) for loc in _VILLES_3C for g in _GRANDEURS_HORAIRES]
    rows = db_session.execute(
        text("SELECT code FROM series_metadonnees WHERE code = ANY(:codes)"),
        {"codes": codes},
    ).all()
    codes_trouves = {r.code for r in rows}
    assert codes_trouves == set(codes), (
        f"24 series 3c attendues, manquantes : {set(codes) - codes_trouves}"
    )


def test_3c_metadonnees_series(db_session: Session) -> None:
    """Chaque serie 3c : granularite horaire, fenetre 2001-2023, source/methode."""
    rows = db_session.execute(
        text(
            """
            SELECT sm.granularite, sm.periode_debut, sm.periode_fin,
                   sm.methode_collecte, s.code AS source_code, l.code AS localite_code
            FROM series_metadonnees sm
            JOIN sources s ON s.id = sm.source_id
            JOIN localites l ON l.id = sm.localite_id
            WHERE sm.code = ANY(:codes)
            """
        ),
        {"codes": [_code_serie(loc, g) for loc in _VILLES_3C for g in _GRANDEURS_HORAIRES]},
    ).all()

    assert len(rows) == 24
    for r in rows:
        assert r.granularite == "horaire"
        assert r.periode_debut == dt.date(2001, 1, 1)
        assert r.periode_fin == dt.date(2023, 12, 31)
        assert r.source_code == "nasa_power"
        assert r.methode_collecte == "modele_satellitaire"
        assert r.localite_code in _VILLES_3C


def test_3c_serie_unique_par_ville_grandeur(db_session: Session) -> None:
    """Serie NASA POWER unique pleine profondeur par (ville, grandeur) - forme exigee par 3a.

    Scope **source nasa_power** : la couche satellite a une serie horaire unique
    par (ville, grandeur). Les sources sol (terrain-lite esmap_wapp, confiance A)
    sont une couche distincte et peuvent ajouter une 2e serie horaire (ex. GHI
    Kankan) sans casser l'unicite du rollout satellite.
    """
    for localite in _VILLES_3C:
        for grandeur in _GRANDEURS_HORAIRES:
            n = db_session.execute(
                text(
                    """
                    SELECT COUNT(*) FROM series_metadonnees sm
                    JOIN localites l ON l.id = sm.localite_id
                    JOIN sources s ON s.id = sm.source_id
                    WHERE l.code = :loc AND sm.grandeur_code = :grandeur
                      AND sm.granularite = 'horaire'
                      AND s.code = 'nasa_power'
                    """
                ),
                {"loc": localite, "grandeur": grandeur},
            ).scalar_one()
            assert n == 1, f"{localite}/{grandeur} : {n} series horaires nasa_power (attendu 1)"


def test_3c_mamou_radiatif_documente_d29(db_session: Session) -> None:
    """Mamou (co-pixel D-29) : les 4 series radiatives portent la note d'identite Kindia."""
    for grandeur in _GRANDEURS_COPIXEL_MAMOU:
        commentaire = db_session.execute(
            text("SELECT commentaire_editorial FROM series_metadonnees WHERE code = :c"),
            {"c": _code_serie("gin_mamou", grandeur)},
        ).scalar_one()
        assert "Kindia" in commentaire and "D-29" in commentaire, (
            f"Mamou/{grandeur} : commentaire ne documente pas le co-pixel D-29"
        )
    # t2m / rh2m (MERRA-2, donnee propre) : pas de note co-pixel.
    for grandeur in ("t2m", "rh2m"):
        commentaire = db_session.execute(
            text("SELECT commentaire_editorial FROM series_metadonnees WHERE code = :c"),
            {"c": _code_serie("gin_mamou", grandeur)},
        ).scalar_one()
        assert "D-29" not in commentaire, f"Mamou/{grandeur} ne devrait pas porter la note D-29"
