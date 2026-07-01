"""seed_grandeur_poa_bifacial_vague5

Revision ID: 079
Revises: 078
Create Date: 2026-06-18 12:00:00.000000+00:00

Bifacial : enregistre la grandeur F2 paramétrable ``poa_bifacial``
(POA global bifacial, modèle infinite-sheds row-aware) dans
``grandeurs_referentiel``. Grandeur **calculee_volee** : aucune série, aucune
valeur stockée (calcul à la volée par l'endpoint ``/v1/grandeurs/poa_bifacial``).
**Migration de référentiel uniquement** - aucune DDL, aucune donnée, aucun
réseau ; ``alembic check`` reste aligné (la grandeur est l'unique ajout).

Périmètre (énumération exhaustive) :

1. INSERT 1 ligne dans ``grandeurs_referentiel`` (code ``poa_bifacial``, famille
   F2, strategie ``calculee_volee``, unité ``kwh_par_m2_jour`` résolue par code).

Miroir du pattern d'insertion grandeur de la migration 072. Downgrade : DELETE de
la grandeur ``poa_bifacial``.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "079"
down_revision: str | Sequence[str] | None = "078"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_GRANDEUR_POA_BIFACIAL = "poa_bifacial"


def upgrade() -> None:
    bind = op.get_bind()

    unite_id = bind.execute(
        sa.text("SELECT id FROM unites WHERE code = :code"),
        {"code": "kwh_par_m2_jour"},
    ).scalar_one_or_none()
    if unite_id is None:
        raise RuntimeError("Migration 079 : unite 'kwh_par_m2_jour' introuvable (migration 009).")

    grandeurs_table = sa.table(
        "grandeurs_referentiel",
        sa.column("code", sa.String),
        sa.column("libelle", sa.Text),
        sa.column("famille", sa.String),
        sa.column("strategie_calcul", sa.String),
        sa.column("unite_id", sa.BigInteger),
        sa.column("description", sa.Text),
    )
    op.bulk_insert(
        grandeurs_table,
        [
            {
                "code": _GRANDEUR_POA_BIFACIAL,
                "libelle": "POA bifacial (irradiance globale row-aware)",
                "famille": "F2",
                "strategie_calcul": "calculee_volee",
                "unite_id": int(unite_id),
                "description": (
                    "POA global bifacial d'un champ de rangees (modele infinite-sheds "
                    "row-aware, pvlib.bifacial). Irradiation incidente face avant + gain "
                    "face arriere (rayonnement reflechi par le sol), selon la geometrie de "
                    "rangees (gcr, hauteur, pitch), la bifacialite du module et l'albedo. "
                    "Distinct du poa_parametrable mono-plan. Calculee a la volee. Famille "
                    "F2."
                    ""
                ),
            }
        ],
    )


def downgrade() -> None:
    op.execute(
        sa.text("DELETE FROM grandeurs_referentiel WHERE code = :code").bindparams(
            code=_GRANDEUR_POA_BIFACIAL
        )
    )
