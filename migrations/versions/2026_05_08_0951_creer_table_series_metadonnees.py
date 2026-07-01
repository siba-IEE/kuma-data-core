"""creer_table_series_metadonnees

Revision ID: 008
Revises: 007
Create Date: 2026-05-08 09:51:03.300447+00:00

Référentiel éditorial des séries de
mesures, sans versioning temporel, sans statut workflow,
sans niveau de confiance à l'échelle série. FK grandeur_code vers
colonne UNIQUE non-PK de
grandeurs_referentiel - premier usage du pattern dans le projet.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "008"
down_revision: str | Sequence[str] | None = "007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # === 1. Création de la table ===
    op.create_table(
        "series_metadonnees",
        # Identifiants
        sa.Column(
            "id",
            sa.BigInteger(),
            sa.Identity(always=False, start=1),
            nullable=False,
        ),
        sa.Column("code", sa.String(length=80), nullable=False),
        sa.Column("libelle", sa.Text(), nullable=False),
        # Identité métier (triplet localité × grandeur × source)
        sa.Column("localite_id", sa.BigInteger(), nullable=False),
        sa.Column("grandeur_code", sa.String(length=80), nullable=False),
        sa.Column("source_id", sa.BigInteger(), nullable=False),
        # Période
        sa.Column("periode_debut", sa.Date(), nullable=False),
        sa.Column("periode_fin", sa.Date(), nullable=True),
        # Métadonnées éditoriales
        sa.Column("methode_collecte", sa.String(length=40), nullable=True),
        sa.Column("methode_collecte_doc", sa.Text(), nullable=True),
        sa.Column("commentaire_editorial", sa.Text(), nullable=True),
        sa.Column("url_documentation", sa.Text(), nullable=True),
        # Soft delete
        sa.Column(
            "actif",
            sa.Boolean(),
            server_default=sa.text("TRUE"),
            nullable=False,
        ),
        sa.Column("desactive_le", sa.DateTime(timezone=True), nullable=True),
        # Audit applicatif
        sa.Column(
            "cree_le",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("cree_par", sa.BigInteger(), nullable=True),
        sa.Column(
            "modifie_le",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("modifie_par", sa.BigInteger(), nullable=True),
        # Contraintes nommées : PK -> UNIQUE simple -> UNIQUE composite -> FK -> CHECK
        sa.PrimaryKeyConstraint("id", name="pk_series_metadonnees"),
        sa.UniqueConstraint("code", name="uq_series_metadonnees_code"),
        sa.UniqueConstraint(
            "localite_id",
            "grandeur_code",
            "source_id",
            name="uq_series_metadonnees_localite_id_grandeur_code_source_id",
        ),
        sa.ForeignKeyConstraint(
            ["localite_id"],
            ["localites.id"],
            name="fk_series_metadonnees_localite_id__localites",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["grandeur_code"],
            ["grandeurs_referentiel.code"],
            name="fk_series_metadonnees_grandeur_code__grandeurs_referentiel",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["source_id"],
            ["sources.id"],
            name="fk_series_metadonnees_source_id__sources",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["cree_par"],
            ["contributeurs.id"],
            name="fk_series_metadonnees_cree_par__contributeurs",
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["modifie_par"],
            ["contributeurs.id"],
            name="fk_series_metadonnees_modifie_par__contributeurs",
            ondelete="SET NULL",
        ),
        sa.CheckConstraint(
            "periode_fin IS NULL OR periode_fin >= periode_debut",
            name="ck_series_metadonnees_periode_coherente",
        ),
        sa.CheckConstraint(
            "(actif = TRUE AND desactive_le IS NULL) "
            "OR (actif = FALSE AND desactive_le IS NOT NULL)",
            name="ck_series_metadonnees_actif_desactive_coherent",
        ),
    )

    # === 2. Index ===
    op.create_index("idx_series_metadonnees_actif", "series_metadonnees", ["actif"])
    op.create_index("idx_series_metadonnees_localite_id", "series_metadonnees", ["localite_id"])
    op.create_index("idx_series_metadonnees_grandeur_code", "series_metadonnees", ["grandeur_code"])
    op.create_index("idx_series_metadonnees_source_id", "series_metadonnees", ["source_id"])

    # === 3. Trigger d'audit ===
    # La fonction kuma_log_audit() est créée en migration 005 et n'est
    # pas recréée ici. La liste _TABLES_AUDITEES de la migration 005
    # reste immuable (convention d'immuabilité des migrations mergées).
    op.execute(
        """
        CREATE TRIGGER trg_audit_series_metadonnees
            AFTER INSERT OR UPDATE OR DELETE ON series_metadonnees
            FOR EACH ROW EXECUTE FUNCTION kuma_log_audit()
        """
    )

    # === 4. Commentaires de documentation (ASCII pur) ===
    op.execute(
        "COMMENT ON TABLE series_metadonnees IS "
        "'Referentiel editorial des series de mesures Kuma. "
        "Une serie = un triplet (localite, grandeur, source) "
        "avec ses metadonnees editoriales communes.'"
    )
    op.execute(
        "COMMENT ON COLUMN series_metadonnees.code IS "
        "'Cle naturelle metier (ASCII pur, snake_case). "
        "Convention : <localite>_<grandeur>_<source>[_<periode>] "
        "ex. gin_conakry_hep_nasa_power_2010_2024.'"
    )
    op.execute(
        "COMMENT ON COLUMN series_metadonnees.grandeur_code IS "
        "'FK vers grandeurs_referentiel.code (colonne UNIQUE non-PK). "
        "Lisibilite metier prioritaire sur convention SQL classique.'"
    )
    op.execute(
        "COMMENT ON COLUMN series_metadonnees.methode_collecte IS "
        "'Methode dominante de collecte de la serie. "
        "Liste indicative des 6 valeurs en spec mecaniques-transverses sec. 6.4. "
        "CHECK formel pose en 1-2b.'"
    )
    op.execute(
        "COMMENT ON COLUMN series_metadonnees.periode_fin IS "
        "'NULL si la serie est en cours (pas de fin annoncee). "
        "Sinon date de la derniere mesure attendue, >= periode_debut.'"
    )


def downgrade() -> None:
    # Symétrie stricte : trigger -> index -> table.

    # 1. Suppression du trigger.
    op.execute("DROP TRIGGER IF EXISTS trg_audit_series_metadonnees ON series_metadonnees")

    # 2. Suppression des index (ordre inverse de la création).
    op.drop_index("idx_series_metadonnees_source_id", table_name="series_metadonnees")
    op.drop_index("idx_series_metadonnees_grandeur_code", table_name="series_metadonnees")
    op.drop_index("idx_series_metadonnees_localite_id", table_name="series_metadonnees")
    op.drop_index("idx_series_metadonnees_actif", table_name="series_metadonnees")

    # 3. Suppression de la table (contraintes en cascade).
    op.drop_table("series_metadonnees")
