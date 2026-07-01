"""creer_table_unites

Revision ID: 002
Revises: 001
Create Date: 2026-05-03 15:45:00

Création de la table ``unites`` (référentiel des unités de mesure de
Kuma Data Core) et seed exhaustif des 153 unités validées contre 20+
organismes normatifs internationaux (BIPM, AIE, ONU, NIST, IUPAC, IEC,
DIN, ISO, IPCC, IRENA, UNECE, etc.).

Couverture : 30 grandeurs physiques, économiques, environnementales.

Décisions structurantes (voir docs et seed_data pour le détail) :
- Classification ``systeme`` à 5 valeurs : SI, non_SI_acceptee,
  composee_mixte, imperial, autre.
- Colonne ``est_unite_de_base`` (BOOLEAN) avec contrainte CHECK de
  cohérence : seules les unités SI peuvent être de base.
- Type ``Numeric(60, 30)`` pour les facteurs/décalages : précision
  décimale exacte couvrant à la fois ``electronvolt`` (1.602e-19) et
  ``quad`` (1.055e+18). Voir docstring du modèle ``Unite`` pour la
  justification complète.
- Stratégie 2 (seed exhaustif dans la migration via ``op.bulk_insert``).
- 5 SI de base seedées : seconde, metre, kilogramme, ampere, kelvin.
- Conventions pragmatiques :
  * intensite_carbone -> gCO2/kWh (pas kg/J)
  * irradiation_solaire -> MJ/m²/jour
  * pouvoir_calorifique -> PCI par défaut
  * devises -> Stratégie B (chaque devise est sa propre référence)
  * ordre du seed -> GNF prioritaire (signal éditorial Kuma)
- Aliases sémantiques (NON seedés ici, à porter au niveau mesure
  ultérieurement via un champ ``convention``) : travail, chaleur,
  energie_electrique -> energie ; puissance_active -> puissance ;
  capacite_stockage_electrique -> charge_electrique ;
  facteur_puissance -> sans_dimension ; vitesse_vent -> vitesse ;
  hauteur_chute -> longueur ; cout_actualise_energie (LCOE),
  tarif_soutirage, tarif_rachat -> cout_unitaire_energie.
- Grandeurs mineures non couvertes (à ajouter ultérieurement) :
  densite_energie, densite_puissance, conductance_electrique,
  capacite_electrique.

Note de transcription métrologique sur ``quad`` :
Le facteur appliqué ici est 1.05505585262e18 J (= 10^15 BTU_IT × 1055,05585262
J/BTU). La valeur 1.05505585262e15 que l'on rencontre parfois confond
le BTU lui-même (10^3 J) avec le joule. Sanity check : la consommation
énergétique des USA 100 quad/an correspond à 100 EJ/an, conforme
aux bilans EIA et AIE.

``cree_par`` et ``modifie_par`` restent NULL : les unités primordiales
sont seedées par la migration et n'ont pas d'antécédent humain
identifiable, comme le contributeur génétique de la migration 001.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import ARRAY

from kuma_data_core.db.seeds.unites_seed_data import UNITES_SEED

# revision identifiers, used by Alembic.
revision: str = "002"
down_revision: str | Sequence[str] | None = "001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # === Création de la table ===
    op.create_table(
        "unites",
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
        sa.Column("symbole", sa.String(length=50), nullable=False),
        sa.Column("grandeur", sa.String(length=100), nullable=False),
        sa.Column("systeme", sa.String(length=20), nullable=False),
        sa.Column(
            "est_unite_de_base",
            sa.Boolean(),
            server_default=sa.text("FALSE"),
            nullable=False,
        ),
        # Conversion vers l'unité de référence interne
        # Numeric(60, 30) : couvre 1.602e-19 (eV) à 1.055e+18 (quad)
        # sans perte de précision décimale.
        sa.Column(
            "facteur_conversion_si",
            sa.Numeric(60, 30),
            server_default=sa.text("1"),
            nullable=False,
        ),
        sa.Column(
            "decalage_conversion_si",
            sa.Numeric(60, 30),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column("code_unite_si", sa.String(length=80), nullable=False),
        # Notes éditoriales
        sa.Column("note_methodologique", sa.Text(), nullable=True),
        sa.Column("contexte_usage", sa.Text(), nullable=True),
        sa.Column("references_normatives", ARRAY(sa.Text()), nullable=True),
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
        sa.PrimaryKeyConstraint("id", name="pk_unites"),
        sa.UniqueConstraint("code", name="uq_unites_code"),
        sa.ForeignKeyConstraint(
            ["cree_par"],
            ["contributeurs.id"],
            name="fk_unites_cree_par__contributeurs",
        ),
        sa.ForeignKeyConstraint(
            ["modifie_par"],
            ["contributeurs.id"],
            name="fk_unites_modifie_par__contributeurs",
        ),
        sa.CheckConstraint(
            "systeme IN ('SI', 'non_SI_acceptee', 'composee_mixte', 'imperial', 'autre')",
            name="ck_unites_systeme_valide",
        ),
        sa.CheckConstraint(
            "(est_unite_de_base = TRUE AND systeme = 'SI') OR (est_unite_de_base = FALSE)",
            name="ck_unites_base_coherence_systeme",
        ),
        sa.CheckConstraint(
            "(actif = TRUE AND desactive_le IS NULL) "
            "OR (actif = FALSE AND desactive_le IS NOT NULL)",
            name="ck_unites_actif_desactive_le",
        ),
    )

    # === Index ===
    op.create_index("idx_unites_actif", "unites", ["actif"])
    op.create_index("idx_unites_grandeur", "unites", ["grandeur"])
    op.create_index("idx_unites_systeme", "unites", ["systeme"])
    op.create_index(
        "idx_unites_est_unite_de_base",
        "unites",
        ["est_unite_de_base"],
        postgresql_where=sa.text("est_unite_de_base = TRUE"),
    )
    op.create_index("idx_unites_code_unite_si", "unites", ["code_unite_si"])

    # === Commentaire de table (utile pour les outils d'introspection) ===
    op.execute(
        "COMMENT ON TABLE unites IS "
        "'Référentiel des unités de mesure de Kuma Data Core. "
        "153 unités sur 30 grandeurs, validées contre 20+ organismes "
        "normatifs internationaux (BIPM, AIE, ONU, NIST, IUPAC, IEC, "
        "DIN, ISO, IPCC, IRENA, UNECE, etc.).'"
    )

    # === Seed exhaustif des 153 unités ===
    _seed_unites()


def downgrade() -> None:
    op.drop_index("idx_unites_code_unite_si", table_name="unites")
    op.drop_index("idx_unites_est_unite_de_base", table_name="unites")
    op.drop_index("idx_unites_systeme", table_name="unites")
    op.drop_index("idx_unites_grandeur", table_name="unites")
    op.drop_index("idx_unites_actif", table_name="unites")
    op.drop_table("unites")


def _seed_unites() -> None:
    """Insère les 153 unités via ``op.bulk_insert``.

    L'ordre de ``UNITES_SEED`` (importé depuis le module de seed) est
    stratégique : SI fondamentales d'abord, puis les grandeurs au cœur
    de Kuma (énergie, puissance, solaire, électricité), puis mécanique
    et carbone, et enfin les économiques avec GNF prioritaire (signal
    éditorial Kuma Science depuis la Guinée).
    """
    unites_table = sa.table(
        "unites",
        sa.column("code", sa.String),
        sa.column("libelle", sa.Text),
        sa.column("symbole", sa.String),
        sa.column("grandeur", sa.String),
        sa.column("systeme", sa.String),
        sa.column("est_unite_de_base", sa.Boolean),
        sa.column("facteur_conversion_si", sa.Numeric(60, 30)),
        sa.column("decalage_conversion_si", sa.Numeric(60, 30)),
        sa.column("code_unite_si", sa.String),
        sa.column("note_methodologique", sa.Text),
        sa.column("references_normatives", ARRAY(sa.Text())),
    )
    op.bulk_insert(unites_table, UNITES_SEED)
