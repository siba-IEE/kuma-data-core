"""etendre_exclude_grandeurs_metier_series_metadonnees_id

Revision ID: 037
Revises: 036
Create Date: 2026-05-14 09:30:00.000000+00:00

Extension de la contrainte ``ex_grandeurs_metier_identite_periode`` par
ajout de ``series_metadonnees_id WITH =`` a la cle GiST.

Posee initialement en migration 023, la cle EXCLUDE actuelle est :

```
EXCLUDE USING gist (
    grandeur_code WITH =,
    localite_id WITH =,
    periode_type WITH =,
    annee_debut WITH =,
    annee_fin WITH =,
    COALESCE(mois, 0) WITH =,
    version_formule WITH =,
    tstzrange(valide_du, valide_au) WITH &&
)
```

Cette forme suffit pour les grandeurs calculees Kuma (`hep`,
`fraction_diffuse`, `humidex`, `productible_specifique_theorique`,
`variabilite_journaliere`) ou la convention veut **1 serie calculee
par (localite, grandeur)** : 1 ligne par identite metier coincide
avec 1 serie pointee.

Drift identifie a l'execution : la grandeur
``indicateur_qualite_donnees`` pointe **plusieurs
series brutes par localite** (6 brutes NASA POWER GHI/DNI/DHI/T2M/RH2M/KT
par ville pilote). La cle EXCLUDE actuelle interdit donc plus d'une
ligne ``indicateur_qualite_donnees`` par (localite, periode, version),
incompatible avec les 36 lignes prescrites.

Resolution Option A : ajout de ``series_metadonnees_id``
a la cle EXCLUDE. Permet la coexistence de plusieurs lignes
``grandeurs_metier`` partageant la meme identite metier (grandeur,
localite, periode, version) tant qu'elles pointent des series
``series_metadonnees`` distinctes.

Verification factuelle prealable : 0 doublon hypothetique sur
les 1 578 lignes courantes avec la cle augmentee. La
modification est retro-compatible.
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "037"
down_revision: str | Sequence[str] | None = "036"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("ALTER TABLE grandeurs_metier DROP CONSTRAINT ex_grandeurs_metier_identite_periode")
    op.execute(
        """
        ALTER TABLE grandeurs_metier
        ADD CONSTRAINT ex_grandeurs_metier_identite_periode
        EXCLUDE USING gist (
            grandeur_code WITH =,
            localite_id WITH =,
            series_metadonnees_id WITH =,
            periode_type WITH =,
            annee_debut WITH =,
            annee_fin WITH =,
            COALESCE(mois, 0) WITH =,
            version_formule WITH =,
            tstzrange(valide_du, valide_au) WITH &&
        )
        """
    )


def downgrade() -> None:
    op.execute("ALTER TABLE grandeurs_metier DROP CONSTRAINT ex_grandeurs_metier_identite_periode")
    op.execute(
        """
        ALTER TABLE grandeurs_metier
        ADD CONSTRAINT ex_grandeurs_metier_identite_periode
        EXCLUDE USING gist (
            grandeur_code WITH =,
            localite_id WITH =,
            periode_type WITH =,
            annee_debut WITH =,
            annee_fin WITH =,
            COALESCE(mois, 0) WITH =,
            version_formule WITH =,
            tstzrange(valide_du, valide_au) WITH &&
        )
        """
    )
