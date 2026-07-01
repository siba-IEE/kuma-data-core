"""creer_vue_grandeurs_metier_courantes

Revision ID: 024
Revises: 023
Create Date: 2026-05-12 09:30:00.000000+00:00

Crée la vue ``v_grandeurs_metier_courantes`` qui projette les lignes
courantes de ``grandeurs_metier`` avec filtrage triple :

- ``valide_au IS NULL`` (ligne ouverte, versioning temporel).
- ``version_formule = grandeurs_referentiel.version_formule_actuelle``
  (formule en vigueur).
- ``statut <> 'deprecie'`` (non retirée du circuit éditorial).

Ajoute une colonne calculée ``niveau_effectif = COALESCE(
niveau_confiance_override, niveau_confiance_derive)``. Pattern et
nomenclature symétriques à la vue ``v_mesures_avec_niveau_effectif``
(migration 017) et à la ``@hybrid_property niveau_effectif`` de
``GrandeurMetier``. Choix de ``niveau_effectif`` pour cohérence stricte
avec le pattern existant et avec la hybrid property du modèle ORM
(lecture homogène entre ORM et SQL direct).

Préfixe ``v_`` pour les vues (convention ``01-naming.md``).

Pré-requis : table ``grandeurs_metier`` (migration 023), table
``grandeurs_referentiel`` (migration 007, colonne
``version_formule_actuelle`` introduite dans ce même DDL).
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "024"
down_revision: str | Sequence[str] | None = "023"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        CREATE VIEW v_grandeurs_metier_courantes AS
        SELECT
            gm.id,
            gm.grandeur_code,
            gm.localite_id,
            gm.series_metadonnees_id,
            gm.periode_type,
            gm.annee_debut,
            gm.annee_fin,
            gm.mois,
            gm.version_formule,
            gm.valeur,
            gm.valide_du,
            gm.valide_au,
            gm.statut,
            gm.niveau_confiance_derive,
            gm.niveau_confiance_override,
            COALESCE(gm.niveau_confiance_override, gm.niveau_confiance_derive)
                AS niveau_effectif,
            gm.commentaire_editorial,
            gm.cree_le,
            gm.cree_par,
            gm.modifie_le,
            gm.modifie_par
        FROM grandeurs_metier AS gm
        JOIN grandeurs_referentiel AS gr ON gr.code = gm.grandeur_code
        WHERE gm.valide_au IS NULL
          AND gm.version_formule = gr.version_formule_actuelle
          AND gm.statut <> 'deprecie'
        """
    )

    op.execute(
        "COMMENT ON VIEW v_grandeurs_metier_courantes IS "
        "'Vue projetant les lignes courantes de grandeurs_metier (valide_au "
        "IS NULL) en version de formule actuelle (version_formule = "
        "grandeurs_referentiel.version_formule_actuelle) et hors statut "
        "deprecie. Ajoute la colonne calculee niveau_effectif = "
        "COALESCE(niveau_confiance_override, niveau_confiance_derive). "
        "Equivalent SQL de l''hybrid_property GrandeurMetier.niveau_effectif. "
        "Cf. spec 1-5 sec. 4.'"
    )


def downgrade() -> None:
    op.execute("DROP VIEW IF EXISTS v_grandeurs_metier_courantes")
