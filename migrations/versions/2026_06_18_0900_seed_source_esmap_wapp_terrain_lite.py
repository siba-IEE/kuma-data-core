"""seed_source_esmap_wapp_terrain_lite

Revision ID: 074
Revises: 073
Create Date: 2026-06-18 09:00:00.000000+00:00

Terrain-lite GHI - seed de la source ``esmap_wapp`` dans ``sources``.

Campagne de mesures sol **ESMAP/WAPP** « Solar Development in Sub-Saharan Africa /
Solar resource measurement campaign in West Africa » (World Bank / EEEOA-WAPP,
opérateur CSP Services GmbH). Stations météo automatiques **Tier-1** mesurant
GHI/DNI/DHI + météo au pas 1 minute. Première source en appui de la **couche
confiance A** (mesure sol), cf. note ``calage-terrain-solaire.md`` (actée).

Licence **CC-BY-4.0** (vérifiée [web] energydata.info, jeu Guinée, 2026-06-17) :
attribution standard, aucune restriction supplémentaire. L'attribution requise est
portée dans le ``commentaire_editorial`` des séries (migration 075) et ci-dessous.

``annee_publication`` laissée **NULL** : année de publication du jeu non confirmée
par source autoritaire (rapports d'installation 2021, de mesure 2022 & final 2024)
- **non inventée** (cf. ``metadonnees.annee_publication_statut``).

La confiance A n'est **pas** un champ de ``sources`` : elle est **dérivée** (règle
R3 : ``methode_collecte='mesure_directe'`` ET ``fiabilite='haute'`` → A). La source
ne porte que ``fiabilite='haute'``.

Pattern dupliqué de la migration 070 (``op.bulk_insert`` d'une ligne ``sources``).
Downgrade : DELETE ciblé par ``code``.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "074"
down_revision: str | Sequence[str] | None = "073"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_CODE_SOURCE = "esmap_wapp"

_SOURCE: dict[str, object] = {
    "code": _CODE_SOURCE,
    "titre": (
        "ESMAP/WAPP - Solar resource measurement campaign in West Africa "
        "(stations sol Tier-1, Solar Development in Sub-Saharan Africa)"
    ),
    "auteurs": None,
    "organisation": ("World Bank / ESMAP / WAPP (EEEOA) ; operateur CSP Services GmbH"),
    "type_source": "base_donnees",
    "annee_publication": None,  # [a confirmer] - non inventee (cf. metadonnees)
    "date_consultation": date(2026, 6, 17),
    "url": "https://energydata.info/dataset/guinea-solar-radiation-measurement-data",
    "doi": None,
    "isbn": None,
    "metadonnees": {
        "campagne": "Solar Development in Sub-Saharan Africa (ESMAP/WAPP)",
        "store": "energydata.info (World Bank Group)",
        "licence": "CC-BY-4.0",
        "operateur": "CSP Services GmbH",
        "stations_guinee": ["Kankan", "Tarambaly"],
        "instruments": "Kipp & Zonen CMP10 (GHI/DHI), CHP1 (DNI), NRG 40C/200M, Vaisala PTB110",
        "pas_temporel_source": "1 minute (UTC+0)",
        "grandeur_ingeree": "GHI (agrege horaire, terrain-lite Lot A)",
        "niveaux_qc_source": "donnees QC fournisseur (CSP Services)",
        "annee_publication_statut": "a confirmer (rapports 2021 install / 2022 / 2024 final)",
    },
    "fiabilite": "haute",
    "langue": "en",
    "notes": (
        "Campagne de mesures solaires au sol ESMAP/WAPP (World Bank / West "
        "African Power Pool), stations meteorologiques automatiques Tier-1 "
        "(operateur CSP Services GmbH) mesurant GHI/DNI/DHI + meteo au pas "
        "1 minute. Deux stations en Guinee : Kankan (10.36465 N / -9.30466 E, "
        "375 m, co-localisee < 2 km du pilote gin_kankan) et Tarambaly "
        "(11.356 N / -12.137 W, 860 m, Fouta-Djalon 16 km de Labe). Pyrheliometre "
        "DNI thermopile CHP1, pyranometres CMP10 GHI/DHI (Kipp & Zonen). Licence "
        "CC-BY-4.0 (energydata.info, jeu Guinee, consulte le 2026-06-17). "
        "Attribution requise : « World Bank / ESMAP / WAPP - Solar resource "
        "measurement campaign in West Africa (CC-BY-4.0) ». Source en appui de la "
        "couche confiance A (mesure sol) : terrain-lite GHI Lot A, premiere "
        "grandeur Kuma en confiance A via la regle R3. Annee de publication du jeu "
        "a confirmer (non inventee)."
    ),
}


def upgrade() -> None:
    sources_table = sa.table(
        "sources",
        sa.column("code", sa.String),
        sa.column("titre", sa.Text),
        sa.column("auteurs", postgresql.ARRAY(sa.Text)),
        sa.column("organisation", sa.String),
        sa.column("type_source", sa.String),
        sa.column("annee_publication", sa.Integer),
        sa.column("date_consultation", sa.Date),
        sa.column("url", sa.Text),
        sa.column("doi", sa.String),
        sa.column("isbn", sa.String),
        sa.column("metadonnees", postgresql.JSONB),
        sa.column("fiabilite", sa.String),
        sa.column("langue", sa.String),
        sa.column("notes", sa.Text),
    )
    op.bulk_insert(sources_table, [_SOURCE])


def downgrade() -> None:
    op.execute(sa.text("DELETE FROM sources WHERE code = :code").bindparams(code=_CODE_SOURCE))
