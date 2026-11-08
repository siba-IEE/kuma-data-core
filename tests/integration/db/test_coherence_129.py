"""Tests d'intégration de la migration 129 (jargon des fiches de compilation).

La garde générale (toutes les colonnes de texte publiées, y compris les
colonnes non masquées des tables assainies, avec le motif étendu) vit dans
``test_coherence_128.py``. Ici :

- la garde lit bien les colonnes de documentation des séries et laisse de côté
  la colonne masquée ;
- les liens de documentation des séries visent le dépôt public et un fichier
  qui existe dans le dépôt ;
- le contenu porté par les codes retirés est conservé en clair (règles du
  cahier des charges, ordre de tutelle, restrictions d'accès, fait sur le
  chiffre 93 304 de Mamou, correction du code ``wmo_8_2024``).
"""

from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

from tests.integration.db.test_coherence_128 import _colonnes_texte

pytestmark = pytest.mark.integration

_RACINE_DEPOT = Path(__file__).resolve().parents[3]
_DEPOT_PUBLIC = "https://github.com/siba-IEE/kuma-data-core/blob/main/"


def test_garde_couvre_la_documentation_des_series(db_session: Session) -> None:
    colonnes = _colonnes_texte(db_session, "series_metadonnees")
    assert {"methode_collecte_doc", "url_documentation", "note_publique"} <= set(colonnes)
    assert "commentaire_editorial" not in colonnes


def test_documentation_series_vise_le_depot_public(db_session: Session) -> None:
    valeurs = (
        db_session.execute(
            text(
                """
                SELECT DISTINCT v FROM series_metadonnees,
                  LATERAL (VALUES (methode_collecte_doc), (url_documentation)) AS t(v)
                WHERE v IS NOT NULL AND v NOT LIKE 'http%'
                """
            )
        )
        .scalars()
        .all()
    )
    assert valeurs == [], "chemin de dépôt relatif dans une colonne publiée"

    liens = (
        db_session.execute(
            text(
                """
                SELECT v, count(*) FROM series_metadonnees,
                  LATERAL (VALUES (methode_collecte_doc), (url_documentation)) AS t(v)
                WHERE v LIKE :prefixe || '%'
                GROUP BY v
                """
            ),
            {"prefixe": _DEPOT_PUBLIC},
        )
        .tuples()
        .all()
    )
    if not liens:
        pytest.skip("séries calculées non peuplées (base sans seed)")
    for lien, _ in liens:
        chemin = _RACINE_DEPOT / lien.removeprefix(_DEPOT_PUBLIC)
        assert chemin.is_file(), f"{lien} ne vise aucun fichier du dépôt"
    assert sum(n for _, n in liens) == 2 * 198


def test_rang_referentiel_temporel_vise_sa_note_methodologique(db_session: Session) -> None:
    liens = (
        db_session.execute(
            text(
                """
                SELECT DISTINCT url_documentation FROM series_metadonnees
                WHERE grandeur_code = 'rang_referentiel_temporel'
                  AND url_documentation IS NOT NULL
                """
            )
        )
        .scalars()
        .all()
    )
    if not liens:
        pytest.skip("séries calculées non peuplées (base sans seed)")
    assert liens == [_DEPOT_PUBLIC + "docs/methodologie/referentiels-comparatifs-phase-1.md"]


def _notes_localite(session: Session, code: str) -> str:
    return str(
        session.execute(
            text("SELECT notes FROM localites WHERE code = :c"), {"c": code}
        ).scalar_one()
    )


def _notes_source(session: Session, code: str) -> str:
    return str(
        session.execute(text("SELECT notes FROM sources WHERE code = :c"), {"c": code}).scalar_one()
    )


def test_localites_regles_en_clair(db_session: Session) -> None:
    n_demographie = db_session.execute(
        text("SELECT count(*) FROM localites WHERE notes LIKE '%Demographie NULL : %'")
    ).scalar_one()
    assert n_demographie == 61
    assert "pas du centroid régional (convention Kuma)" in _notes_localite(db_session, "gin_boke")
    assert "(règle Kuma : RGPH-3 brut strict)" in _notes_localite(db_session, "gin_conakry_matam")
    mamou = _notes_localite(db_session, "gin_mamou")
    assert "Le chiffre 93 304 est une projection RGPH-3 à 2017" in mamou
    assert "verifiee en relecture le 2026-06-20" in _notes_localite(db_session, "gin_lelouma")
    assert "Chef-lieu deja ingere (commune existante, Wikidata Q874317)" in _notes_localite(
        db_session, "gin_kankan_prefecture"
    )


def test_sources_contenu_en_clair(db_session: Session) -> None:
    n_tutelle = db_session.execute(
        text("SELECT count(*) FROM sources WHERE strpos(notes, :f) > 0"),
        {"f": "Convention de code (ordre de tutelle) :"},
    ).scalar_one()
    assert n_tutelle == 9
    assert "Accès à la source primaire fortement restreint" in _notes_source(
        db_session, "anm_guinee_stations"
    )
    wmo_8 = _notes_source(db_session, "wmo_8_2024")
    assert "`wmo_8_2023` (provisoire en mai 2026), a été corrigé en `wmo_8_2024`" in wmo_8
    hydrosheds = _notes_source(db_session, "wwf_hydrosheds")
    assert "statut du vecteur hydro (schéma de validation conçu, population différée)" in hydrosheds
