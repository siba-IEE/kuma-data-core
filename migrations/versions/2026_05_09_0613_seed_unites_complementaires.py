"""seed_unites_complementaires

Revision ID: 009
Revises: 008
Create Date: 2026-05-09 06:13:53.488191+00:00

Migration corrective de seed : ajoute 4 unités complémentaires à la
table ``unites`` (seedée à 153 lignes par la migration 002), pré-requis
au seed des 15 grandeurs (migration 010).

Décisions :

- migration corrective d'unités préalable au seed grandeurs ;
- HEP unité dédiée ``heure_equivalente_pleine`` (distincte
  sémantiquement de ``heure``).

Aucune modification de ``unites_seed_data.py`` (153 unités
figées par la migration 002). Le présent seed vit dans un fichier
dédié ``unites_complementaires_009_seed_data.py``.

Trigger d'audit : ``kuma_log_audit()`` (créé en migration 005, branché
sur ``unites`` par cette même 005) se déclenchera automatiquement à
l'INSERT des 4 lignes. ``auteur_applicatif`` reste NULL - comportement
accepté (sémantiquement « seedé par migration, pas par humain »).
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import ARRAY

from kuma_data_core.db.seeds.unites_complementaires_009_seed_data import (
    UNITES_COMPLEMENTAIRES_009_SEED,
)

# revision identifiers, used by Alembic.
revision: str = "009"
down_revision: str | Sequence[str] | None = "008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# Codes des 4 unités complémentaires - utilisés par le downgrade pour
# cibler les lignes à supprimer (la PK BIGINT n'est pas stable entre
# environnements).
_CODES_UNITES_COMPLEMENTAIRES: tuple[str, ...] = tuple(
    entry["code"] for entry in UNITES_COMPLEMENTAIRES_009_SEED
)


def upgrade() -> None:
    unites_table = sa.table(
        "unites",
        sa.column("code", sa.String),
        sa.column("libelle", sa.Text),
        sa.column("symbole", sa.String),
        sa.column("grandeur", sa.String),
        sa.column("systeme", sa.String),
        sa.column("est_unite_de_base", sa.Boolean),
        sa.column("facteur_conversion_si", sa.Numeric(60, 30)),
        sa.column("decalage_conversion_si", sa.Numeric(60, 30)),
        sa.column("code_unite_si", sa.String),
        sa.column("note_methodologique", sa.Text),
        sa.column("references_normatives", ARRAY(sa.Text())),
    )
    op.bulk_insert(unites_table, UNITES_COMPLEMENTAIRES_009_SEED)


def downgrade() -> None:
    op.execute(
        sa.text("DELETE FROM unites WHERE code = ANY(:codes)").bindparams(
            sa.bindparam("codes", value=list(_CODES_UNITES_COMPLEMENTAIRES))
        )
    )
