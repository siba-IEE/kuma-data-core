"""creer_table_grandeurs_metier

Revision ID: 023
Revises: 022
Create Date: 2026-05-12 09:00:00.000000+00:00

Crée la table ``grandeurs_metier`` - première table de fabrication
éditoriale Kuma. Stocke les grandeurs F1
``strategie_calcul='stockee'`` calculées par Kuma à partir des mesures
brutes (typiquement HEP, autres F1 stockées ultérieurement).

Identité métier étendue : 7-uplet ``(grandeur_code, localite_id,
periode_type, annee_debut, annee_fin, COALESCE(mois, 0),
version_formule)`` avec
``tstzrange(valide_du, valide_au) WITH &&`` pour le versioning temporel.
Permet la coexistence des lignes v1 et v2 d'une même formule après
upgrade ``version_formule_actuelle`` dans ``grandeurs_referentiel``
(« les anciennes lignes restent en base pour audit »).

Superpose les 3 mécaniques transverses (statut éditorial,
versioning temporel, niveau de confiance dérive/override).

Pré-requis :
- extension ``btree_gist`` activée (migration 013) ;
- fonction ``kuma_log_audit()`` (migration 005) ;
- table ``grandeurs_referentiel`` (migration 007, seedée 010 + 015) ;
- table ``localites`` (migration 003, seedée 011) ;
- table ``series_metadonnees`` (migration 008).
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "023"
down_revision: str | Sequence[str] | None = "022"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "grandeurs_metier",
        # === Identifiant ===
        sa.Column(
            "id",
            sa.BigInteger(),
            sa.Identity(start=1, increment=1),
            primary_key=True,
        ),
        # === Identité métier ===
        sa.Column("grandeur_code", sa.String(length=80), nullable=False),
        sa.Column("localite_id", sa.BigInteger(), nullable=False),
        sa.Column("series_metadonnees_id", sa.BigInteger(), nullable=False),
        sa.Column("periode_type", sa.String(length=8), nullable=False),
        sa.Column("annee_debut", sa.Integer(), nullable=False),
        sa.Column("annee_fin", sa.Integer(), nullable=False),
        sa.Column("mois", sa.Integer(), nullable=True),
        sa.Column("version_formule", sa.Integer(), nullable=False),
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
            ["grandeur_code"],
            ["grandeurs_referentiel.code"],
            name="fk_grandeurs_metier_grandeur_code__grandeurs_referentiel",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["localite_id"],
            ["localites.id"],
            name="fk_grandeurs_metier_localite_id__localites",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["series_metadonnees_id"],
            ["series_metadonnees.id"],
            name="fk_grandeurs_metier_series_metadonnees_id__series_metadonnees",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["cree_par"],
            ["contributeurs.id"],
            name="fk_grandeurs_metier_cree_par__contributeurs",
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["modifie_par"],
            ["contributeurs.id"],
            name="fk_grandeurs_metier_modifie_par__contributeurs",
            ondelete="SET NULL",
        ),
        # === CHECK constraints ===
        sa.CheckConstraint(
            "periode_type IN ('mensuel', 'annuel')",
            name="ck_grandeurs_metier_periode_type_valide",
        ),
        sa.CheckConstraint(
            "(periode_type = 'annuel' AND mois IS NULL) "
            "OR (periode_type = 'mensuel' AND mois IS NOT NULL AND mois BETWEEN 1 AND 12)",
            name="ck_grandeurs_metier_periode_coherente",
        ),
        sa.CheckConstraint(
            "annee_fin >= annee_debut",
            name="ck_grandeurs_metier_annees_coherentes",
        ),
        sa.CheckConstraint(
            "version_formule >= 1",
            name="ck_grandeurs_metier_version_formule_positive",
        ),
        sa.CheckConstraint(
            "statut IN ('brut', 'valide_auto', 'valide_humain', 'publie', 'deprecie')",
            name="ck_grandeurs_metier_statut_valide",
        ),
        sa.CheckConstraint(
            "niveau_confiance_derive IN ('A', 'B', 'C')",
            name="ck_grandeurs_metier_niveau_confiance_derive_valide",
        ),
        sa.CheckConstraint(
            "niveau_confiance_override IS NULL OR niveau_confiance_override IN ('A', 'B', 'C')",
            name="ck_grandeurs_metier_niveau_confiance_override_valide",
        ),
        sa.CheckConstraint(
            "valide_au IS NULL OR valide_au > valide_du",
            name="ck_grandeurs_metier_periode_validite_coherente",
        ),
        comment=(
            "Grandeurs metier calculees par Kuma a partir des mesures brutes. "
            "Premiere table de fabrication editoriale phase 1 (etape 1-5). "
            "F1 stockee, agregations annuelles et mensuelles. Versioning "
            "temporel par (valide_du, valide_au) + EXCLUDE BTree-GiST sur "
            "identite metier etendue avec version_formule. Statut editorial "
            "et niveau de confiance derive/override par couche service editoriale."
        ),
    )

    # === EXCLUDE BTree-GiST sur identité métier étendue + période ===
    # Pas directement supporté en op.create_table via sa.ExcludeConstraint
    # avec opérateurs sur tstzrange et COALESCE(mois, 0) ; on pose la
    # contrainte via DDL brut (pattern cohérent avec migration 014
    # mesures_ressource).
    op.execute(
        """
        ALTER TABLE grandeurs_metier
        ADD CONSTRAINT ex_grandeurs_metier_identite_periode
        EXCLUDE USING gist (
            grandeur_code WITH =,
            localite_id WITH =,
            periode_type WITH =,
            annee_debut WITH =,
            annee_fin WITH =,
            COALESCE(mois, 0) WITH =,
            version_formule WITH =,
            tstzrange(valide_du, valide_au) WITH &&
        )
        """
    )

    # === Index partiel sur lignes courantes ===
    op.create_index(
        "idx_grandeurs_metier_courantes",
        "grandeurs_metier",
        [
            "grandeur_code",
            "localite_id",
            "periode_type",
            "annee_debut",
            "annee_fin",
            "mois",
            "version_formule",
        ],
        postgresql_where=sa.text("valide_au IS NULL"),
    )

    # === Trigger d'audit (fonction kuma_log_audit posée en migration 005) ===
    op.execute(
        """
        CREATE TRIGGER trg_audit_grandeurs_metier
            AFTER INSERT OR UPDATE OR DELETE ON grandeurs_metier
            FOR EACH ROW EXECUTE FUNCTION kuma_log_audit()
        """
    )

    # === Commentaires SQL sur les colonnes structurantes (ASCII pur) ===
    op.execute(
        """
        COMMENT ON COLUMN grandeurs_metier.periode_type IS
            'Granularite temporelle de l''agregation : annuel (1 ligne par '
            '(localite, grandeur, annee, version_formule), mois NULL) ou '
            'mensuel (12 lignes par annee, mois 1-12). Cf. cadrage phase 1 '
            'Q2 et Q6.'
        """
    )
    op.execute(
        """
        COMMENT ON COLUMN grandeurs_metier.version_formule IS
            'Version de la formule de calcul en vigueur au moment de '
            'l''insertion. Lien implicite avec '
            'grandeurs_referentiel.version_formule_actuelle pour la grandeur '
            'concernee. Incremente lors de toute revision methodologique. '
            'Inclus dans l''EXCLUDE pour permettre la coexistence v1/v2 '
            'apres upgrade (spec 1-5 sec. 3.2, cadrage Q7).'
        """
    )
    op.execute(
        """
        COMMENT ON COLUMN grandeurs_metier.statut IS
            'Statut editorial Kuma : brut (calcule non valide), valide_auto '
            '(controle qualite automatique passe), valide_humain (validation '
            'editoriale humaine), publie (publie publiquement), deprecie '
            '(retire du circuit editorial). Transitions encadrees par la '
            'couche service Python (cf. kuma_data_core.editorial.statuts).'
        """
    )
    op.execute(
        """
        COMMENT ON COLUMN grandeurs_metier.niveau_confiance_derive IS
            'Niveau de confiance derive automatiquement par la couche service '
            'a partir des regles R1-R4 (cf. spec mecaniques-transverses-phase-1 '
            'sec. 6.4). A = haute, B = moyenne, C = basse. Recalcule a chaque '
            'modification de methode_collecte ou source_id de la serie.'
        """
    )
    op.execute(
        """
        COMMENT ON COLUMN grandeurs_metier.niveau_confiance_override IS
            'Override editorial du niveau derive. NULL = pas override (valeur '
            'effective = derive). Sinon valeur effective = override. Pose par '
            'la fonction service overrider_niveau_confiance avec justification '
            'obligatoire dans commentaire_editorial.'
        """
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_audit_grandeurs_metier ON grandeurs_metier")
    op.drop_index("idx_grandeurs_metier_courantes", table_name="grandeurs_metier")
    op.execute(
        "ALTER TABLE grandeurs_metier "
        "DROP CONSTRAINT IF EXISTS ex_grandeurs_metier_identite_periode"
    )
    op.drop_table("grandeurs_metier")
