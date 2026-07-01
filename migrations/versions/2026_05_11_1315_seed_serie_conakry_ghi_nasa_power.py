"""seed_serie_conakry_ghi_nasa_power_et_check_methode_collecte

Revision ID: 016
Revises: 015
Create Date: 2026-05-11 13:15:00.000000+00:00

Deux opérations atomiques :

1. **CHECK constraint** ``ck_series_metadonnees_methode_collecte_valide``
   sur ``series_metadonnees.methode_collecte`` : 6 valeurs anticipées.
   La colonne reste nullable
   (cohérent avec le modèle mergé) ; le CHECK admet NULL.

2. **Seed** d'une ligne unique dans ``series_metadonnees`` pour la
   série pivot : ``gin_conakry_ghi_nasa_power_2021_2025``.
   Pattern de résolution dynamique des codes naturels en IDs hérité
   des migrations 010 et 011 (les IDs ``IDENTITY`` ne sont pas stables
   entre environnements).
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date
from typing import Any

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "016"
down_revision: str | Sequence[str] | None = "015"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# Liste exhaustive des 6 valeurs autorisées.
METHODES_COLLECTE_AUTORISEES: tuple[str, ...] = (
    "mesure_directe",
    "modele_satellitaire",
    "interpolation_geographique",
    "extrapolation_temporelle",
    "calcul_derive",
    "expertise_humaine",
)

# Définition de la série pivot (résolution code -> id dynamique)
_SERIE_CONAKRY_GHI: dict[str, Any] = {
    "code": "gin_conakry_ghi_nasa_power_2021_2025",
    "libelle": "GHI journalier Conakry-Kaloum 2021-2025 (NASA POWER)",
    "localite_code": "gin_conakry_kaloum",
    "grandeur_code": "ghi",
    "source_code": "nasa_power",
    "periode_debut": date(2021, 1, 1),
    "periode_fin": date(2025, 12, 31),
    "methode_collecte": "modele_satellitaire",
    "methode_collecte_doc": "https://power.larc.nasa.gov/docs/methodology/",
    "commentaire_editorial": (
        "Premiere serie Kuma ingeree en phase 1. Source pivot solaire phase 1. "
        "Spike 1-2a a valide la viabilite technique (latence P95 1.7s) et la "
        "qualite semantique (cross-check ERA5 correlation 0.964 Conakry, biais "
        "-2.87%). Acknowledgement NASA POWER cf. fiche source seedee en 1-1E."
    ),
    "url_documentation": "https://power.larc.nasa.gov/",
}


def upgrade() -> None:
    bind = op.get_bind()

    # === 1. CHECK constraint methode_collecte ===
    liste_valeurs_sql = ", ".join(f"'{v}'" for v in METHODES_COLLECTE_AUTORISEES)
    op.create_check_constraint(
        "ck_series_metadonnees_methode_collecte_valide",
        "series_metadonnees",
        f"methode_collecte IS NULL OR methode_collecte IN ({liste_valeurs_sql})",
    )

    # === 2. Résolution code -> id pour localite, grandeur (key=code), source ===
    localite_id = bind.execute(
        sa.text("SELECT id FROM localites WHERE code = :code"),
        {"code": _SERIE_CONAKRY_GHI["localite_code"]},
    ).scalar_one_or_none()
    if localite_id is None:
        raise RuntimeError(
            f"Migration 016 : localite_code "
            f"{_SERIE_CONAKRY_GHI['localite_code']!r} introuvable. Verifier "
            f"que la migration 011 a bien ete appliquee."
        )

    grandeur_existe = bind.execute(
        sa.text("SELECT 1 FROM grandeurs_referentiel WHERE code = :code"),
        {"code": _SERIE_CONAKRY_GHI["grandeur_code"]},
    ).scalar_one_or_none()
    if grandeur_existe is None:
        raise RuntimeError(
            f"Migration 016 : grandeur_code {_SERIE_CONAKRY_GHI['grandeur_code']!r} "
            f"introuvable dans grandeurs_referentiel. Verifier que la "
            f"migration 015 a bien ete appliquee."
        )

    source_id = bind.execute(
        sa.text("SELECT id FROM sources WHERE code = :code"),
        {"code": _SERIE_CONAKRY_GHI["source_code"]},
    ).scalar_one_or_none()
    if source_id is None:
        raise RuntimeError(
            f"Migration 016 : source_code {_SERIE_CONAKRY_GHI['source_code']!r} "
            f"introuvable dans sources. Verifier que la migration 012 a bien "
            f"ete appliquee."
        )

    # === 3. INSERT de la série ===
    series_metadonnees_table = sa.table(
        "series_metadonnees",
        sa.column("code", sa.String),
        sa.column("libelle", sa.Text),
        sa.column("localite_id", sa.BigInteger),
        sa.column("grandeur_code", sa.String),
        sa.column("source_id", sa.BigInteger),
        sa.column("periode_debut", sa.Date),
        sa.column("periode_fin", sa.Date),
        sa.column("methode_collecte", sa.String),
        sa.column("methode_collecte_doc", sa.Text),
        sa.column("commentaire_editorial", sa.Text),
        sa.column("url_documentation", sa.Text),
    )
    ligne_a_inserer: dict[str, Any] = {
        "code": _SERIE_CONAKRY_GHI["code"],
        "libelle": _SERIE_CONAKRY_GHI["libelle"],
        "localite_id": localite_id,
        "grandeur_code": _SERIE_CONAKRY_GHI["grandeur_code"],
        "source_id": source_id,
        "periode_debut": _SERIE_CONAKRY_GHI["periode_debut"],
        "periode_fin": _SERIE_CONAKRY_GHI["periode_fin"],
        "methode_collecte": _SERIE_CONAKRY_GHI["methode_collecte"],
        "methode_collecte_doc": _SERIE_CONAKRY_GHI["methode_collecte_doc"],
        "commentaire_editorial": _SERIE_CONAKRY_GHI["commentaire_editorial"],
        "url_documentation": _SERIE_CONAKRY_GHI["url_documentation"],
    }
    op.bulk_insert(series_metadonnees_table, [ligne_a_inserer])


def downgrade() -> None:
    op.execute(
        sa.text("DELETE FROM series_metadonnees WHERE code = :code").bindparams(
            sa.bindparam("code", value=_SERIE_CONAKRY_GHI["code"])
        )
    )
    op.drop_constraint(
        "ck_series_metadonnees_methode_collecte_valide",
        "series_metadonnees",
        type_="check",
    )
