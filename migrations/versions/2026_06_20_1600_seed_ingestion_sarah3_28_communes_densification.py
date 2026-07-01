"""seed_ingestion_sarah3_28_communes_densification

Revision ID: 088
Revises: 087
Create Date: 2026-06-20 16:00:00

Densification prefectorale - SARAH-3. Seed des series PVGIS
SARAH-3 ICDR (GHI mensuel 2021-2023) pour les **28 nouvelles communes chef-lieu**,
puis ingestion offline depuis le seed committe (``sarah3_monthly_seed_data``).

C'est la 1re reference d'ecart inter-source ajoutee aux nouveaux points : avec NASA
deja en base, l'ecart NASA vs SARAH-3 devient calculable aux 33 = la
couche atlas.

Perimetre : 28 communes x 1 grandeur (GHI) = **28 series** ; SARAH-3 = GHI seul,
36 mois (2021-2023) -> **1 008 mesures** (28 x 36, jeu ICDR fige, deterministe).

Ingestion offline (seam existant) : ``ingerer_serie_sarah3_monthly``
route par ``_fetch_sarah3_monthly_raw`` qui, sous ``KUMA_INGESTION_MODE=offline``,
lit le payload PVGIS committe au lieu de l'appel JRC. Cumul mensuel converti en
moyenne quotidienne (``calendar.monthrange``), comme pour les 6 pilotes.

Naming des series : ``gin_<slug>_ghi_sarah3_2021_2023`` (plage ICDR effective).
``granularite='mensuel'``, source ``sarah3_monthly``, methode satellitaire.

Bornes : 28 communes seulement ; les 6 pilotes gardent leurs series (041, immuable,
ZERO retrofit). Source ``sarah3_monthly`` deja seedee (041). Pas de CAMS.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date
from typing import Any

import sqlalchemy as sa
from alembic import op
from sqlalchemy.orm import Session

from kuma_data_core.db.seeds.localites_prefectures_seed_data import PREFECTURES_GUINEE
from kuma_data_core.ingestion.sarah3_monthly import ingerer_serie_sarah3_monthly

# revision identifiers, used by Alembic.
revision: str = "088"
down_revision: str | Sequence[str] | None = "087"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# === 28 communes cibles (code -> nom) =====================================
_NOM_PAR_COMMUNE: dict[str, str] = {
    p["commune_code"]: p["nom"] for p in PREFECTURES_GUINEE if p["existante"] is None
}
_COMMUNES: tuple[str, ...] = tuple(_NOM_PAR_COMMUNE)

_GRANDEUR_GHI: str = "ghi"
_SOURCE_CODE: str = "sarah3_monthly"
_ANNEE_DEBUT, _ANNEE_FIN = 2021, 2023
_GRANULARITE: str = "mensuel"
_METHODE_COLLECTE: str = "modele_satellitaire"
_METHODE_COLLECTE_DOC: str = "https://re.jrc.ec.europa.eu/pvg_static/methods.html"
_URL_DOCUMENTATION: str = "https://re.jrc.ec.europa.eu/api/v5_3/MRcalc"

_COMMENTAIRE_TEMPLATE: str = (
    "Serie GHI mensuelle PVGIS-SARAH3 ICDR (CM SAF/EUMETSAT, portage JRC), fenetre "
    "2021-2023 (plage ICDR effective D-38). Localite : {ville} (chef-lieu de "
    "prefecture), Guinee. Densification Etape 1 Groupe B lot B-2a : reference "
    "d'ecart inter-source (vs NASA) -> couche atlas. Niveau de confiance B."
)


def _code_serie(commune_code: str) -> str:
    """Convention naming : ``<commune>_ghi_sarah3_2021_2023``."""
    return f"{commune_code}_{_GRANDEUR_GHI}_sarah3_{_ANNEE_DEBUT}_{_ANNEE_FIN}"


def _tous_codes_series() -> list[str]:
    return [_code_serie(c) for c in _COMMUNES]


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
            f"Migration 088 : commune(s) introuvable(s) : {sorted(manquantes)}. "
            f"Verifier la migration 085."
        )

    # === 2. Resolution source_id sarah3_monthly + verification grandeur ====
    source_id = bind.execute(
        sa.text("SELECT id FROM sources WHERE code = :code"),
        {"code": _SOURCE_CODE},
    ).scalar_one_or_none()
    if source_id is None:
        raise RuntimeError(
            f"Migration 088 : source {_SOURCE_CODE!r} introuvable. Verifier la migration 041."
        )
    grandeur_ok = bind.execute(
        sa.text("SELECT 1 FROM grandeurs_referentiel WHERE code = :c AND actif = TRUE"),
        {"c": _GRANDEUR_GHI},
    ).scalar_one_or_none()
    if grandeur_ok is None:
        raise RuntimeError(f"Migration 088 : grandeur {_GRANDEUR_GHI!r} introuvable/inactive.")

    # === 3. Seed des 28 series ============================================
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
        lignes_series.append(
            {
                "code": _code_serie(commune_code),
                "libelle": f"GHI mensuel SARAH-3 {ville} 2021-2023 (PVGIS ICDR)",
                "localite_id": info_par_commune[commune_code]["id"],
                "grandeur_code": _GRANDEUR_GHI,
                "source_id": source_id,
                "periode_debut": date(_ANNEE_DEBUT, 1, 1),
                "periode_fin": date(_ANNEE_FIN, 12, 31),
                "granularite": _GRANULARITE,
                "methode_collecte": _METHODE_COLLECTE,
                "methode_collecte_doc": _METHODE_COLLECTE_DOC,
                "commentaire_editorial": _COMMENTAIRE_TEMPLATE.format(ville=ville),
                "url_documentation": _URL_DOCUMENTATION,
            }
        )

    assert len(lignes_series) == 28, f"Attendu 28 series SARAH-3, obtenu {len(lignes_series)}"
    op.bulk_insert(series_metadonnees_table, lignes_series)

    # === 4. Ingestion offline (1 appel par commune) =======================
    session = Session(bind=bind)
    try:
        total = 0
        for commune_code in _COMMUNES:
            info = info_par_commune[commune_code]
            total += ingerer_serie_sarah3_monthly(
                session=session,
                code_serie=_code_serie(commune_code),
                latitude=info["lat"],
                longitude=info["lon"],
                annee_debut=_ANNEE_DEBUT,
                annee_fin=_ANNEE_FIN,
            )
        op.execute(
            f"-- Migration 088 : {total} lignes inserees dans mesures_ressource_mensuelles "
            f"sur 28 communes x GHI SARAH-3 (densification B-2a, offline)."
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
