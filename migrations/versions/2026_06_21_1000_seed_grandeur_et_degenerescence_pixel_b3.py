"""seed_grandeur_et_degenerescence_pixel_b3

Revision ID: 090
Revises: 089
Create Date: 2026-06-21 10:00:00

Densification - indicateur de **degenerescence de pixel**,
2e couche d'honnetete de l'atlas (distincte de l'ecart inter-source). Montre ou la
donnee se repete (plusieurs prefectures dans la meme cellule source) vs ou elle est
reellement resolue.

Deux temps (enumeration exhaustive) :

1. **Declaration** de la grandeur ``degenerescence_pixel`` dans
   ``grandeurs_referentiel`` (famille F1, strategie ``calculee_volee``, unite
   ``sans_unite`` : un compte de jumeaux entier).
2. **Materialisation** dans ``grandeurs_metier`` via
   ``calculer_et_inserer_degenerescence`` : 1 ligne ``statique`` par (localite x
   source x parametre), ``valeur`` = nombre de jumeaux-pixel (0 = point resolu),
   ``niveau_confiance_derive='B'`` (A reservee aux mesures terrain ;
   la degenerescence est exacte mais reste B, son exactitude est dite par caveat -- pas
   par une remontee en A), le groupe de jumeaux + les caveats dans
   ``commentaire_editorial``.

Methode empirique : detection de series climato mensuelles **identiques**
(meme cellule = meme valeur sur grille fixe). Grilles fixes NASA (radiation CERES
1deg, meteo MERRA 0.5deg) -> compte mesure. Services interpoles SARAH-3 / CAMS
5 km -> compte 0 naturel + caveat de resolution. Calcul deterministe depuis
la base, aucun reseau (discipline alpha). Aucune DDL au-dela de l'INSERT grandeur :
``alembic check`` reste aligne.

Pas de nouvelle serie : ``series_metadonnees_id`` pointe la serie source climato
(precedent ``indicateur_qualite_donnees``).
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.orm import Session

from kuma_data_core.services.grandeurs.degenerescence_pixel import (
    GRANDEUR_DEGENERESCENCE,
    calculer_et_inserer_degenerescence,
)

# revision identifiers, used by Alembic.
revision: str = "090"
down_revision: str | Sequence[str] | None = "089"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_UNITE_CODE = "sans_unite"


def upgrade() -> None:
    bind = op.get_bind()

    # === 1. Declaration de la grandeur ====================================
    unite_id = bind.execute(
        sa.text("SELECT id FROM unites WHERE code = :code"),
        {"code": _UNITE_CODE},
    ).scalar_one_or_none()
    if unite_id is None:
        raise RuntimeError(f"Migration 090 : unite {_UNITE_CODE!r} introuvable (seed unites).")

    grandeurs_table = sa.table(
        "grandeurs_referentiel",
        sa.column("code", sa.String),
        sa.column("libelle", sa.Text),
        sa.column("famille", sa.String),
        sa.column("strategie_calcul", sa.String),
        sa.column("unite_id", sa.BigInteger),
        sa.column("description", sa.Text),
    )
    op.bulk_insert(
        grandeurs_table,
        [
            {
                "code": GRANDEUR_DEGENERESCENCE,
                "libelle": "Degenerescence de pixel (nombre de jumeaux-pixel)",
                "famille": "F1",
                "strategie_calcul": "calculee_volee",
                "unite_id": int(unite_id),
                "description": (
                    "Indicateur d'honnetete structurelle de l'atlas : pour une (localite, "
                    "source, parametre), nombre d'autres points partageant la meme cellule "
                    "source (0 = point reellement resolu). Detection empirique par identite de "
                    "series climato mensuelles sur grille fixe (NASA radiation CERES 1deg, "
                    "meteo MERRA 0.5deg). Services interpoles (SARAH-3 / CAMS 5 km) : compte "
                    "0 + caveat de resolution. F1 calculee_volee, materialisee statique, "
                    "confiance B (A reservee aux mesures terrain ; exactitude dite par "
                    "caveat, pas par une remontee en A)."
                    ""
                ),
            }
        ],
    )

    # === 2. Materialisation =================================================
    session = Session(bind=bind)
    try:
        total = calculer_et_inserer_degenerescence(session)
        session.commit()
        op.execute(
            f"-- Migration 090 : {total} lignes degenerescence_pixel inserees dans "
            f"grandeurs_metier (epine radiative aux 33, offline, deterministe)."
        )
    finally:
        session.close()


def downgrade() -> None:
    op.execute(
        sa.text("DELETE FROM grandeurs_metier WHERE grandeur_code = :code").bindparams(
            code=GRANDEUR_DEGENERESCENCE
        )
    )
    op.execute(
        sa.text("DELETE FROM grandeurs_referentiel WHERE code = :code").bindparams(
            code=GRANDEUR_DEGENERESCENCE
        )
    )
