"""reecrire_commentaires_degenerescence_pixel

Revision ID: 126
Revises: 125
Create Date: 2026-11-11 11:00:00

Le commentaire éditorial des 374 lignes ``degenerescence_pixel`` de
``grandeurs_metier`` est servi tel quel par l'API (champ
``degenerescence.note``) et part avec l'édition publique. Il était écrit sans
accents et avec le vocabulaire de travail du projet. Chacun des 151 textes
distincts est réécrit en clair ; la grille, la résolution, la grandeur et les
codes des localités de la même cellule sont repris à l'identique.

Mise à jour sur place du seul commentaire d'une table versionnée, décidée pour
ce texte : aucune nouvelle version n'est créée. Le trigger d'audit journalise.
Valeurs, versions, validité, statut, niveau de confiance et ``modifie_le`` ne
bougent pas : leur empreinte est comparée avant et après.

Les paires (texte de départ, texte d'arrivée) sont dans
``migrations/donnees/126_commentaires_degenerescence.json``. Gardes : 374
lignes, toutes porteuses d'un texte de départ, aucun texte d'arrivée déjà
présent, puis contrôle après écriture. Une garde qui échoue lève
``RuntimeError`` et annule la transaction. Le downgrade rend les anciens textes
à l'identique.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from pathlib import Path

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "126"
down_revision: str | Sequence[str] | None = "125"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


_FICHIER = Path(__file__).resolve().parents[1] / "donnees" / "126_commentaires_degenerescence.json"
_GRANDEUR = "degenerescence_pixel"
_NB_LIGNES = 374
_NB_TEXTES = 151

# Tout ce qui doit rester intact sur les lignes de la grandeur.
_SQL_EMPREINTE = sa.text(
    """
    SELECT md5(COALESCE(string_agg(
        concat_ws('|', id::text, COALESCE(valeur::text, '~'), version_formule::text,
                  valide_du::text, COALESCE(valide_au::text, '~'), statut,
                  niveau_confiance_derive, modifie_le::text),
        ';' ORDER BY id), ''))
    FROM grandeurs_metier WHERE grandeur_code = :grandeur
    """
)
# Lignes commentées de la table, lignes et textes distincts parmi les textes donnés.
_SQL_COMPTES = sa.text(
    """
    SELECT count(*) FILTER (WHERE commentaire_editorial IS NOT NULL),
           count(*) FILTER (WHERE grandeur_code = :grandeur
                              AND commentaire_editorial = ANY(:textes)),
           count(DISTINCT commentaire_editorial) FILTER (
               WHERE grandeur_code = :grandeur AND commentaire_editorial = ANY(:textes))
    FROM grandeurs_metier
    """
)


def _garde(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(f"Migration 126 : {message}")


def _paires() -> list[tuple[str, str]]:
    """Paires (texte de départ, texte d'arrivée) du fichier compagnon."""
    paires = [(p["ancien"], p["nouveau"]) for p in json.loads(_FICHIER.read_text("utf-8"))]
    _garde(
        len(paires) == _NB_TEXTES
        and len({depart for depart, _ in paires} | {cible for _, cible in paires})
        == 2 * _NB_TEXTES,
        f"le fichier compagnon ne porte pas {_NB_TEXTES} paires de textes tous distincts.",
    )
    return paires


def _comptes(bind: sa.Connection, textes: list[str]) -> tuple[int, int, int]:
    commentees, lignes, distincts = bind.execute(
        _SQL_COMPTES, {"grandeur": _GRANDEUR, "textes": textes}
    ).one()
    return int(commentees), int(lignes), int(distincts)


def _reecrire(paires: list[tuple[str, str]]) -> None:
    """Passe chaque commentaire de son texte de départ à son texte d'arrivée, ou n'écrit rien."""
    bind = op.get_bind()
    departs = [depart for depart, _ in paires]
    cibles = [cible for _, cible in paires]
    _garde(
        _comptes(bind, departs) == (_NB_LIGNES, _NB_LIGNES, _NB_TEXTES),
        "les commentaires de départ ne sont pas ceux attendus, rien n'est écrit.",
    )
    _garde(
        _comptes(bind, cibles)[1] == 0,
        "des commentaires d'arrivée sont déjà présents, rien n'est écrit.",
    )
    empreinte = bind.execute(_SQL_EMPREINTE, {"grandeur": _GRANDEUR}).scalar_one()

    resultat = bind.execute(
        sa.text(
            """
            UPDATE grandeurs_metier AS gm SET commentaire_editorial = v.cible
            FROM unnest(CAST(:departs AS text[]), CAST(:cibles AS text[])) AS v(depart, cible)
            WHERE gm.grandeur_code = :grandeur AND gm.commentaire_editorial = v.depart
            """
        ),
        {"grandeur": _GRANDEUR, "departs": departs, "cibles": cibles},
    )
    _garde(resultat.rowcount == _NB_LIGNES, f"{resultat.rowcount} lignes modifiées.")
    _garde(
        _comptes(bind, departs)[1] == 0
        and _comptes(bind, cibles) == (_NB_LIGNES, _NB_LIGNES, _NB_TEXTES),
        "contrôle après écriture en échec.",
    )
    _garde(
        bind.execute(_SQL_EMPREINTE, {"grandeur": _GRANDEUR}).scalar_one() == empreinte,
        "une colonne autre que le commentaire a changé.",
    )


def upgrade() -> None:
    _reecrire(_paires())


def downgrade() -> None:
    _reecrire([(nouveau, ancien) for ancien, nouveau in _paires()])
