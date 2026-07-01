"""ingerer_mesures_ressource_conakry_ghi

Revision ID: 018
Revises: 017
Create Date: 2026-05-11 14:00:00.000000+00:00

Ingestion persistée snapshot Conakry GHI 2021-2025 depuis NASA POWER
(1825 lignes après skip sentinelles).

Consomme :
- ``kuma_data_core.ingestion.nasa_power_daily.ingerer_serie_daily``
  (couche service)
- ``kuma_data_core.external.nasa_power.fetch_daily`` (client API)

Pattern d'appel réseau dans une migration : assumé pour ce snapshot
historique. Tous les jours 2021-2025 sont
climat-quality à la date d'exécution (~mai 2026, frontière daily ≈
mois courant -2 mois).

Variable d'env ``KUMA_SKIP_NASA_POWER_INGESTION`` (truthy) court-circuite
l'appel réseau et fait un upgrade vide. Utile pour CI sans accès NASA
POWER : la migration upgrade succeed mais 0 lignes insérées. Le test
d'intégration peut soit (a) injecter cette variable + tester d'autres
mécaniques, soit (b) tester l'ingestion réelle via une fixture
``ingerer_serie_daily(..., httpx_client=MockTransport(...))``.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date

from alembic import op
from sqlalchemy import text
from sqlalchemy.orm import Session

from kuma_data_core.ingestion.nasa_power_daily import ingerer_serie_daily

# revision identifiers, used by Alembic.
revision: str = "018"
down_revision: str | Sequence[str] | None = "017"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# Configuration ingestion
_CODE_SERIE: str = "gin_conakry_ghi_nasa_power_2021_2025"
_PARAMETRE_NASA: str = "ALLSKY_SFC_SW_DWN"
_LATITUDE_CONAKRY_KALOUM: float = 9.50917
_LONGITUDE_CONAKRY_KALOUM: float = -13.71222
_PERIODE_DEBUT: date = date(2021, 1, 1)
_PERIODE_FIN: date = date(2025, 12, 31)


def upgrade() -> None:
    bind = op.get_bind()
    session = Session(bind=bind)
    try:
        nb_insere = ingerer_serie_daily(
            session=session,
            code_serie=_CODE_SERIE,
            parametre_nasa=_PARAMETRE_NASA,
            latitude=_LATITUDE_CONAKRY_KALOUM,
            longitude=_LONGITUDE_CONAKRY_KALOUM,
            periode_debut=_PERIODE_DEBUT,
            periode_fin=_PERIODE_FIN,
        )
        # Log via op.execute pour visibilité dans la sortie alembic
        op.execute(
            f"-- Migration 018 : {nb_insere} lignes inserees dans mesures_ressource "
            f"pour serie {_CODE_SERIE}"
        )
    finally:
        session.close()


def downgrade() -> None:
    op.execute(
        text(
            """
            DELETE FROM mesures_ressource
            WHERE serie_id IN (
                SELECT id FROM series_metadonnees WHERE code = :code
            )
            """
        ).bindparams(code=_CODE_SERIE)
    )
