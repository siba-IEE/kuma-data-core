"""seed_ingestion_cams_dni_28_communes_densification

Revision ID: 089
Revises: 088
Create Date: 2026-06-20 17:00:00

Densification prefectorale - CAMS Radiation DNI. Seed des
series CAMS Radiation DNI all-sky mensuel **recent 2021-2023** pour les **28
nouvelles communes chef-lieu**, depuis le seed committe DENSIFICATION
(``cams_radiation_2021_2023_densification_seed_data``, produit hors-ligne par
``scripts/preparer_seed_cams.py 2021 2023 --densification``).

C'est la 2e reference d'ecart inter-source ajoutee aux nouveaux points (apres
SARAH-3 GHI). Avec NASA daily DNI deja en base (2021-2025), l'ecart
DNI NASA vs CAMS devient calculable aux 33 sur la fenetre 2021-2023 = couche atlas
(le triptyque NASA / SARAH-3 / CAMS coexiste). Le calcul formel de l'ecart vient
ensuite ; ici on pose le substrat.

Perimetre : 28 communes x 1 grandeur (DNI) = **28 series** ; CAMS = DNI seul,
36 mois (2021-2023) -> **1 008 mesures** (28 x 36, jeu CAMS fige, deterministe).

Pattern NE-OFFLINE (comme EAC4 / migration 073) : pas de seam d'ingestion ; la
migration lit directement le seed committe (aucun ``cdsapi`` ni reseau au runtime,
discipline alpha). **Seed DENSIFICATION SEPARE** du seed 6-pilotes : la migration
073 (immuable) itere tout son seed, on ne doit donc pas y injecter les communes.

Naming des series : ``gin_<slug>_dni_cams_2021_2023``. ``granularite='mensuel'``, source
``cams_radiation`` (070), methode satellitaire, confiance B. Caveat conserve
en metadonnees (CAMS DNI all-sky sur-estime le DNI decompose +28 %, signal de
reference d'ecart, pas une mesure primaire).

Bornes : 28 communes seulement ; les 6 pilotes gardent leurs series (073 immuable,
ZERO retrofit). Climato 2004-2020 (071) inchangee. Pas de SARAH-3 (deja fait).
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date
from typing import Any

import sqlalchemy as sa
from alembic import op

from kuma_data_core.db.seeds.cams_radiation_2021_2023_densification_seed_data import (
    CAMS_DNI_MENSUEL_2021_2023_DENSIFICATION_SEED,
)
from kuma_data_core.db.seeds.localites_prefectures_seed_data import PREFECTURES_GUINEE

# revision identifiers, used by Alembic.
revision: str = "089"
down_revision: str | Sequence[str] | None = "088"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# === 28 communes cibles (code -> nom) =====================================
_NOM_PAR_COMMUNE: dict[str, str] = {
    p["commune_code"]: p["nom"] for p in PREFECTURES_GUINEE if p["existante"] is None
}
_COMMUNES: tuple[str, ...] = tuple(_NOM_PAR_COMMUNE)

_GRANDEUR = "dni"
_SOURCE_CODE = "cams_radiation"
_AN_DEBUT, _AN_FIN = 2021, 2023
_PERIODE_DEBUT = date(2021, 1, 1)
_PERIODE_FIN = date(2023, 12, 31)
_GRANULARITE = "mensuel"
_METHODE_COLLECTE = "modele_satellitaire"
_DATASET_URL = "https://ads.atmosphere.copernicus.eu/datasets/cams-solar-radiation-timeseries"

_COMMENTAIRE_TEMPLATE = (
    "Serie CAMS Radiation DNI all-sky mensuel 2021-2023 (recent), {ville} (chef-lieu "
    "de prefecture), Guinee. DNI direct normal aerosol-corrige (BNI, methode "
    "Heliosat-4), ciel reel (all-sky). Conversion Wh/m2/mois -> kWh/m2/jour. "
    "Densification Etape 1 Groupe B lot B-2b : reference d'ecart inter-source (vs NASA "
    "DNI) sur la fenetre 2021-2023 -> couche atlas. Caveat D-71 : CAMS DNI all-sky "
    "sur-estime le DNI decompose (+28 %), signal de reference d'ecart et non mesure "
    "primaire. Niveau de confiance B. Attribution : Generated using Copernicus "
    "Atmosphere Monitoring Service Information 2026 (licence CC-BY, DOI 10.24381/5cab0912)."
)


def _code_serie(commune_code: str) -> str:
    """Convention naming : ``<commune>_dni_cams_2021_2023``."""
    return f"{commune_code}_{_GRANDEUR}_cams_{_AN_DEBUT}_{_AN_FIN}"


def _tous_codes_series() -> list[str]:
    return [_code_serie(c) for c in _COMMUNES]


def upgrade() -> None:
    bind = op.get_bind()

    # === 1. Resolution localite_id des 28 communes =========================
    rows = bind.execute(
        sa.text("SELECT code, id FROM localites WHERE code = ANY(:codes)"),
        {"codes": list(_COMMUNES)},
    ).all()
    localite_id: dict[str, int] = {r.code: int(r.id) for r in rows}
    manquantes = set(_COMMUNES) - localite_id.keys()
    if manquantes:
        raise RuntimeError(
            f"Migration 089 : commune(s) introuvable(s) : {sorted(manquantes)}. "
            f"Verifier la migration 085."
        )

    # === 2. Resolution source_id cams_radiation + verification grandeur ====
    source_id = bind.execute(
        sa.text("SELECT id FROM sources WHERE code = :code"),
        {"code": _SOURCE_CODE},
    ).scalar_one_or_none()
    if source_id is None:
        raise RuntimeError(
            f"Migration 089 : source {_SOURCE_CODE!r} introuvable. Verifier la migration 070."
        )
    grandeur_ok = bind.execute(
        sa.text("SELECT 1 FROM grandeurs_referentiel WHERE code = :c AND actif = TRUE"),
        {"c": _GRANDEUR},
    ).scalar_one_or_none()
    if grandeur_ok is None:
        raise RuntimeError(f"Migration 089 : grandeur {_GRANDEUR!r} introuvable/inactive.")

    # === 3. Seed des 28 series ============================================
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
    for commune_code in _COMMUNES:
        ville = _NOM_PAR_COMMUNE[commune_code]
        lignes_series.append(
            {
                "code": _code_serie(commune_code),
                "libelle": f"DNI CAMS Radiation mensuel {ville} 2021-2023",
                "localite_id": localite_id[commune_code],
                "grandeur_code": _GRANDEUR,
                "source_id": source_id,
                "periode_debut": _PERIODE_DEBUT,
                "periode_fin": _PERIODE_FIN,
                "granularite": _GRANULARITE,
                "methode_collecte": _METHODE_COLLECTE,
                "methode_collecte_doc": _DATASET_URL,
                "commentaire_editorial": _COMMENTAIRE_TEMPLATE.format(ville=ville),
                "url_documentation": _DATASET_URL,
            }
        )
    assert len(lignes_series) == 28, f"Attendu 28 series CAMS, obtenu {len(lignes_series)}"
    op.bulk_insert(series_table, lignes_series)

    serie_id_par_code: dict[str, int] = {
        r.code: int(r.id)
        for r in bind.execute(
            sa.text("SELECT code, id FROM series_metadonnees WHERE code = ANY(:codes)"),
            {"codes": _tous_codes_series()},
        ).all()
    }

    # === 4. Mesures depuis le seed densification (28 communes seulement) ===
    mensuelles_table = sa.table(
        "mesures_ressource_mensuelles",
        sa.column("serie_id", sa.BigInteger),
        sa.column("annee", sa.SmallInteger),
        sa.column("mois", sa.SmallInteger),
        sa.column("valeur", sa.Float),
        sa.column("niveau_confiance_derive", sa.String),
    )
    codes_attendus = set(_COMMUNES)
    lignes_mensuelles: list[dict[str, Any]] = []
    for r in CAMS_DNI_MENSUEL_2021_2023_DENSIFICATION_SEED:
        if r["localite_code"] not in codes_attendus:
            raise RuntimeError(
                f"Migration 089 : seed densification contient une localite hors perimetre "
                f"({r['localite_code']!r}). Re-generer le seed (--densification)."
            )
        lignes_mensuelles.append(
            {
                "serie_id": serie_id_par_code[_code_serie(r["localite_code"])],
                "annee": r["annee"],
                "mois": r["mois"],
                "valeur": r["valeur"],
                "niveau_confiance_derive": "B",
            }
        )
    assert len(lignes_mensuelles) == 1008, (
        f"Attendu 1 008 mesures CAMS (28 x 36), obtenu {len(lignes_mensuelles)}"
    )
    op.bulk_insert(mensuelles_table, lignes_mensuelles)

    op.execute(
        f"-- Migration 089 : 28 series CAMS Radiation DNI 2021-2023 (densification B-2b) + "
        f"{len(lignes_mensuelles)} mesures mensuelles (offline, seed densification)."
    )


def downgrade() -> None:
    codes_series = _tous_codes_series()
    op.execute(
        sa.text(
            "DELETE FROM mesures_ressource_mensuelles WHERE serie_id IN "
            "(SELECT id FROM series_metadonnees WHERE code = ANY(:codes))"
        ).bindparams(sa.bindparam("codes", value=codes_series))
    )
    op.execute(
        sa.text("DELETE FROM series_metadonnees WHERE code = ANY(:codes)").bindparams(
            sa.bindparam("codes", value=codes_series)
        )
    )
