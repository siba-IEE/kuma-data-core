"""seed_ingestion_daily_nasa_power_28_communes_densification

Revision ID: 086
Revises: 085
Create Date: 2026-06-20 12:00:00

Densification prefectorale (daily). Seed des series NASA POWER
daily 2021-2025 pour les **28 nouvelles communes chef-lieu** (les 33 prefectures
moins les 5 capitales regionales deja ingerees), puis ingestion offline des
mesures depuis le seed committe.

Perimetre :

- 28 communes x 9 grandeurs brutes daily = **252 series** dans
  ``series_metadonnees`` (naming ``gin_<slug>_<grandeur>_nasa_power_2021_2025``,
  slug = code commune). ``granularite='journalier'``,
  ``methode_collecte='modele_satellitaire'``, source ``nasa_power``.
- Ingestion offline : ``ingerer_series_daily_groupe`` route par
  ``_fetch_nasa_daily_raw`` qui, sous ``KUMA_INGESTION_MODE=offline``, lit le payload
  committe (seed ``nasa_power_daily_seed_data``, 28 ``.json.gz``) au lieu du reseau.
  Decompte deterministe (non-sentinelles), pas de bornes.

Les 9 grandeurs (ghi/dni/dhi/t2m/rh2m/kt/vent_2m/vent_10m/albedo_surface) existent
deja (seedees migrations 028 / 047) : aucune creation de grandeur ici.

Bornes : **28 nouvelles communes seulement** ; les 6 points pilotes gardent leurs
series daily (zero re-ingestion). Pas de monthly (lot separe), pas de
SARAH-3/CAMS/ERA5.

Hors offline (mode live), l'ingestion appelle NASA POWER ; en CI
``KUMA_INGESTION_MODE=offline`` -> reseau nul. Sous seed absent + offline, l'appel
leve (fail-safe) ; sous ``KUMA_SKIP_NASA_POWER_INGESTION`` truthy, 0 mesure (series
seules). Pattern seed+ingest herite de la migration 050 (monthly) ; ingestion
groupee de la migration 048.

Donnees commune : ``localites_prefectures_seed_data`` (codes + noms) ; coordonnees
resolues en base (source de verite, = cle offline).
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date
from typing import Any

import sqlalchemy as sa
from alembic import op
from sqlalchemy.orm import Session

from kuma_data_core.db.seeds.localites_prefectures_seed_data import PREFECTURES_GUINEE
from kuma_data_core.ingestion.nasa_power_daily import ingerer_series_daily_groupe

# revision identifiers, used by Alembic.
revision: str = "086"
down_revision: str | Sequence[str] | None = "085"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# === Communes cibles (28 nouvelles, code -> nom) ==========================
# Derive du seed de densification : les communes neuves (existante is None). Les 5
# capitales regionales (Kankan, Kindia, Labe, Mamou, Nzerekore) sont exclues.
_NOM_PAR_COMMUNE: dict[str, str] = {
    p["commune_code"]: p["nom"] for p in PREFECTURES_GUINEE if p["existante"] is None
}
_COMMUNES: tuple[str, ...] = tuple(_NOM_PAR_COMMUNE)


# === Grandeurs daily + mapping NASA POWER (union du seed) ==================
_MAPPING_GRANDEUR_PARAMETRE_NASA: dict[str, str] = {
    "ghi": "ALLSKY_SFC_SW_DWN",
    "dni": "ALLSKY_SFC_SW_DNI",
    "dhi": "ALLSKY_SFC_SW_DIFF",
    "t2m": "T2M",
    "rh2m": "RH2M",
    "kt": "ALLSKY_KT",
    "vent_2m": "WS2M",
    "vent_10m": "WS10M",
    "albedo_surface": "ALLSKY_SRF_ALB",
}
_GRANDEURS: tuple[str, ...] = tuple(_MAPPING_GRANDEUR_PARAMETRE_NASA)

_LIBELLES_GRANDEURS_SERIE: dict[str, str] = {
    "ghi": "GHI journalier",
    "dni": "DNI journalier",
    "dhi": "DHI journalier",
    "t2m": "Temperature 2m journaliere",
    "rh2m": "Humidite relative 2m journaliere",
    "kt": "Indice de clarte journalier",
    "vent_2m": "Vent 2m journalier",
    "vent_10m": "Vent 10m journalier",
    "albedo_surface": "Albedo de surface journalier",
}

_SOURCE_CODE: str = "nasa_power"
_PERIODE_DEBUT: date = date(2021, 1, 1)
_PERIODE_FIN: date = date(2025, 12, 31)
_METHODE_COLLECTE: str = "modele_satellitaire"
_GRANULARITE: str = "journalier"
_METHODE_COLLECTE_DOC: str = "https://power.larc.nasa.gov/docs/methodology/"
_URL_DOCUMENTATION: str = "https://power.larc.nasa.gov/"

_COMMENTAIRE_EDITORIAL_TEMPLATE: str = (
    "Serie brute {grandeur_upper} journaliere ingeree depuis NASA POWER (methode "
    "satellitaire). Localite : {ville_libelle} (chef-lieu de prefecture), Guinee. "
    "Densification prefectorale Etape 1 Groupe B lot B-1 : 28 nouvelles communes x 9 "
    "grandeurs daily = 252 series. Niveau de confiance B (modele satellitaire)."
)


def _code_serie(commune_code: str, grandeur_code: str) -> str:
    """Convention naming : ``<commune>_<grandeur>_nasa_power_2021_2025``."""
    return f"{commune_code}_{grandeur_code}_{_SOURCE_CODE}_2021_2025"


def _tous_codes_series() -> list[str]:
    """Les 252 codes serie (deterministe, pour seed et downgrade)."""
    return [_code_serie(c, g) for c in _COMMUNES for g in _GRANDEURS]


def upgrade() -> None:
    bind = op.get_bind()

    # === 1. Resolution localite_id + coordonnees des 28 communes ===========
    rows = bind.execute(
        sa.text(
            "SELECT code, id, "
            "CAST(latitude AS DOUBLE PRECISION) AS lat, "
            "CAST(longitude AS DOUBLE PRECISION) AS lon "
            "FROM localites WHERE code = ANY(:codes)"
        ),
        {"codes": list(_COMMUNES)},
    ).all()
    info_par_commune: dict[str, dict[str, Any]] = {
        r.code: {"id": int(r.id), "lat": float(r.lat), "lon": float(r.lon)} for r in rows
    }
    manquantes = set(_COMMUNES) - info_par_commune.keys()
    if manquantes:
        raise RuntimeError(
            f"Migration 086 : commune(s) introuvable(s) : {sorted(manquantes)}. "
            f"Verifier la migration 085 (densification)."
        )

    # === 2. Resolution source_id NASA POWER ================================
    source_id = bind.execute(
        sa.text("SELECT id FROM sources WHERE code = :code"),
        {"code": _SOURCE_CODE},
    ).scalar_one_or_none()
    if source_id is None:
        raise RuntimeError(
            f"Migration 086 : source_code {_SOURCE_CODE!r} introuvable. Verifier la migration 012."
        )

    # === 3. Verification des 9 grandeurs daily actives =====================
    grandeurs_trouvees = set(
        bind.execute(
            sa.text(
                "SELECT code FROM grandeurs_referentiel WHERE code = ANY(:codes) AND actif = TRUE"
            ),
            {"codes": list(_GRANDEURS)},
        )
        .scalars()
        .all()
    )
    grandeurs_manquantes = set(_GRANDEURS) - grandeurs_trouvees
    if grandeurs_manquantes:
        raise RuntimeError(
            f"Migration 086 : grandeur(s) daily introuvable(s)/inactive(s) : "
            f"{sorted(grandeurs_manquantes)}. Doivent etre seedees (1-2b / 028 / 047)."
        )

    # === 4. Seed des 252 series (28 communes x 9 grandeurs) ================
    series_metadonnees_table = sa.table(
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
    for commune_code in _COMMUNES:
        ville_libelle = _NOM_PAR_COMMUNE[commune_code]
        for grandeur_code in _GRANDEURS:
            libelle = (
                f"{_LIBELLES_GRANDEURS_SERIE[grandeur_code]} {ville_libelle} 2021-2025 (NASA POWER)"
            )
            commentaire = _COMMENTAIRE_EDITORIAL_TEMPLATE.format(
                grandeur_upper=grandeur_code.upper(),
                ville_libelle=ville_libelle,
            )
            lignes_series.append(
                {
                    "code": _code_serie(commune_code, grandeur_code),
                    "libelle": libelle,
                    "localite_id": info_par_commune[commune_code]["id"],
                    "grandeur_code": grandeur_code,
                    "source_id": source_id,
                    "periode_debut": _PERIODE_DEBUT,
                    "periode_fin": _PERIODE_FIN,
                    "granularite": _GRANULARITE,
                    "methode_collecte": _METHODE_COLLECTE,
                    "methode_collecte_doc": _METHODE_COLLECTE_DOC,
                    "commentaire_editorial": commentaire,
                    "url_documentation": _URL_DOCUMENTATION,
                }
            )

    assert len(lignes_series) == 252, (
        f"Attendu 252 series (28 communes x 9 grandeurs), obtenu {len(lignes_series)}"
    )
    op.bulk_insert(series_metadonnees_table, lignes_series)

    # === 5. Ingestion offline groupee (1 appel multi-parametres / commune) ==
    session = Session(bind=bind)
    try:
        decomptes_totaux: dict[str, int] = {}
        for commune_code in _COMMUNES:
            info = info_par_commune[commune_code]
            codes_series_commune = [_code_serie(commune_code, g) for g in _GRANDEURS]
            decompte = ingerer_series_daily_groupe(
                session=session,
                codes_series=codes_series_commune,
                mapping_grandeur_parametre_nasa=_MAPPING_GRANDEUR_PARAMETRE_NASA,
                latitude=info["lat"],
                longitude=info["lon"],
                periode_debut=_PERIODE_DEBUT,
                periode_fin=_PERIODE_FIN,
            )
            decomptes_totaux.update(decompte)

        total = sum(decomptes_totaux.values())
        op.execute(
            f"-- Migration 086 : {total} lignes inserees dans mesures_ressource "
            f"sur 28 communes x 9 grandeurs daily (densification B-1, offline)."
        )
    finally:
        session.close()


def downgrade() -> None:
    codes_series = _tous_codes_series()
    # Mesures d'abord (FK RESTRICT sur serie_id), puis series.
    op.execute(
        sa.text(
            """
            DELETE FROM mesures_ressource
            WHERE serie_id IN (
                SELECT id FROM series_metadonnees WHERE code = ANY(:codes)
            )
            """
        ).bindparams(codes=codes_series)
    )
    op.execute(
        sa.text("DELETE FROM series_metadonnees WHERE code = ANY(:codes)").bindparams(
            sa.bindparam("codes", value=codes_series)
        )
    )
