"""declarer_unite_ppb_et_grandeurs_eac4_aod_ozone

Revision ID: 122
Revises: 121
Create Date: 2026-11-07 10:00:00.000000+00:00

Declarations de referentiel, sans donnees :

1. unite ``partie_par_milliard`` (ppb, fraction molaire, nouvelle categorie
   ``fraction_molaire`` ; aucun DDL, ``unites.grandeur`` est String sans CHECK) ;
2. grandeurs brutes ``aod_550``, ``aod_poussiere_550`` (unite ``sans_unite``,
   migration 002), ``ozone_surface`` et ``ozone_surface_diurne`` (unite
   ``partie_par_milliard``), toutes F1, stockees.

Source amont : reanalyse CAMS EAC4 (``cams_eac4``, migration 081). Aucune serie,
aucune mesure : elles arriveront avec la capture des donnees
(``scripts/preparer_seed_cams_eac4_aod_ozone.py``). Aucun reseau.

Pattern : etapes 2 et 3 de la migration 081 (unite puis grandeurs, resolution des
``unite_id`` avec echec explicite).
"""

from __future__ import annotations

from collections.abc import Sequence
from decimal import Decimal
from typing import Any

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import ARRAY

# revision identifiers, used by Alembic.
revision: str = "122"
down_revision: str | Sequence[str] | None = "121"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# === Unite partie_par_milliard =============================================

_UNITE_PPB = "partie_par_milliard"
_UNITE_SANS = "sans_unite"

_UNITE_SEED: dict[str, Any] = {
    "code": _UNITE_PPB,
    "libelle": "partie par milliard (fraction molaire)",
    "symbole": "ppb",
    "grandeur": "fraction_molaire",
    "systeme": "non_SI_acceptee",
    "est_unite_de_base": False,
    "facteur_conversion_si": Decimal("1E-9"),
    "decalage_conversion_si": Decimal("0"),
    "code_unite_si": _UNITE_SANS,
    "note_methodologique": (
        "Fraction molaire exprimee en parties par milliard : 1 ppb = 1 nmol/mol = 1e-9 "
        "(grandeur de dimension 1). Usage : ozone de surface de la reanalyse CAMS EAC4, "
        "converti depuis le rapport de melange massique (kg/kg) par le rapport des "
        "masses molaires de l'air sec et de l'ozone."
    ),
    "references_normatives": [
        "BIPM SI Brochure 9eme edition (2019)",
    ],
}


# === Grandeurs brutes EAC4 =================================================

_GRANDEURS: list[dict[str, Any]] = [
    {
        "code": "aod_550",
        "unite_code": _UNITE_SANS,
        "libelle": "Épaisseur optique des aérosols à 550 nm",
        "famille": "F1",
        "strategie_calcul": "stockee",
        "description": (
            "Épaisseur optique totale des aérosols à 550 nm (sans unité), qui mesure "
            "l'atténuation de la lumière solaire par l'ensemble des particules en "
            "suspension sur toute la colonne atmosphérique. Donnée brute de la "
            "réanalyse de composition atmosphérique Copernicus CAMS EAC4 (grille de "
            "0,75°, pas de 3 heures), moyenne journalière des 8 pas de 3 heures au "
            "point de grille le plus proche."
        ),
    },
    {
        "code": "aod_poussiere_550",
        "unite_code": _UNITE_SANS,
        "libelle": "Épaisseur optique des poussières à 550 nm",
        "famille": "F1",
        "strategie_calcul": "stockee",
        "description": (
            "Part de l'épaisseur optique des aérosols à 550 nm due aux poussières "
            "minérales (sans unité), sur toute la colonne atmosphérique. Donnée brute "
            "de la réanalyse de composition atmosphérique Copernicus CAMS EAC4 (grille "
            "de 0,75°, pas de 3 heures), moyenne journalière des 8 pas de 3 heures au "
            "point de grille le plus proche. Inférieure ou égale à l'épaisseur optique "
            "totale."
        ),
    },
    {
        "code": "ozone_surface",
        "unite_code": _UNITE_PPB,
        "libelle": "Ozone de surface",
        "famille": "F1",
        "strategie_calcul": "stockee",
        "description": (
            "Fraction molaire d'ozone près de la surface, en parties par milliard (ppb). "
            "Donnée brute de la réanalyse de composition "
            "atmosphérique Copernicus CAMS EAC4 au niveau modèle le plus bas (grille "
            "de 0,75°, pas de 3 heures), convertie depuis le rapport de mélange "
            "massique ; moyenne journalière des 8 pas de 3 heures au point de grille "
            "le plus proche."
        ),
    },
    {
        "code": "ozone_surface_diurne",
        "unite_code": _UNITE_PPB,
        "libelle": "Ozone de surface diurne",
        "famille": "F1",
        "strategie_calcul": "stockee",
        "description": (
            "Fraction molaire d'ozone près de la surface en journée, en parties par "
            "milliard (ppb) : moyenne des pas de 09 h, 12 h et 15 h "
            "UTC (heure locale en Guinée). Donnée brute de la réanalyse de composition "
            "atmosphérique Copernicus CAMS EAC4 au niveau modèle le plus bas (grille "
            "de 0,75°), convertie depuis le rapport de mélange massique, au point de "
            "grille le plus proche."
        ),
    },
]
_CODES_GRANDEURS: tuple[str, ...] = tuple(g["code"] for g in _GRANDEURS)


def upgrade() -> None:
    bind = op.get_bind()

    # === Etape 1 : unite partie_par_milliard ==============================
    unites_table = sa.table(
        "unites",
        sa.column("code", sa.String),
        sa.column("libelle", sa.Text),
        sa.column("symbole", sa.String),
        sa.column("grandeur", sa.String),
        sa.column("systeme", sa.String),
        sa.column("est_unite_de_base", sa.Boolean),
        sa.column("facteur_conversion_si", sa.Numeric(60, 30)),
        sa.column("decalage_conversion_si", sa.Numeric(60, 30)),
        sa.column("code_unite_si", sa.String),
        sa.column("note_methodologique", sa.Text),
        sa.column("references_normatives", ARRAY(sa.Text())),
    )
    op.bulk_insert(unites_table, [_UNITE_SEED])

    # === Etape 2 : grandeurs (resolution des unite_id) =====================
    unite_id: dict[str, int] = {}
    for code in (_UNITE_PPB, _UNITE_SANS):
        uid = bind.execute(
            sa.text("SELECT id FROM unites WHERE code = :code"), {"code": code}
        ).scalar_one_or_none()
        if uid is None:
            raise RuntimeError(f"Migration 122 : unite {code!r} introuvable.")
        unite_id[code] = int(uid)

    grandeurs_table = sa.table(
        "grandeurs_referentiel",
        sa.column("code", sa.String),
        sa.column("libelle", sa.Text),
        sa.column("unite_id", sa.BigInteger),
        sa.column("famille", sa.String),
        sa.column("strategie_calcul", sa.String),
        sa.column("description", sa.Text),
    )
    op.bulk_insert(
        grandeurs_table,
        [
            {
                "code": g["code"],
                "libelle": g["libelle"],
                "unite_id": unite_id[g["unite_code"]],
                "famille": g["famille"],
                "strategie_calcul": g["strategie_calcul"],
                "description": g["description"],
            }
            for g in _GRANDEURS
        ],
    )

    op.execute(
        "-- Migration 122 : unite partie_par_milliard + grandeurs aod_550, "
        "aod_poussiere_550, ozone_surface, ozone_surface_diurne (declarations seules)."
    )


def downgrade() -> None:
    # Ordre impose par la FK grandeurs_referentiel.unite_id (ON DELETE RESTRICT).
    op.execute(
        sa.text("DELETE FROM grandeurs_referentiel WHERE code = ANY(:codes)").bindparams(
            sa.bindparam("codes", value=list(_CODES_GRANDEURS))
        )
    )
    op.execute(
        sa.text("DELETE FROM unites WHERE code = :code").bindparams(
            sa.bindparam("code", value=_UNITE_PPB)
        )
    )
