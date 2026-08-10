"""etendre_uq_series_identite_granularite

Revision ID: 106
Revises: 105
Create Date: 2026-08-09 17:00:00

Migration corrective UNIQUE sur ``series_metadonnees`` (drift attrape
pre-implementation du backfill journalier, meme geste que la migration 040).

La contrainte ``uq_series_metadonnees_identite_metier_plage`` (posee en 040)
impose une serie unique par ``(localite_id, grandeur_code, source_id,
periode_debut, periode_fin)``. Cette forme convenait tant que chaque paire
granularites d'une meme (localite, grandeur, source) couvrait des plages
distinctes.

Drift identifie : le backfill journalier profondeur (migration suivante) pose
des series dni/kt/albedo_surface **2001-01-01 -> 2020-12-31** en granularite
``journalier``, plage strictement identique aux normales mensuelles
2001-2020 deja en base (050/087) pour les memes (localite, grandeur,
source). La contrainte actuelle interdit cette coexistence pourtant
legitime : ``granularite`` est le discriminant de routage table-cible du
modele, il appartient a l'identite metier d'une serie.

Resolution (option A de 040, etendue) : la cle UNIQUE devient
``(localite_id, grandeur_code, source_id, periode_debut, periode_fin,
granularite)``, sous le nom
``uq_series_metadonnees_identite_metier_plage_granularite``.

Retro-compatible par construction : on ajoute une colonne a une cle deja
unique, aucun doublon possible parmi les series existantes. Nuance
PostgreSQL : ``granularite`` est NULL pour les series ``kuma_calculs``
(temporalite portee par ``grandeurs_metier``) et les NULL sont distincts
sous UNIQUE ; pour ces series, la garde forte reste l'unicite du ``code``.

Modele SQLAlchemy mis a jour en miroir (``series_metadonnees.py``), sinon
``alembic check`` casse.
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "106"
down_revision: str | Sequence[str] | None = "105"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLE = "series_metadonnees"
_ANCIEN_NOM = "uq_series_metadonnees_identite_metier_plage"
_NOUVEAU_NOM = "uq_series_metadonnees_identite_metier_plage_granularite"
_COLONNES_ANCIENNES = ["localite_id", "grandeur_code", "source_id", "periode_debut", "periode_fin"]
_COLONNES_NOUVELLES = [*_COLONNES_ANCIENNES, "granularite"]


def upgrade() -> None:
    op.drop_constraint(_ANCIEN_NOM, _TABLE, type_="unique")
    op.create_unique_constraint(_NOUVEAU_NOM, _TABLE, _COLONNES_NOUVELLES)


def downgrade() -> None:
    op.drop_constraint(_NOUVEAU_NOM, _TABLE, type_="unique")
    op.create_unique_constraint(_ANCIEN_NOM, _TABLE, _COLONNES_ANCIENNES)
