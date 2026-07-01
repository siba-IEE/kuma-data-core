"""creer_table_grandeurs_referentiel

Revision ID: 007
Revises: 006
Create Date: 2026-05-07 20:35:00

Crée la table
``grandeurs_referentiel`` : référentiel statique des grandeurs
solaires/climatiques traduites par Kuma (15 entrées prévues).

La table est citée en aval par ``series_metadonnees.grandeur_code``,
``mesures_ressource.grandeur_code`` et
``grandeurs_metier.grandeur_code`` via la clé naturelle
``code``.

Décisions structurantes
-----------------------
* D1 - ``strategie_calcul`` (``VARCHAR(16) CHECK IN ('stockee',
  'calculee_volee')``), orthogonale à ``famille``. Distingue les
  grandeurs F1 stockées dans ``grandeurs_metier`` de celles calculées
  à la volée (écart relatif, rang). Aucune combinaison
  ``(famille, strategie_calcul)`` interdite par CHECK.
* PK ``id BIGINT IDENTITY``
  + ``code VARCHAR(80) UNIQUE NOT NULL``. La fonction d'audit
  ``kuma_log_audit()`` (migration 005) suppose une colonne ``id`` sur
  les tables auditées (cf. ``docs/conventions/01-naming.md`` §*Audit
  et convention de PK pour les tables auditées*). La clé naturelle
  ``code`` reste la cible des FK aval.
* Conventions ``01-naming.md`` - ``VARCHAR + CHECK`` pour les
  catégoriels (jamais ``CREATE TYPE ... AS ENUM``), suffixe
  ``_valide`` sur les CHECK de listes fermées (``famille``,
  ``strategie_calcul``), descriptif libre sur les CHECK
  multi-colonnes (``actif_desactive_coherent``,
  ``version_formule_positive``).

Trigger d'audit
---------------
La fonction ``kuma_log_audit()`` créée en migration 005 n'est PAS
recréée. Le trigger ``trg_audit_grandeurs_referentiel`` est posé
dans la présente migration : la liste ``_TABLES_AUDITEES`` de la
migration 005 reste immuable (cf. ``docs/conventions/02-migrations.md``
§*Une migration mergée n'est plus modifiée*).

Hors-scope
----------
Aucun seed dans cette migration. Pas de table
``series_metadonnees``. Pas de contrainte cross-table
``grandeurs_metier.grandeur_code ⊂ {strategie_calcul='stockee'}``.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "007"
down_revision: str | Sequence[str] | None = "006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # === 1. Création de la table ===
    op.create_table(
        "grandeurs_referentiel",
        # Identifiants
        sa.Column(
            "id",
            sa.BigInteger(),
            sa.Identity(always=False, start=1),
            nullable=False,
        ),
        sa.Column("code", sa.String(length=80), nullable=False),
        # Métier
        sa.Column("libelle", sa.Text(), nullable=False),
        sa.Column("unite_id", sa.BigInteger(), nullable=False),
        sa.Column("famille", sa.String(length=2), nullable=False),
        sa.Column("strategie_calcul", sa.String(length=16), nullable=False),
        sa.Column("methode_calcul_doc", sa.Text(), nullable=True),
        sa.Column(
            "version_formule_actuelle",
            sa.Integer(),
            server_default=sa.text("1"),
            nullable=False,
        ),
        sa.Column("description", sa.Text(), nullable=True),
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
        # Contraintes nommées : PK -> UNIQUE -> FK -> CHECK
        sa.PrimaryKeyConstraint("id", name="pk_grandeurs_referentiel"),
        sa.UniqueConstraint("code", name="uq_grandeurs_referentiel_code"),
        sa.ForeignKeyConstraint(
            ["unite_id"],
            ["unites.id"],
            name="fk_grandeurs_referentiel_unite_id__unites",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["cree_par"],
            ["contributeurs.id"],
            name="fk_grandeurs_referentiel_cree_par__contributeurs",
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["modifie_par"],
            ["contributeurs.id"],
            name="fk_grandeurs_referentiel_modifie_par__contributeurs",
            ondelete="SET NULL",
        ),
        sa.CheckConstraint(
            "famille IN ('F1', 'F2')",
            name="ck_grandeurs_referentiel_famille_valide",
        ),
        sa.CheckConstraint(
            "strategie_calcul IN ('stockee', 'calculee_volee')",
            name="ck_grandeurs_referentiel_strategie_calcul_valide",
        ),
        sa.CheckConstraint(
            "version_formule_actuelle >= 1",
            name="ck_grandeurs_referentiel_version_formule_positive",
        ),
        sa.CheckConstraint(
            "(actif = TRUE AND desactive_le IS NULL) "
            "OR (actif = FALSE AND desactive_le IS NOT NULL)",
            name="ck_grandeurs_referentiel_actif_desactive_coherent",
        ),
    )

    # === 2. Index ===
    op.create_index(
        "idx_grandeurs_referentiel_actif",
        "grandeurs_referentiel",
        ["actif"],
    )

    # === 3. Trigger d'audit ===
    # La fonction kuma_log_audit() est créée en migration 005 et n'est
    # pas recréée ici. La liste _TABLES_AUDITEES de la migration 005
    # reste immuable (convention d'immuabilité des migrations mergées).
    op.execute(
        """
        CREATE TRIGGER trg_audit_grandeurs_referentiel
            AFTER INSERT OR UPDATE OR DELETE ON grandeurs_referentiel
            FOR EACH ROW EXECUTE FUNCTION kuma_log_audit()
        """
    )

    # === 4. Commentaires de documentation ===
    op.execute(
        "COMMENT ON TABLE grandeurs_referentiel IS "
        "'Referentiel statique des grandeurs traduites Kuma "
        "(15 entrees en phase 1).'"
    )
    op.execute(
        "COMMENT ON COLUMN grandeurs_referentiel.code IS "
        "'Cle naturelle metier (ASCII pur, snake_case, citee par les FK "
        "aval). Cf. 01-naming.md section Codes metier des referentiels.'"
    )
    op.execute(
        "COMMENT ON COLUMN grandeurs_referentiel.libelle IS "
        "'Titre humain de la grandeur (accents et casse normale "
        "autorises).'"
    )
    op.execute(
        "COMMENT ON COLUMN grandeurs_referentiel.famille IS "
        "'F1 : grandeur ontologique (mesuree ou derivee simple). "
        "F2 : grandeur parametree (calcul necessitant des parametres "
        "utilisateur).'"
    )
    op.execute(
        "COMMENT ON COLUMN grandeurs_referentiel.strategie_calcul IS "
        "'stockee : valeur persistee dans grandeurs_metier. "
        "calculee_volee : recalculee a chaque consultation, dependante "
        "du perimetre.'"
    )
    op.execute(
        "COMMENT ON COLUMN grandeurs_referentiel.version_formule_actuelle IS "
        "'Compteur applicatif de la formule en vigueur. Incremente a "
        "chaque revision methodologique. Initial : 1.'"
    )


def downgrade() -> None:
    # Symétrie stricte : trigger -> index -> table.

    # 1. Suppression du trigger.
    op.execute("DROP TRIGGER IF EXISTS trg_audit_grandeurs_referentiel ON grandeurs_referentiel")

    # 2. Suppression de l'index.
    op.drop_index(
        "idx_grandeurs_referentiel_actif",
        table_name="grandeurs_referentiel",
    )

    # 3. Suppression de la table (contraintes en cascade).
    op.drop_table("grandeurs_referentiel")
