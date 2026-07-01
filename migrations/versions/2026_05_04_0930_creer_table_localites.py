"""creer_table_localites

Revision ID: 003
Revises: 002
Create Date: 2026-05-04 09:30:00

Création de la table ``localites`` (référentiel des localités
géographiques de Kuma Data Core). 6 niveaux hiérarchiques supportés :
``continent``, ``region_supranationale``, ``pays``,
``region_administrative``, ``commune``, ``site``.

Décisions structurantes (D1-D11)
--------------------------------
* D1 - Pas de seed : les localités sont ajoutées via API
  (ou scripts d'ingestion dédiés).
* D2 - FK ``localite_id`` sur ``contributeurs`` reportée en migration
  005 dédiée (séparation des préoccupations).
* D3 - ``type_localite`` à 6 valeurs avec CHECK
  (``ck_localites_type_valide``).
* D4 - Validation hiérarchique en deux étages :
    - Ici : CHECK simple (un ``continent`` ne peut avoir de parent).
    - Migration 007 : trigger PL/pgSQL ``valider_hierarchie_localites()``
      pour la matrice parent-enfant complète et la détection de boucles
      via ``WITH RECURSIVE``.
* D5 - Coordonnées ``Numeric(11, 8)`` / ``Numeric(12, 8)`` avec bornes
  CHECK (1 mm de précision à l'équateur).
* D6 - ``pays_iso3`` validé par regex ``^[A-Z]{3}$`` (cohérent avec
  ``contributeurs``).
* D7 - Démographie cohérente : ``population_estimee`` et
  ``annee_population`` sont soit toutes deux NULL, soit toutes deux
  NOT NULL (CHECK ``ck_localites_demographie_coherente``).
* D8 - ``code`` en convention hybride : ISO 3166-1 alpha-3 minuscule
  pour les pays, ``<code_pays>_<slug>`` pour le sous-national. Format
  général imposé par regex ``^[a-z][a-z0-9_]*$``.
* D9 - ``nom_local`` du brief v1 supprimé : Kuma publie en français.
  Internationalisation différée à une table ``localites_traductions``
  ultérieure.
* D10 - 4 index : ``actif``, ``type_localite``, ``pays_iso3``,
  ``parent_id``. L'index unique sur ``code`` est généré
  automatiquement par la contrainte ``UNIQUE``.
* D11 - ``fuseau_horaire`` au format IANA Time Zone Database
  (``Africa/Conakry``, ``Europe/Paris``...). Pas de CHECK : la liste
  IANA évolue.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "003"
down_revision: str | Sequence[str] | None = "002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # === Création de la table ===
    op.create_table(
        "localites",
        # Identifiants
        sa.Column(
            "id",
            sa.BigInteger(),
            sa.Identity(always=False, start=1),
            nullable=False,
        ),
        sa.Column("code", sa.String(length=100), nullable=False),
        # Métier
        sa.Column("nom", sa.Text(), nullable=False),
        sa.Column("type_localite", sa.String(length=50), nullable=False),
        sa.Column("parent_id", sa.BigInteger(), nullable=True),
        # Géographie
        sa.Column("pays_iso3", sa.String(length=3), nullable=True),
        sa.Column("latitude", sa.Numeric(11, 8), nullable=True),
        sa.Column("longitude", sa.Numeric(12, 8), nullable=True),
        sa.Column("altitude_metres", sa.Integer(), nullable=True),
        # Démographie
        sa.Column("population_estimee", sa.Integer(), nullable=True),
        sa.Column("annee_population", sa.Integer(), nullable=True),
        # Métadonnées
        sa.Column("fuseau_horaire", sa.String(length=50), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
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
        # Contraintes nommées
        sa.PrimaryKeyConstraint("id", name="pk_localites"),
        sa.UniqueConstraint("code", name="uq_localites_code"),
        sa.ForeignKeyConstraint(
            ["parent_id"],
            ["localites.id"],
            name="fk_localites_parent_id__localites",
        ),
        sa.ForeignKeyConstraint(
            ["cree_par"],
            ["contributeurs.id"],
            name="fk_localites_cree_par__contributeurs",
        ),
        sa.ForeignKeyConstraint(
            ["modifie_par"],
            ["contributeurs.id"],
            name="fk_localites_modifie_par__contributeurs",
        ),
        sa.CheckConstraint(
            "type_localite IN ("
            "'continent', 'region_supranationale', 'pays', "
            "'region_administrative', 'commune', 'site')",
            name="ck_localites_type_valide",
        ),
        sa.CheckConstraint(
            "(type_localite = 'continent' AND parent_id IS NULL) OR (type_localite != 'continent')",
            name="ck_localites_continent_racine",
        ),
        sa.CheckConstraint(
            "latitude IS NULL OR (latitude BETWEEN -90 AND 90)",
            name="ck_localites_latitude_bornes",
        ),
        sa.CheckConstraint(
            "longitude IS NULL OR (longitude BETWEEN -180 AND 180)",
            name="ck_localites_longitude_bornes",
        ),
        sa.CheckConstraint(
            "pays_iso3 IS NULL OR pays_iso3 ~ '^[A-Z]{3}$'",
            name="ck_localites_pays_iso3_format",
        ),
        sa.CheckConstraint(
            "population_estimee IS NULL OR population_estimee >= 0",
            name="ck_localites_population_positive",
        ),
        sa.CheckConstraint(
            "annee_population IS NULL OR (annee_population BETWEEN 1900 AND 2100)",
            name="ck_localites_annee_population_bornes",
        ),
        sa.CheckConstraint(
            "(population_estimee IS NULL AND annee_population IS NULL) "
            "OR (population_estimee IS NOT NULL "
            "AND annee_population IS NOT NULL)",
            name="ck_localites_demographie_coherente",
        ),
        sa.CheckConstraint(
            "code ~ '^[a-z][a-z0-9_]*$'",
            name="ck_localites_code_format",
        ),
        sa.CheckConstraint(
            "(actif = TRUE AND desactive_le IS NULL) "
            "OR (actif = FALSE AND desactive_le IS NOT NULL)",
            name="ck_localites_actif_desactive_le",
        ),
    )

    # === Index ===
    op.create_index("idx_localites_actif", "localites", ["actif"])
    op.create_index("idx_localites_type_localite", "localites", ["type_localite"])
    op.create_index("idx_localites_pays_iso3", "localites", ["pays_iso3"])
    op.create_index("idx_localites_parent_id", "localites", ["parent_id"])


def downgrade() -> None:
    op.drop_index("idx_localites_parent_id", table_name="localites")
    op.drop_index("idx_localites_pays_iso3", table_name="localites")
    op.drop_index("idx_localites_type_localite", table_name="localites")
    op.drop_index("idx_localites_actif", table_name="localites")
    op.drop_table("localites")
