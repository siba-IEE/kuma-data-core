"""ingerer_fraction_diffuse_6_villes

Revision ID: 031
Revises: 030
Create Date: 2026-05-13 10:30:00.000000+00:00

Ingestion fraction_diffuse 6 villes pilotes.
Pour chaque ville, appel à `calculer_et_inserer_fraction_diffuse`
avec les séries DHI et GHI amont déjà ingérées.

Volume attendu : 6 villes × 13 lignes (1 annuel + 12 mensuels × 5 ans)
= 78 lignes dans `grandeurs_metier`.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.orm import Session

from kuma_data_core.services.grandeurs.fraction_diffuse import (
    calculer_et_inserer_fraction_diffuse,
)

# revision identifiers, used by Alembic.
revision: str = "031"
down_revision: str | Sequence[str] | None = "030"
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


CODES_SERIES_FRACTION_DIFFUSE: tuple[str, ...] = tuple(
    _code(loc, "fraction_diffuse", "kuma_calculs") for loc in _LOCALITES
)


def upgrade() -> None:
    bind = op.get_bind()
    session = Session(bind=bind)
    try:
        nb_annuel_total = 0
        nb_mensuel_total = 0
        for localite in _LOCALITES:
            resultat = calculer_et_inserer_fraction_diffuse(
                session=session,
                code_serie_fraction_diffuse=_code(localite, "fraction_diffuse", "kuma_calculs"),
                code_serie_dhi_amont=_code(localite, "dhi", "nasa_power"),
                code_serie_ghi_amont=_code(localite, "ghi", "nasa_power"),
                version_formule=1,
            )
            nb_annuel_total += resultat["nb_annuel_insere"]
            nb_mensuel_total += resultat["nb_mensuel_insere"]
        op.execute(
            f"-- Migration 031 : {nb_annuel_total} annuelles + "
            f"{nb_mensuel_total} mensuelles fraction_diffuse pour 6 villes "
            f"(total {nb_annuel_total + nb_mensuel_total} ; theorique 78)."
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
        ).bindparams(sa.bindparam("codes", value=list(CODES_SERIES_FRACTION_DIFFUSE)))
    )
