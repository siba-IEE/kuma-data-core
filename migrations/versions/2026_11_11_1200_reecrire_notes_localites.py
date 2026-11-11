"""reecrire_notes_localites

Revision ID: 128
Revises: 127
Create Date: 2026-11-11 12:00:00

Les notes de 79 localités (``localites.notes``) partent avec l'édition
publique. Elles renvoyaient à des documents de travail et à l'histoire du
projet. Chacune est réécrite en clair : références, coordonnées, dates et
sources citées sont conservées.

Correction sur place d'une table de référentiel, journalisée par le trigger
d'audit. Seule la colonne ``notes`` change : ``modifie_le`` n'est
maintenue ni par un trigger ni par le modèle, elle reste donc intacte.

Les textes sont dans ``migrations/donnees/128_notes_localites.json`` (code de la localité,
texte de départ, texte d'arrivée). Gardes : 79 lignes, chacune avec
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
revision: str = "128"
down_revision: str | Sequence[str] | None = "127"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


_FICHIER = Path(__file__).resolve().parents[1] / "donnees" / "128_notes_localites.json"
_NB_ATTENDU = 79
_CLE = ("code",)

_SQL_LIRE = sa.text("SELECT code, notes FROM localites")
_SQL_ECRIRE = sa.text("UPDATE localites SET notes = :cible WHERE code = :code AND notes = :depart")


def _garde(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(f"Migration 128 : {message}")


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
