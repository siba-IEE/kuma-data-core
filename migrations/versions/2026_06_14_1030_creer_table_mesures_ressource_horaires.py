"""creer_table_mesures_ressource_horaires

Revision ID: 053
Revises: 052
Create Date: 2026-06-14 10:30:00.000000+00:00

Crée la table ``mesures_ressource_horaires`` - pendant horaire de
``mesures_ressource`` (journalier strict) et
``mesures_ressource_mensuelles`` (mensuel).

Identité métier : 2-uplet ``(serie_id, instant_mesure)`` avec
``instant_mesure TIMESTAMPTZ`` (UTC), versioning temporel
``tstzrange(valide_du, valide_au)`` + EXCLUDE BTree-GiST. Le choix UTC
(plutôt qu'un instant naïf LST) est dicté par le contrôle qualité
horaire (lot 2) qui calcule la position solaire sans ambiguïté de fuseau
(cf. ``docs/methodologie/doctrine-qc-horaire.md`` §3).

Pré-requis : extension ``btree_gist`` activée en migration 013 (commune
avec ``mesures_ressource`` et ``mesures_ressource_mensuelles``).
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "053"
down_revision: str | Sequence[str] | None = "052"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "mesures_ressource_horaires",
        # === Identifiant ===
        sa.Column(
            "id",
            sa.BigInteger(),
            sa.Identity(start=1, increment=1),
            primary_key=True,
        ),
        # === Identité métier (2-uplet serie_id + instant_mesure) ===
        sa.Column("serie_id", sa.BigInteger(), nullable=False),
        sa.Column("instant_mesure", sa.DateTime(timezone=True), nullable=False),
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
            name="fk_mesures_ressource_horaires_serie_id__series_metadonnees",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["cree_par"],
            ["contributeurs.id"],
            name="fk_mesures_ressource_horaires_cree_par__contributeurs",
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["modifie_par"],
            ["contributeurs.id"],
            name="fk_mesures_ressource_horaires_modifie_par__contributeurs",
            ondelete="SET NULL",
        ),
        # === CHECK constraints ===
        sa.CheckConstraint(
            "statut IN ('brut', 'valide_auto', 'valide_humain', 'publie', 'deprecie')",
            name="ck_mesures_ressource_horaires_statut_valide",
        ),
        sa.CheckConstraint(
            "niveau_confiance_derive IN ('A', 'B', 'C')",
            name="ck_mesures_ressource_horaires_niveau_confiance_derive_valide",
        ),
        sa.CheckConstraint(
            "niveau_confiance_override IS NULL OR niveau_confiance_override IN ('A', 'B', 'C')",
            name="ck_mesures_ressource_horaires_niveau_confiance_override_valide",
        ),
        sa.CheckConstraint(
            "valide_au IS NULL OR valide_au > valide_du",
            name="ck_mesures_ressource_horaires_periode_coherente",
        ),
        comment=(
            "Mesures horaires ingerees depuis sources externes (NASA POWER, "
            "Vague 3). Pendant horaire de mesures_ressource (journalier) et "
            "mesures_ressource_mensuelles (mensuel). instant_mesure en "
            "TIMESTAMPTZ (UTC) pour le controle qualite horaire (position "
            "solaire sans ambiguite de fuseau). Versioning temporel par "
            "(valide_du, valide_au) + EXCLUDE BTree-GiST sur identite metier "
            "(serie_id, instant_mesure). Statut editorial et niveau de "
            "confiance derive/override par couche service editoriale."
        ),
    )

    # === EXCLUDE BTree-GiST sur identité métier + période ===
    op.execute(
        """
        ALTER TABLE mesures_ressource_horaires
        ADD CONSTRAINT ex_mesures_ressource_horaires_identite_periode
        EXCLUDE USING gist (
            serie_id WITH =,
            instant_mesure WITH =,
            tstzrange(valide_du, valide_au) WITH &&
        )
        """
    )

    # === Index partiel sur lignes courantes ===
    op.create_index(
        "idx_mesures_ressource_horaires_courantes",
        "mesures_ressource_horaires",
        ["serie_id", "instant_mesure"],
        postgresql_where=sa.text("valide_au IS NULL"),
    )

    # === Trigger d'audit (fonction kuma_log_audit posée en migration 005) ===
    op.execute(
        """
        CREATE TRIGGER trg_audit_mesures_ressource_horaires
            AFTER INSERT OR UPDATE OR DELETE ON mesures_ressource_horaires
            FOR EACH ROW EXECUTE FUNCTION kuma_log_audit()
        """
    )


def downgrade() -> None:
    op.execute(
        "DROP TRIGGER IF EXISTS trg_audit_mesures_ressource_horaires ON mesures_ressource_horaires"
    )
    op.drop_index(
        "idx_mesures_ressource_horaires_courantes",
        table_name="mesures_ressource_horaires",
    )
    op.execute(
        "ALTER TABLE mesures_ressource_horaires "
        "DROP CONSTRAINT IF EXISTS ex_mesures_ressource_horaires_identite_periode"
    )
    op.drop_table("mesures_ressource_horaires")
