"""seed_serie_et_mesures_dni_kankan_esmap_wapp_terrain_lite

Revision ID: 077
Revises: 076
Create Date: 2026-06-18 10:30:00.000000+00:00

Calage DNI - série + mesures **DNI sol horaire Kankan** (confiance A).

Prérequis du calage DNI (étape ultérieure, hors de cette migration) : ingérer le
**DNI mesuré** au sol, en miroir du GHI. Insère **1 série**
``gin_kankan_dni_esmap_wapp_2021_2023`` (DNI mesuré, **source ``esmap_wapp``
RÉUTILISÉE** - migration 074, pas de nouvelle source ; localité ``gin_kankan``)
et ses **17 520 mesures horaires** depuis le seed committé
``kankan_dni_esmap_wapp_2021_2023_seed_data.py`` (produit hors-ligne par
``scripts/preparer_seed_esmap_wapp.py kankan dni``). **Aucun réseau ici** :
``alembic upgrade head`` déterministe et offline.

DNI mesuré au **pyrhéliomètre Kipp & Zonen CHP1** (thermopile). Agrégation 1-min
→ horaire UTC hour-beginning, clamp des offsets nocturnes négatifs à 0, complétude
≥ 80 %. Plage 2021-10-18 → 2023-10-17.

**Confiance A** : ``niveau_confiance_derive='A'`` - dérivation **R3**
(``methode_collecte='mesure_directe'`` ET ``source.fiabilite='haute'`` → A).
Statut ``brut`` (défaut SQL) ; le QC BSRN volet DNI est appliqué en migration 078.

Pattern dupliqué de la migration 075 (GHI), grandeur ``dni``.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date, datetime
from typing import Any

import sqlalchemy as sa
from alembic import op

from kuma_data_core.db.seeds.kankan_dni_esmap_wapp_2021_2023_seed_data import (
    KANKAN_DNI_HORAIRE_2021_2023_SEED,
)

# revision identifiers, used by Alembic.
revision: str = "077"
down_revision: str | Sequence[str] | None = "076"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_LOCALITE_CODE = "gin_kankan"
_GRANDEUR = "dni"
_SOURCE_CODE_SQL = "esmap_wapp"
_CODE_SERIE = "gin_kankan_dni_esmap_wapp_2021_2023"

_PERIODE_DEBUT = date(2021, 10, 18)
_PERIODE_FIN = date(2023, 10, 17)
_METHODE_COLLECTE = "mesure_directe"
_NIVEAU_CONFIANCE = "A"  # R3 : mesure_directe + esmap_wapp (haute) -> A
_DATASET_URL = "https://energydata.info/dataset/guinea-solar-radiation-measurement-data"

_COMMENTAIRE_SERIE = (
    "Serie DNI sol mesure (station WAPP Kankan, EDG substation, 10.36465 N / "
    "-9.30466 E, 375 m), pyrheliometre thermopile Kipp & Zonen CHP1, pas 1 min "
    "agrege horaire UTC hour-beginning (moyenne [H:00,H+1:00), clamp nuit, "
    "completude >= 80 %). Recouvrement 2021-10-18 -> 2023-10-17. Confiance A "
    "(R3 : mesure directe sur source fiabilite haute). Co-localisee < 2 km du "
    "pilote gin_kankan -> prerequis du calage de biais DNI vs CAMS (etape "
    "ulterieure, hors de cette migration). Attribution : World Bank / ESMAP / "
    "WAPP (CC-BY-4.0)."
)


def upgrade() -> None:
    bind = op.get_bind()

    # === Étape 1 : résolution des IDs ====================================
    localite_id = bind.execute(
        sa.text("SELECT id FROM localites WHERE code = :code"),
        {"code": _LOCALITE_CODE},
    ).scalar_one_or_none()
    if localite_id is None:
        raise RuntimeError(f"Migration 077 : localite {_LOCALITE_CODE!r} introuvable.")

    source_id = bind.execute(
        sa.text("SELECT id FROM sources WHERE code = :code"),
        {"code": _SOURCE_CODE_SQL},
    ).scalar_one_or_none()
    if source_id is None:
        raise RuntimeError(
            f"Migration 077 : source {_SOURCE_CODE_SQL!r} introuvable (migration 074)."
        )

    grandeur_active = bind.execute(
        sa.text("SELECT code FROM grandeurs_referentiel WHERE code = :code AND actif = TRUE"),
        {"code": _GRANDEUR},
    ).scalar_one_or_none()
    if grandeur_active is None:
        raise RuntimeError(f"Migration 077 : grandeur {_GRANDEUR!r} inactive/absente.")

    # === Étape 2 : 1 série horaire ======================================
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
    op.bulk_insert(
        series_table,
        [
            {
                "code": _CODE_SERIE,
                "libelle": "DNI sol horaire Kankan (ESMAP/WAPP) 2021-2023",
                "localite_id": int(localite_id),
                "grandeur_code": _GRANDEUR,
                "source_id": int(source_id),
                "periode_debut": _PERIODE_DEBUT,
                "periode_fin": _PERIODE_FIN,
                "granularite": "horaire",
                "methode_collecte": _METHODE_COLLECTE,
                "methode_collecte_doc": _DATASET_URL,
                "commentaire_editorial": _COMMENTAIRE_SERIE,
                "url_documentation": _DATASET_URL,
            }
        ],
    )

    serie_id = bind.execute(
        sa.text("SELECT id FROM series_metadonnees WHERE code = :code"),
        {"code": _CODE_SERIE},
    ).scalar_one()

    # === Étape 3 : mesures horaires depuis le seed ======================
    horaires_table = sa.table(
        "mesures_ressource_horaires",
        sa.column("serie_id", sa.BigInteger),
        sa.column("instant_mesure", sa.DateTime(timezone=True)),
        sa.column("valeur", sa.Float),
        sa.column("niveau_confiance_derive", sa.String),
    )
    lignes: list[dict[str, Any]] = [
        {
            "serie_id": int(serie_id),
            "instant_mesure": datetime.fromisoformat(r["instant_mesure"]),
            "valeur": r["valeur"],
            "niveau_confiance_derive": _NIVEAU_CONFIANCE,
        }
        for r in KANKAN_DNI_HORAIRE_2021_2023_SEED
    ]
    if lignes:
        op.bulk_insert(horaires_table, lignes)

    op.execute(
        f"-- Migration 077 : serie {_CODE_SERIE} + {len(lignes)} mesures horaires "
        f"DNI sol Kankan confiance A (statut brut, QC en 078)."
    )


def downgrade() -> None:
    op.execute(
        sa.text(
            "DELETE FROM mesures_ressource_horaires WHERE serie_id IN "
            "(SELECT id FROM series_metadonnees WHERE code = :code)"
        ).bindparams(code=_CODE_SERIE)
    )
    op.execute(
        sa.text("DELETE FROM series_metadonnees WHERE code = :code").bindparams(code=_CODE_SERIE)
    )
