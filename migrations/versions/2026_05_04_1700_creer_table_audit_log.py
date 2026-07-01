"""creer_table_audit_log

Revision ID: 005
Revises: 004
Create Date: 2026-05-04 17:00:00

Pose l'infrastructure d'audit de Kuma Data Core :

* Table ``audit_log`` (granularité hybride : ``valeurs_avant``,
  ``valeurs_apres``, ``champs_modifies`` en JSONB).
* Cinq index couvrant les cas d'usage (par table, par horodatage, par
  utilisateur PG, par auteur applicatif partiel, par ligne auditée).
* Fonction PL/pgSQL générique ``kuma_log_audit()``.
* Quatre triggers ``AFTER INSERT OR UPDATE OR DELETE`` sur les tables
  socles : ``sources``, ``localites``, ``unites``, ``contributeurs``.

Mécanisme
---------
Les triggers row-level appellent la fonction générique qui écrit une
ligne dans ``audit_log`` à chaque modification effective. Les UPDATE
sans changement réel (``UPDATE ... SET col = col``) ne créent aucune
entrée. L'auteur applicatif est récupéré via
``current_setting('kuma.auteur_applicatif', true)`` (NULL si non
positionné).

Convention requise (voir docs/conventions/01-naming.md)
-------------------------------------------------------
Toute table auditée doit avoir une PK auto-incrémentée nommée ``id``,
de type ``BIGINT IDENTITY``. La fonction d'audit utilise
``OLD.id::TEXT`` / ``NEW.id::TEXT`` pour construire la référence
``audit_log.id_ligne_auditee``. Les 4 tables socles respectent déjà
cette convention.

Sécurité
--------
La fonction est créée en ``SECURITY DEFINER`` : elle s'exécute avec
les droits du rôle propriétaire (ici ``kuma_admin``).
La protection en INSERT-only de ``audit_log`` reposera sur des
GRANT/REVOKE PostgreSQL (séparation des rôles). Voir
``docs/architecture/03-audit.md`` section « Dettes anticipées ».

Audit non récursif : aucun trigger n'est posé sur ``audit_log``
elle-même (éviterait une boucle infinie sur INSERT).
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import INET, JSONB

# revision identifiers, used by Alembic.
revision: str = "005"
down_revision: str | Sequence[str] | None = "004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# Liste des tables socles auditées par cette migration. Centralisée
# pour que upgrade() et downgrade() restent symétriques.
_TABLES_AUDITEES: tuple[str, ...] = (
    "sources",
    "localites",
    "unites",
    "contributeurs",
)


def upgrade() -> None:
    # === 1. Création de la table audit_log ===
    op.create_table(
        "audit_log",
        sa.Column(
            "id",
            sa.BigInteger(),
            sa.Identity(always=False, start=1),
            nullable=False,
        ),
        # Identification de la modification
        sa.Column("table_auditee", sa.Text(), nullable=False),
        sa.Column(
            "schema_audite",
            sa.Text(),
            nullable=False,
            server_default=sa.text("'public'"),
        ),
        sa.Column("type_operation", sa.CHAR(length=1), nullable=False),
        sa.Column("id_ligne_auditee", sa.Text(), nullable=False),
        # Contenu de la modification (granularité hybride)
        sa.Column("champs_modifies", JSONB, nullable=True),
        sa.Column("valeurs_avant", JSONB, nullable=True),
        sa.Column("valeurs_apres", JSONB, nullable=True),
        # Identification de l'auteur (combinaison)
        sa.Column("utilisateur_pg", sa.Text(), nullable=False),
        sa.Column("auteur_applicatif", sa.Text(), nullable=True),
        sa.Column("adresse_client", INET, nullable=True),
        # Horodatage : clock_timestamp() (instant réel) et non now()
        # (début de transaction). Important pour les batchs.
        sa.Column(
            "horodatage",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("clock_timestamp()"),
        ),
        sa.PrimaryKeyConstraint("id", name="pk_audit_log"),
        sa.CheckConstraint(
            "type_operation IN ('I', 'U', 'D')",
            name="ck_audit_log_type_operation",
        ),
    )

    # === 2. Index ===
    # Utilisation de op.execute() pour un alignement strict sur le SQL
    # de la spec (DESC, WHERE partiel) et éviter toute surprise de
    # génération côté Alembic.
    op.execute(
        """
        CREATE INDEX idx_audit_log_table_horodatage
            ON audit_log (schema_audite, table_auditee, horodatage DESC)
        """
    )
    op.execute(
        """
        CREATE INDEX idx_audit_log_horodatage
            ON audit_log (horodatage DESC)
        """
    )
    op.execute(
        """
        CREATE INDEX idx_audit_log_utilisateur_pg
            ON audit_log (utilisateur_pg, horodatage DESC)
        """
    )
    op.execute(
        """
        CREATE INDEX idx_audit_log_auteur_applicatif
            ON audit_log (auteur_applicatif, horodatage DESC)
            WHERE auteur_applicatif IS NOT NULL
        """
    )
    op.execute(
        """
        CREATE INDEX idx_audit_log_ligne
            ON audit_log (
                schema_audite, table_auditee, id_ligne_auditee, horodatage DESC
            )
        """
    )

    # === 3. Fonction PL/pgSQL générique ===
    op.execute(
        """
        CREATE OR REPLACE FUNCTION kuma_log_audit() RETURNS TRIGGER AS $$
        DECLARE
            v_id_ligne TEXT;
            v_avant JSONB;
            v_apres JSONB;
            v_modifies JSONB;
            v_auteur_app TEXT;
        BEGIN
            -- Identifiant de la ligne auditée
            -- On suppose une colonne 'id' sur les tables auditées
            -- (convention Kuma Data Core : voir 01-naming.md).
            IF TG_OP = 'DELETE' THEN
                v_id_ligne := OLD.id::TEXT;
            ELSE
                v_id_ligne := NEW.id::TEXT;
            END IF;

            -- Construction des JSONB selon l'opération
            IF TG_OP = 'INSERT' THEN
                v_avant := NULL;
                v_apres := to_jsonb(NEW);
                v_modifies := NULL;

            ELSIF TG_OP = 'UPDATE' THEN
                v_avant := to_jsonb(OLD);
                v_apres := to_jsonb(NEW);

                -- Calcul des champs réellement modifiés
                SELECT jsonb_object_agg(
                    key,
                    jsonb_build_array(v_avant -> key, v_apres -> key)
                )
                INTO v_modifies
                FROM jsonb_object_keys(v_apres) AS key
                WHERE v_avant -> key IS DISTINCT FROM v_apres -> key;

                -- Si aucun champ n'a changé (UPDATE sans modification effective),
                -- on ne crée pas d'entrée d'audit
                IF v_modifies IS NULL OR v_modifies = '{}'::JSONB THEN
                    RETURN NULL;
                END IF;

            ELSIF TG_OP = 'DELETE' THEN
                v_avant := to_jsonb(OLD);
                v_apres := NULL;
                v_modifies := NULL;
            END IF;

            -- Identifiant applicatif (peut être absent)
            BEGIN
                v_auteur_app := current_setting('kuma.auteur_applicatif', true);
                IF v_auteur_app = '' THEN
                    v_auteur_app := NULL;
                END IF;
            EXCEPTION WHEN OTHERS THEN
                v_auteur_app := NULL;
            END;

            -- Insertion dans audit_log
            INSERT INTO audit_log (
                table_auditee,
                schema_audite,
                type_operation,
                id_ligne_auditee,
                champs_modifies,
                valeurs_avant,
                valeurs_apres,
                utilisateur_pg,
                auteur_applicatif,
                adresse_client
            ) VALUES (
                TG_TABLE_NAME,
                TG_TABLE_SCHEMA,
                LEFT(TG_OP, 1),
                v_id_ligne,
                v_modifies,
                v_avant,
                v_apres,
                current_user,
                v_auteur_app,
                inet_client_addr()
            );

            RETURN NULL;  -- AFTER trigger : valeur de retour ignorée
        END;
        $$ LANGUAGE plpgsql SECURITY DEFINER;
        """
    )

    op.execute(
        """
        COMMENT ON FUNCTION kuma_log_audit() IS
            'Fonction generique d''audit Kuma Data Core. A utiliser en AFTER trigger '
            'sur les tables structurantes. Suppose une colonne id (PK) sur la table auditee.'
        """
    )

    # === 4. Triggers sur les 4 tables socles ===
    for table in _TABLES_AUDITEES:
        op.execute(
            f"""
            CREATE TRIGGER trg_audit_{table}
                AFTER INSERT OR UPDATE OR DELETE ON {table}
                FOR EACH ROW EXECUTE FUNCTION kuma_log_audit()
            """
        )


def downgrade() -> None:
    # Symétrie stricte : triggers -> fonction -> table (les index
    # sont supprimés en cascade avec la table).

    # 1. Suppression des triggers (ordre inverse de la création).
    for table in reversed(_TABLES_AUDITEES):
        op.execute(f"DROP TRIGGER IF EXISTS trg_audit_{table} ON {table}")

    # 2. Suppression de la fonction.
    op.execute("DROP FUNCTION IF EXISTS kuma_log_audit()")

    # 3. Suppression de la table (les index suivent en cascade).
    op.drop_table("audit_log")
