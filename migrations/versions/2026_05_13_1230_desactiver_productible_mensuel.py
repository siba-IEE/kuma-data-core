"""desactiver_productible_mensuel

Revision ID: 035
Revises: 034
Create Date: 2026-05-13 12:30:00.000000+00:00

Désactivation soft delete de la grandeur `productible_mensuel` dans
`grandeurs_referentiel`.

Justification : `productible_mensuel` est numériquement redondant avec
`productible_specifique_theorique` mensuel (déjà calculé).
Maintien de la ligne dans la table pour traçabilité du seed historique
010 / 015 qui la référence ; soft delete via `actif=FALSE` +
`desactive_le=NOW()`.

Garde-fou : aucune ligne `series_metadonnees` ne référence
`productible_mensuel` (vérifié en début de migration ; attendu = 0).

Pattern symétrique aux références (`unites`, `localites`,
`sources`) qui utilisent `actif`/`desactive_le` pour le retrait sans
modification d'identité métier.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "035"
down_revision: str | Sequence[str] | None = "034"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_GRANDEUR_CODE_A_DESACTIVER: str = "productible_mensuel"


def upgrade() -> None:
    bind = op.get_bind()

    # === Garde-fou : aucune serie ne reference la grandeur a desactiver ===
    n_series_referencantes = bind.execute(
        sa.text("SELECT COUNT(*) FROM series_metadonnees WHERE grandeur_code = :code"),
        {"code": _GRANDEUR_CODE_A_DESACTIVER},
    ).scalar_one()
    if n_series_referencantes > 0:
        raise RuntimeError(
            f"Migration 035 : {n_series_referencantes} serie(s) "
            f"reference(nt) encore {_GRANDEUR_CODE_A_DESACTIVER!r} dans "
            "series_metadonnees. Soft delete de la grandeur impossible. "
            "Verifier la cohorte 1-6 ou ouvrir une dette."
        )

    # === Verification que la ligne existe et est actuellement active ===
    statut_actuel = bind.execute(
        sa.text("SELECT actif FROM grandeurs_referentiel WHERE code = :code"),
        {"code": _GRANDEUR_CODE_A_DESACTIVER},
    ).scalar_one_or_none()
    if statut_actuel is None:
        raise RuntimeError(
            f"Migration 035 : grandeur {_GRANDEUR_CODE_A_DESACTIVER!r} "
            "introuvable dans grandeurs_referentiel."
        )
    if statut_actuel is False:
        # Idempotence : si deja desactivee, on log et on continue (no-op)
        op.execute(
            f"-- Migration 035 : grandeur {_GRANDEUR_CODE_A_DESACTIVER!r} "
            "deja desactivee (actif=FALSE). Migration idempotente, no-op."
        )
        return

    # === Soft delete : actif=FALSE + desactive_le=NOW() ===
    op.execute(
        sa.text(
            "UPDATE grandeurs_referentiel "
            "SET actif = FALSE, desactive_le = NOW() "
            "WHERE code = :code"
        ).bindparams(sa.bindparam("code", value=_GRANDEUR_CODE_A_DESACTIVER))
    )

    op.execute(
        f"-- Migration 035 : grandeur {_GRANDEUR_CODE_A_DESACTIVER!r} "
        "desactivee par soft delete (actif=FALSE, desactive_le=NOW()). "
        "Redondance avec productible_specifique_theorique mensuel "
        "(spec 1-6 sec. 3.3, Q1 arbitrage utilisateur prealable factuel 1-6)."
    )


def downgrade() -> None:
    op.execute(
        sa.text(
            "UPDATE grandeurs_referentiel SET actif = TRUE, desactive_le = NULL WHERE code = :code"
        ).bindparams(sa.bindparam("code", value=_GRANDEUR_CODE_A_DESACTIVER))
    )
