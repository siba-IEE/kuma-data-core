"""reecrire_fiches_sources

Revision ID: 127
Revises: 126
Create Date: 2026-11-11 11:30:00

Les fiches des sources partent avec l'édition publique. Les notes des 15
sources (``sources.notes``) et quelques valeurs des métadonnées de 4 d'entre
elles (``sources.metadonnees``) renvoyaient à l'organisation du projet et à des
vérifications remises à plus tard. Les notes sont réécrites en clair
(références, DOI, licences, résolutions, périodes et mises en garde
conservés) ; dans les métadonnées, seules des valeurs texte changent, les clés
et les types restent les mêmes.

Correction sur place d'une table de référentiel, journalisée par le trigger
d'audit ; ``modifie_le`` n'est maintenue ni par un trigger ni par le modèle,
elle reste donc intacte.

Les textes sont dans ``migrations/donnees/127_fiches_sources.json`` (code de
la source, valeur de départ, valeur d'arrivée ; pour ``metadonnees``, l'objet
JSON entier). Gardes : 15 notes et 4 objets, chacun exactement égal à sa valeur
de départ, puis égalité à la valeur d'arrivée après écriture et, pour les
métadonnées, mêmes clés et mêmes types qu'avant. Une garde qui échoue lève
``RuntimeError`` et annule la transaction. Le downgrade rend les anciennes
valeurs à l'identique.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "127"
down_revision: str | Sequence[str] | None = "126"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


_FICHIER = Path(__file__).resolve().parents[1] / "donnees" / "127_fiches_sources.json"
_NB_ATTENDUS = {"notes": 15, "metadonnees": 4}

_SQL_LIRE = sa.text("SELECT code, notes, metadonnees FROM sources")
_SQL_ECRIRE = {
    "notes": sa.text("UPDATE sources SET notes = :cible WHERE code = :code AND notes = :depart"),
    # Égalité jsonb : insensible à l'ordre des clés, exacte sur les valeurs.
    "metadonnees": sa.text(
        "UPDATE sources SET metadonnees = CAST(:cible AS jsonb) "
        "WHERE code = :code AND metadonnees = CAST(:depart AS jsonb)"
    ),
}

# (colonne, code de la source, valeur de départ, valeur d'arrivée)
Changement = tuple[str, str, Any, Any]


def _garde(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(f"Migration 127 : {message}")


def _changements() -> list[Changement]:
    donnees = json.loads(_FICHIER.read_text("utf-8"))
    changements = [
        (colonne, e["code"], e["ancien"], e["nouveau"])
        for colonne in _NB_ATTENDUS
        for e in donnees[colonne]
    ]
    for colonne, nb in _NB_ATTENDUS.items():
        codes = [code for col, code, _, _ in changements if col == colonne]
        _garde(
            len(set(codes)) == len(codes) == nb,
            f"le fichier compagnon ne porte pas {nb} lignes distinctes pour {colonne}.",
        )
    return changements


def _forme(valeur: Any) -> Any:
    """Clés et types d'une valeur JSON, sans son contenu."""
    if isinstance(valeur, dict):
        return {cle: _forme(v) for cle, v in valeur.items()}
    if isinstance(valeur, list):
        return [_forme(v) for v in valeur]
    return type(valeur).__name__


def _actuels(bind: sa.Connection) -> dict[tuple[str, str], Any]:
    actuels: dict[tuple[str, str], Any] = {}
    for code, notes, metadonnees in bind.execute(_SQL_LIRE):
        actuels["notes", code] = notes
        actuels["metadonnees", code] = metadonnees
    return actuels


def _ecarts(actuels: dict[tuple[str, str], Any], attendus: list[tuple[str, str, Any]]) -> list[str]:
    """Valeurs actuelles qui ne sont pas la valeur attendue."""
    return [
        f"{colonne}/{code}"
        for colonne, code, valeur in attendus
        if actuels.get((colonne, code)) != valeur
    ]


def _appliquer(changements: list[Changement]) -> None:
    """Passe chaque valeur de son état de départ à son état d'arrivée, ou n'écrit rien."""
    bind = op.get_bind()
    avant = _actuels(bind)
    modifies = _ecarts(avant, [(col, code, depart) for col, code, depart, _ in changements])
    _garde(not modifies, f"valeurs absentes ou déjà modifiées, rien n'est écrit : {modifies}")
    for colonne, code, depart, cible in changements:
        en_json = colonne == "metadonnees"
        resultat = bind.execute(
            _SQL_ECRIRE[colonne],
            {
                "code": code,
                "depart": json.dumps(depart, ensure_ascii=False) if en_json else depart,
                "cible": json.dumps(cible, ensure_ascii=False) if en_json else cible,
            },
        )
        _garde(
            resultat.rowcount == 1, f"{resultat.rowcount} lignes modifiées pour {colonne}/{code}."
        )
    apres = _actuels(bind)
    restants = _ecarts(apres, [(col, code, cible) for col, code, _, cible in changements])
    _garde(not restants, f"valeurs non écrites : {restants}")
    deformes = [
        code
        for colonne, code, _, _ in changements
        if colonne == "metadonnees"
        and _forme(apres["metadonnees", code]) != _forme(avant["metadonnees", code])
    ]
    _garde(not deformes, f"clés ou types des métadonnées modifiés : {deformes}")


def upgrade() -> None:
    _appliquer(_changements())


def downgrade() -> None:
    _appliquer([(col, code, nouveau, ancien) for col, code, ancien, nouveau in _changements()])
