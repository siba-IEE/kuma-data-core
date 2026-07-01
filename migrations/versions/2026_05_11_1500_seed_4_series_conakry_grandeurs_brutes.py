"""seed_4_series_conakry_grandeurs_brutes

Revision ID: 019
Revises: 018
Create Date: 2026-05-11 15:00:00.000000+00:00

Seed des 4 nouvelles séries Conakry pour les grandeurs brutes DNI, DHI,
T2M, RH2M. Élargit le périmètre qui n'avait seedé que
``gin_conakry_ghi_nasa_power_2021_2025`` (migration 016).

Pattern hérité de la migration 016 : résolution dynamique des codes
naturels (``localite_code``, ``grandeur_code``, ``source_code``) en
IDs via SELECT.

Toutes les séries partagent :
- localite_code = ``gin_conakry_kaloum``
- source_code = ``nasa_power``
- periode_debut = 2021-01-01
- periode_fin = 2025-12-31
- methode_collecte = ``modele_satellitaire``
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date
from typing import Any

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "019"
down_revision: str | Sequence[str] | None = "018"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# Énumération exhaustive des 4 nouvelles séries.
_SERIES_1_3: list[dict[str, Any]] = [
    {
        "code": "gin_conakry_dni_nasa_power_2021_2025",
        "libelle": "DNI journalier Conakry-Kaloum 2021-2025 (NASA POWER)",
        "grandeur_code": "dni",
        "commentaire_editorial": (
            "Serie etendue en etape 1-3 sur le pattern de gin_conakry_ghi_nasa_"
            "power_2021_2025 (1-2b). Donnee brute DNI (ALLSKY_SFC_SW_DNI) "
            "ingeree depuis NASA POWER, methode satellitaire CERES SYN1deg. "
            "Entree du calcul POA parametrable F2 (etape 1-7)."
        ),
    },
    {
        "code": "gin_conakry_dhi_nasa_power_2021_2025",
        "libelle": "DHI journalier Conakry-Kaloum 2021-2025 (NASA POWER)",
        "grandeur_code": "dhi",
        "commentaire_editorial": (
            "Serie etendue en etape 1-3. Donnee brute DHI (ALLSKY_SFC_SW_DIFF) "
            "ingeree depuis NASA POWER, composant diffus CERES SYN1deg. "
            "Entree du calcul fraction_diffuse F1 stockee et du POA "
            "parametrable F2."
        ),
    },
    {
        "code": "gin_conakry_t2m_nasa_power_2021_2025",
        "libelle": "Temperature 2m journaliere Conakry-Kaloum 2021-2025 (NASA POWER)",
        "grandeur_code": "t2m",
        "commentaire_editorial": (
            "Serie etendue en etape 1-3. Donnee brute T2M ingeree depuis "
            "NASA POWER, source MERRA-2 GMAO. Entree du calcul humidex F1 "
            "stockee et du productible avec correction thermique F2."
        ),
    },
    {
        "code": "gin_conakry_rh2m_nasa_power_2021_2025",
        "libelle": "Humidite relative 2m journaliere Conakry-Kaloum 2021-2025 (NASA POWER)",
        "grandeur_code": "rh2m",
        "commentaire_editorial": (
            "Serie etendue en etape 1-3. Donnee brute RH2M ingeree depuis "
            "NASA POWER, source MERRA-2 GMAO. Entree du calcul humidex F1 "
            "stockee (formule Masterton & Richardson 1979)."
        ),
    },
]

_LOCALITE_CODE: str = "gin_conakry_kaloum"
_SOURCE_CODE: str = "nasa_power"
_PERIODE_DEBUT: date = date(2021, 1, 1)
_PERIODE_FIN: date = date(2025, 12, 31)
_METHODE_COLLECTE: str = "modele_satellitaire"
_METHODE_COLLECTE_DOC: str = "https://power.larc.nasa.gov/docs/methodology/"
_URL_DOCUMENTATION: str = "https://power.larc.nasa.gov/"


def upgrade() -> None:
    bind = op.get_bind()

    # === Résolution localite_id, source_id (uniques pour les 4 séries) ===
    localite_id = bind.execute(
        sa.text("SELECT id FROM localites WHERE code = :code"),
        {"code": _LOCALITE_CODE},
    ).scalar_one_or_none()
    if localite_id is None:
        raise RuntimeError(
            f"Migration 019 : localite_code {_LOCALITE_CODE!r} introuvable. "
            f"Verifier que la migration 011 a bien ete appliquee."
        )

    source_id = bind.execute(
        sa.text("SELECT id FROM sources WHERE code = :code"),
        {"code": _SOURCE_CODE},
    ).scalar_one_or_none()
    if source_id is None:
        raise RuntimeError(
            f"Migration 019 : source_code {_SOURCE_CODE!r} introuvable. "
            f"Verifier que la migration 012 a bien ete appliquee."
        )

    # === Vérification que chaque grandeur_code existe dans grandeurs_referentiel ===
    grandeur_codes_attendus = {s["grandeur_code"] for s in _SERIES_1_3}
    grandeurs_trouvees = set(
        bind.execute(
            sa.text("SELECT code FROM grandeurs_referentiel WHERE code = ANY(:codes)"),
            {"codes": list(grandeur_codes_attendus)},
        )
        .scalars()
        .all()
    )
    grandeurs_manquantes = grandeur_codes_attendus - grandeurs_trouvees
    if grandeurs_manquantes:
        raise RuntimeError(
            f"Migration 019 : grandeur_code(s) introuvable(s) dans "
            f"grandeurs_referentiel : {sorted(grandeurs_manquantes)}. "
            f"Verifier que la migration 015 a bien ete appliquee."
        )

    # === Construction des 4 lignes à insérer ===
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

    lignes_a_inserer: list[dict[str, Any]] = []
    for s in _SERIES_1_3:
        lignes_a_inserer.append(
            {
                "code": s["code"],
                "libelle": s["libelle"],
                "localite_id": localite_id,
                "grandeur_code": s["grandeur_code"],
                "source_id": source_id,
                "periode_debut": _PERIODE_DEBUT,
                "periode_fin": _PERIODE_FIN,
                "methode_collecte": _METHODE_COLLECTE,
                "methode_collecte_doc": _METHODE_COLLECTE_DOC,
                "commentaire_editorial": s["commentaire_editorial"],
                "url_documentation": _URL_DOCUMENTATION,
            }
        )

    op.bulk_insert(series_metadonnees_table, lignes_a_inserer)


def downgrade() -> None:
    codes_supprimer = [s["code"] for s in _SERIES_1_3]
    op.execute(
        sa.text("DELETE FROM series_metadonnees WHERE code = ANY(:codes)").bindparams(
            sa.bindparam("codes", value=codes_supprimer)
        )
    )
