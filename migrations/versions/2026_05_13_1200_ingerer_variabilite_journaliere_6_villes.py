"""ingerer_variabilite_journaliere_6_villes

Revision ID: 034
Revises: 033
Create Date: 2026-05-13 12:00:00.000000+00:00

Ingestion variabilite_journaliere 6 villes pilotes. Pour
chaque ville, appel à `calculer_et_inserer_variabilite_journaliere` avec
la série GHI amont. Périodicité annuelle uniquement (CoV non robuste
statistiquement sur 28-31 jours).

Volume attendu : 6 villes × 5 lignes annuelles = 30 lignes dans
grandeurs_metier.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.orm import Session

from kuma_data_core.services.grandeurs.variabilite_journaliere import (
    calculer_et_inserer_variabilite_journaliere,
)

# revision identifiers, used by Alembic.
revision: str = "034"
down_revision: str | Sequence[str] | None = "033"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


_LOCALITES: tuple[str, ...] = (
    "gin_conakry_kaloum",
    "gin_kankan",
    "gin_kindia",
    "gin_labe",
    "gin_mamou",
    "gin_nzerekore",
)


def _prefixe_ville_pour_serie(localite_code: str) -> str:
    """Préfixe ville pour code série (cf. migration 028)."""
    if localite_code == "gin_conakry_kaloum":
        return "gin_conakry"
    return localite_code


def _code(localite: str, grandeur: str, source: str) -> str:
    return f"{_prefixe_ville_pour_serie(localite)}_{grandeur}_{source}_2021_2025"


CODES_SERIES_VARIABILITE: tuple[str, ...] = tuple(
    _code(loc, "variabilite_journaliere", "kuma_calculs") for loc in _LOCALITES
)


def upgrade() -> None:
    bind = op.get_bind()
    session = Session(bind=bind)
    try:
        nb_annuel_total = 0
        for localite in _LOCALITES:
            resultat = calculer_et_inserer_variabilite_journaliere(
                session=session,
                code_serie_variabilite=_code(localite, "variabilite_journaliere", "kuma_calculs"),
                code_serie_ghi_amont=_code(localite, "ghi", "nasa_power"),
                version_formule=1,
            )
            nb_annuel_total += resultat["nb_annuel_insere"]
        op.execute(
            f"-- Migration 034 : {nb_annuel_total} annuelles "
            f"variabilite_journaliere (CoV) pour 6 villes (theorique 30, "
            f"annuel uniquement)."
        )
    finally:
        session.close()


def downgrade() -> None:
    op.execute(
        sa.text(
            """
            DELETE FROM grandeurs_metier
            WHERE series_metadonnees_id IN (
                SELECT id FROM series_metadonnees WHERE code = ANY(:codes)
            )
            """
        ).bindparams(sa.bindparam("codes", value=list(CODES_SERIES_VARIABILITE)))
    )
