"""seed_grandeur_pr_realiste_vague5

Revision ID: 083
Revises: 082
Create Date: 2026-06-19 11:00:00.000000+00:00

PR realiste saisonnier : enregistre la grandeur F1 ``pr_realiste`` dans
``grandeurs_referentiel``. PR effectif site-specifique
= ``PR_fourni x ratio_T x (1 - salissure)``, dont la **courbe mensuelle est la
"PR saisonniere"** (creux Harmattan). Grandeur **calculee_volee** : aucune serie,
aucune valeur stockee (calcul a la volee par l'endpoint, Temps 2). **Migration de
referentiel uniquement** : aucune DDL, aucune donnee, aucun reseau ; ``alembic
check`` reste aligne (la grandeur est l'unique ajout).

Compose, ne reimplemente pas : facteur thermique = NOCT Ross 1980
(``productible_correction_thermique``, deja partage par ``productible_pr_fourni``) ;
facteur salissure = proxy HSU (``taux_salissure_proxy``). Confiance B derivee.

Doctrine PR-reference (anti double-comptage) : le ``PR_fourni`` est suppose **hors
salissure ET hors temperature** ; les deux corrections se superposent en facteurs
multiplicatifs separables.

Perimetre (enumeration exhaustive) :

1. INSERT 1 ligne dans ``grandeurs_referentiel`` (code ``pr_realiste``, famille F1,
   strategie ``calculee_volee``, unite ``sans_unite`` resolue par code).

Miroir du pattern d'insertion grandeur des migrations 082 / 079. Downgrade : DELETE
de la grandeur ``pr_realiste``.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "083"
down_revision: str | Sequence[str] | None = "082"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_GRANDEUR_CODE = "pr_realiste"


def upgrade() -> None:
    bind = op.get_bind()

    unite_id = bind.execute(
        sa.text("SELECT id FROM unites WHERE code = :code"),
        {"code": "sans_unite"},
    ).scalar_one_or_none()
    if unite_id is None:
        raise RuntimeError("Migration 083 : unite 'sans_unite' introuvable (seed initial unites).")

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
                "code": _GRANDEUR_CODE,
                "libelle": "PR realiste saisonnier (PR effectif site-specifique)",
                "famille": "F1",
                "strategie_calcul": "calculee_volee",
                "unite_id": int(unite_id),
                "description": (
                    "PR effectif site-specifique = PR_fourni x ratio_T x "
                    "(1 - salissure), ratio sans dimension. Modes de correction "
                    "aucune / temperature / salissure / temperature_salissure. "
                    "Compose le facteur thermique NOCT (Ross 1980, "
                    "productible_correction_thermique) et le proxy de salissure HSU "
                    "(taux_salissure_proxy, Lot C). La courbe mensuelle est la 'PR "
                    "saisonniere' (creux Harmattan). F1 calculee_volee, confiance B. "
                    "Doctrine PR-reference (anti double-comptage) : le PR_fourni est "
                    "suppose hors salissure ET hors temperature ; corrections "
                    "multiplicatives separables. Ne traite pas la correction "
                    "meteo/climat."
                    ""
                ),
            }
        ],
    )


def downgrade() -> None:
    op.execute(
        sa.text("DELETE FROM grandeurs_referentiel WHERE code = :code").bindparams(
            code=_GRANDEUR_CODE
        )
    )
