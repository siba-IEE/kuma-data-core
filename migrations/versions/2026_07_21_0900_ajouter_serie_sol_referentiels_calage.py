"""ajouter_serie_sol_referentiels_calage

Revision ID: 103
Revises: 102
Create Date: 2026-07-21 09:00:00.000000+00:00

Genericite pays, residu 3 (brief de chantier, 2026-07-21) : le
referentiel de calage declare lui-meme sa serie sol de fondation -
la sequence horaire de reference que les consommateurs d'etude
doivent utiliser avec ce calage. Jusqu'ici cette information
n'existait qu'en texte dans la provenance, et les consommateurs la
portaient en constante de configuration (Solar Bridge :
SERIE_SEQUENCE_V1). Machine-lisible, elle devient decouvrable par
l'API : ajouter une station = publier son referentiel, zero
constante cote consommateurs.

Deux gestes :

1. colonne ``serie_sol`` (code de serie, NOT NULL apres remplissage) ;
2. remplissage des lignes existantes : le referentiel GHI de Kankan
   est fonde sur gin_kankan_ghi_esmap_wapp_2021_2023 (17 520 h,
   confiance A).
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "103"
down_revision: str | Sequence[str] | None = "102"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_SERIE_SOL_KANKAN = "gin_kankan_ghi_esmap_wapp_2021_2023"
_CODE_REFERENTIEL = "gin_kankan_ghi_calage_saisonnier"


def upgrade() -> None:
    op.add_column(
        "referentiels_calage",
        sa.Column("serie_sol", sa.String(120), nullable=True),
    )
    op.execute(
        sa.text("UPDATE referentiels_calage SET serie_sol = :serie WHERE code = :code").bindparams(
            serie=_SERIE_SOL_KANKAN, code=_CODE_REFERENTIEL
        )
    )
    op.alter_column("referentiels_calage", "serie_sol", nullable=False)


def downgrade() -> None:
    op.drop_column("referentiels_calage", "serie_sol")
