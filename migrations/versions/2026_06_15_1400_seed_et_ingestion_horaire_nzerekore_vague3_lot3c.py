"""seed_et_ingestion_horaire_nzerekore_vague3_lot3c

Revision ID: 064
Revises: 063
Create Date: 2026-06-15 14:00:00.000000+00:00

Ingestion horaire pleine profondeur (2001-2023, 6
grandeurs) pour Nzerekore (``gin_nzerekore``). Clone du patron de la
migration 056, serie unique pleine profondeur par grandeur. Pixel
distinct (Guinee forestiere, sud-est).

Garde-fou d'ingestion de masse :
``KUMA_SKIP_INGESTION_MASSE_HORAIRE`` court-circuite la seule ingestion ;
les 6 series restent seedees. Volume : 138 appels NASA / 1,1 M lignes.
"""

from __future__ import annotations

import os
from collections.abc import Sequence
from datetime import date
from typing import Any

import sqlalchemy as sa
from alembic import op
from sqlalchemy.orm import Session

from kuma_data_core.ingestion.nasa_power_hourly import ingerer_serie_horaire

# revision identifiers, used by Alembic.
revision: str = "064"
down_revision: str | Sequence[str] | None = "063"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


_VARIABLE_ENV_SKIP_MASSE: str = "KUMA_SKIP_INGESTION_MASSE_HORAIRE"


def _skip_ingestion_masse() -> bool:
    return os.environ.get(_VARIABLE_ENV_SKIP_MASSE, "").strip().lower() in ("1", "true", "yes")


_LOCALITE_CODE: str = "gin_nzerekore"
_VILLE_LIBELLE: str = "Nzerekore"

_MAPPING_GRANDEURS: dict[str, str] = {
    "ghi": "ALLSKY_SFC_SW_DWN",
    "dni": "ALLSKY_SFC_SW_DNI",
    "dhi": "ALLSKY_SFC_SW_DIFF",
    "t2m": "T2M",
    "rh2m": "RH2M",
    "kt": "ALLSKY_KT",
}

_ANNEE_DEBUT: int = 2001
_ANNEE_FIN: int = 2023

_SOURCE_CODE_SQL: str = "nasa_power"
_METHODE_COLLECTE: str = "modele_satellitaire"
_METHODE_COLLECTE_DOC: str = "https://power.larc.nasa.gov/docs/methodology/"
_URL_DOCUMENTATION: str = "https://power.larc.nasa.gov/"
_GRANULARITE: str = "horaire"

_LIBELLES_GRANDEURS_SERIE: dict[str, str] = {
    "ghi": "GHI horaire brut",
    "dni": "DNI horaire brut",
    "dhi": "DHI horaire brut",
    "t2m": "Temperature 2m horaire brute",
    "rh2m": "Humidite relative 2m horaire brute",
    "kt": "Indice de clarte horaire brut",
}

_COMMENTAIRE_EDITORIAL_TEMPLATE: str = (
    "Serie horaire brute pleine profondeur inscrite en Phase 2 vague 3 "
    "lot 3c. Donnee {grandeur_upper} ingeree depuis NASA POWER endpoint "
    "hourly, parametre {parametre_nasa}, fenetre {annee_debut}-{annee_fin}, "
    "fuseau UTC. Methode satellitaire. Localite : {ville_libelle}, Guinee. "
    "Statut brut (non validee) : le QC algorithmique horaire (migration 065) "
    "fera passer les lignes valides en valide_auto. Niveau de confiance B "
    "(modele satellitaire)."
)


def _code_serie(grandeur_code: str) -> str:
    return f"{_LOCALITE_CODE}_{grandeur_code}_nasa_power_{_ANNEE_DEBUT}_{_ANNEE_FIN}"


def upgrade() -> None:
    bind = op.get_bind()

    ligne_localite = bind.execute(
        sa.text(
            "SELECT id, "
            "CAST(latitude AS DOUBLE PRECISION) AS lat, "
            "CAST(longitude AS DOUBLE PRECISION) AS lon "
            "FROM localites WHERE code = :code"
        ),
        {"code": _LOCALITE_CODE},
    ).first()
    if ligne_localite is None:
        raise RuntimeError(
            f"Migration 064 : localite {_LOCALITE_CODE!r} introuvable. "
            f"Verifier la migration 010 (seed 20 localites)."
        )
    localite_id = int(ligne_localite.id)
    latitude = float(ligne_localite.lat)
    longitude = float(ligne_localite.lon)

    source_id = bind.execute(
        sa.text("SELECT id FROM sources WHERE code = :code"),
        {"code": _SOURCE_CODE_SQL},
    ).scalar_one_or_none()
    if source_id is None:
        raise RuntimeError(
            f"Migration 064 : source_code {_SOURCE_CODE_SQL!r} introuvable. "
            f"Verifier la migration 012 (seed sources)."
        )

    codes_grandeurs = sorted(_MAPPING_GRANDEURS.keys())
    grandeurs_trouvees = set(
        bind.execute(
            sa.text(
                "SELECT code FROM grandeurs_referentiel WHERE code = ANY(:codes) AND actif = TRUE"
            ),
            {"codes": codes_grandeurs},
        )
        .scalars()
        .all()
    )
    grandeurs_manquantes = set(codes_grandeurs) - grandeurs_trouvees
    if grandeurs_manquantes:
        raise RuntimeError(
            f"Migration 064 : grandeur_code(s) introuvable(s) ou inactive(s) : "
            f"{sorted(grandeurs_manquantes)}. Les 6 brutes doivent etre actives."
        )

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
    for grandeur_code, parametre_nasa in _MAPPING_GRANDEURS.items():
        libelle = (
            f"{_LIBELLES_GRANDEURS_SERIE[grandeur_code]} {_VILLE_LIBELLE} "
            f"{_ANNEE_DEBUT}-{_ANNEE_FIN} (NASA POWER hourly, UTC)"
        )
        commentaire = _COMMENTAIRE_EDITORIAL_TEMPLATE.format(
            grandeur_upper=grandeur_code.upper(),
            parametre_nasa=parametre_nasa,
            annee_debut=_ANNEE_DEBUT,
            annee_fin=_ANNEE_FIN,
            ville_libelle=_VILLE_LIBELLE,
        )
        lignes_series.append(
            {
                "code": _code_serie(grandeur_code),
                "libelle": libelle,
                "localite_id": localite_id,
                "grandeur_code": grandeur_code,
                "source_id": source_id,
                "periode_debut": date(_ANNEE_DEBUT, 1, 1),
                "periode_fin": date(_ANNEE_FIN, 12, 31),
                "granularite": _GRANULARITE,
                "methode_collecte": _METHODE_COLLECTE,
                "methode_collecte_doc": _METHODE_COLLECTE_DOC,
                "commentaire_editorial": commentaire,
                "url_documentation": _URL_DOCUMENTATION,
            }
        )

    assert len(lignes_series) == 6, (
        f"Expected 6 series (6 grandeurs x 1 ville), got {len(lignes_series)}"
    )
    op.bulk_insert(series_metadonnees_table, lignes_series)

    if _skip_ingestion_masse():
        op.execute(
            f"-- Migration 064 : ingestion de masse court-circuitee "
            f"({_VARIABLE_ENV_SKIP_MASSE}). 6 series Nzerekore seedees, 0 mesure "
            f"ingeree. Ingestion reelle a executer manuellement (cf. dette D-64)."
        )
        return

    session = Session(bind=bind)
    try:
        decomptes_totaux: dict[str, int] = {}
        for grandeur_code, parametre_nasa in _MAPPING_GRANDEURS.items():
            code_serie = _code_serie(grandeur_code)
            n_lignes = ingerer_serie_horaire(
                session=session,
                code_serie=code_serie,
                parametre_nasa=parametre_nasa,
                latitude=latitude,
                longitude=longitude,
                annee_debut=_ANNEE_DEBUT,
                annee_fin=_ANNEE_FIN,
            )
            decomptes_totaux[code_serie] = n_lignes

        total = sum(decomptes_totaux.values())
        op.execute(
            f"-- Migration 064 : {total} lignes inserees dans "
            f"mesures_ressource_horaires (6 grandeurs x Nzerekore "
            f"{_ANNEE_DEBUT}-{_ANNEE_FIN}). Decompte par serie : {decomptes_totaux}"
        )
    finally:
        session.close()


def downgrade() -> None:
    codes_series = [_code_serie(grandeur_code) for grandeur_code in _MAPPING_GRANDEURS]
    op.execute(
        sa.text(
            """
            DELETE FROM mesures_ressource_horaires
            WHERE serie_id IN (
                SELECT id FROM series_metadonnees WHERE code = ANY(:codes)
            )
            """
        ).bindparams(sa.bindparam("codes", value=codes_series))
    )
    op.execute(
        sa.text("DELETE FROM series_metadonnees WHERE code = ANY(:codes)").bindparams(
            sa.bindparam("codes", value=codes_series)
        )
    )
