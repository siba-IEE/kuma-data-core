"""elargir_check_annee_mensuelles_1981

Revision ID: 104
Revises: 103
Create Date: 2026-08-09 10:00:00

Prealable au volet mensuel du chantier profondeur NASA POWER : la contrainte
``ck_mesures_ressource_mensuelles_annee_valide`` bornait ``annee`` a
``BETWEEN 1991 AND 2099`` (borne posee a la creation de la table, quand la
seule fenetre mensuelle etait la normale climato 1991-2020). La profondeur reelle de NASA POWER
mensuel commence en **1981** (meteo MERRA-2 : t2m, rh2m, vents,
precipitation ; sonde API du 2026-08-09), 1984 pour ghi/dhi, 2001 pour les
parametres CERES (dni, kt, albedo_surface).

Geste : DROP + re-CREATE de la contrainte CHECK avec ``BETWEEN 1981 AND 2099``.
Aucune donnee existante n'est affectee (minimum actuel en base : 1991).
Modele SQLAlchemy mis a jour en miroir (``mesures_ressource_mensuelles.py``),
sinon ``alembic check`` casse.

Downgrade : restaure la borne 1991. Necessite d'avoir d'abord downgrade la
migration de seed suivante (les mesures pre-1991 violeraient la contrainte
restauree) ; l'ordre inverse des revisions le garantit.
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "104"
down_revision: str | Sequence[str] | None = "103"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLE = "mesures_ressource_mensuelles"
_CONTRAINTE = "ck_mesures_ressource_mensuelles_annee_valide"


def upgrade() -> None:
    op.drop_constraint(_CONTRAINTE, _TABLE, type_="check")
    op.create_check_constraint(_CONTRAINTE, _TABLE, "annee BETWEEN 1981 AND 2099")


def downgrade() -> None:
    op.drop_constraint(_CONTRAINTE, _TABLE, type_="check")
    op.create_check_constraint(_CONTRAINTE, _TABLE, "annee BETWEEN 1991 AND 2099")
