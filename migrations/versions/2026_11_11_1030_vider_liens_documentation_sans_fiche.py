"""vider_liens_documentation_sans_fiche

Revision ID: 125
Revises: 124
Create Date: 2026-11-11 10:30:00

``series_metadonnees.methode_collecte_doc`` et ``url_documentation`` citaient,
pour 28 séries ``rang_referentiel_temporel``, le chemin d'une fiche
méthodologique qui n'existe pas. Les deux colonnes passent à NULL, comme pour
les six autres séries de la même grandeur.

Correction sur place d'une table de référentiel, journalisée par le trigger
d'audit ; ``modifie_le`` reste intacte. Gardes : les lignes qui portent le
chemin sont exactement les 28 séries listées, puis contrôle après écriture. Une
garde qui échoue lève ``RuntimeError`` et annule la transaction. Le downgrade
rend le chemin aux mêmes 28 séries.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "125"
down_revision: str | Sequence[str] | None = "124"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


_COLONNES = ("methode_collecte_doc", "url_documentation")
CHEMIN_SANS_FICHE = "docs/methodologie/grandeurs/rang_referentiel_temporel.md"

_PREFIXES = (
    "gin_beyla",
    "gin_boffa",
    "gin_boke_centre",
    "gin_coyah",
    "gin_dabola",
    "gin_dalaba",
    "gin_dinguiraye",
    "gin_dubreka",
    "gin_faranah_centre",
    "gin_forecariah",
    "gin_fria",
    "gin_gaoual",
    "gin_gueckedou",
    "gin_kerouane",
    "gin_kissidougou",
    "gin_koubia",
    "gin_koundara",
    "gin_kouroussa",
    "gin_lelouma",
    "gin_lola",
    "gin_macenta",
    "gin_mali",
    "gin_mandiana",
    "gin_pita",
    "gin_siguiri",
    "gin_telimele",
    "gin_tougue",
    "gin_yomou",
)
CODES: list[str] = [
    f"{prefixe}_rang_referentiel_temporel_kuma_calculs_2021_2025" for prefixe in _PREFIXES
]
_NB_ATTENDU = 28


def _garde(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(f"Migration 125 : {message}")


def _codes(bind: sa.Connection, colonne: str, *, avec_chemin: bool) -> list[str]:
    """Séries qui portent le chemin dans la colonne, ou séries listées où elle est vide."""
    # ``colonne`` vient de la constante _COLONNES, jamais d'une entrée extérieure.
    condition = (
        f"{colonne} = :chemin" if avec_chemin else f"{colonne} IS NULL AND code = ANY(:codes)"
    )
    return list(
        bind.execute(
            sa.text(f"SELECT code FROM series_metadonnees WHERE {condition} ORDER BY code"),
            {"chemin": CHEMIN_SANS_FICHE, "codes": CODES},
        ).scalars()
    )


def _basculer(*, vider: bool) -> None:
    """Vide les deux colonnes des 28 séries, ou leur rend le chemin ; sinon n'écrit rien."""
    bind = op.get_bind()
    _garde(len(CODES) == _NB_ATTENDU, f"{len(CODES)} codes listés, {_NB_ATTENDU} attendus.")
    for colonne in _COLONNES:
        avec_chemin = _codes(bind, colonne, avec_chemin=True)
        vides = _codes(bind, colonne, avec_chemin=False)
        _garde(
            (avec_chemin, vides) == ((CODES, []) if vider else ([], CODES)),
            f"{colonne} : {len(avec_chemin)} séries portent le chemin et {len(vides)} des séries "
            "listées sont vides, rien n'est écrit.",
        )
    for colonne in _COLONNES:
        resultat = bind.execute(
            sa.text(
                f"UPDATE series_metadonnees SET {colonne} = CAST(:cible AS text) "
                f"WHERE code = ANY(:codes) AND {colonne} IS NOT DISTINCT FROM CAST(:depart AS text)"
            ),
            {
                "codes": CODES,
                "depart": CHEMIN_SANS_FICHE if vider else None,
                "cible": None if vider else CHEMIN_SANS_FICHE,
            },
        )
        _garde(
            resultat.rowcount == _NB_ATTENDU, f"{colonne} : {resultat.rowcount} lignes modifiées."
        )
    for colonne in _COLONNES:
        _garde(
            (_codes(bind, colonne, avec_chemin=True), _codes(bind, colonne, avec_chemin=False))
            == (([], CODES) if vider else (CODES, [])),
            f"{colonne} : contrôle après écriture en échec.",
        )


def upgrade() -> None:
    _basculer(vider=True)


def downgrade() -> None:
    _basculer(vider=False)
