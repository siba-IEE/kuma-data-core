"""ingerer_hep_6_villes

Revision ID: 027
Revises: 026
Create Date: 2026-05-12 11:00:00.000000+00:00

Ingestion HEP 6 villes pilotes. Pour chaque
série HEP ``gin_<ville>_hep_kuma_calculs_2021_2025`` (seedée 026), appel
à ``calculer_et_inserer_hep`` avec la série GHI amont
``gin_<ville>_ghi_nasa_power_2021_2025``.

Décompte théorique : 390 lignes (6 villes × 65 = 1 annuel + 12 mensuels
× 5 ans). Décompte effectif dépend de la politique de complétude 100%
jours civils v1 : skip si une (annee) ou
(annee, mois) n'a pas exactement le nombre de jours civils attendus.

Vérification factuelle préalable : 6 villes
plage ``2021-01-01 → 2025-12-31`` toutes à 1826 / 1826 lignes courantes
GHI.

Pré-requis :

- table ``grandeurs_metier`` (migration 023) ;
- 6 séries HEP seedées (migration 026) ;
- 6 séries GHI ingérées en ``mesures_ressource`` (migrations 018 + 022) ;
- fonction ``calculer_et_inserer_hep`` (module
  ``kuma_data_core.services.grandeurs.hep``).
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.orm import Session

from kuma_data_core.services.grandeurs.hep import calculer_et_inserer_hep

# revision identifiers, used by Alembic.
revision: str = "027"
down_revision: str | Sequence[str] | None = "026"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# Énumération exhaustive des 6 correspondances
# (code_serie_hep, code_serie_ghi_amont) pour les 6 villes pilotes.
# Convention de naming : ``gin_<ville>_<grandeur>_<source>_<periode>``.
CORRESPONDANCES_HEP_GHI: tuple[tuple[str, str], ...] = (
    (
        "gin_conakry_hep_kuma_calculs_2021_2025",
        "gin_conakry_ghi_nasa_power_2021_2025",
    ),
    (
        "gin_kindia_hep_kuma_calculs_2021_2025",
        "gin_kindia_ghi_nasa_power_2021_2025",
    ),
    (
        "gin_mamou_hep_kuma_calculs_2021_2025",
        "gin_mamou_ghi_nasa_power_2021_2025",
    ),
    (
        "gin_labe_hep_kuma_calculs_2021_2025",
        "gin_labe_ghi_nasa_power_2021_2025",
    ),
    (
        "gin_kankan_hep_kuma_calculs_2021_2025",
        "gin_kankan_ghi_nasa_power_2021_2025",
    ),
    (
        "gin_nzerekore_hep_kuma_calculs_2021_2025",
        "gin_nzerekore_ghi_nasa_power_2021_2025",
    ),
)

CODES_SERIES_HEP_1_5: tuple[str, ...] = tuple(c[0] for c in CORRESPONDANCES_HEP_GHI)
"""Codes naturels des 6 séries HEP, exposés pour les tests d'intégration
et la cohérence du downgrade."""


def upgrade() -> None:
    bind = op.get_bind()
    session = Session(bind=bind)
    try:
        nb_annuel_total = 0
        nb_mensuel_total = 0
        annees_skip_global: list[tuple[str, tuple[int, ...]]] = []
        mois_skip_global: list[tuple[str, tuple[tuple[int, int], ...]]] = []

        for code_serie_hep, code_serie_ghi in CORRESPONDANCES_HEP_GHI:
            resultat = calculer_et_inserer_hep(
                session=session,
                code_serie_hep=code_serie_hep,
                code_serie_ghi_amont=code_serie_ghi,
                version_formule=1,
            )
            nb_annuel_total += resultat["nb_annuel_insere"]
            nb_mensuel_total += resultat["nb_mensuel_insere"]
            if resultat["annees_skip_completude"]:
                annees_skip_global.append((code_serie_hep, resultat["annees_skip_completude"]))
            if resultat["mois_skip_completude"]:
                mois_skip_global.append((code_serie_hep, resultat["mois_skip_completude"]))

        op.execute(
            f"-- Migration 027 : {nb_annuel_total} lignes HEP annuelles + "
            f"{nb_mensuel_total} lignes HEP mensuelles inserees dans "
            f"grandeurs_metier pour {len(CORRESPONDANCES_HEP_GHI)} villes "
            f"(total = {nb_annuel_total + nb_mensuel_total} lignes ; "
            f"theorique = 390)."
        )
        if annees_skip_global or mois_skip_global:
            op.execute(
                f"-- Migration 027 : politique de completude 100% jours "
                f"civils v1 a skipe les (annee) et (annee, mois) "
                f"suivantes : annees_skip={annees_skip_global!r}, "
                f"mois_skip={mois_skip_global!r}. Cf. spec 1-5 sec. 5.3."
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
        ).bindparams(sa.bindparam("codes", value=list(CODES_SERIES_HEP_1_5)))
    )
