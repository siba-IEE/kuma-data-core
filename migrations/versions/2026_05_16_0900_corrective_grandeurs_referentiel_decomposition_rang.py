"""corrective_grandeurs_referentiel_decomposition_rang

Revision ID: 042
Revises: 041
Create Date: 2026-05-16 09:00:00.000000+00:00

Migration corrective `grandeurs_referentiel` - décomposition de la
grandeur `rang_referentiel` (singulier, seedée en migration 010,
immuable post-merge) en deux grandeurs distinctes pour refléter la
sémantique tranchée :

- `rang_referentiel_temporel` : percentile dans la climatologie NASA
  POWER 1991-2020 par mois calendrier (cohérence intra-source).
- `rang_referentiel_spatial` : rang ordinal 1-6 dans le pool des 6
  villes Kuma pour le même mois (cohérence intra-périmètre).

Drift attrapé en pré-investigation DDL, en mode pré-implémentation.

Pattern de désactivation hérité de la migration 035 (`productible_mensuel`
désactivée) : `actif=FALSE`, `desactive_le=NOW()`.
Préservation de l'audit historique de `rang_referentiel` singulier.

Périmètre (énumération exhaustive) :

1. `UPDATE` `rang_referentiel` (singulier) avec `actif=FALSE` et
   `desactive_le=NOW()`.
2. `INSERT` `rang_referentiel_temporel` (famille=F1, strategie=calculee_volee,
   unite=sans_unite - aligné sur `rang_referentiel` singulier original
   pour cohérence).
3. `INSERT` `rang_referentiel_spatial` (idem : F1, calculee_volee,
   sans_unite).

`ecart_relatif_referentiel` déjà seedée en migration 010 et compatible
sémantiquement - aucune modification requise.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "042"
down_revision: str | Sequence[str] | None = "041"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()

    # === Étape 1 : désactivation rang_referentiel (singulier) =================
    op.execute(
        sa.text(
            """
            UPDATE grandeurs_referentiel
            SET actif = FALSE,
                desactive_le = NOW(),
                description = COALESCE(description, '') || ' [D-39 : '
                  || 'desactivee en migration 042, decomposee en '
                  || 'rang_referentiel_temporel + rang_referentiel_spatial '
                  || 'cf. spec 1-7 PR #54.]'
            WHERE code = 'rang_referentiel'
              AND actif = TRUE
            """
        )
    )

    # === Étape 2 : résolution unite_id 'sans_unite' (cohérence Option α) ======
    unite_sans_unite_id = bind.execute(
        sa.text("SELECT id FROM unites WHERE code = :code"),
        {"code": "sans_unite"},
    ).scalar_one_or_none()
    if unite_sans_unite_id is None:
        raise RuntimeError(
            "Migration 042 : unite 'sans_unite' introuvable. "
            "Verifier que la migration 009 (seed unites) a bien ete appliquee."
        )

    # === Étape 3 : insertion rang_referentiel_temporel + rang_referentiel_spatial =
    grandeurs_table = sa.table(
        "grandeurs_referentiel",
        sa.column("code", sa.String),
        sa.column("libelle", sa.Text),
        sa.column("famille", sa.String),
        sa.column("strategie_calcul", sa.String),
        sa.column("unite_id", sa.BigInteger),
        sa.column("description", sa.Text),
    )

    lignes_a_inserer = [
        {
            "code": "rang_referentiel_temporel",
            "libelle": "Rang temporel dans la climatologie",
            "famille": "F1",
            "strategie_calcul": "calculee_volee",
            "unite_id": int(unite_sans_unite_id),
            "description": (
                "Rang temporel dans la climatologie de reference (percentile "
                "calcule par mois calendrier sur la distribution NASA POWER "
                "1991-2020 par localite). Formule type 7 numpy/R : "
                "p = (rang - 1) / (n - 1) x 100, capping [0, 100]. "
                "Plage de calcul phase 1 : 2021-2025 sur les 6 villes "
                "pilotes guineennes. Decomposition de rang_referentiel "
                "singulier seede en 1-1C (D-39 fermee dans le meme cycle "
                "1-7b). Cf. note methodologique amont PR #53 et spec 1-7 "
                "PR #54."
            ),
        },
        {
            "code": "rang_referentiel_spatial",
            "libelle": "Rang spatial dans le perimetre Kuma",
            "famille": "F1",
            "strategie_calcul": "calculee_volee",
            "unite_id": int(unite_sans_unite_id),
            "description": (
                "Rang spatial dans le perimetre Kuma (rang ordinal 1-6 "
                "parmi les 6 villes pilotes guineennes pour le meme mois). "
                "Calcule a la volee a partir des mesures NASA POWER 2021-2025 "
                "agregees mensuellement. Decomposition de rang_referentiel "
                "singulier seede en 1-1C (D-39 fermee dans le meme cycle "
                "1-7b). Cf. note methodologique amont PR #53 et spec 1-7 "
                "PR #54."
            ),
        },
    ]
    op.bulk_insert(grandeurs_table, lignes_a_inserer)


def downgrade() -> None:
    # Suppression des 2 nouvelles grandeurs
    op.execute(
        sa.text(
            "DELETE FROM grandeurs_referentiel "
            "WHERE code IN ('rang_referentiel_temporel', 'rang_referentiel_spatial')"
        )
    )
    # Reactivation de rang_referentiel singulier
    op.execute(
        sa.text(
            """
            UPDATE grandeurs_referentiel
            SET actif = TRUE,
                desactive_le = NULL,
                description = REGEXP_REPLACE(
                    COALESCE(description, ''),
                    ' \\[D-39 : desactivee en migration 042.*\\]',
                    ''
                )
            WHERE code = 'rang_referentiel'
            """
        )
    )
