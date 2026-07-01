"""alterer_series_metadonnees_ajouter_granularite

Revision ID: 052
Revises: 051
Create Date: 2026-06-14 10:00:00.000000+00:00

Ajoute la colonne discriminante ``granularite`` sur ``series_metadonnees``.
Résout un manque du routage table-cible
(``serie_lecture.resolve_table_from_series_metadata``) qui ne disposait
d'aucune dimension de granularité et ne pouvait distinguer une future
série horaire ``nasa_power`` 2021→ d'une série journalière (même
``source`` + même année de début).

Colonne **NULLABLE** : ``NULL`` pour les séries ``kuma_calculs``
(granularité non applicable - leur temporalité est portée par
``grandeurs_metier.periode_type``, domaine ``mensuel``/``annuel``/
``statique`` qui ne se projette pas sur ``journalier``/``mensuel``/
``horaire``). Backfill rétroactif des séries existantes dérivé du
routage actuel (``source.code`` + ``periode_debut``).
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "052"
down_revision: str | Sequence[str] | None = "051"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 1. Ajout de la colonne (nullable : NULL legitime pour kuma_calculs).
    op.add_column(
        "series_metadonnees",
        sa.Column(
            "granularite",
            sa.String(length=16),
            nullable=True,
            comment=(
                "Discriminant de granularite temporelle pour le routage "
                "table-cible (journalier/mensuel/horaire). NULL pour les series "
                "kuma_calculs (routees par source vers grandeurs_metier ; "
                "temporalite portee par grandeurs_metier.periode_type). "
                "Resout D-36 (Vague 3 lot 1)."
            ),
        ),
    )

    # 2. Backfill derive du routage actuel (source.code + periode_debut.year).
    #    Les series kuma_calculs restent NULL (granularite non applicable).
    op.execute(
        """
        UPDATE series_metadonnees sm
        SET granularite = 'mensuel'
        FROM sources s
        WHERE sm.source_id = s.id
          AND (
              s.code = 'sarah3_monthly'
              OR (s.code = 'nasa_power' AND EXTRACT(YEAR FROM sm.periode_debut) < 2021)
          )
        """
    )
    op.execute(
        """
        UPDATE series_metadonnees sm
        SET granularite = 'journalier'
        FROM sources s
        WHERE sm.source_id = s.id
          AND s.code = 'nasa_power'
          AND EXTRACT(YEAR FROM sm.periode_debut) >= 2021
        """
    )

    # 3. CHECK (NULL admis ; kuma_calculs = NULL).
    op.create_check_constraint(
        "ck_series_metadonnees_granularite_valide",
        "series_metadonnees",
        "granularite IS NULL OR granularite IN ('journalier', 'mensuel', 'horaire')",
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_series_metadonnees_granularite_valide",
        "series_metadonnees",
        type_="check",
    )
    op.drop_column("series_metadonnees", "granularite")
