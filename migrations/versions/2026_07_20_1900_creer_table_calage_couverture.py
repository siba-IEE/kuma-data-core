"""creer_table_calage_couverture

Revision ID: 102
Revises: 101
Create Date: 2026-07-20 19:00:00.000000+00:00

Couverture progressive du calage (ADR-0004, complement du
2026-07-20 au soir, decision du fondateur) : le domaine de validite
du transport d'un referentiel de calage devient une donnee servie -
la liste des localites qualifiees, avec justification. C'est elle
qui pilote la couverture geographique des logiciels consommateurs :
etendre la couverture = ajouter des lignes et publier une edition,
zero code cote consommateurs.

Deux gestes :

1. creation de la table ``calage_couverture`` (une ligne par
   localite qualifiee d'un referentiel, justification obligatoire)
   + declencheur d'audit ;
2. seed du domaine initial du referentiel GHI Kankan : les 5
   communes points d'ingestion de la region administrative de
   Kankan (Kankan, Kerouane, Kouroussa, Mandiana, Siguiri). Meme
   regime soudanien, precedent de transport declare de l'etude
   Tokounou.

Publication : table ajoutee a TABLES_PUBLIEES du manifeste (PR
associee). Servie par GET /v1/calage/{localite}/{grandeur} (champ
localites_couvertes).

Trigger d'audit : ``kuma_log_audit()``, ``auteur_applicatif`` NULL
(pattern phase 0).
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

from kuma_data_core.db.seeds.calage_couverture_102_seed_data import (
    JUSTIFICATION_102,
    LOCALITES_COUVERTES_102,
    REFERENTIEL_CODE_102,
)

# revision identifiers, used by Alembic.
revision: str = "102"
down_revision: str | Sequence[str] | None = "101"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # === 1. Table ===
    op.create_table(
        "calage_couverture",
        sa.Column("id", sa.BigInteger(), sa.Identity(start=1, increment=1), primary_key=True),
        sa.Column("referentiel_code", sa.String(120), nullable=False),
        sa.Column(
            "localite_id",
            sa.BigInteger(),
            sa.ForeignKey("localites.id", name="fk_calage_couverture_localite__localites"),
            nullable=False,
        ),
        sa.Column("justification", sa.Text(), nullable=False),
        sa.Column("version", sa.String(20), nullable=False, server_default=sa.text("'v1'")),
        sa.Column("actif", sa.Boolean(), nullable=False, server_default=sa.text("TRUE")),
        sa.Column(
            "cree_le",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "modifie_le",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint(
            "referentiel_code",
            "localite_id",
            "version",
            name="uq_calage_couverture_referentiel_localite_version",
        ),
        comment=(
            "Domaine de couverture des referentiels de calage : "
            "localites qualifiees pour le transport, avec justification. "
            "Pilote la couverture geographique des consommateurs "
            "(ADR-0004, couverture progressive)."
        ),
    )
    op.create_index("idx_calage_couverture_referentiel", "calage_couverture", ["referentiel_code"])
    op.create_index("idx_calage_couverture_actif", "calage_couverture", ["actif"])

    # === 2. Declencheur d'audit ===
    op.execute(
        """
        CREATE TRIGGER trg_audit_calage_couverture
            AFTER INSERT OR UPDATE OR DELETE ON calage_couverture
            FOR EACH ROW EXECUTE FUNCTION kuma_log_audit()
        """
    )

    # === 3. Seed : domaine initial, region de Kankan (5 communes) ===
    bind = op.get_bind()
    table_seed = sa.table(
        "calage_couverture",
        sa.column("referentiel_code", sa.String),
        sa.column("localite_id", sa.BigInteger),
        sa.column("justification", sa.Text),
        sa.column("version", sa.String),
    )
    lignes = []
    for code_localite in LOCALITES_COUVERTES_102:
        localite_id = bind.execute(
            sa.text("SELECT id FROM localites WHERE code = :code"),
            {"code": code_localite},
        ).scalar_one()
        lignes.append(
            {
                "referentiel_code": REFERENTIEL_CODE_102,
                "localite_id": localite_id,
                "justification": JUSTIFICATION_102,
                "version": "v1",
            }
        )
    op.bulk_insert(table_seed, lignes)


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_audit_calage_couverture ON calage_couverture")
    op.drop_index("idx_calage_couverture_actif", table_name="calage_couverture")
    op.drop_index("idx_calage_couverture_referentiel", table_name="calage_couverture")
    op.drop_table("calage_couverture")
