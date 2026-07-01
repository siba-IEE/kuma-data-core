"""recalcul_ecart_relatif_referentiel_post_correction_sarah3

Revision ID: 045
Revises: 044
Create Date: 2026-05-17 09:30:00.000000+00:00

Migration corrective des 216 valeurs ecart_relatif_referentiel
calculees en migration 042 a partir de
valeurs SARAH-3 elles-memes erronees (cumul mensuel kWh/m^2/mois
au lieu de moyenne quotidienne kWh/m^2/jour), corrigees en
migration 044 precedente.

Bug de propagation :

- La formule ecart_relatif_referentiel s'ecrit
  ``e = (kuma - sarah3) / sarah3 * 100`` (cf.
  services/grandeurs/referentiels.py:_calcul_ecart_relatif ligne 121).
- Avec sarah3 = cumul mensuel (168) et kuma = moyenne quotidienne
  (5.5), les ecarts calcules etaient artificiellement enormes
  (-97%) au lieu des -6% physiquement attendus.

Strategie de recalcul : transformation algebrique inline, sans
re-execution du service Python.

Demonstration :

- Soit s = valeur SARAH-3 ancienne (cumul mensuel kWh/m^2/mois).
- Soit s' = s / N la nouvelle valeur (moyenne quotidienne) avec
  N = calendar.monthrange(annee, mois)[1] (cf. migration 044).
- Soit k = valeur Kuma (inchangee, moyenne quotidienne deja correcte).

Ancien ecart_relatif :  e_ancien = (k - s) / s * 100
                                 = k/s * 100 - 100
Nouvel ecart_relatif :  e_nouveau = (k - s') / s' * 100
                                  = (k - s/N) / (s/N) * 100
                                  = (kN - s) / s * 100
                                  = N * (k/s * 100) - 100
                                  = N * (e_ancien + 100) - 100

Verification numerique (Conakry janvier 2022) :

- k = 5.25, s_ancien = 175.20 (cumul mensuel NASA-equivalent),
  e_ancien = (5.25 - 175.20) / 175.20 * 100 = -97.00%.
- N_janvier = 31, e_nouveau = 31 * (-97.00 + 100) - 100
            = 31 * 3.00 - 100 = -7.00%.
- Verification directe : s' = 175.20 / 31 = 5.65,
  e = (5.25 - 5.65) / 5.65 * 100 = -7.08%. (Concordance.)

Filtrage : grandeurs_metier WHERE grandeur_code =
'ecart_relatif_referentiel' AND periode_type = 'mensuel'. 216 lignes
attendues (6 villes x 36 mois 2021-2023, plage de chevauchement
Kuma/SARAH-3).

Doctrine Alembic standard : execution unique trackee par
alembic_version. Implementation Python (pas SQL pur) pour lisibilite
de la formule transformee et de la gestion bissextiles via stdlib.

Refs : migrations 042 (calcul initial), 044 (correction valeurs
SARAH-3 sources).
"""

from __future__ import annotations

import calendar
from collections.abc import Sequence

from alembic import op
from sqlalchemy import text

# revision identifiers, used by Alembic.
revision: str = "045"
down_revision: str | Sequence[str] | None = "044"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


_GRANDEUR_ECART: str = "ecart_relatif_referentiel"


def _appliquer_transformation(operation: str) -> None:
    """Recalcule les valeurs ecart_relatif_referentiel via transformation algebrique.

    Args:
        operation : 'upgrade' applique e' = N * (e + 100) - 100
            (correspond a la division SARAH-3 par N en migration 044),
            'downgrade' applique e = (e' + 100) / N - 100
            (inverse stricte).
    """
    conn = op.get_bind()
    rows = conn.execute(
        text(
            """
            SELECT id, annee_debut, mois, valeur
            FROM grandeurs_metier
            WHERE grandeur_code = :grandeur_code
              AND periode_type = 'mensuel'
            """
        ),
        {"grandeur_code": _GRANDEUR_ECART},
    ).fetchall()

    nb_lignes = len(rows)
    if nb_lignes == 0:
        # Cas environnement test sans referentiels seedes : no-op.
        return

    for row in rows:
        if row.mois is None:
            # Garde-fou : periode_type='mensuel' impose mois NOT NULL
            # par contrainte CK ck_grandeurs_metier_periode_coherente.
            # Cette branche est defensive uniquement.
            continue
        nombre_jours = calendar.monthrange(int(row.annee_debut), int(row.mois))[1]
        ancienne_valeur = float(row.valeur)
        if operation == "upgrade":
            nouvelle_valeur = nombre_jours * (ancienne_valeur + 100.0) - 100.0
        elif operation == "downgrade":
            nouvelle_valeur = (ancienne_valeur + 100.0) / nombre_jours - 100.0
        else:
            raise ValueError(f"Operation {operation!r} non supportee (attendu : upgrade/downgrade)")

        conn.execute(
            text("UPDATE grandeurs_metier SET valeur = :v WHERE id = :id"),
            {"v": nouvelle_valeur, "id": row.id},
        )

    op.execute(
        f"-- correction ecart_relatif_referentiel 1-7β : "
        f"{nb_lignes} valeurs {operation}d (transformation algebrique post-sarah3)"
    )


def upgrade() -> None:
    """Recalcule les 216 ecart_relatif_referentiel via N * (e + 100) - 100.

    Compense l'erreur historique liee aux valeurs SARAH-3 brutes
    erronees (cumul au lieu de moyenne quotidienne), corrigees en
    migration 044 sur mesures_ressource_mensuelles.
    """
    _appliquer_transformation("upgrade")


def downgrade() -> None:
    """Restaure les valeurs ecart_relatif_referentiel pre-correction.

    Operation inverse stricte : e = (e' + 100) / N - 100. A executer
    de pair avec le downgrade de la migration 044 pour coherence
    SARAH-3.
    """
    _appliquer_transformation("downgrade")
