"""Tests d'intégration de la migration 135 (libellés des écarts inter-source).

- Les deux grandeurs d'écart portent un libellé qui nomme la grandeur et les
  deux sources dans l'ordre de leur formule, celui de leur description.
- Les notes publiques qui reprennent le libellé le reprennent à l'identique.
- Aucun texte publié (colonnes texte des tables hors journal d'audit,
  commentaires du catalogue, document OpenAPI) ne porte plus les anciens
  libellés.
"""

from __future__ import annotations

import json

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

from kuma_data_core.api.main import creer_application

pytestmark = pytest.mark.integration

_LIBELLES = {
    "ecart_relatif_referentiel": "Écart relatif GHI NASA POWER vs SARAH-3",
    "ecart_relatif_dni_cams": "Écart relatif DNI NASA POWER vs CAMS",
}
_FORMULES = {
    "ecart_relatif_referentiel": "(NASA POWER - SARAH-3) / SARAH-3",
    "ecart_relatif_dni_cams": "(NASA POWER - CAMS) / CAMS",
}
_ANCIENS = ("Écart relatif au référentiel Kuma", "Ecart relatif DNI CAMS vs NASA POWER")


def test_libelles_des_ecarts(db_session: Session) -> None:
    rows = dict(
        db_session.execute(
            text("SELECT code, libelle FROM grandeurs_referentiel WHERE code = ANY(:c)"),
            {"c": list(_LIBELLES)},
        ).all()
    )
    assert rows == _LIBELLES


def test_description_suit_l_ordre_du_libelle(db_session: Session) -> None:
    rows = dict(
        db_session.execute(
            text("SELECT code, description FROM grandeurs_referentiel WHERE code = ANY(:c)"),
            {"c": list(_FORMULES)},
        ).all()
    )
    for code, formule in _FORMULES.items():
        assert formule in rows[code], code


def test_notes_reprennent_le_nouveau_libelle(db_session: Session) -> None:
    rows = dict(
        db_session.execute(
            text(
                """
                SELECT s.grandeur_code, count(*) FROM series_metadonnees s
                JOIN grandeurs_referentiel g ON g.code = s.grandeur_code
                WHERE s.note_publique LIKE 'Série ' || g.libelle || ' pour %'
                  AND g.code = ANY(:c)
                GROUP BY s.grandeur_code
                """
            ),
            {"c": list(_LIBELLES)},
        ).all()
    )
    assert rows == {"ecart_relatif_referentiel": 34, "ecart_relatif_dni_cams": 40}


def test_aucun_texte_publie_ne_porte_les_anciens_libelles(db_session: Session) -> None:
    colonnes = db_session.execute(
        text(
            """
            SELECT c.table_name, c.column_name FROM information_schema.columns c
            JOIN information_schema.tables t
              ON t.table_schema = c.table_schema AND t.table_name = c.table_name
            WHERE c.table_schema = 'public' AND t.table_type = 'BASE TABLE'
              AND c.data_type IN ('text', 'character varying', 'jsonb', 'json')
              AND c.table_name <> 'audit_log'
            """
        )
    ).all()
    porteurs = []
    for table, colonne in colonnes:
        n = db_session.execute(
            text(
                f'SELECT count(*) FROM "{table}" '
                f'WHERE strpos("{colonne}"::text, :a) > 0 OR strpos("{colonne}"::text, :b) > 0'
            ),
            {"a": _ANCIENS[0], "b": _ANCIENS[1]},
        ).scalar_one()
        if n:
            porteurs.append((table, colonne, n))
    assert porteurs == []

    commentaires = db_session.execute(
        text(
            "SELECT count(*) FROM pg_description "
            "WHERE strpos(description, :a) > 0 OR strpos(description, :b) > 0"
        ),
        {"a": _ANCIENS[0], "b": _ANCIENS[1]},
    ).scalar_one()
    assert commentaires == 0


def test_document_openapi_sans_anciens_libelles() -> None:
    document = json.dumps(creer_application().openapi(), ensure_ascii=False)
    for ancien in _ANCIENS:
        assert ancien not in document
