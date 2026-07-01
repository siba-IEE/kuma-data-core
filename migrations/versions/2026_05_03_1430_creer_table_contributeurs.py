"""creer_table_contributeurs

Revision ID: 001
Revises:
Create Date: 2026-05-03 14:30:00

Première migration de Kuma Data Core. Crée la table ``contributeurs``
(auto-référente via ``cree_par``/``modifie_par``) et insère le seed
initial du contributeur principal. L'email du seed est paramétrable
via la variable d'environnement ``KUMA_INITIAL_EDITOR_EMAIL``, exposée
par ``Settings``.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import ARRAY

from kuma_data_core.core.config import get_settings

# revision identifiers, used by Alembic.
revision: str = "001"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # === Création de la table ===
    op.create_table(
        "contributeurs",
        # Identifiants
        sa.Column(
            "id",
            sa.BigInteger(),
            sa.Identity(always=False, start=1),
            nullable=False,
        ),
        sa.Column("code", sa.String(length=100), nullable=False),
        # Identité
        sa.Column("nom_complet", sa.Text(), nullable=False),
        sa.Column("nom_court", sa.Text(), nullable=True),
        sa.Column("email_principal", sa.Text(), nullable=False),
        # Type et statut
        sa.Column("type_contributeur", sa.String(length=50), nullable=False),
        sa.Column("statut", sa.String(length=50), nullable=False),
        # Profil
        sa.Column("biographie", sa.Text(), nullable=True),
        sa.Column("affiliation_principale", sa.Text(), nullable=True),
        sa.Column("pays_iso3", sa.String(length=3), nullable=True),
        sa.Column("url_publique", sa.Text(), nullable=True),
        sa.Column("orcid", sa.String(length=19), nullable=True),
        sa.Column("domaines_expertise", ARRAY(sa.Text()), nullable=True),
        # Engagement
        sa.Column("date_premier_engagement", sa.Date(), nullable=True),
        sa.Column("date_dernier_engagement", sa.Date(), nullable=True),
        sa.Column("notes_internes", sa.Text(), nullable=True),
        # Soft delete
        sa.Column(
            "actif",
            sa.Boolean(),
            server_default=sa.text("TRUE"),
            nullable=False,
        ),
        sa.Column("desactive_le", sa.DateTime(timezone=True), nullable=True),
        # Audit applicatif (FK auto-référentes vers contributeurs.id)
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
        # Contraintes nommées explicitement
        sa.PrimaryKeyConstraint("id", name="pk_contributeurs"),
        sa.UniqueConstraint("code", name="uq_contributeurs_code"),
        sa.UniqueConstraint("email_principal", name="uq_contributeurs_email_principal"),
        sa.ForeignKeyConstraint(
            ["cree_par"],
            ["contributeurs.id"],
            name="fk_contributeurs_cree_par__contributeurs",
        ),
        sa.ForeignKeyConstraint(
            ["modifie_par"],
            ["contributeurs.id"],
            name="fk_contributeurs_modifie_par__contributeurs",
        ),
        sa.CheckConstraint(
            "type_contributeur IN ("
            "'editeur_principal', 'contributeur_regulier', 'contributeur_invite', "
            "'expert_externe', 'institution', 'agent_automatique')",
            name="ck_contributeurs_type_valide",
        ),
        sa.CheckConstraint(
            "statut IN ('actif', 'inactif', 'archive', 'suspendu')",
            name="ck_contributeurs_statut_valide",
        ),
        sa.CheckConstraint(
            "(actif = TRUE AND desactive_le IS NULL) "
            "OR (actif = FALSE AND desactive_le IS NOT NULL)",
            name="ck_contributeurs_actif_desactive_coherent",
        ),
        sa.CheckConstraint(
            "pays_iso3 IS NULL OR pays_iso3 ~ '^[A-Z]{3}$'",
            name="ck_contributeurs_pays_iso3_format",
        ),
        sa.CheckConstraint(
            "orcid IS NULL OR orcid ~ '^[0-9]{4}-[0-9]{4}-[0-9]{4}-[0-9X]{4}$'",
            name="ck_contributeurs_orcid_format",
        ),
    )

    # === Index ===
    op.create_index("idx_contributeurs_actif", "contributeurs", ["actif"])
    op.create_index("idx_contributeurs_type_contributeur", "contributeurs", ["type_contributeur"])
    op.create_index("idx_contributeurs_statut", "contributeurs", ["statut"])
    op.create_index("idx_contributeurs_pays_iso3", "contributeurs", ["pays_iso3"])

    # === Seed initial : contributeur principal ===
    # Email lu depuis Settings (alimenté par .env, valeur de fallback
    # définie dans kuma_data_core.core.config). cree_par et modifie_par
    # restent NULL : le contributeur génétique n'a pas d'antécédent.
    initial_email = get_settings().kuma_initial_editor_email
    op.execute(
        sa.text(
            """
            INSERT INTO contributeurs (
                code, nom_complet, email_principal,
                type_contributeur, statut,
                date_premier_engagement,
                actif, cree_le, modifie_le
            ) VALUES (
                'siba_kalivogui',
                'Siba Kalivogui',
                :email,
                'editeur_principal',
                'actif',
                DATE '2026-05-01',
                TRUE, NOW(), NOW()
            )
            ON CONFLICT (code) DO NOTHING
            """
        ).bindparams(email=initial_email)
    )


def downgrade() -> None:
    # Les index et contraintes sont supprimés automatiquement avec la
    # table. On supprime explicitement les index nommés pour la
    # symétrie et la lisibilité du downgrade.
    op.drop_index("idx_contributeurs_pays_iso3", table_name="contributeurs")
    op.drop_index("idx_contributeurs_statut", table_name="contributeurs")
    op.drop_index("idx_contributeurs_type_contributeur", table_name="contributeurs")
    op.drop_index("idx_contributeurs_actif", table_name="contributeurs")
    op.drop_table("contributeurs")
