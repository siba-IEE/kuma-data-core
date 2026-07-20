"""creer_table_referentiels_calage

Revision ID: 101
Revises: 100
Create Date: 2026-07-20 12:00:00.000000+00:00

Exposition du calage satellite/sol (ADR-0004, chantier mini-reseaux) :
le biais saisonnier mesure aux stations de reference devient une
donnee editoriale publiee de l'edition, avec provenance et portee de
transport, au lieu de vivre uniquement dans les notes de methodologie.

Pourquoi une table et non une grandeur F1 recalculee a la volee : les
lignes satellite horaires de l'appariement d'origine ne sont plus
stockees en base (la serie gin_kankan_ghi_nasa_power_2001_2023 n'a
plus que ses metadonnees). Le resultat est publie, la methode reste
documentee dans les notes et les scripts reproductibles - conforme a
la doctrine D6 (le serveur public ne detient et ne calcule que du
reconstructible).

Deux gestes :

1. creation de la table ``referentiels_calage`` (une ligne par
   station, grandeur, saison ; biais relatif satellite moins sol ;
   provenance et portee obligatoires) + declencheur d'audit ;
2. seed du referentiel GHI de Kankan (3 saisons : harmattan +4,4 %,
   mousson +1,5 %, intersaison +1,9 %), la premiere entree du
   referentiel. Le referentiel DNI attendra son premier consommateur
   (une migration = un changement).

Publication : table ajoutee a TABLES_PUBLIEES du manifeste (PR
associee). Consommateur type : Solar Bridge (methode d'etude
mini-reseau v1, k = 1/(1+biais)).

Trigger d'audit : ``kuma_log_audit()`` journalise INSERT/UPDATE/
DELETE ; ``auteur_applicatif`` NULL (pattern phase 0).
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import ARRAY

from kuma_data_core.db.seeds.referentiels_calage_101_seed_data import (
    REFERENTIELS_CALAGE_101_SEED,
)

# revision identifiers, used by Alembic.
revision: str = "101"
down_revision: str | Sequence[str] | None = "100"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_CODE_STATION_SEED = "gin_kankan"


def upgrade() -> None:
    # === 1. Table ===
    op.create_table(
        "referentiels_calage",
        sa.Column("id", sa.BigInteger(), sa.Identity(start=1, increment=1), primary_key=True),
        sa.Column("code", sa.String(120), nullable=False),
        sa.Column(
            "localite_id",
            sa.BigInteger(),
            sa.ForeignKey("localites.id", name="fk_referentiels_calage_localite__localites"),
            nullable=False,
        ),
        sa.Column("grandeur_code", sa.String(50), nullable=False),
        sa.Column("saison", sa.String(40), nullable=False),
        sa.Column("mois", ARRAY(sa.BigInteger()), nullable=False),
        sa.Column("biais", sa.Numeric(8, 6), nullable=False),
        sa.Column("provenance", sa.Text(), nullable=False),
        sa.Column("portee", sa.Text(), nullable=False),
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
            "localite_id",
            "grandeur_code",
            "saison",
            "version",
            name="uq_referentiels_calage_station_grandeur_saison_version",
        ),
        sa.CheckConstraint("biais > -1", name="ck_referentiels_calage_biais_definissable"),
        comment=(
            "Referentiel de calage satellite/sol : biais saisonniers "
            "mesures aux stations de reference, publies avec provenance "
            "et portee de transport (ADR-0004)."
        ),
    )
    op.create_index(
        "idx_referentiels_calage_localite_grandeur",
        "referentiels_calage",
        ["localite_id", "grandeur_code"],
    )
    op.create_index("idx_referentiels_calage_actif", "referentiels_calage", ["actif"])

    # === 2. Declencheur d'audit ===
    op.execute(
        """
        CREATE TRIGGER trg_audit_referentiels_calage
            AFTER INSERT OR UPDATE OR DELETE ON referentiels_calage
            FOR EACH ROW EXECUTE FUNCTION kuma_log_audit()
        """
    )

    # === 3. Seed : referentiel GHI de Kankan (3 saisons) ===
    bind = op.get_bind()
    localite_id = bind.execute(
        sa.text("SELECT id FROM localites WHERE code = :code"),
        {"code": _CODE_STATION_SEED},
    ).scalar_one()

    table_seed = sa.table(
        "referentiels_calage",
        sa.column("code", sa.String),
        sa.column("localite_id", sa.BigInteger),
        sa.column("grandeur_code", sa.String),
        sa.column("saison", sa.String),
        sa.column("mois", ARRAY(sa.BigInteger())),
        sa.column("biais", sa.Numeric(8, 6)),
        sa.column("provenance", sa.Text),
        sa.column("portee", sa.Text),
        sa.column("version", sa.String),
    )
    op.bulk_insert(
        table_seed,
        [{**ligne, "localite_id": localite_id} for ligne in REFERENTIELS_CALAGE_101_SEED],
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_audit_referentiels_calage ON referentiels_calage")
    op.drop_index("idx_referentiels_calage_actif", table_name="referentiels_calage")
    op.drop_index("idx_referentiels_calage_localite_grandeur", table_name="referentiels_calage")
    op.drop_table("referentiels_calage")
