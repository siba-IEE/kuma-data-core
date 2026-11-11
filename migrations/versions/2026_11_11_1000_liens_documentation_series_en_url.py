"""liens_documentation_series_en_url

Revision ID: 124
Revises: 123
Create Date: 2026-11-11 10:00:00

``series_metadonnees.methode_collecte_doc`` et ``url_documentation`` portaient,
pour 170 séries calculées, le chemin d'une fiche méthodologique relatif au
dépôt. Hors du dépôt ce chemin ne mène nulle part : il devient l'URL publique
de la fiche, comme les autres séries qui citent déjà une URL.

Cinq fiches existent et sont converties (34 séries chacune, les deux colonnes).
Le chemin ``docs/methodologie/grandeurs/rang_referentiel_temporel.md`` (28
séries) désigne une fiche qui n'existe pas : ces lignes ne sont pas touchées
ici, leur sort reste à décider.

Correction sur place d'une table de référentiel, journalisée par le trigger
d'audit ; ``modifie_le`` reste intacte. Gardes : nombre exact de lignes par
valeur de départ, aucune ligne déjà convertie, puis contrôle après écriture.
Une garde qui échoue lève ``RuntimeError`` et annule la transaction. Le
downgrade rend les chemins à l'identique.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "124"
down_revision: str | Sequence[str] | None = "123"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


_BASE_URL = "https://github.com/siba-IEE/kuma-data-core/blob/main/"
_COLONNES = ("methode_collecte_doc", "url_documentation")
_NB_PAR_FICHE = 34

CHEMINS: tuple[str, ...] = (
    "docs/methodologie/grandeurs/fraction_diffuse.md",
    "docs/methodologie/grandeurs/hep.md",
    "docs/methodologie/grandeurs/humidex.md",
    "docs/methodologie/grandeurs/productible_specifique_theorique.md",
    "docs/methodologie/grandeurs/variabilite_journaliere.md",
)

# Fiche absente du dépôt : lignes laissées en l'état.
CHEMIN_SANS_FICHE = "docs/methodologie/grandeurs/rang_referentiel_temporel.md"
_NB_SANS_FICHE = 28


def _garde(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(f"Migration 124 : {message}")


def _nb(bind: sa.Connection, colonne: str, valeur: str) -> int:
    # ``colonne`` vient de la constante _COLONNES, jamais d'une entrée extérieure.
    return int(
        bind.execute(
            sa.text(f"SELECT count(*) FROM series_metadonnees WHERE {colonne} = :valeur"),
            {"valeur": valeur},
        ).scalar_one()
    )


def _nb_hors_url(bind: sa.Connection, colonne: str) -> int:
    return int(
        bind.execute(
            sa.text(f"SELECT count(*) FROM series_metadonnees WHERE {colonne} !~ '^https?://'")
        ).scalar_one()
    )


def _remplacer(paires: list[tuple[str, str]], *, nb_hors_url_apres: int) -> None:
    """Remplace chaque valeur de départ par sa cible dans les deux colonnes, ou n'écrit rien."""
    bind = op.get_bind()
    for colonne in _COLONNES:
        for depart, cible in paires:
            n_depart, n_cible = _nb(bind, colonne, depart), _nb(bind, colonne, cible)
            _garde(
                n_depart == _NB_PAR_FICHE and n_cible == 0,
                f"{colonne} : {n_depart} lignes « {depart} » ({_NB_PAR_FICHE} attendues) et "
                f"{n_cible} déjà converties, rien n'est écrit.",
            )
        n_sans_fiche = _nb(bind, colonne, CHEMIN_SANS_FICHE)
        _garde(
            n_sans_fiche == _NB_SANS_FICHE,
            f"{colonne} : {n_sans_fiche} lignes sans fiche, {_NB_SANS_FICHE} attendues.",
        )
    for colonne in _COLONNES:
        for depart, cible in paires:
            resultat = bind.execute(
                sa.text(
                    f"UPDATE series_metadonnees SET {colonne} = :cible WHERE {colonne} = :depart"
                ),
                {"depart": depart, "cible": cible},
            )
            _garde(
                resultat.rowcount == _NB_PAR_FICHE,
                f"{colonne} : {resultat.rowcount} lignes modifiées pour « {depart} ».",
            )
    for colonne in _COLONNES:
        for depart, cible in paires:
            _garde(
                _nb(bind, colonne, depart) == 0 and _nb(bind, colonne, cible) == _NB_PAR_FICHE,
                f"{colonne} : contrôle après écriture en échec pour « {depart} ».",
            )
        _garde(
            _nb(bind, colonne, CHEMIN_SANS_FICHE) == _NB_SANS_FICHE
            and _nb_hors_url(bind, colonne) == nb_hors_url_apres,
            f"{colonne} : le nombre de valeurs qui ne sont pas des URL n'est pas celui attendu.",
        )


def upgrade() -> None:
    _remplacer(
        [(chemin, _BASE_URL + chemin) for chemin in CHEMINS], nb_hors_url_apres=_NB_SANS_FICHE
    )


def downgrade() -> None:
    _remplacer(
        [(_BASE_URL + chemin, chemin) for chemin in CHEMINS],
        nb_hors_url_apres=_NB_SANS_FICHE + _NB_PAR_FICHE * len(CHEMINS),
    )
