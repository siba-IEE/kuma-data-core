"""activer_extension_btree_gist

Revision ID: 013
Revises: 012
Create Date: 2026-05-11 12:00:00.000000+00:00

Active l'extension PostgreSQL ``btree_gist`` requise par la contrainte
``EXCLUDE`` BTree-GiST des tables versionnées temporellement.

Migration dédiée préférée à un ajout dans la première migration
utilisatrice (014 ``mesures_ressource``) pour deux raisons :

1. Découplage temporel : si la table ``grandeurs_metier`` est
   livrée avant ``mesures_ressource`` dans un futur réordonnancement,
   l'extension est disponible quoi qu'il arrive.
2. Lisibilité de l'historique : un commit dédié *« active l'extension
   btree_gist pour le versioning temporel »* est plus lisible qu'un mix
   avec la création de ``mesures_ressource``.

Le ``downgrade()`` retire l'extension. Possible uniquement si plus
aucune contrainte EXCLUDE ne l'utilise (sinon PostgreSQL refuse).
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "013"
down_revision: str | Sequence[str] | None = "012"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS btree_gist")


def downgrade() -> None:
    op.execute("DROP EXTENSION IF EXISTS btree_gist")
