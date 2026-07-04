"""corriger_unite_psp_periode_d63

Revision ID: 100
Revises: 099
Create Date: 2026-07-04 11:00:00.000000+00:00

Résorption de la dette D-63 (drift d'unité affichée du productible
spécifique théorique), option (a) de l'arbitrage du 2026-07-04 :
correction de l'étiquette, sans recalcul des valeurs.

Constat (registre des dettes, D-63) : l'unité référentielle de
``productible_specifique_theorique`` était ``kwh_par_kwc_jour`` alors
que les valeurs stockées sont des totaux par période (annuelle ou
mensuelle). Les valeurs sont justes, l'étiquette mentait. Le
déclencheur de levée (exposition sur l'API publique avec consommateur
tiers) est rempli depuis la mise en ligne du 2026-07-02.

Deux gestes :

1. seed de l'unité ``kwh_par_kwc_periode`` (symbole ``kWh/kWc``,
   total sur la période de la mesure ; dimension temps, facteur SI
   3600 comme ``heure_equivalente_pleine``) ;
2. repointage de ``grandeurs_referentiel.unite_id`` pour
   ``productible_specifique_theorique`` vers cette unité.

Les unités ``kwh_par_kwc_jour`` et ``kwh_par_kwc_mois`` (migration
009) restent en place : d'autres usages futurs pourront les employer
correctement. La note publique de la série (migration 099) annonce
déjà des totaux par période.

Le registre des dettes est mis à jour par PR doc dédiée (convention
du fichier dettes-editoriales.md).

Trigger d'audit : ``kuma_log_audit()`` journalise l'INSERT unites et
l'UPDATE grandeurs_referentiel ; ``auteur_applicatif`` NULL (pattern
phase 0).
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import ARRAY

from kuma_data_core.db.seeds.unites_psp_periode_100_seed_data import (
    UNITES_PSP_PERIODE_100_SEED,
)

# revision identifiers, used by Alembic.
revision: str = "100"
down_revision: str | Sequence[str] | None = "099"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


_CODE_UNITE_PERIODE = "kwh_par_kwc_periode"
_CODE_UNITE_JOUR = "kwh_par_kwc_jour"
_CODE_GRANDEUR_PSP = "productible_specifique_theorique"


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
    op.bulk_insert(unites_table, UNITES_PSP_PERIODE_100_SEED)

    op.execute(
        sa.text(
            """
            UPDATE grandeurs_referentiel
            SET unite_id = (SELECT id FROM unites WHERE code = :unite_periode)
            WHERE code = :grandeur_psp
            """
        ).bindparams(unite_periode=_CODE_UNITE_PERIODE, grandeur_psp=_CODE_GRANDEUR_PSP)
    )


def downgrade() -> None:
    op.execute(
        sa.text(
            """
            UPDATE grandeurs_referentiel
            SET unite_id = (SELECT id FROM unites WHERE code = :unite_jour)
            WHERE code = :grandeur_psp
            """
        ).bindparams(unite_jour=_CODE_UNITE_JOUR, grandeur_psp=_CODE_GRANDEUR_PSP)
    )
    op.execute(
        sa.text("DELETE FROM unites WHERE code = :code").bindparams(code=_CODE_UNITE_PERIODE)
    )
