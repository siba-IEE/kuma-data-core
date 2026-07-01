"""ingerer_mesures_4_grandeurs_conakry

Revision ID: 020
Revises: 019
Create Date: 2026-05-11 15:30:00.000000+00:00

Ingestion des 4 nouvelles séries Conakry (DNI, DHI, T2M, RH2M) en 1 seul
appel NASA POWER multi-paramètres via ``ingerer_series_daily_groupe``.

Volume attendu : 4 séries × 1826 jours = 7304 lignes (modulo sentinelles
``-999.0`` filtrées). Avec les 1826 lignes GHI déjà ingérées en
migration 018, la table ``mesures_ressource`` atteint 9130 lignes.

**GHI Conakry n'est PAS réingéré ici** : la migration 018 l'a déjà fait,
réingérer provoquerait un conflit EXCLUDE BTree-GiST (double ligne
courante pour mêmes ``(serie_id, instant_mesure)``).

Variable d'env ``KUMA_SKIP_NASA_POWER_INGESTION`` court-circuite
l'appel réseau si truthy : upgrade succeed mais
``ingerer_series_daily_groupe`` retourne dict vide.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date

from alembic import op
from sqlalchemy import text
from sqlalchemy.orm import Session

from kuma_data_core.ingestion.nasa_power_daily import ingerer_series_daily_groupe

# revision identifiers, used by Alembic.
revision: str = "020"
down_revision: str | Sequence[str] | None = "019"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# Configuration ingestion
_CODES_SERIES_1_3: tuple[str, ...] = (
    "gin_conakry_dni_nasa_power_2021_2025",
    "gin_conakry_dhi_nasa_power_2021_2025",
    "gin_conakry_t2m_nasa_power_2021_2025",
    "gin_conakry_rh2m_nasa_power_2021_2025",
)

_MAPPING_GRANDEUR_PARAMETRE_NASA: dict[str, str] = {
    "dni": "ALLSKY_SFC_SW_DNI",
    "dhi": "ALLSKY_SFC_SW_DIFF",
    "t2m": "T2M",
    "rh2m": "RH2M",
}

_LATITUDE_CONAKRY_KALOUM: float = 9.50917
_LONGITUDE_CONAKRY_KALOUM: float = -13.71222
_PERIODE_DEBUT: date = date(2021, 1, 1)
_PERIODE_FIN: date = date(2025, 12, 31)


def upgrade() -> None:
    bind = op.get_bind()
    session = Session(bind=bind)
    try:
        decompte = ingerer_series_daily_groupe(
            session=session,
            codes_series=list(_CODES_SERIES_1_3),
            mapping_grandeur_parametre_nasa=_MAPPING_GRANDEUR_PARAMETRE_NASA,
            latitude=_LATITUDE_CONAKRY_KALOUM,
            longitude=_LONGITUDE_CONAKRY_KALOUM,
            periode_debut=_PERIODE_DEBUT,
            periode_fin=_PERIODE_FIN,
        )
        total = sum(decompte.values())
        op.execute(
            f"-- Migration 020 : {total} lignes inserees dans mesures_ressource "
            f"sur 4 series Conakry 1-3 (decompte par serie : {decompte})"
        )
    finally:
        session.close()


def downgrade() -> None:
    op.execute(
        text(
            """
            DELETE FROM mesures_ressource
            WHERE serie_id IN (
                SELECT id FROM series_metadonnees WHERE code = ANY(:codes)
            )
            """
        ).bindparams(codes=list(_CODES_SERIES_1_3))
    )
