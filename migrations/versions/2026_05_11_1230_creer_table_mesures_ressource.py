"""creer_table_mesures_ressource

Revision ID: 014
Revises: 013
Create Date: 2026-05-11 12:30:00.000000+00:00

Crée la table ``mesures_ressource`` - première table métier
opérationnelle, premier consommateur en production des 4
mécaniques structurantes superposées (statut éditorial + versioning
temporel EXCLUDE BTree-GiST + niveau_confiance A/B/C dérivé + identité
métier 2-uplet via ``serie_id``).

Identité métier (Option D) : 2-uplet ``(serie_id, instant_mesure)`` avec
``instant_mesure DATE``. La FK ``serie_id`` vers ``series_metadonnees``
détermine implicitement la source via traversée.

Pré-requis posé par migration 013 : extension ``btree_gist`` activée
(nécessaire à l'EXCLUDE).
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "014"
down_revision: str | Sequence[str] | None = "013"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "mesures_ressource",
        # === Identifiant ===
        sa.Column(
            "id",
            sa.BigInteger(),
            sa.Identity(start=1, increment=1),
            primary_key=True,
        ),
        # === Identité métier (Option D) ===
        sa.Column("serie_id", sa.BigInteger(), nullable=False),
        sa.Column("instant_mesure", sa.Date(), nullable=False),
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
        # === Commentaire éditorial (justification override) ===
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
            name="fk_mesures_ressource_serie_id__series_metadonnees",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["cree_par"],
            ["contributeurs.id"],
            name="fk_mesures_ressource_cree_par__contributeurs",
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["modifie_par"],
            ["contributeurs.id"],
            name="fk_mesures_ressource_modifie_par__contributeurs",
            ondelete="SET NULL",
        ),
        # === CHECK constraints ===
        sa.CheckConstraint(
            "statut IN ('brut', 'valide_auto', 'valide_humain', 'publie', 'deprecie')",
            name="ck_mesures_ressource_statut_valide",
        ),
        sa.CheckConstraint(
            "niveau_confiance_derive IN ('A', 'B', 'C')",
            name="ck_mesures_ressource_niveau_confiance_derive_valide",
        ),
        sa.CheckConstraint(
            "niveau_confiance_override IS NULL OR niveau_confiance_override IN ('A', 'B', 'C')",
            name="ck_mesures_ressource_niveau_confiance_override_valide",
        ),
        sa.CheckConstraint(
            "valide_au IS NULL OR valide_au > valide_du",
            name="ck_mesures_ressource_periode_coherente",
        ),
        comment=(
            "Mesures journalieres ingerees depuis sources externes. Premiere "
            "table metier operationnelle phase 1. Versioning temporel par "
            "(valide_du, valide_au) + EXCLUDE BTree-GiST sur identite metier "
            "(serie_id, instant_mesure). Statut editorial et niveau de "
            "confiance derive/override par couche service editoriale."
        ),
    )

    # === EXCLUDE BTree-GiST sur identité métier + période ===
    # Pas directement supporté en op.create_table via sa.ExcludeConstraint
    # avec opérateurs sur tstzrange ; on pose la contrainte via DDL brut
    # (pattern cohérent avec la migration 005 qui a posé la fonction et les
    # triggers d'audit via op.execute).
    op.execute(
        """
        ALTER TABLE mesures_ressource
        ADD CONSTRAINT ex_mesures_ressource_identite_periode
        EXCLUDE USING gist (
            serie_id WITH =,
            instant_mesure WITH =,
            tstzrange(valide_du, valide_au) WITH &&
        )
        """
    )

    # === Index partiel sur lignes courantes ===
    op.create_index(
        "idx_mesures_ressource_courantes",
        "mesures_ressource",
        ["serie_id", "instant_mesure"],
        postgresql_where=sa.text("valide_au IS NULL"),
    )

    # === Trigger d'audit (fonction kuma_log_audit posée en migration 005) ===
    op.execute(
        """
        CREATE TRIGGER trg_audit_mesures_ressource
            AFTER INSERT OR UPDATE OR DELETE ON mesures_ressource
            FOR EACH ROW EXECUTE FUNCTION kuma_log_audit()
        """
    )

    # === Commentaires SQL sur les colonnes structurantes (ASCII pur) ===
    op.execute(
        """
        COMMENT ON COLUMN mesures_ressource.statut IS
            'Statut editorial Kuma : brut (importe non valide), valide_auto '
            '(controle qualite automatique passe), valide_humain (validation '
            'editoriale humaine), publie (publie publiquement), deprecie '
            '(retire du circuit editorial). Transitions encadrees par la '
            'couche service Python (cf. kuma_data_core.editorial.statuts).'
        """
    )
    op.execute(
        """
        COMMENT ON COLUMN mesures_ressource.niveau_confiance_derive IS
            'Niveau de confiance derive automatiquement par la couche service '
            'a partir des regles R1-R4 (cf. spec mecaniques-transverses-phase-1 '
            'sec. 6.4). A = haute, B = moyenne, C = basse. Recalcule a chaque '
            'modification de methode_collecte ou source_id de la serie.'
        """
    )
    op.execute(
        """
        COMMENT ON COLUMN mesures_ressource.niveau_confiance_override IS
            'Override editorial du niveau derive. NULL = pas override (valeur '
            'effective = derive). Sinon valeur effective = override. Pose par '
            'la fonction service overrider_niveau_confiance avec justification '
            'obligatoire dans commentaire_editorial.'
        """
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_audit_mesures_ressource ON mesures_ressource")
    op.drop_index("idx_mesures_ressource_courantes", table_name="mesures_ressource")
    op.execute(
        "ALTER TABLE mesures_ressource "
        "DROP CONSTRAINT IF EXISTS ex_mesures_ressource_identite_periode"
    )
    op.drop_table("mesures_ressource")
