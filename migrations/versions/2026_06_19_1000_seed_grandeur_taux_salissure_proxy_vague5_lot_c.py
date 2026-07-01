"""seed_grandeur_taux_salissure_proxy_vague5_lot_c

Revision ID: 082
Revises: 081
Create Date: 2026-06-19 10:00:00.000000+00:00

Enregistre la grandeur F1 ``taux_salissure_proxy``
(perte de transmission par salissure, en % = (1 - ratio_hsu) x 100) dans
``grandeurs_referentiel``. Grandeur **calculee_volee** : aucune serie, aucune
valeur stockee (calcul a la volee par l'endpoint, Temps 2). **Migration de
referentiel uniquement** : aucune DDL, aucune donnee, aucun reseau ; ``alembic
check`` reste aligne (la grandeur est l'unique ajout).

Modele HSU (``pvlib.soiling.hsu``, Coello & Boyle 2019) a partir des PM2.5/PM10
EAC4 et de la pluie NASA POWER. Confiance B derivee.

Perimetre (enumeration exhaustive) :

1. INSERT 1 ligne dans ``grandeurs_referentiel`` (code ``taux_salissure_proxy``,
   famille F1, strategie ``calculee_volee``, unite ``pourcent`` resolue par code).

Miroir du pattern d'insertion grandeur de la migration 079 (poa_bifacial). Downgrade :
DELETE de la grandeur ``taux_salissure_proxy``.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "082"
down_revision: str | Sequence[str] | None = "081"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_GRANDEUR_CODE = "taux_salissure_proxy"


def upgrade() -> None:
    bind = op.get_bind()

    unite_id = bind.execute(
        sa.text("SELECT id FROM unites WHERE code = :code"),
        {"code": "pourcent"},
    ).scalar_one_or_none()
    if unite_id is None:
        raise RuntimeError("Migration 082 : unite 'pourcent' introuvable (seed initial unites).")

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
                "libelle": "Proxy de salissure (perte de transmission, %)",
                "famille": "F1",
                "strategie_calcul": "calculee_volee",
                "unite_id": int(unite_id),
                "description": (
                    "Proxy de salissure des modules PV : perte de transmission par "
                    "salissure, en % = (1 - ratio HSU) x 100. Modele HSU "
                    "(pvlib.soiling.hsu, Coello & Boyle 2019) a partir des PM2.5/PM10 "
                    "EAC4 (convertis ug/m3 -> g/m3, unite attendue par pvlib) et de la "
                    "pluie NASA POWER (mm). F1 calculee_volee, confiance B derivee. Tilt "
                    "et seuil de nettoyage par defaut documentes (10 deg, 1 mm). Caveats "
                    "L-SOIL : proxy modele (pas une mesure de salissure, terrain) ; "
                    "spin-up (HSU demarre propre, premiers jours sous-estimes, L-SOIL-3) ; "
                    "grille EAC4 grossiere 0,75 deg (L-SOIL-4). "
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
