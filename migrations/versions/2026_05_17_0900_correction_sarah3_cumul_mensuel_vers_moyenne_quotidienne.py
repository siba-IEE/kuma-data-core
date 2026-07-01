"""correction_sarah3_cumul_mensuel_vers_moyenne_quotidienne

Revision ID: 044
Revises: 043
Create Date: 2026-05-17 09:00:00.000000+00:00

Migration corrective des 216 valeurs SARAH-3 historiques ingerees en
migration 041.

Bug d'agregation diagnostique empiriquement post-livraison :

- Le pipeline sarah3_monthly.py lisait le champ PVGIS H(h)_m en pensant
  qu'il s'agissait de la moyenne quotidienne mensuelle (kWh/m^2/jour).
- H(h)_m designe en realite le cumul mensuel total kWh/m^2/mois selon
  la documentation officielle PVGIS JRC (indice _m = pas de temps
  monthly, pas l'unite).
- Les 216 valeurs SARAH-3 historiques (6 villes x 12 mois x 3 ans
  2021-2023) ont ete stockees comme cumul mensuel sous un
  unite_code='kwh_par_m2_jour' errone.
- Validation empirique : Conakry-Kaloum 2022 moyenne 167.79 kWh/m^2/jour
  observee vs 5.5 attendu (NASA POWER meme localite meme annee = 5.25
  kWh/m^2/jour). Ratio = 30 = nombre de jours par mois.

Fix code applique dans le commit fix(ingestion) precedent :
H(h)_m / calendar.monthrange(annee, mois)[1] dans
_extraire_valeurs_mensuelles. Toutes les ingestions futures seront
correctes.

Cette migration corrige les valeurs historiques en place :

- upgrade : divise chaque valeur SARAH-3 par calendar.monthrange(annee,
  mois)[1] (gere les annees bissextiles).
- downgrade : multiplie par les memes facteurs pour reversibilite
  stricte.

Filtrage : sources.code = 'sarah3_monthly' (cf. migration 041 ligne
_SOURCE_SARAH3_CODE). 216 lignes attendues (6 villes x 36 mois).

Impact secondaire : les 216 ecart_relatif_referentiel inseres en
migration 042 consomment ces valeurs
SARAH-3. Recalcul correctif dans la migration 045 suivante.

Doctrine Alembic standard : execution unique trackee par
alembic_version. Implementation Python (pas SQL pur) pour lisibilite
de la gestion des bissextiles via la stdlib.
"""

from __future__ import annotations

import calendar
from collections.abc import Sequence

from alembic import op
from sqlalchemy import text

# revision identifiers, used by Alembic.
revision: str = "044"
down_revision: str | Sequence[str] | None = "043"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


_SOURCE_SARAH3_CODE: str = "sarah3_monthly"


def _appliquer_facteur(operation: str) -> None:
    """Recalcule les valeurs SARAH-3 en divisant ou multipliant par jours_du_mois.

    Args:
        operation : 'divide' pour upgrade (cumul -> moyenne quotidienne),
            'multiply' pour downgrade (moyenne quotidienne -> cumul).
    """
    conn = op.get_bind()
    rows = conn.execute(
        text(
            """
            SELECT m.id, m.annee, m.mois, m.valeur
            FROM mesures_ressource_mensuelles m
            JOIN series_metadonnees sm ON sm.id = m.serie_id
            JOIN sources s ON s.id = sm.source_id
            WHERE s.code = :source_code
            """
        ),
        {"source_code": _SOURCE_SARAH3_CODE},
    ).fetchall()

    nb_lignes = len(rows)
    if nb_lignes == 0:
        # Cas environnement test sans donnees SARAH-3 seedees : no-op.
        return

    for row in rows:
        nombre_jours = calendar.monthrange(int(row.annee), int(row.mois))[1]
        if operation == "divide":
            nouvelle_valeur = float(row.valeur) / nombre_jours
        elif operation == "multiply":
            nouvelle_valeur = float(row.valeur) * nombre_jours
        else:
            raise ValueError(f"Operation {operation!r} non supportee (attendu : divide/multiply)")

        conn.execute(
            text("UPDATE mesures_ressource_mensuelles SET valeur = :v WHERE id = :id"),
            {"v": nouvelle_valeur, "id": row.id},
        )

    op.execute(f"-- correction sarah3 1-7α : {nb_lignes} valeurs {operation}d par jours_du_mois")


def upgrade() -> None:
    """Divise les 216 valeurs SARAH-3 historiques par jours_du_mois.

    Conversion cumul kWh/m^2/mois -> moyenne quotidienne kWh/m^2/jour
    pour alignement avec unite_code='kwh_par_m2_jour'.
    """
    _appliquer_facteur("divide")


def downgrade() -> None:
    """Restaure les 216 valeurs SARAH-3 en cumul mensuel (multiplie par jours_du_mois).

    Reversibilite stricte de l'upgrade : valeur * calendar.monthrange(
    annee, mois)[1].
    """
    _appliquer_facteur("multiply")
