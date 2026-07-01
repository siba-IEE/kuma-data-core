"""creer_table_sources

Revision ID: 004
Revises: 003
Create Date: 2026-05-04 14:30:00

Création de la table ``sources`` (référentiel des références
bibliographiques de Kuma Data Core). Pilier de la traçabilité
éditoriale : chaque mesure publiée doit pouvoir être tracée jusqu'à sa
source originale.

10 types de sources supportés : ``rapport``, ``article_scientifique``,
``texte_legal``, ``communique``, ``page_web``, ``base_donnees``,
``livre``, ``chapitre_livre``, ``these``, ``norme_technique``.

Décisions structurantes (D1-D11)
--------------------------------
* D1 - Pas de seed : les sources sont ajoutées via API.
* D2 - Polymorphisme via table unique + JSONB plutôt que tables
  séparées ou Single Table Inheritance ORM.
* D3 - ``type_source`` à 10 valeurs avec CHECK liste fermée.
* D4 - ``metadonnees`` doit être un objet JSON (pas scalaire ni
  tableau). La validation par type est déléguée à l'applicatif.
* D5 - Validation regex URL, DOI, ISBN. DOI sans préfixe URL,
  ISBN sans tirets - conventions documentées via ``COMMENT ON COLUMN``.
* D6 - Lien ``sources`` <-> ``localites`` différé : passera par la
  future table ``mesures``.
* D7 - ``fiabilite`` à 3 niveaux : ``haute``, ``moyenne``, ``faible``.
  Africa Energy Portal classé ``haute`` (porté par la BAD).
* D8 - ``langue`` au format ISO 639-1 strict : 2 lettres minuscules.
* D9 - ``annee_publication`` bornée 1900-2100, cohérent avec la 003.
* D10 - Versioning des sources évolutives via convention de ``code`` :
  une ligne par édition, ``<organisme>_<theme>[_<annee>]``.
* D11 - 6 index : ``actif``, ``type_source``, ``organisation``,
  ``annee_publication``, ``langue``, ``metadonnees`` (GIN).

Pas de champ ISSN : peut transiter par ``metadonnees->>'issn'``
(YAGNI en 004).
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql
from sqlalchemy.dialects.postgresql import ARRAY

# revision identifiers, used by Alembic.
revision: str = "004"
down_revision: str | Sequence[str] | None = "003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # === Création de la table ===
    op.create_table(
        "sources",
        # Identifiants
        sa.Column(
            "id",
            sa.BigInteger(),
            sa.Identity(always=False, start=1),
            nullable=False,
        ),
        sa.Column("code", sa.String(length=100), nullable=False),
        # Métier
        sa.Column("titre", sa.Text(), nullable=False),
        sa.Column("auteurs", ARRAY(sa.Text()), nullable=True),
        sa.Column("organisation", sa.String(length=255), nullable=True),
        sa.Column("type_source", sa.String(length=50), nullable=False),
        # Temporalité
        sa.Column("annee_publication", sa.Integer(), nullable=True),
        sa.Column("date_consultation", sa.Date(), nullable=True),
        # Identifiants externes
        sa.Column("url", sa.Text(), nullable=True),
        sa.Column("doi", sa.String(length=255), nullable=True),
        sa.Column("isbn", sa.String(length=50), nullable=True),
        # Métadonnées polymorphes
        sa.Column(
            "metadonnees",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
        # Qualification éditoriale
        sa.Column("fiabilite", sa.String(length=20), nullable=True),
        sa.Column("langue", sa.String(length=2), nullable=True),
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
        sa.PrimaryKeyConstraint("id", name="pk_sources"),
        sa.UniqueConstraint("code", name="uq_sources_code"),
        sa.ForeignKeyConstraint(
            ["cree_par"],
            ["contributeurs.id"],
            name="fk_sources_cree_par__contributeurs",
        ),
        sa.ForeignKeyConstraint(
            ["modifie_par"],
            ["contributeurs.id"],
            name="fk_sources_modifie_par__contributeurs",
        ),
        sa.CheckConstraint(
            "type_source IN ("
            "'rapport', 'article_scientifique', 'texte_legal', "
            "'communique', 'page_web', 'base_donnees', "
            "'livre', 'chapitre_livre', 'these', 'norme_technique')",
            name="ck_sources_type_source_valide",
        ),
        sa.CheckConstraint(
            "metadonnees IS NULL OR jsonb_typeof(metadonnees) = 'object'",
            name="ck_sources_metadonnees_objet",
        ),
        sa.CheckConstraint(
            r"url IS NULL OR url ~ '^https?://[^\s]+$'",
            name="ck_sources_url_format",
        ),
        sa.CheckConstraint(
            r"doi IS NULL OR doi ~ '^10\.[0-9]{4,}(\.[0-9]+)*/[^\s]+$'",
            name="ck_sources_doi_format",
        ),
        sa.CheckConstraint(
            "isbn IS NULL OR isbn ~ '^(97[89][0-9]{10}|[0-9]{9}[0-9X])$'",
            name="ck_sources_isbn_format",
        ),
        sa.CheckConstraint(
            "fiabilite IS NULL OR fiabilite IN ('haute', 'moyenne', 'faible')",
            name="ck_sources_fiabilite_valide",
        ),
        sa.CheckConstraint(
            "langue IS NULL OR langue ~ '^[a-z]{2}$'",
            name="ck_sources_langue_format_iso6391",
        ),
        sa.CheckConstraint(
            "annee_publication IS NULL OR annee_publication BETWEEN 1900 AND 2100",
            name="ck_sources_annee_publication_valide",
        ),
        sa.CheckConstraint(
            "(actif = TRUE AND desactive_le IS NULL) "
            "OR (actif = FALSE AND desactive_le IS NOT NULL)",
            name="ck_sources_actif_desactive_le",
        ),
    )

    # === Index ===
    op.create_index("idx_sources_actif", "sources", ["actif"])
    op.create_index("idx_sources_type_source", "sources", ["type_source"])
    op.create_index("idx_sources_organisation", "sources", ["organisation"])
    op.create_index("idx_sources_annee_publication", "sources", ["annee_publication"])
    op.create_index("idx_sources_langue", "sources", ["langue"])
    op.create_index(
        "idx_sources_metadonnees_gin",
        "sources",
        ["metadonnees"],
        postgresql_using="gin",
    )

    # === Commentaires de documentation ===
    # ASCII pur, apostrophes francaises doublees pour SQL standard.
    op.execute(
        "COMMENT ON COLUMN sources.code IS "
        "'Identifiant court unique. Convention : <organisme>_<theme>[_<annee>]. "
        "Ex: irena_lcoe_2024, bcrg_rapport_annuel_2023, iso_50001_2018. "
        "Pour les publications recurrentes, inclure l''annee.'"
    )
    op.execute(
        "COMMENT ON COLUMN sources.doi IS "
        "'Digital Object Identifier (ISO 26324). Stocke sans prefixe URL. "
        "Ex: 10.1038/nature12373 (pas https://doi.org/10.1038/nature12373).'"
    )
    op.execute(
        "COMMENT ON COLUMN sources.isbn IS "
        "'International Standard Book Number (ISO 2108). "
        "Stocke sans tirets ni espaces. "
        "Ex: 9782123456789 (pas 978-2-1234-5678-9). "
        "ISBN-10 ou ISBN-13 acceptes.'"
    )
    op.execute(
        "COMMENT ON COLUMN sources.fiabilite IS "
        "'Qualification editoriale Kuma (3 niveaux). "
        "Voir docs/architecture/04.md pour le mapping editorial complet.'"
    )
    op.execute(
        "COMMENT ON COLUMN sources.langue IS "
        "'Code ISO 639-1 (2 lettres minuscules). "
        "Ex: fr, en, ar, pt, sw, yo, wo.'"
    )


def downgrade() -> None:
    op.drop_index("idx_sources_metadonnees_gin", table_name="sources")
    op.drop_index("idx_sources_langue", table_name="sources")
    op.drop_index("idx_sources_annee_publication", table_name="sources")
    op.drop_index("idx_sources_organisation", table_name="sources")
    op.drop_index("idx_sources_type_source", table_name="sources")
    op.drop_index("idx_sources_actif", table_name="sources")
    op.drop_table("sources")
