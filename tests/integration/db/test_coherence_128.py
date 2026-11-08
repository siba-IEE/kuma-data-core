"""Tests d'intégration de la migration 128 (jargon interne des données publiées).

Garde définitive : aucune colonne de texte (``text``, ``varchar``, tableau,
``jsonb``) d'une table publiée (``TABLES_PUBLIEES`` du manifeste de
publication, et colonnes non neutralisées par ``ASSAINISSEMENTS`` des
``TABLES_ASSAINIES`` depuis la migration 129) ne porte de vocabulaire de
chantier interne (``JARGON_INTERNE``, étendu par la migration 129). Les
colonnes sont lues dans le catalogue : une colonne ajoutée plus tard est
couverte d'office.

Chaque colonne est lue en valeurs distinctes non nulles, sans exclusion : les
tables de mesures (plusieurs millions de lignes) n'ont comme texte que des
codes courts (statut, niveaux de confiance) et un ``commentaire_editorial``
presque toujours nul, ce qui garde la lecture sous quelques secondes.

Pour les tables assainies (``series_metadonnees``, ``contributeurs``), seules
les colonnes masquées (``commentaire_editorial``, courriel, biographie, notes
internes) sont hors de cette garde ; la note publique des séries a en outre
sa propre garde (``test_note_publique_series.py``).

S'y ajoutent la note de dégénérescence servie par l'API (sans « D-29 », règle
conservée en clair) et les corrections de fond de la migration.
"""

from __future__ import annotations

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

from kuma_data_core.api.v1.grandeurs import _lire_degenerescence_localite
from kuma_data_core.publication.manifeste import (
    ASSAINISSEMENTS,
    TABLES_ASSAINIES,
    TABLES_PUBLIEES,
)
from tests._jargon import JARGON_INTERNE

pytestmark = pytest.mark.integration

_TYPES_TEXTE = ("text", "character varying", "character", "ARRAY", "jsonb", "json")


def _colonnes_texte(session: Session, table: str) -> list[str]:
    colonnes = (
        session.execute(
            text(
                """
                SELECT column_name FROM information_schema.columns
                WHERE table_schema = 'public' AND table_name = :t
                  AND data_type = ANY(:types)
                ORDER BY column_name
                """
            ),
            {"t": table, "types": list(_TYPES_TEXTE)},
        )
        .scalars()
        .all()
    )
    masquees = ASSAINISSEMENTS.get(table, {})
    return [c for c in colonnes if c not in masquees]


@pytest.mark.parametrize("table", sorted(TABLES_PUBLIEES | TABLES_ASSAINIES))
def test_table_publiee_sans_jargon_interne(db_session: Session, table: str) -> None:
    colonnes = _colonnes_texte(db_session, table)
    assert colonnes, f"aucune colonne de texte lue pour {table}"
    fautifs: list[tuple[str, str, str]] = []
    for colonne in colonnes:
        valeurs = (
            db_session.execute(
                text(
                    f'SELECT DISTINCT CAST("{colonne}" AS text) FROM "{table}" '
                    f'WHERE "{colonne}" IS NOT NULL'
                )
            )
            .scalars()
            .all()
        )
        fautifs.extend(
            (colonne, m.group(0), valeur[:120])
            for valeur in valeurs
            if (m := JARGON_INTERNE.search(valeur))
        )
    assert fautifs == []


def test_garde_couvre_les_textes_corriges(db_session: Session) -> None:
    """La lecture du catalogue voit bien les colonnes corrigées par la migration."""
    attendues = {
        "grandeurs_metier": "commentaire_editorial",
        "localites": "notes",
        "referentiels_calage": "provenance",
        "sources": "metadonnees",
    }
    for table, colonne in attendues.items():
        assert colonne in _colonnes_texte(db_session, table), (table, colonne)
    assert "notes" in _colonnes_texte(db_session, "sources")


def test_note_degenerescence_api_sans_d29(db_session: Session) -> None:
    nombre = db_session.execute(
        text(
            "SELECT count(*) FROM grandeurs_metier "
            "WHERE grandeur_code = 'degenerescence_pixel' "
            "AND commentaire_editorial LIKE '%D-29%'"
        )
    ).scalar_one()
    assert nombre == 0

    fiche, _ = _lire_degenerescence_localite(db_session, "gin_kindia")
    if fiche is None:
        pytest.skip("degenerescence_pixel non peuplee (base sans seed)")
    assert "D-29" not in fiche.note
    assert "ne pas presenter comme des mesures independantes." in fiche.note


def test_ecmwf_era5_ne_revendique_pas_de_serie(db_session: Session) -> None:
    notes, series = db_session.execute(
        text(
            """
            SELECT s.notes,
                   (SELECT count(*) FROM series_metadonnees sm WHERE sm.source_id = s.id)
            FROM sources s WHERE s.code = 'ecmwf_era5'
            """
        )
    ).one()
    assert series == 0
    assert "Aucune série Kuma n'est ingérée depuis cette source" in notes
    assert "opérationnel phase 1" not in notes


def test_esmap_wapp_declare_ghi_et_dni(db_session: Session) -> None:
    grandeur, grandeurs_series = db_session.execute(
        text(
            """
            SELECT s.metadonnees ->> 'grandeur_ingeree',
                   (SELECT array_agg(DISTINCT sm.grandeur_code ORDER BY sm.grandeur_code)
                    FROM series_metadonnees sm WHERE sm.source_id = s.id)
            FROM sources s WHERE s.code = 'esmap_wapp'
            """
        )
    ).one()
    assert grandeur == "GHI et DNI (agreges horaires, terrain-lite)"
    if grandeurs_series:
        assert grandeurs_series == ["dni", "ghi"]
