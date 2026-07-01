"""etendre_check_sources_type_source_seed_kuma_calculs

Revision ID: 025
Revises: 024
Create Date: 2026-05-12 10:00:00.000000+00:00

Deux opérations cohérentes :

1. **Extension non destructive** du CHECK ``ck_sources_type_source_valide``
   (migration 004) : ajout de la valeur ``auteur_kuma`` aux 10 valeurs
   documentaires externes existantes. Pattern conforme
   (ajout d'une valeur dans une liste fermée VARCHAR + CHECK : drop +
   create_check_constraint avec la nouvelle liste).

2. **Seed** d'une nouvelle source ``kuma_calculs`` dans ``sources``, source
   synthétique représentant la couche éditoriale Kuma elle-même. Sera
   consommée par les séries HEP ``gin_<ville>_hep_kuma_calculs_*``
   et les autres grandeurs calculées Kuma.

Option retenue : extension de la liste fermée plutôt que réutilisation
d'une valeur documentaire existante qui aurait abusé la sémantique.

Pattern symétrique migration 006 (correction commentaire ``sources.fiabilite``
post-merge) : une migration corrective non destructive peut introduire
une valeur supplémentaire dans une liste catégorielle sans
modifier la migration d'origine.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "025"
down_revision: str | Sequence[str] | None = "024"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


_VALEURS_TYPE_SOURCE_INITIALES: tuple[str, ...] = (
    "rapport",
    "article_scientifique",
    "texte_legal",
    "communique",
    "page_web",
    "base_donnees",
    "livre",
    "chapitre_livre",
    "these",
    "norme_technique",
)
"""10 valeurs initiales du CHECK ``ck_sources_type_source_valide`` (migration 004)."""

_VALEUR_NOUVELLE_AUTEUR_KUMA: str = "auteur_kuma"
"""Valeur ajoutée : source synthétique représentant la couche
éditoriale Kuma."""

_VALEURS_TYPE_SOURCE_ETENDUES: tuple[str, ...] = (
    *_VALEURS_TYPE_SOURCE_INITIALES,
    _VALEUR_NOUVELLE_AUTEUR_KUMA,
)
"""11 valeurs après extension."""


_SOURCE_KUMA_CALCULS: dict[str, Any] = {
    "code": "kuma_calculs",
    "titre": "Kuma Science - Couche de calculs internes",
    "auteurs": ["Kuma Science"],
    "organisation": "Kuma Science",
    "type_source": _VALEUR_NOUVELLE_AUTEUR_KUMA,
    "fiabilite": "haute",
    "langue": "fr",
    "notes": (
        "Source synthetique representant la couche editoriale Kuma. "
        "Utilisee comme source primaire des series methode_collecte='calcul_derive' "
        "(HEP en 1-5 ; futures grandeurs calculees Kuma en 1-6+). "
        "Auto-evaluation fiabilite='haute' coherente avec la doctrine editoriale "
        "phase 1 (Kuma engage son autorite editoriale sur la correction du "
        "calcul, cf. cadrage phase 1 Principe 1). Acknowledgement des sources "
        "amont (par exemple gin_*_ghi_nasa_power_* pour HEP) trace par "
        "commentaire_editorial de chaque serie calculee."
    ),
}


def _liste_sql_check(valeurs: tuple[str, ...]) -> str:
    """Formate une liste de valeurs catégorielles pour un CHECK IN (...)."""
    return ", ".join(f"'{v}'" for v in valeurs)


def upgrade() -> None:
    # === 1. Extension du CHECK constraint (drop + recreate avec 11 valeurs) ===
    op.drop_constraint("ck_sources_type_source_valide", "sources", type_="check")
    op.create_check_constraint(
        "ck_sources_type_source_valide",
        "sources",
        f"type_source IN ({_liste_sql_check(_VALEURS_TYPE_SOURCE_ETENDUES)})",
    )

    # === 2. COMMENT ON COLUMN sources.type_source (documentation 11 valeurs) ===
    op.execute(
        "COMMENT ON COLUMN sources.type_source IS "
        "'11 valeurs autorisees : rapport, article_scientifique, texte_legal, "
        "communique, page_web, base_donnees, livre, chapitre_livre, these, "
        "norme_technique (10 valeurs documentaires externes initiales, "
        "migration 004) + auteur_kuma (couche editoriale interne Kuma, "
        "introduite en 1-5D-i pour la source synthetique kuma_calculs).'"
    )

    # === 3. Seed source kuma_calculs ===
    # Bulk INSERT via bind.execute (psycopg3 convertit list[str] -> ARRAY(text)
    # nativement pour la colonne sources.auteurs).
    bind = op.get_bind()
    bind.execute(
        sa.text(
            """
            INSERT INTO sources
                (code, titre, auteurs, organisation, type_source, fiabilite,
                 langue, notes)
            VALUES
                (:code, :titre, :auteurs, :organisation, :type_source,
                 :fiabilite, :langue, :notes)
            """
        ),
        _SOURCE_KUMA_CALCULS,
    )


def downgrade() -> None:
    # === 1. DELETE source kuma_calculs ===
    # Les migrations postérieures (026 seed séries, 027 ingestion HEP) auront
    # déjà été annulées en cascade par la procédure downgrade. Donc aucune
    # FK ne référence kuma_calculs.id à ce stade - DELETE direct.
    bind = op.get_bind()
    bind.execute(
        sa.text("DELETE FROM sources WHERE code = :code"),
        {"code": _SOURCE_KUMA_CALCULS["code"]},
    )

    # === 2. Retrait COMMENT ON COLUMN sources.type_source (statu quo migration 004) ===
    op.execute("COMMENT ON COLUMN sources.type_source IS NULL")

    # === 3. Restauration CHECK 10 valeurs initiales ===
    op.drop_constraint("ck_sources_type_source_valide", "sources", type_="check")
    op.create_check_constraint(
        "ck_sources_type_source_valide",
        "sources",
        f"type_source IN ({_liste_sql_check(_VALEURS_TYPE_SOURCE_INITIALES)})",
    )
