"""seed_ingestion_monthly_nasa_power_28_communes_densification

Revision ID: 087
Revises: 086
Create Date: 2026-06-20 14:00:00

Densification prefectorale - climato mensuelle NASA POWER. Seed des series
climato mensuelles NASA POWER pour les **28 nouvelles communes chef-lieu**, puis
ingestion **offline** depuis le seed committe (``nasa_power_monthly_seed_data``).

Complete le cœur national : la climato mensuelle long-terme (P50/P90) que seuls
les 6 pilotes possedaient (041 GHI + 050 les 8 autres).

Perimetre : 28 communes x 9 grandeurs = **252 series**, deux fenetres (asymetrie
source assumee, identique au cadrage) :

| Grandeur | Parametre NASA | Fenetre   | Lignes/serie |
|----------|----------------|-----------|--------------|
| ghi      | ALLSKY_SFC_SW_DWN | 1991-2020 | 360 |
| t2m      | T2M            | 1991-2020 | 360 |
| rh2m     | RH2M           | 1991-2020 | 360 |
| vent_2m  | WS2M           | 1991-2020 | 360 |
| vent_10m | WS10M          | 1991-2020 | 360 |
| dhi      | ALLSKY_SFC_SW_DIFF | 2001-2020 | 240 |
| dni      | ALLSKY_SFC_SW_DNI  | 2001-2020 | 240 |
| kt       | ALLSKY_KT      | 2001-2020 | 240 |
| albedo_surface | ALLSKY_SRF_ALB | 2001-2020 | 240 |

Volume attendu : 28 x (5 x 360 + 4 x 240) = 28 x 2760 = **77 280 lignes**
mensuelles (climato entierement murie, deterministe).

Ingestion offline : ``ingerer_serie_monthly`` route par
``_fetch_nasa_monthly_raw`` qui, sous ``KUMA_INGESTION_MODE=offline``, lit le
payload committe restreint a (parametre, fenetre) au lieu du reseau. Climato
figee -> compte exact, pas de bornes.

Naming des series : ``gin_<slug>_<grandeur>_power_<an_debut>_<an_fin>`` (le segment
``power`` est le raccourci climato mensuelle ; source SQL = ``nasa_power``).
``granularite='mensuel'``. Series attachees aux communes.

Bornes : 28 communes seulement ; les 6 pilotes gardent leurs series (041/050,
immuables, qui liront desormais le seed en offline).
050 inchangee. Pattern seed+ingest herite de 050.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date
from typing import Any

import sqlalchemy as sa
from alembic import op
from sqlalchemy.orm import Session

from kuma_data_core.db.seeds.localites_prefectures_seed_data import PREFECTURES_GUINEE
from kuma_data_core.ingestion.nasa_power_monthly import ingerer_serie_monthly

# revision identifiers, used by Alembic.
revision: str = "087"
down_revision: str | Sequence[str] | None = "086"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# === 28 communes cibles (code -> nom) =====================================
_NOM_PAR_COMMUNE: dict[str, str] = {
    p["commune_code"]: p["nom"] for p in PREFECTURES_GUINEE if p["existante"] is None
}
_COMMUNES: tuple[str, ...] = tuple(_NOM_PAR_COMMUNE)


# === 9 grandeurs climato : grandeur -> (parametre NASA, annee_debut) =======
_MAPPING_GRANDEURS: dict[str, tuple[str, int]] = {
    "ghi": ("ALLSKY_SFC_SW_DWN", 1991),
    "t2m": ("T2M", 1991),
    "rh2m": ("RH2M", 1991),
    "vent_2m": ("WS2M", 1991),
    "vent_10m": ("WS10M", 1991),
    "dhi": ("ALLSKY_SFC_SW_DIFF", 2001),
    "dni": ("ALLSKY_SFC_SW_DNI", 2001),
    "kt": ("ALLSKY_KT", 2001),
    "albedo_surface": ("ALLSKY_SRF_ALB", 2001),
}
_ANNEE_FIN: int = 2020

_LIBELLES_GRANDEURS: dict[str, str] = {
    "ghi": "GHI mensuel climato",
    "t2m": "Temperature 2m mensuelle climato",
    "rh2m": "Humidite relative 2m mensuelle climato",
    "vent_2m": "Vent 2m mensuel climato",
    "vent_10m": "Vent 10m mensuel climato",
    "dhi": "DHI mensuel climato",
    "dni": "DNI mensuel climato",
    "kt": "Indice de clarte mensuel climato",
    "albedo_surface": "Albedo de surface mensuel climato",
}

_SOURCE_CODE: str = "nasa_power"
_GRANULARITE: str = "mensuel"
_METHODE_COLLECTE: str = "modele_satellitaire"
_METHODE_COLLECTE_DOC: str = "https://power.larc.nasa.gov/docs/methodology/"
_URL_DOCUMENTATION: str = "https://power.larc.nasa.gov/"

_COMMENTAIRE_TEMPLATE: str = (
    "Serie climato mensuelle long-terme {grandeur_upper} ingeree depuis NASA POWER "
    "endpoint monthly, fenetre {annee_debut}-{annee_fin}. Methode satellitaire. "
    "Localite : {ville} (chef-lieu de prefecture), Guinee. Densification Etape 1 "
    "Groupe B (monthly, D-40 lot 3) : profondeur climato (P50/P90) aux 28 nouveaux "
    "points. Niveau de confiance B (modele satellitaire)."
)


def _code_serie(commune_code: str, grandeur_code: str, annee_debut: int) -> str:
    """Convention naming : ``<commune>_<grandeur>_power_<an_debut>_<an_fin>``."""
    return f"{commune_code}_{grandeur_code}_power_{annee_debut}_{_ANNEE_FIN}"


def _tous_codes_series() -> list[str]:
    """Les 252 codes serie (deterministe, pour downgrade)."""
    return [
        _code_serie(c, g, annee_debut)
        for c in _COMMUNES
        for g, (_, annee_debut) in _MAPPING_GRANDEURS.items()
    ]


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
            f"Migration 087 : commune(s) introuvable(s) : {sorted(manquantes)}. "
            f"Verifier la migration 085."
        )

    # === 2. Resolution source_id + verification des 9 grandeurs ============
    source_id = bind.execute(
        sa.text("SELECT id FROM sources WHERE code = :code"),
        {"code": _SOURCE_CODE},
    ).scalar_one_or_none()
    if source_id is None:
        raise RuntimeError(f"Migration 087 : source {_SOURCE_CODE!r} introuvable (migration 012).")

    grandeurs_trouvees = set(
        bind.execute(
            sa.text(
                "SELECT code FROM grandeurs_referentiel WHERE code = ANY(:codes) AND actif = TRUE"
            ),
            {"codes": list(_MAPPING_GRANDEURS)},
        )
        .scalars()
        .all()
    )
    grandeurs_manquantes = set(_MAPPING_GRANDEURS) - grandeurs_trouvees
    if grandeurs_manquantes:
        raise RuntimeError(
            f"Migration 087 : grandeur(s) introuvable(s)/inactive(s) : "
            f"{sorted(grandeurs_manquantes)}."
        )

    # === 3. Seed des 252 series ===========================================
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
        ville = _NOM_PAR_COMMUNE[commune_code]
        for grandeur_code, (_parametre, annee_debut) in _MAPPING_GRANDEURS.items():
            lignes_series.append(
                {
                    "code": _code_serie(commune_code, grandeur_code, annee_debut),
                    "libelle": (
                        f"{_LIBELLES_GRANDEURS[grandeur_code]} {ville} "
                        f"{annee_debut}-{_ANNEE_FIN} (NASA POWER monthly)"
                    ),
                    "localite_id": info_par_commune[commune_code]["id"],
                    "grandeur_code": grandeur_code,
                    "source_id": source_id,
                    "periode_debut": date(annee_debut, 1, 1),
                    "periode_fin": date(_ANNEE_FIN, 12, 31),
                    "granularite": _GRANULARITE,
                    "methode_collecte": _METHODE_COLLECTE,
                    "methode_collecte_doc": _METHODE_COLLECTE_DOC,
                    "commentaire_editorial": _COMMENTAIRE_TEMPLATE.format(
                        grandeur_upper=grandeur_code.upper(),
                        annee_debut=annee_debut,
                        annee_fin=_ANNEE_FIN,
                        ville=ville,
                    ),
                    "url_documentation": _URL_DOCUMENTATION,
                }
            )

    assert len(lignes_series) == 252, (
        f"Attendu 252 series (28 communes x 9 grandeurs), obtenu {len(lignes_series)}"
    )
    op.bulk_insert(series_metadonnees_table, lignes_series)

    # === 4. Ingestion offline mensuelle des 252 series ====================
    session = Session(bind=bind)
    try:
        total = 0
        for commune_code in _COMMUNES:
            info = info_par_commune[commune_code]
            for grandeur_code, (parametre_nasa, annee_debut) in _MAPPING_GRANDEURS.items():
                total += ingerer_serie_monthly(
                    session=session,
                    code_serie=_code_serie(commune_code, grandeur_code, annee_debut),
                    parametre_nasa=parametre_nasa,
                    latitude=info["lat"],
                    longitude=info["lon"],
                    annee_debut=annee_debut,
                    annee_fin=_ANNEE_FIN,
                )
        op.execute(
            f"-- Migration 087 : {total} lignes inserees dans mesures_ressource_mensuelles "
            f"sur 28 communes x 9 grandeurs climato (densification monthly, offline)."
        )
    finally:
        session.close()


def downgrade() -> None:
    codes_series = _tous_codes_series()
    op.execute(
        sa.text(
            """
            DELETE FROM mesures_ressource_mensuelles
            WHERE serie_id IN (SELECT id FROM series_metadonnees WHERE code = ANY(:codes))
            """
        ).bindparams(codes=codes_series)
    )
    op.execute(
        sa.text("DELETE FROM series_metadonnees WHERE code = ANY(:codes)").bindparams(
            sa.bindparam("codes", value=codes_series)
        )
    )
