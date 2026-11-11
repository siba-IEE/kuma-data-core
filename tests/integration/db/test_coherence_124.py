"""Liens de documentation des séries : des URL, sauf une exception listée. Lecture seule.

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

# Chemin d'une fiche qui n'existe pas dans le dépôt : valeur encore en base, à
# traiter (écrire la fiche, citer un autre document ou vider la colonne).
_CHEMIN_SANS_FICHE = "docs/methodologie/grandeurs/rang_referentiel_temporel.md"


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
    hors_url = {
        valeur: n
        for valeur, n in valeurs.items()
        if not valeur.startswith("https://") and valeur != _CHEMIN_SANS_FICHE
    }
    assert not hors_url


@pytest.mark.parametrize("colonne", _COLONNES)
def test_les_fiches_du_depot_citees_existent(db_session: Session, colonne: str) -> None:
    citees = [v for v in _valeurs(db_session, colonne) if v.startswith(_URL_DEPOT)]
    assert citees
    absentes = [v for v in citees if not (_RACINE / v.removeprefix(_URL_DEPOT)).is_file()]
    assert not absentes


@pytest.mark.parametrize("colonne", _COLONNES)
def test_l_exception_du_chemin_sans_fiche_est_encore_utile(
    db_session: Session, colonne: str
) -> None:
    """Échoue quand l'exception peut être retirée : valeur corrigée en base ou fiche écrite."""
    assert _CHEMIN_SANS_FICHE in _valeurs(db_session, colonne), (
        "Plus aucune série ne cite ce chemin : retirer l'exception de ce module."
    )
    assert not (_RACINE / _CHEMIN_SANS_FICHE).is_file(), (
        "La fiche existe désormais : convertir le chemin en URL et retirer l'exception."
    )
