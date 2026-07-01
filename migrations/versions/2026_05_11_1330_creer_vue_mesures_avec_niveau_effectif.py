"""creer_vue_mesures_avec_niveau_effectif

Revision ID: 017
Revises: 016
Create Date: 2026-05-11 13:30:00.000000+00:00

Crée la vue ``v_mesures_avec_niveau_effectif`` qui projette toutes les
colonnes de ``mesures_ressource`` + une colonne calculée
``niveau_effectif`` :

- ``niveau_effectif = COALESCE(niveau_confiance_override, niveau_confiance_derive)``

Équivalent SQL de la ``@hybrid_property niveau_effectif`` du modèle
``MesureRessource``. Permet aux requêtes lecture massives d'éviter le
scan applicatif Python.

Note de cadrage : l'ordre vue (017) puis ingestion (018) est retenu
par cohérence d'écriture (la vue ne dépend que
de la table créée en 014, l'ingestion vient logiquement après la
disponibilité de la vue pour consommation immédiate post-INSERT). Pas
d'impact fonctionnel.

Préfixe ``v_`` adopté pour les vues PostgreSQL, utilisé dès l'écriture
de la vue par cohérence avec le pattern annoncé.
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "017"
down_revision: str | Sequence[str] | None = "016"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        CREATE VIEW v_mesures_avec_niveau_effectif AS
        SELECT
            m.id,
            m.serie_id,
            m.instant_mesure,
            m.valeur,
            m.valide_du,
            m.valide_au,
            m.statut,
            m.niveau_confiance_derive,
            m.niveau_confiance_override,
            COALESCE(m.niveau_confiance_override, m.niveau_confiance_derive)
                AS niveau_effectif,
            m.commentaire_editorial,
            m.cree_le,
            m.cree_par,
            m.modifie_le,
            m.modifie_par
        FROM mesures_ressource AS m
        """
    )

    op.execute(
        "COMMENT ON VIEW v_mesures_avec_niveau_effectif IS "
        "'Vue projetant mesures_ressource + colonne calculee niveau_effectif = "
        "COALESCE(niveau_confiance_override, niveau_confiance_derive). "
        "Equivalent SQL de l''hybrid_property MesureRessource.niveau_effectif. "
        "Permet d''eviter le scan applicatif Python pour les requetes lecture "
        "massives. Cf. spec 1-2b sec. 3.4.'"
    )


def downgrade() -> None:
    op.execute("DROP VIEW IF EXISTS v_mesures_avec_niveau_effectif")
