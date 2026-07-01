"""seed_source_ecmwf_era5_land_vague4_lot_a

Revision ID: 068
Revises: 067
Create Date: 2026-06-16 09:00:00.000000+00:00

Seed de la source ``ecmwf_era5_land`` dans ``sources``.

Source ERA5-Land (composante terrestre de la réanalyse ERA5, Copernicus C3S),
**anticipée explicitement** par la fiche ``ecmwf_era5`` du seed initial des
sources (« à acter comme source distincte ``ecmwf_era5_land`` ultérieurement »).
DOI mensuel ``10.24381/cds.68d2bb30`` (Muñoz-Sabater 2019). Grille API 0.1°
(11 km ; la grille native 9 km n'est pas servie par l'API CDS, cf.
investigation dediee).

Licence **CC-BY** (ex « Licence to use Copernicus Products », remplacée le
2025-07-02) : l'attribution Copernicus requise est portée dans le
``commentaire_editorial`` des séries (migration 069).

Pattern dupliqué de la migration 012 (``op.bulk_insert`` d'une ligne
``sources``). Downgrade : DELETE ciblé par ``code``.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "068"
down_revision: str | Sequence[str] | None = "067"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_CODE_SOURCE = "ecmwf_era5_land"

_SOURCE: dict[str, object] = {
    "code": _CODE_SOURCE,
    "titre": (
        "ECMWF ERA5-Land - Land component of the ERA5 reanalysis "
        "(Copernicus Climate Change Service)"
    ),
    "auteurs": None,
    "organisation": "European Centre for Medium-Range Weather Forecasts (ECMWF)",
    "type_source": "base_donnees",
    "annee_publication": 2019,
    "date_consultation": date(2026, 6, 16),
    "url": "https://cds.climate.copernicus.eu/datasets/reanalysis-era5-land",
    "doi": "10.24381/cds.68d2bb30",
    "isbn": None,
    "metadonnees": {
        "grille_api": "0.1deg_regulier",
        "resolution_native": "9km_TCo1279_non_servie_par_api",
        "couverture_temporelle": "1950-present",
        "forcage": "ERA5_interpole_MIR",
        "produits_utilises": ["monthly-means", "hourly (agrege en journalier)"],
        "licence": "CC-BY (ex Licence to use Copernicus Products, remplacee 2025-07-02)",
    },
    "fiabilite": "haute",
    "langue": "en",
    "notes": (
        "Réanalyse land-only haute résolution, replay de la composante terrestre "
        "d'ERA5 forcée par ERA5 (interpolation MIR depuis 2020). Référence : "
        "Muñoz-Sabater et al. (2021), « ERA5-Land: a state-of-the-art global "
        "reanalysis dataset for land applications », ESSD 13, 4349-4380, "
        "DOI 10.5194/essd-13-4349-2021. Distribution CDS Copernicus. Le DOI "
        "10.24381/cds.68d2bb30 cible le produit monthly-means ; le produit "
        "hourly (agrégé en journalier côté Kuma) porte un DOI distinct. "
        "Attribution requise (CC-BY) : « Generated using Copernicus Climate "
        "Change Service Information [Year] ». Vague 4 Lot A : co-localisation "
        "(D-29) et altitude (D-24) sur les 6 villes pilotes. Consulté le "
        "2026-06-16."
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
