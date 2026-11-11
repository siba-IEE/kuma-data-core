"""Liens de documentation des séries : des URL. Lecture seule.

``methode_collecte_doc`` et ``url_documentation`` citent une URL ; un chemin
relatif au dépôt ne mène nulle part hors du dépôt.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

pytestmark = pytest.mark.integration

_RACINE = Path(__file__).resolve().parents[3]
_URL_DEPOT = "https://github.com/siba-IEE/kuma-data-core/blob/main/"
_COLONNES = ("methode_collecte_doc", "url_documentation")


def _valeurs(db_session: Session, colonne: str) -> dict[str, int]:
    # ``colonne`` vient de la constante _COLONNES.
    return dict(
        db_session.execute(
            text(
                f"SELECT {colonne}, COUNT(*) FROM series_metadonnees "
                f"WHERE {colonne} IS NOT NULL GROUP BY {colonne}"
            )
        )
        .tuples()
        .all()
    )


@pytest.mark.parametrize("colonne", _COLONNES)
def test_les_liens_sont_des_url_https(db_session: Session, colonne: str) -> None:
    valeurs = _valeurs(db_session, colonne)
    assert valeurs
    hors_url = {valeur: n for valeur, n in valeurs.items() if not valeur.startswith("https://")}
    assert not hors_url


@pytest.mark.parametrize("colonne", _COLONNES)
def test_les_fiches_du_depot_citees_existent(db_session: Session, colonne: str) -> None:
    citees = [v for v in _valeurs(db_session, colonne) if v.startswith(_URL_DEPOT)]
    assert citees
    absentes = [v for v in citees if not (_RACINE / v.removeprefix(_URL_DEPOT)).is_file()]
    assert not absentes
