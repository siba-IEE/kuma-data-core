"""seed_source_cams_radiation_vague4_lot_b

Revision ID: 070
Revises: 069
Create Date: 2026-06-16 10:00:00.000000+00:00

Seed de la source ``cams_radiation`` dans ``sources``.

Service de rayonnement solaire CAMS (Copernicus Atmosphere Monitoring Service),
**non anticipée** au seed initial des sources → créée ici. Fournit le **DNI
all-sky aérosol-corrigé** (``BNI``, méthode Heliosat-4) : 3ᵉ référence d'écart
inter-source (enjeu Harmattan), ferme l'avant-dernière case du critère
« solaire API-maximal ».

``doi`` = ``10.24381/5cab0912`` : DOI de catalogue ADS Copernicus, lu dans la
section « Citation and attribution » de la page dataset (capturé 2026-06-16,
corroboré par recherche web). Confirme le DOI laissé à vérifier au cadrage.

Licence **CC-BY** : l'attribution Copernicus/CAMS requise est portée dans le
``commentaire_editorial`` des séries (migration 071).

Pattern dupliqué de la migration 068 (``op.bulk_insert`` d'une ligne
``sources``). Downgrade : DELETE ciblé par ``code``.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "070"
down_revision: str | Sequence[str] | None = "069"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_CODE_SOURCE = "cams_radiation"

_SOURCE: dict[str, object] = {
    "code": _CODE_SOURCE,
    "titre": (
        "CAMS Radiation Service - solar radiation time-series "
        "(Copernicus Atmosphere Monitoring Service)"
    ),
    "auteurs": None,
    "organisation": "Copernicus Atmosphere Monitoring Service (CAMS) / ECMWF",
    "type_source": "base_donnees",
    "annee_publication": 2017,
    "date_consultation": date(2026, 6, 16),
    "url": "https://ads.atmosphere.copernicus.eu/datasets/cams-solar-radiation-timeseries",
    "doi": "10.24381/5cab0912",
    "isbn": None,
    "metadonnees": {
        "dataset_id": "cams-solar-radiation-timeseries",
        "store": "ADS (Atmosphere Data Store)",
        "methode": "Heliosat-4 (all-sky) + McClear (clear-sky)",
        "sky_type_ingere": "observed_cloud (all-sky)",
        "grandeur_ingeree": "BNI (DNI all-sky, aerosol-corrige)",
        "unite_source": "Wh/m2 integres sur le pas (StatisticalMeasure sum)",
        "pas_temporel_ingere": "1month (agregat mensuel natif)",
        "couverture_temporelle": "2004-02 a J-1 (Meteosat MSG/IODC)",
        "licence": "CC-BY (attribution Copernicus/CAMS requise)",
    },
    "fiabilite": "haute",
    "langue": "en",
    "notes": (
        "Service de rayonnement solaire CAMS (Copernicus Atmosphere Monitoring "
        "Service) : méthode Heliosat-4 pour le ciel réel (all-sky) et McClear "
        "pour le ciel clair, à partir des images Meteosat (MSG/IODC) et des "
        "champs d'aérosols / vapeur d'eau CAMS. Référence méthode : Qu et al. "
        "(2017), « Fast radiative transfer parameterisation for assessing the "
        "surface solar irradiance: the Heliosat-4 method », Meteorologische "
        "Zeitschrift 26(1), 33-57. DOI du dataset : 10.24381/5cab0912 (catalogue "
        "ADS Copernicus, section citation de la page dataset). Distribution ADS Copernicus. "
        "Attribution requise (CC-BY) : « Generated using Copernicus Atmosphere "
        "Monitoring Service Information 2026 ». Vague 4 Lot B : DNI all-sky "
        "aérosol-corrigé (BNI), 3ᵉ référence d'écart inter-source (enjeu "
        "Harmattan). Consulté le 2026-06-16."
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
