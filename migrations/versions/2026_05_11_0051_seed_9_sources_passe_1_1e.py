"""seed_9_sources_passe_1_1e

Revision ID: 012
Revises: 011
Create Date: 2026-05-11 00:51:00.000000+00:00

Seed des 9 sources éditoriales dans la table ``sources``
(créée vide en migration 004, commentaire ``fiabilite`` corrigé en
migration 006 ; trigger d'audit ``trg_audit_sources`` posé en
migration 005).

Contenu :

- 3 bases de données opérationnelles (``nasa_power``,
  ``ecmwf_era5``, ``anm_guinee_stations``)
- 2 normes techniques opérationnelles (``iec_61724_1_2021``,
  ``wmo_8_2024``)
- 4 sources hydro structurelles différées (``wmo_grdc``,
  ``wwf_hydrosheds``, ``iec_60041_1991``, ``wmo_168_2008``)

Pas de hiérarchie parent-enfant (contraste avec migration 011 sur les
``localites``) : un seul batch ``op.bulk_insert`` suffit.

Trigger d'audit ``trg_audit_sources`` (posé en migration 005) se
déclenche automatiquement à l'INSERT des 9 lignes ;
``auteur_applicatif`` reste NULL (pas de ``set_config`` dans la
migration, cohérent avec le pattern des migrations 010 et 011).

Forme du downgrade ``DELETE WHERE code = ANY(:codes)`` strictement
dupliquée des migrations 010 et 011 mergées.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

from kuma_data_core.db.seeds.sources_seed_data import SOURCES_SEED

# revision identifiers, used by Alembic.
revision: str = "012"
down_revision: str | Sequence[str] | None = "011"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# Codes des 9 sources - utilisés par le downgrade pour cibler les lignes
# à supprimer (la PK BIGINT n'est pas stable entre environnements).
# Pattern identique aux migrations 010 et 011.
_CODES_SOURCES: tuple[str, ...] = tuple(entry["code"] for entry in SOURCES_SEED)


def upgrade() -> None:
    sources_table = sa.table(
        "sources",
        sa.column("code", sa.String),
        sa.column("titre", sa.Text),
        sa.column("auteurs", sa.ARRAY(sa.Text)),
        sa.column("organisation", sa.String),
        sa.column("type_source", sa.String),
        sa.column("annee_publication", sa.Integer),
        sa.column("date_consultation", sa.Date),
        sa.column("url", sa.Text),
        sa.column("doi", sa.String),
        sa.column("isbn", sa.String),
        sa.column("metadonnees", sa.dialects.postgresql.JSONB),
        sa.column("fiabilite", sa.String),
        sa.column("langue", sa.String),
        sa.column("notes", sa.Text),
    )

    op.bulk_insert(sources_table, SOURCES_SEED)


def downgrade() -> None:
    op.execute(
        sa.text("DELETE FROM sources WHERE code = ANY(:codes)").bindparams(
            sa.bindparam("codes", value=list(_CODES_SOURCES))
        )
    )
