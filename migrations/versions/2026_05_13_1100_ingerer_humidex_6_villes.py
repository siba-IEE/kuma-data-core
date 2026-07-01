"""ingerer_humidex_6_villes

Revision ID: 032
Revises: 031
Create Date: 2026-05-13 11:00:00.000000+00:00

Ingestion humidex 6 villes pilotes. Pour chaque
ville, appel à `calculer_et_inserer_humidex` avec les séries T2M et
RH2M amont. Stockage humidex moyen annuel + mensuel (pas de
nb_jours_inconfort persisté).

Volume attendu : 6 villes × 13 lignes = 78 lignes dans grandeurs_metier.

Le compteur nb_jours_inconfort_modere (seuil 40 °C) est retourné par
chaque appel et loggé via op.execute('-- ...') pour traçabilité.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.orm import Session

from kuma_data_core.services.grandeurs.humidex import calculer_et_inserer_humidex

# revision identifiers, used by Alembic.
revision: str = "032"
down_revision: str | Sequence[str] | None = "031"
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


CODES_SERIES_HUMIDEX: tuple[str, ...] = tuple(
    _code(loc, "humidex", "kuma_calculs") for loc in _LOCALITES
)


def upgrade() -> None:
    bind = op.get_bind()
    session = Session(bind=bind)
    try:
        nb_annuel_total = 0
        nb_mensuel_total = 0
        nb_inconfort_par_ville: dict[str, dict[int, int]] = {}
        for localite in _LOCALITES:
            resultat = calculer_et_inserer_humidex(
                session=session,
                code_serie_humidex=_code(localite, "humidex", "kuma_calculs"),
                code_serie_t2m_amont=_code(localite, "t2m", "nasa_power"),
                code_serie_rh2m_amont=_code(localite, "rh2m", "nasa_power"),
                version_formule=1,
            )
            nb_annuel_total += resultat["nb_annuel_insere"]
            nb_mensuel_total += resultat["nb_mensuel_insere"]
            nb_inconfort_par_ville[localite] = resultat["nb_jours_inconfort_modere_par_annee"]
        op.execute(
            f"-- Migration 032 : {nb_annuel_total} annuelles + "
            f"{nb_mensuel_total} mensuelles humidex moyen pour 6 villes "
            f"(total {nb_annuel_total + nb_mensuel_total} ; theorique 78). "
            f"nb_jours_inconfort_modere par ville et annee : {nb_inconfort_par_ville!r}"
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
        ).bindparams(sa.bindparam("codes", value=list(CODES_SERIES_HUMIDEX)))
    )
