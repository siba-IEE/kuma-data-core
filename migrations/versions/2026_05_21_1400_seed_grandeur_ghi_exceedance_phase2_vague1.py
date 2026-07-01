"""seed_grandeur_ghi_exceedance_phase2_vague1

Revision ID: 049
Revises: 048
Create Date: 2026-05-21 14:00:00.000000+00:00

Seed de la grandeur
``ghi_exceedance`` : exceedance inter-annuelle de l'irradiation annuelle,
dérivée de la série GHI mensuelle 1991-2020 (6 villes pilotes).

Grandeur F1 **calculée à la volée** (`strategie_calcul = 'calculee_volee'`),
jamais stockée. L'endpoint dérivera les 30 totaux annuels par
pondération journalière (`Σ_mois [GHI(y,m) × nb_jours(m,y)]`, unité
source `kwh_par_m2_jour`) et calculera deux percentiles : P50 (médiane,
percentile 50) et P90 (valeur dépassée 90 % des années, percentile 10
côté distribution - scénario conservateur).

Aucune entrée dans ``series_metadonnees`` (pas de série stockée pour
les grandeurs calculées à la volée - pattern hérité des grandeurs
référentielles `ecart_relatif_referentiel` /
`rang_referentiel_*`).

Unité de sortie : ``kwh_par_m2_an`` (déjà présente dans le seed initial
des unités). Aucune unité à créer.

Pattern hérité de la migration 047 (seed inline avec résolution
dynamique ``unite_code -> unite_id``).
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "049"
down_revision: str | Sequence[str] | None = "048"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


_GRANDEUR_GHI_EXCEEDANCE: dict[str, Any] = {
    "code": "ghi_exceedance",
    "libelle": "Exceedance inter-annuelle de l'irradiation annuelle (GHI)",
    "famille": "F1",
    "strategie_calcul": "calculee_volee",
    "unite_code": "kwh_par_m2_an",
    "description": (
        "Exceedance inter-annuelle de l'irradiation annuelle dérivée de "
        "la série GHI mensuelle 1991-2020 (NASA POWER, climatologie OMM). "
        "Pour une ville pilote donnée, le calcul reconstruit les 30 totaux "
        "annuels (somme des 12 mensuels pondérée par le nombre de jours "
        "du mois, années bissextiles incluses) puis extrait deux "
        "percentiles : P50 (médiane) et P90 (valeur dépassée 90 % des "
        "années = 10ᵉ percentile, scénario conservateur). Grandeur "
        "calculée à la volée à chaque appel API, jamais stockée. Indicateur "
        "de variabilité inter-annuelle, ne propage pas l'incertitude de "
        "modèle ; ce n'est pas un P90 bancable complet."
    ),
}

_CODE_GRANDEUR: str = "ghi_exceedance"


def upgrade() -> None:
    bind = op.get_bind()

    # Résolution dynamique unite_code -> unite_id (pattern migration 015/047).
    unite_code = _GRANDEUR_GHI_EXCEEDANCE["unite_code"]
    row = bind.execute(
        sa.text("SELECT id FROM unites WHERE code = :code"),
        {"code": unite_code},
    ).first()
    if row is None:
        raise RuntimeError(
            f"Migration 049 : unite_code {unite_code!r} introuvable dans unites. "
            f"Verifier le seed initial des unites (phase 0)."
        )
    unite_id = int(row.id)

    grandeurs_referentiel_table = sa.table(
        "grandeurs_referentiel",
        sa.column("code", sa.String),
        sa.column("libelle", sa.Text),
        sa.column("unite_id", sa.BigInteger),
        sa.column("famille", sa.String),
        sa.column("strategie_calcul", sa.String),
        sa.column("description", sa.Text),
    )

    ligne = {**_GRANDEUR_GHI_EXCEEDANCE, "unite_id": unite_id}
    ligne.pop("unite_code")

    op.bulk_insert(grandeurs_referentiel_table, [ligne])


def downgrade() -> None:
    op.execute(
        sa.text("DELETE FROM grandeurs_referentiel WHERE code = :code").bindparams(
            sa.bindparam("code", value=_CODE_GRANDEUR)
        )
    )
