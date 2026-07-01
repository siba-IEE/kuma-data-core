"""corriger_commentaire_fiabilite_sources

Revision ID: 006
Revises: 005
Create Date: 2026-05-04 22:00:00

Migration corrective.

Objet : aligner le ``COMMENT ON COLUMN sources.fiabilite`` sur le nom
de fichier réel du document d'architecture
(``docs/architecture/04-api.md``).

Contexte
--------
La migration 004 avait posé un commentaire pointant
vers ``docs/architecture/04.md``, sur la base d'un nom de fichier
provisoire. Le document a finalement été nommé ``04-api.md`` lors de
sa rédaction. Le pointeur du commentaire
était donc devenu un lien mort.

Le modèle SQLAlchemy ``Source`` a été aligné sur le nom correct
(``comment="...docs/architecture/04-api.md..."``
sur la colonne ``fiabilite``). Cette migration corrective met la base
en cohérence avec le modèle, ce qui permet à ``alembic check`` de
passer aussi bien sur une base fraîche (``upgrade head`` complet) que
sur une base existante (issue d'``upgrade head`` antérieur à la 006).

Pourquoi une migration corrective et non un patch sur la 004 ?
--------------------------------------------------------------
La règle « ne jamais modifier une migration mergée » de
``docs/conventions/02-migrations.md`` interdit toute édition de la 004
une fois publiée. Une migration corrective dédiée est la voie propre :

- Elle respecte l'historique chronologique des évolutions du schéma.
- Elle est ré-applicable de manière déterministe sur n'importe quelle
  base.
- Son ``downgrade()`` repose l'ancien commentaire - symétrie complète.

Pas de changement de schéma : seul le commentaire SQL change. Aucun
risque de perte de données, aucun verrou long.
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "006"
down_revision: str | Sequence[str] | None = "005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        "COMMENT ON COLUMN sources.fiabilite IS "
        "'Qualification editoriale Kuma (3 niveaux). "
        "Voir docs/architecture/04-api.md pour le mapping editorial complet.'"
    )


def downgrade() -> None:
    op.execute(
        "COMMENT ON COLUMN sources.fiabilite IS "
        "'Qualification editoriale Kuma (3 niveaux). "
        "Voir docs/architecture/04.md pour le mapping editorial complet.'"
    )
