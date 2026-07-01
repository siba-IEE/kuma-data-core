"""seed_series_et_mesures_era5_land_vague4_lot_a

Revision ID: 069
Revises: 068
Create Date: 2026-06-16 09:30:00.000000+00:00

Séries + mesures ERA5-Land (Seed Offline).

Insère 36 séries (6 villes × 3 grandeurs `ghi`/`t2m`/`vent_10m` × 2
granularités) et leurs mesures depuis le seed committé
``era5_land_seed_data.py`` (produit hors-ligne par
``scripts/preparer_seed_era5_land.py``). **Aucun ``cdsapi`` / ``xarray`` /
``netCDF4`` ni réseau ici** : discipline α préservée, ``alembic upgrade head``
déterministe et offline.

- Mensuel climato **2001-2020** → ``mesures_ressource_mensuelles``
  (granularité ``mensuel``).
- Journalier récent **2021-2025** → ``mesures_ressource`` (granularité
  ``journalier``).

Naming des series : ``<alias_ville>_<grandeur>_era5_land_<an_debut>_<an_fin>``
(alias source ``era5_land`` raccourci de ``ecmwf_era5_land``, sur le précédent
``power``/``nasa_power`` ; exception ``gin_conakry`` via helper local).
Confiance ``B``, statut ``brut`` (server_default), ``modele_satellitaire``.

**Ordre d'application** : appliquer après peuplement du seed par le script.
Sur seed vide, les 36 séries sont créées avec 0 mesure (le test d'intégration
saute alors ses assertions de données).

Pattern dupliqué de la migration 050 (résolution IDs, ``bulk_insert``,
downgrade DELETE mesures→séries).
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date
from typing import Any

import sqlalchemy as sa
from alembic import op

from kuma_data_core.db.seeds.era5_land_seed_data import (
    ERA5_LAND_JOURNALIER_SEED,
    ERA5_LAND_MENSUEL_SEED,
    ERA5_LAND_PIXELS,
)

# revision identifiers, used by Alembic.
revision: str = "069"
down_revision: str | Sequence[str] | None = "068"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# === Énumérations exhaustives =============================================

_LOCALITES_PILOTES: tuple[str, ...] = (
    "gin_conakry_kaloum",
    "gin_kankan",
    "gin_kindia",
    "gin_labe",
    "gin_mamou",
    "gin_nzerekore",
)

_LIBELLES_VILLES: dict[str, str] = {
    "gin_conakry_kaloum": "Conakry-Kaloum",
    "gin_kankan": "Kankan",
    "gin_kindia": "Kindia",
    "gin_labe": "Labe",
    "gin_mamou": "Mamou",
    "gin_nzerekore": "Nzerekore",
}

_GRANDEURS: tuple[str, ...] = ("ghi", "t2m", "vent_10m")

_LIBELLES_GRANDEURS: dict[str, str] = {
    "ghi": "GHI",
    "t2m": "Temperature 2m",
    "vent_10m": "Vent 10m",
}

_SOURCE_CODE_SQL = "ecmwf_era5_land"

# (granularite, an_debut, an_fin, table_mesures)
_MENSUEL = ("mensuel", 2001, 2020)
_JOURNALIER = ("journalier", 2021, 2025)

_METHODE_COLLECTE = "modele_satellitaire"
_METHODE_COLLECTE_DOC = "https://confluence.ecmwf.int/display/CKB/ERA5-Land"
_URL_DOCUMENTATION = "https://cds.climate.copernicus.eu/datasets/reanalysis-era5-land"


def _prefixe_ville_pour_serie(localite_code: str) -> str:
    """Préfixe ville pour code série (exception Conakry-Kaloum).

    Dupliqué du helper des migrations 041 / 050 (immuabilité post-merge :
    pas d'import croisé entre migrations).
    """
    if localite_code == "gin_conakry_kaloum":
        return "gin_conakry"
    return localite_code


def _code_serie(localite_code: str, grandeur_code: str, an_debut: int, an_fin: int) -> str:
    return (
        f"{_prefixe_ville_pour_serie(localite_code)}_{grandeur_code}_era5_land_{an_debut}_{an_fin}"
    )


def _commentaire(
    localite_code: str, grandeur_code: str, granularite: str, an_debut: int, an_fin: int
) -> str:
    pixel = ERA5_LAND_PIXELS.get(localite_code)
    pixel_txt = (
        f"pixel ({pixel['latitude']:.2f}, {pixel['longitude']:.2f})"
        + (" [repli terrestre, masque ocean ERA5-Land]" if pixel.get("repli_applique") else "")
        if pixel
        else "pixel a renseigner (seed non peuple)"
    )
    caveat = ""
    if grandeur_code == "ghi" and localite_code in ("gin_kindia", "gin_mamou"):
        caveat = (
            " Caveat D-29 : ERA5-Land separe geometriquement Kindia/Mamou (vs "
            "cellule CERES 1deg unique), mais le rayonnement est herite du forcage "
            "ERA5 (31 km, interpole MIR) - separation geometrique, realisme du "
            "differentiel radiatif limite (resolution complete = calage sol)."
        )
    if grandeur_code == "vent_10m" and granularite == "mensuel":
        caveat += (
            " Vent mensuel = module des composantes u10/v10 moyennes (sous-estime "
            "legerement la vitesse moyenne reelle)."
        )
    return (
        f"Serie ERA5-Land {grandeur_code.upper()} {granularite} {an_debut}-{an_fin}, "
        f"{_LIBELLES_VILLES[localite_code]}, Guinee. Reanalyse Copernicus "
        f"(grille API 0.1deg 11 km), {pixel_txt}. Niveau de confiance B "
        f"(reanalyse). Vague 4 Lot A : co-localisation D-29 / altitude D-24."
        f"{caveat} Attribution : Generated using Copernicus Climate Change Service "
        f"Information 2026 (licence CC-BY)."
    )


def upgrade() -> None:
    bind = op.get_bind()

    # === Étape 1 : résolution des IDs ====================================
    lignes_localites = bind.execute(
        sa.text("SELECT code, id FROM localites WHERE code = ANY(:codes)"),
        {"codes": list(_LOCALITES_PILOTES)},
    ).all()
    localite_id: dict[str, int] = {r.code: int(r.id) for r in lignes_localites}
    manquants = set(_LOCALITES_PILOTES) - localite_id.keys()
    if manquants:
        raise RuntimeError(f"Migration 069 : localite(s) introuvable(s) : {sorted(manquants)}.")

    source_id = bind.execute(
        sa.text("SELECT id FROM sources WHERE code = :code"),
        {"code": _SOURCE_CODE_SQL},
    ).scalar_one_or_none()
    if source_id is None:
        raise RuntimeError(
            f"Migration 069 : source {_SOURCE_CODE_SQL!r} introuvable (migration 068)."
        )

    grandeurs_actives = set(
        bind.execute(
            sa.text(
                "SELECT code FROM grandeurs_referentiel WHERE code = ANY(:codes) AND actif = TRUE"
            ),
            {"codes": list(_GRANDEURS)},
        )
        .scalars()
        .all()
    )
    grandeurs_manquantes = set(_GRANDEURS) - grandeurs_actives
    if grandeurs_manquantes:
        raise RuntimeError(
            f"Migration 069 : grandeur(s) inactive(s)/absente(s) : {sorted(grandeurs_manquantes)}."
        )

    # === Étape 2 : 36 séries =============================================
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

    lignes_series: list[dict[str, Any]] = []
    for localite_code in _LOCALITES_PILOTES:
        for grandeur_code in _GRANDEURS:
            for granularite, an_debut, an_fin in (_MENSUEL, _JOURNALIER):
                lignes_series.append(
                    {
                        "code": _code_serie(localite_code, grandeur_code, an_debut, an_fin),
                        "libelle": (
                            f"{_LIBELLES_GRANDEURS[grandeur_code]} ERA5-Land {granularite} "
                            f"{_LIBELLES_VILLES[localite_code]} {an_debut}-{an_fin}"
                        ),
                        "localite_id": localite_id[localite_code],
                        "grandeur_code": grandeur_code,
                        "source_id": source_id,
                        "periode_debut": date(an_debut, 1, 1),
                        "periode_fin": date(an_fin, 12, 31),
                        "granularite": granularite,
                        "methode_collecte": _METHODE_COLLECTE,
                        "methode_collecte_doc": _METHODE_COLLECTE_DOC,
                        "commentaire_editorial": _commentaire(
                            localite_code, grandeur_code, granularite, an_debut, an_fin
                        ),
                        "url_documentation": _URL_DOCUMENTATION,
                    }
                )
    assert len(lignes_series) == 36, f"Attendu 36 séries, obtenu {len(lignes_series)}"
    op.bulk_insert(series_table, lignes_series)

    # Map code_serie -> id (après insert).
    serie_id_par_code: dict[str, int] = {
        r.code: int(r.id)
        for r in bind.execute(
            sa.text("SELECT code, id FROM series_metadonnees WHERE code = ANY(:codes)"),
            {"codes": [s["code"] for s in lignes_series]},
        ).all()
    }

    # === Étape 3 : mesures depuis le seed ================================
    mensuelles_table = sa.table(
        "mesures_ressource_mensuelles",
        sa.column("serie_id", sa.BigInteger),
        sa.column("annee", sa.SmallInteger),
        sa.column("mois", sa.SmallInteger),
        sa.column("valeur", sa.Float),
        sa.column("niveau_confiance_derive", sa.String),
    )
    journalieres_table = sa.table(
        "mesures_ressource",
        sa.column("serie_id", sa.BigInteger),
        sa.column("instant_mesure", sa.Date),
        sa.column("valeur", sa.Float),
        sa.column("niveau_confiance_derive", sa.String),
    )

    lignes_mensuelles = [
        {
            "serie_id": serie_id_par_code[
                _code_serie(r["localite_code"], r["grandeur_code"], 2001, 2020)
            ],
            "annee": r["annee"],
            "mois": r["mois"],
            "valeur": r["valeur"],
            "niveau_confiance_derive": "B",
        }
        for r in ERA5_LAND_MENSUEL_SEED
    ]
    lignes_journalieres = [
        {
            "serie_id": serie_id_par_code[
                _code_serie(r["localite_code"], r["grandeur_code"], 2021, 2025)
            ],
            "instant_mesure": date.fromisoformat(r["date"]),
            "valeur": r["valeur"],
            "niveau_confiance_derive": "B",
        }
        for r in ERA5_LAND_JOURNALIER_SEED
    ]
    if lignes_mensuelles:
        op.bulk_insert(mensuelles_table, lignes_mensuelles)
    if lignes_journalieres:
        op.bulk_insert(journalieres_table, lignes_journalieres)

    op.execute(
        f"-- Migration 069 : 36 series ERA5-Land + {len(lignes_mensuelles)} mesures "
        f"mensuelles + {len(lignes_journalieres)} mesures journalieres."
    )


def downgrade() -> None:
    codes_series = [
        _code_serie(localite_code, grandeur_code, an_debut, an_fin)
        for localite_code in _LOCALITES_PILOTES
        for grandeur_code in _GRANDEURS
        for _, an_debut, an_fin in (_MENSUEL, _JOURNALIER)
    ]
    for table in ("mesures_ressource_mensuelles", "mesures_ressource"):
        op.execute(
            sa.text(
                f"DELETE FROM {table} WHERE serie_id IN "
                "(SELECT id FROM series_metadonnees WHERE code = ANY(:codes))"
            ).bindparams(sa.bindparam("codes", value=codes_series))
        )
    op.execute(
        sa.text("DELETE FROM series_metadonnees WHERE code = ANY(:codes)").bindparams(
            sa.bindparam("codes", value=codes_series)
        )
    )
