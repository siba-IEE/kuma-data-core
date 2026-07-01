"""seed_grandeur_precipitation_vague5_soiling_lot_b

Revision ID: 080
Revises: 079
Create Date: 2026-06-18 13:00:00.000000+00:00

Precipitation journaliere (Seed Offline).

Premiere des deux ingestions du proxy de salissure. Insere, **tout
depuis le seed committe** ``precipitation_seed_data.py`` (produit hors-ligne par
``scripts/preparer_seed_precipitation.py``, NASA POWER PRECTOTCORR) :

1. l'unite ``mm_par_jour`` (millimetre par jour, absente du referentiel) ;
2. la grandeur brute ``precipitation`` (F1, stockee) ;
3. 6 series journalieres (1 par ville pilote, source ``nasa_power``) ;
4. les mesures journalieres 2021-2025.

**Aucun reseau ici** (pas de ``httpx`` / ``cdsapi`` ni appel NASA) : la
discipline seed-offline est preservee, ``alembic upgrade head`` reste
deterministe et offline, et l'ingestion live jouee en CI n'est pas aggravee.

Naming des series : ``<slug_ville>_precipitation_nasa_power_2021_2025`` (slug
Conakry raccourci ``gin_conakry``, convention historique migrations 016/047).
Confiance ``B`` (``modele_satellitaire``, NASA POWER source haute).

Pattern : unite (migration 009), grandeur brute inline (migration 047), series +
mesures depuis seed (migration 069). Sur seed vide, les 6 series sont creees avec
0 mesure (le test d'integration saute alors ses assertions de donnees).
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date
from decimal import Decimal
from typing import Any

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import ARRAY

from kuma_data_core.db.seeds.precipitation_seed_data import (
    PRECIPITATION_JOURNALIER_SEED,
)

# revision identifiers, used by Alembic.
revision: str = "080"
down_revision: str | Sequence[str] | None = "079"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# === Unite mm/jour (enumeration exhaustive) ================================

_UNITE_CODE: str = "mm_par_jour"

# 1 mm/jour = 1e-3 m / 86400 s = 1.157e-8 m/s (profondeur de pluie par unite de
# temps, dimensionnellement une vitesse). Reference SI : metre_par_seconde.
_FACTEUR_MM_PAR_JOUR_SI: Decimal = (Decimal("0.001") / Decimal("86400")).quantize(Decimal("1E-30"))

_UNITE_SEED: dict[str, Any] = {
    "code": _UNITE_CODE,
    "libelle": "millimetre par jour",
    "symbole": "mm/jour",
    "grandeur": "precipitation",
    "systeme": "composee_mixte",
    "est_unite_de_base": False,
    "facteur_conversion_si": _FACTEUR_MM_PAR_JOUR_SI,
    "decalage_conversion_si": Decimal("0"),
    "code_unite_si": "metre_par_seconde",
    "note_methodologique": (
        "Hauteur de precipitation cumulee sur une journee. Convention "
        "meteorologique standard (lame d'eau en millimetres equivalente a des "
        "litres par metre carre). Dimension SI : vitesse (profondeur / temps), "
        "facteur = 1e-3 / 86400 m/s."
    ),
    "references_normatives": [
        "BIPM SI Brochure 9eme edition (2019)",
        "OMM/WMO Guide to Meteorological Instruments and Methods of Observation (WMO-No. 8)",
    ],
}


# === Grandeur precipitation (enumeration exhaustive) =======================

_GRANDEUR_CODE: str = "precipitation"

_GRANDEUR_SEED: dict[str, Any] = {
    "code": _GRANDEUR_CODE,
    "libelle": "Precipitation journaliere",
    "famille": "F1",
    "strategie_calcul": "stockee",
    "description": (
        "Hauteur de precipitation journaliere (mm/jour). Donnee brute ingeree "
        "depuis NASA POWER parametre PRECTOTCORR (Precipitation Corrected, "
        "source amont MERRA-2 GMAO / IMERG). Entree pluie du modele de salissure "
        "HSU (pvlib.soiling.hsu) pour la grandeur proxy taux_salissure_proxy "
        "(Vague 5 soiling Lot C). Confiance B (modele satellitaire)."
    ),
}


# === Localites et slugs de serie (enumeration exhaustive) ==================

# (localite_code DB, slug_serie, libelle_ville) : Conakry-Kaloum porte le slug
# court historique `gin_conakry` (migrations 016/047), les 5 autres villes
# utilisent leur code tel quel.
_LOCALITES_PILOTES: list[tuple[str, str, str]] = [
    ("gin_conakry_kaloum", "gin_conakry", "Conakry-Kaloum"),
    ("gin_kankan", "gin_kankan", "Kankan"),
    ("gin_kindia", "gin_kindia", "Kindia"),
    ("gin_labe", "gin_labe", "Labe"),
    ("gin_mamou", "gin_mamou", "Mamou"),
    ("gin_nzerekore", "gin_nzerekore", "Nzerekore"),
]

_SOURCE_CODE: str = "nasa_power"
_PERIODE_DEBUT: date = date(2021, 1, 1)
_PERIODE_FIN: date = date(2025, 12, 31)
_GRANULARITE: str = "journalier"
_METHODE_COLLECTE: str = "modele_satellitaire"
_METHODE_COLLECTE_DOC: str = "https://power.larc.nasa.gov/docs/methodology/"
_URL_DOCUMENTATION: str = "https://power.larc.nasa.gov/"

_COMMENTAIRE_EDITORIAL_TEMPLATE: str = (
    "Serie inscrite en Phase 2 vague 5 (soiling Lot B). Precipitation "
    "journaliere brute ingeree depuis NASA POWER PRECTOTCORR (methode "
    "satellitaire, MERRA-2 GMAO / IMERG). Localite : {ville_libelle}, Guinee. "
    "Entree pluie du modele de salissure HSU (Lot C). Confiance B."
)


def _code_serie(slug_serie: str) -> str:
    """Convention naming : ``<slug_serie>_precipitation_nasa_power_2021_2025``."""
    return f"{slug_serie}_{_GRANDEUR_CODE}_{_SOURCE_CODE}_2021_2025"


def upgrade() -> None:
    bind = op.get_bind()

    # === Etape 1 : unite mm_par_jour =====================================
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

    # === Etape 2 : grandeur precipitation (resolution unite_id) ===========
    unite_id = bind.execute(
        sa.text("SELECT id FROM unites WHERE code = :code"),
        {"code": _UNITE_CODE},
    ).scalar_one_or_none()
    if unite_id is None:
        raise RuntimeError(f"Migration 080 : unite {_UNITE_CODE!r} introuvable apres insertion.")

    grandeurs_referentiel_table = sa.table(
        "grandeurs_referentiel",
        sa.column("code", sa.String),
        sa.column("libelle", sa.Text),
        sa.column("unite_id", sa.BigInteger),
        sa.column("famille", sa.String),
        sa.column("strategie_calcul", sa.String),
        sa.column("description", sa.Text),
    )
    op.bulk_insert(
        grandeurs_referentiel_table,
        [{**_GRANDEUR_SEED, "unite_id": int(unite_id)}],
    )

    # === Etape 3 : 6 series journalieres ==================================
    codes_localites = [loc[0] for loc in _LOCALITES_PILOTES]
    lignes_localites = bind.execute(
        sa.text("SELECT code, id FROM localites WHERE code = ANY(:codes)"),
        {"codes": codes_localites},
    ).all()
    localite_id: dict[str, int] = {r.code: int(r.id) for r in lignes_localites}
    manquants = set(codes_localites) - localite_id.keys()
    if manquants:
        raise RuntimeError(f"Migration 080 : localite(s) introuvable(s) : {sorted(manquants)}.")

    source_id = bind.execute(
        sa.text("SELECT id FROM sources WHERE code = :code"),
        {"code": _SOURCE_CODE},
    ).scalar_one_or_none()
    if source_id is None:
        raise RuntimeError(f"Migration 080 : source {_SOURCE_CODE!r} introuvable.")

    series_table = sa.table(
        "series_metadonnees",
        sa.column("code", sa.String),
        sa.column("libelle", sa.Text),
        sa.column("localite_id", sa.BigInteger),
        sa.column("grandeur_code", sa.String),
        sa.column("source_id", sa.BigInteger),
        sa.column("periode_debut", sa.Date),
        sa.column("periode_fin", sa.Date),
        sa.column("granularite", sa.String),
        sa.column("methode_collecte", sa.String),
        sa.column("methode_collecte_doc", sa.Text),
        sa.column("commentaire_editorial", sa.Text),
        sa.column("url_documentation", sa.Text),
    )

    lignes_series: list[dict[str, Any]] = [
        {
            "code": _code_serie(slug_serie),
            "libelle": f"Precipitation journaliere {ville_libelle} 2021-2025 (NASA POWER)",
            "localite_id": localite_id[localite_code],
            "grandeur_code": _GRANDEUR_CODE,
            "source_id": int(source_id),
            "periode_debut": _PERIODE_DEBUT,
            "periode_fin": _PERIODE_FIN,
            "granularite": _GRANULARITE,
            "methode_collecte": _METHODE_COLLECTE,
            "methode_collecte_doc": _METHODE_COLLECTE_DOC,
            "commentaire_editorial": _COMMENTAIRE_EDITORIAL_TEMPLATE.format(
                ville_libelle=ville_libelle
            ),
            "url_documentation": _URL_DOCUMENTATION,
        }
        for localite_code, slug_serie, ville_libelle in _LOCALITES_PILOTES
    ]
    assert len(lignes_series) == 6, f"Attendu 6 series, obtenu {len(lignes_series)}"
    op.bulk_insert(series_table, lignes_series)

    serie_id_par_localite: dict[str, int] = {}
    code_vers_localite = {_code_serie(slug): loc for loc, slug, _ in _LOCALITES_PILOTES}
    for r in bind.execute(
        sa.text("SELECT code, id FROM series_metadonnees WHERE code = ANY(:codes)"),
        {"codes": [s["code"] for s in lignes_series]},
    ).all():
        serie_id_par_localite[code_vers_localite[r.code]] = int(r.id)

    # === Etape 4 : mesures depuis le seed =================================
    mesures_table = sa.table(
        "mesures_ressource",
        sa.column("serie_id", sa.BigInteger),
        sa.column("instant_mesure", sa.Date),
        sa.column("valeur", sa.Float),
        sa.column("niveau_confiance_derive", sa.String),
    )
    lignes_mesures = [
        {
            "serie_id": serie_id_par_localite[r["localite_code"]],
            "instant_mesure": date.fromisoformat(r["date"]),
            "valeur": r["valeur"],
            "niveau_confiance_derive": "B",
        }
        for r in PRECIPITATION_JOURNALIER_SEED
    ]
    if lignes_mesures:
        op.bulk_insert(mesures_table, lignes_mesures)

    op.execute(
        f"-- Migration 080 : unite mm_par_jour + grandeur precipitation + 6 series "
        f"+ {len(lignes_mesures)} mesures journalieres (seed offline NASA POWER)."
    )


def downgrade() -> None:
    codes_series = [_code_serie(slug) for _, slug, _ in _LOCALITES_PILOTES]
    op.execute(
        sa.text(
            "DELETE FROM mesures_ressource WHERE serie_id IN "
            "(SELECT id FROM series_metadonnees WHERE code = ANY(:codes))"
        ).bindparams(sa.bindparam("codes", value=codes_series))
    )
    op.execute(
        sa.text("DELETE FROM series_metadonnees WHERE code = ANY(:codes)").bindparams(
            sa.bindparam("codes", value=codes_series)
        )
    )
    op.execute(
        sa.text("DELETE FROM grandeurs_referentiel WHERE code = :code").bindparams(
            sa.bindparam("code", value=_GRANDEUR_CODE)
        )
    )
    op.execute(
        sa.text("DELETE FROM unites WHERE code = :code").bindparams(
            sa.bindparam("code", value=_UNITE_CODE)
        )
    )
