"""etendre_uq_series_metadonnees_periode_temporelle

Revision ID: 040
Revises: 039
Create Date: 2026-05-15 09:30:00.000000+00:00

Migration corrective UNIQUE sur ``series_metadonnees``
(drift attrapé pré-implémentation).

La contrainte initiale ``uq_series_metadonnees_localite_id_grandeur_code_source_id``
posée à la création de la table en migration 008 impose
une série unique par triplet ``(localite_id, grandeur_code, source_id)``.
Cette forme convenait aux 66 séries existantes où
chaque (localité, grandeur, source) correspondait à une plage temporelle
unique implicite.

Drift identifié : l'insertion de
2 séries NASA POWER GHI distinctes par localité (daily 2021-2025
existante + monthly 1991-2020 nouvelle) - toutes deux ``(localité,
ghi, nasa_power)``. La contrainte initiale interdit cette coexistence.

Résolution Option A : extension de la clé UNIQUE pour
inclure ``(periode_debut, periode_fin)``, ce qui distingue désormais
les séries par leur plage temporelle couverte.

Vérification factuelle préalable : 0 doublon sur la clé augmentée
parmi les 66 séries existantes → modification
rétro-compatible.
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "040"
down_revision: str | Sequence[str] | None = "039"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_constraint(
        "uq_series_metadonnees_localite_id_grandeur_code_source_id",
        "series_metadonnees",
        type_="unique",
    )
    op.create_unique_constraint(
        "uq_series_metadonnees_identite_metier_plage",
        "series_metadonnees",
        ["localite_id", "grandeur_code", "source_id", "periode_debut", "periode_fin"],
    )


def downgrade() -> None:
    op.drop_constraint(
        "uq_series_metadonnees_identite_metier_plage",
        "series_metadonnees",
        type_="unique",
    )
    op.create_unique_constraint(
        "uq_series_metadonnees_localite_id_grandeur_code_source_id",
        "series_metadonnees",
        ["localite_id", "grandeur_code", "source_id"],
    )
