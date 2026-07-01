"""creer_table_mesures_ressource_mensuelles

Revision ID: 039
Revises: 038
Create Date: 2026-05-15 09:00:00.000000+00:00

Crée la table ``mesures_ressource_mensuelles`` - pendant mensuel de
``mesures_ressource`` (journalier strict).

Identité métier : 3-uplet ``(serie_id, annee, mois)`` avec versioning
temporel ``tstzrange(valide_du, valide_au)`` + EXCLUDE BTree-GiST. Le
choix ``(annee SMALLINT, mois SMALLINT)`` séparés est retenu (cohérent
avec ``grandeurs_metier``) plutôt que ``periode_debut DATE`` au 1er du
mois (qui introduirait une ambiguïté sémantique).

Pré-requis : extension ``btree_gist`` activée en migration 013
(commune avec ``mesures_ressource``).

Migration suivante (040) : seed source ``sarah3_monthly``
+ 12 séries brutes + ingestion 2 520 lignes dans cette nouvelle table.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "039"
down_revision: str | Sequence[str] | None = "038"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "mesures_ressource_mensuelles",
        # === Identifiant ===
        sa.Column(
            "id",
            sa.BigInteger(),
            sa.Identity(start=1, increment=1),
            primary_key=True,
        ),
        # === Identité métier (3-uplet serie_id + annee + mois) ===
        sa.Column("serie_id", sa.BigInteger(), nullable=False),
        sa.Column("annee", sa.SmallInteger(), nullable=False),
        sa.Column("mois", sa.SmallInteger(), nullable=False),
        # === Valeur ===
        sa.Column("valeur", sa.Float(precision=53), nullable=False),
        # === Versioning temporel ===
        sa.Column(
            "valide_du",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("valide_au", sa.DateTime(timezone=True), nullable=True),
        # === Statut éditorial ===
        sa.Column(
            "statut",
            sa.String(length=16),
            nullable=False,
            server_default=sa.text("'brut'"),
        ),
        # === Niveau de confiance ===
        sa.Column("niveau_confiance_derive", sa.String(length=1), nullable=False),
        sa.Column("niveau_confiance_override", sa.String(length=1), nullable=True),
        # === Commentaire éditorial ===
        sa.Column("commentaire_editorial", sa.Text(), nullable=True),
        # === Audit applicatif ===
        sa.Column(
            "cree_le",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("cree_par", sa.BigInteger(), nullable=True),
        sa.Column(
            "modifie_le",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("modifie_par", sa.BigInteger(), nullable=True),
        # === FK ===
        sa.ForeignKeyConstraint(
            ["serie_id"],
            ["series_metadonnees.id"],
            name="fk_mesures_ressource_mensuelles_serie_id__series_metadonnees",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["cree_par"],
            ["contributeurs.id"],
            name="fk_mesures_ressource_mensuelles_cree_par__contributeurs",
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["modifie_par"],
            ["contributeurs.id"],
            name="fk_mesures_ressource_mensuelles_modifie_par__contributeurs",
            ondelete="SET NULL",
        ),
        # === CHECK constraints ===
        sa.CheckConstraint(
            "annee BETWEEN 1991 AND 2099",
            name="ck_mesures_ressource_mensuelles_annee_valide",
        ),
        sa.CheckConstraint(
            "mois BETWEEN 1 AND 12",
            name="ck_mesures_ressource_mensuelles_mois_valide",
        ),
        sa.CheckConstraint(
            "statut IN ('brut', 'valide_auto', 'valide_humain', 'publie', 'deprecie')",
            name="ck_mesures_ressource_mensuelles_statut_valide",
        ),
        sa.CheckConstraint(
            "niveau_confiance_derive IN ('A', 'B', 'C')",
            name="ck_mesures_ressource_mensuelles_niveau_confiance_derive_valide",
        ),
        sa.CheckConstraint(
            "niveau_confiance_override IS NULL OR niveau_confiance_override IN ('A', 'B', 'C')",
            name="ck_mesures_ressource_mensuelles_niveau_confiance_override_valide",
        ),
        sa.CheckConstraint(
            "valide_au IS NULL OR valide_au > valide_du",
            name="ck_mesures_ressource_mensuelles_periode_coherente",
        ),
        comment=(
            "Mesures mensuelles ingerees depuis sources externes "
            "(SARAH-3 ICDR + NASA POWER 1991-2020, etape 1-7a). Pendant "
            "mensuel de mesures_ressource (journalier strict, cadrage "
            "Q2 phase 1). Versioning temporel par (valide_du, "
            "valide_au) + EXCLUDE BTree-GiST sur identite metier "
            "(serie_id, annee, mois). Statut editorial et niveau de "
            "confiance derive/override par couche service editoriale."
        ),
    )

    # === EXCLUDE BTree-GiST sur identité métier + période ===
    op.execute(
        """
        ALTER TABLE mesures_ressource_mensuelles
        ADD CONSTRAINT ex_mesures_ressource_mensuelles_identite_periode
        EXCLUDE USING gist (
            serie_id WITH =,
            annee WITH =,
            mois WITH =,
            tstzrange(valide_du, valide_au) WITH &&
        )
        """
    )

    # === Index partiel sur lignes courantes ===
    op.create_index(
        "idx_mesures_ressource_mensuelles_courantes",
        "mesures_ressource_mensuelles",
        ["serie_id", "annee", "mois"],
        postgresql_where=sa.text("valide_au IS NULL"),
    )

    # === Trigger d'audit (fonction kuma_log_audit posée en migration 005) ===
    op.execute(
        """
        CREATE TRIGGER trg_audit_mesures_ressource_mensuelles
            AFTER INSERT OR UPDATE OR DELETE ON mesures_ressource_mensuelles
            FOR EACH ROW EXECUTE FUNCTION kuma_log_audit()
        """
    )


def downgrade() -> None:
    op.execute(
        "DROP TRIGGER IF EXISTS trg_audit_mesures_ressource_mensuelles "
        "ON mesures_ressource_mensuelles"
    )
    op.drop_index(
        "idx_mesures_ressource_mensuelles_courantes",
        table_name="mesures_ressource_mensuelles",
    )
    op.execute(
        "ALTER TABLE mesures_ressource_mensuelles "
        "DROP CONSTRAINT IF EXISTS ex_mesures_ressource_mensuelles_identite_periode"
    )
    op.drop_table("mesures_ressource_mensuelles")
