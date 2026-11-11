"""reecrire_descriptions_grandeurs

Revision ID: 129
Revises: 128
Create Date: 2026-11-11 12:30:00

Les descriptions de 15 grandeurs (``grandeurs_referentiel.description``)
sont servies par l'API et partent avec l'édition publique. Elles renvoyaient à
l'histoire du projet ou décrivaient un périmètre qui n'est plus celui des
données. Chacune est réécrite d'après le calcul et les séries en base.

Correction sur place d'une table de référentiel, journalisée par le trigger
d'audit. Seule la colonne ``description`` change : ``modifie_le`` n'est
maintenue ni par un trigger ni par le modèle, elle reste donc intacte.

Les textes sont dans ``migrations/donnees/129_descriptions_grandeurs.json`` (code de la grandeur,
texte de départ, texte d'arrivée). Gardes : 15 lignes, chacune avec
exactement son texte de départ, puis égalité de chaque ligne à son texte
d'arrivée après écriture. Une garde qui échoue lève ``RuntimeError`` et annule
la transaction. Le downgrade rend les anciens textes à l'identique.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from pathlib import Path

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "129"
down_revision: str | Sequence[str] | None = "128"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


_FICHIER = Path(__file__).resolve().parents[1] / "donnees" / "129_descriptions_grandeurs.json"
_NB_ATTENDU = 15
_CLE = ("code",)

_SQL_LIRE = sa.text("SELECT code, description FROM grandeurs_referentiel")
_SQL_ECRIRE = sa.text(
    "UPDATE grandeurs_referentiel SET description = :cible "
    "WHERE code = :code AND description = :depart"
)


def _garde(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(f"Migration 129 : {message}")


def _changements() -> list[tuple[tuple[str, ...], str, str]]:
    """Triplets (clé, texte de départ, texte d'arrivée) du fichier compagnon."""
    changements = [
        (tuple(e[champ] for champ in _CLE), e["ancien"], e["nouveau"])
        for e in json.loads(_FICHIER.read_text("utf-8"))
    ]
    _garde(
        len({cle for cle, _, _ in changements}) == len(changements) == _NB_ATTENDU,
        f"le fichier compagnon ne porte pas {_NB_ATTENDU} lignes distinctes.",
    )
    return changements


def _ecarts(bind: sa.Connection, attendus: list[tuple[tuple[str, ...], str]]) -> list[str]:
    """Lignes dont le texte actuel n'est pas le texte attendu."""
    actuels = {tuple(ligne[:-1]): ligne[-1] for ligne in bind.execute(_SQL_LIRE)}
    return ["/".join(cle) for cle, texte in attendus if actuels.get(cle) != texte]


def _appliquer(changements: list[tuple[tuple[str, ...], str, str]]) -> None:
    """Passe chaque ligne de son texte de départ à son texte d'arrivée, ou n'écrit rien."""
    bind = op.get_bind()
    modifies = _ecarts(bind, [(cle, depart) for cle, depart, _ in changements])
    _garde(not modifies, f"textes absents ou déjà modifiés, rien n'est écrit : {modifies}")
    for cle, depart, cible in changements:
        resultat = bind.execute(
            _SQL_ECRIRE, {**dict(zip(_CLE, cle, strict=True)), "depart": depart, "cible": cible}
        )
        _garde(resultat.rowcount == 1, f"{resultat.rowcount} lignes modifiées pour {cle}.")
    restants = _ecarts(bind, [(cle, cible) for cle, _, cible in changements])
    _garde(not restants, f"textes non écrits : {restants}")


def upgrade() -> None:
    _appliquer(_changements())


def downgrade() -> None:
    _appliquer([(cle, nouveau, ancien) for cle, ancien, nouveau in _changements()])
