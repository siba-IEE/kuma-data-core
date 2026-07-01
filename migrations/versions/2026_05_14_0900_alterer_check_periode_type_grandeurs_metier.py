"""alterer_check_periode_type_grandeurs_metier

Revision ID: 036
Revises: 035
Create Date: 2026-05-14 09:00:00.000000+00:00

Extension des 2 CHECK constraints `periode_type` sur `grandeurs_metier`
pour autoriser la valeur `'statique'` introduite pour
la grandeur `indicateur_qualite_donnees` (1 ligne par série évaluée,
plage statique 2021-2025).

CHECK affectés :
- `ck_grandeurs_metier_periode_type_valide` : ajout `'statique'` à la
  liste des valeurs autorisées.
- `ck_grandeurs_metier_periode_coherente` : ajout de la branche
  `(periode_type = 'statique' AND mois IS NULL)`.

Aucun impact sur les 1 578 lignes existantes (toutes en `'annuel'` /
`'mensuel'`, compatibles avec le nouveau CHECK).
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "036"
down_revision: str | Sequence[str] | None = "035"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_constraint(
        "ck_grandeurs_metier_periode_type_valide",
        "grandeurs_metier",
        type_="check",
    )
    op.drop_constraint(
        "ck_grandeurs_metier_periode_coherente",
        "grandeurs_metier",
        type_="check",
    )
    op.create_check_constraint(
        "ck_grandeurs_metier_periode_type_valide",
        "grandeurs_metier",
        "periode_type IN ('mensuel', 'annuel', 'statique')",
    )
    op.create_check_constraint(
        "ck_grandeurs_metier_periode_coherente",
        "grandeurs_metier",
        "(periode_type = 'annuel' AND mois IS NULL) "
        "OR (periode_type = 'mensuel' AND mois IS NOT NULL AND mois BETWEEN 1 AND 12) "
        "OR (periode_type = 'statique' AND mois IS NULL)",
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_grandeurs_metier_periode_type_valide",
        "grandeurs_metier",
        type_="check",
    )
    op.drop_constraint(
        "ck_grandeurs_metier_periode_coherente",
        "grandeurs_metier",
        type_="check",
    )
    op.create_check_constraint(
        "ck_grandeurs_metier_periode_type_valide",
        "grandeurs_metier",
        "periode_type IN ('mensuel', 'annuel')",
    )
    op.create_check_constraint(
        "ck_grandeurs_metier_periode_coherente",
        "grandeurs_metier",
        "(periode_type = 'annuel' AND mois IS NULL) "
        "OR (periode_type = 'mensuel' AND mois IS NOT NULL AND mois BETWEEN 1 AND 12)",
    )
