"""ingerer_productible_specifique_theorique_6_villes

Revision ID: 033
Revises: 032
Create Date: 2026-05-13 11:30:00.000000+00:00

Ingestion productible_specifique_theorique 6 villes pilotes.
Pour chaque ville, appel à
`calculer_et_inserer_productible_specifique_theorique` avec PR_théorique
par défaut = 0.8 (industry-standard conservateur). Consomme la série HEP
amont calculée (premier module à
consommer `grandeurs_metier` en amont).

Volume attendu : 6 villes × 13 lignes (1 annuel + 12 mensuels × 5 ans
héritées de HEP) = 78 lignes dans grandeurs_metier.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.orm import Session

from kuma_data_core.services.grandeurs.productible_specifique_theorique import (
    PR_THEORIQUE_DEFAUT,
    calculer_et_inserer_productible_specifique_theorique,
)

# revision identifiers, used by Alembic.
revision: str = "033"
down_revision: str | Sequence[str] | None = "032"
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


CODES_SERIES_PRODUCTIBLE: tuple[str, ...] = tuple(
    _code(loc, "productible_specifique_theorique", "kuma_calculs") for loc in _LOCALITES
)


def upgrade() -> None:
    bind = op.get_bind()
    session = Session(bind=bind)
    try:
        nb_annuel_total = 0
        nb_mensuel_total = 0
        for localite in _LOCALITES:
            resultat = calculer_et_inserer_productible_specifique_theorique(
                session=session,
                code_serie_productible=_code(
                    localite, "productible_specifique_theorique", "kuma_calculs"
                ),
                code_serie_hep_amont=_code(localite, "hep", "kuma_calculs"),
                pr_theorique=PR_THEORIQUE_DEFAUT,
                version_formule=1,
            )
            nb_annuel_total += resultat["nb_annuel_insere"]
            nb_mensuel_total += resultat["nb_mensuel_insere"]
        op.execute(
            f"-- Migration 033 : {nb_annuel_total} annuelles + "
            f"{nb_mensuel_total} mensuelles productible_specifique_theorique "
            f"pour 6 villes (total {nb_annuel_total + nb_mensuel_total} ; "
            f"theorique 78). PR_theorique applique = {PR_THEORIQUE_DEFAUT}."
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
        ).bindparams(sa.bindparam("codes", value=list(CODES_SERIES_PRODUCTIBLE)))
    )
