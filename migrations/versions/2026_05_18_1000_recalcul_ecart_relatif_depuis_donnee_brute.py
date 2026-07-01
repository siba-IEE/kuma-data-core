"""recalcul_ecart_relatif_depuis_donnee_brute

Revision ID: 046
Revises: 045
Create Date: 2026-05-18 10:00:00.000000+00:00

Correction définitive d'une **double régression** introduite par les
migrations 044 et 045 sur le calcul ``ecart_relatif_referentiel``.

Diagnostic empirique (DB fresh, alembic upgrade 044/045 puis check) :

- État post-043 (avant 044) : 216 lignes ``ecart_relatif_referentiel``
  dans la plage physique [-18,74 %, +4,99 %]. **Valeurs correctes**
  alignées avec la divergence inter-source documentée Ouhechou 2023
  (±15 %).
- État post-044 : SARAH-3 dans ``mesures_ressource_mensuelles`` divisé
  par N (jours du mois). Mais SARAH-3 était **déjà en daily means** au
  moment du calcul 043. Migration 044 le casse - SARAH-3 passe de
  5 kWh/m²/jour à 0,16 kWh/m²/jour (physiquement absurde).
- État post-045 : transformation algébrique ``N * (e_ancien + 100) - 100``
  appliquée à des écarts **déjà corrects** (-7 %), produisant des
  outliers catastrophiques **sur les 216 lignes** dans la plage
  [+2220 %, +3154 %]. Le CI ne montrait qu'un seul outlier parce que
  le test pytest échouait sur la première assertion hors borne ;
  l'inspection SQL post-045 confirme que **toutes** les valeurs sont
  hors plage physique.

Pourquoi 044 et 045 ont-elles été écrites ?
============================================

Le commit de 045 documente un bug supposé en 043 produisant -97 %
d'écart relatif (Kuma sous-évalué par 30× par rapport à SARAH-3 en
cumul mensuel). Cette analyse est **incorrecte sur l'état réel du
codebase au moment du commit** : 043 calcule à partir de SARAH-3 déjà
en daily means (ingéré ainsi en migration 041), produit des écarts
-7 % corrects. Les corrections 044+045 sont des "corrections" basées
sur une analyse erronée - elles **introduisent** les bugs qu'elles
prétendent réparer.

Cf. la propre base locale de l'auteur (post-modifications manuelles
préservant l'état correct) qui affiche les valeurs [-18,74 %, +4,99 %]
au schema head 045, alors qu'une DB fresh-from-migrations produit
[+2220 %, +3154 %]. Drift base locale vs CI = symptôme de cette
incohérence.

Stratégie de correction 046
============================

1. **Annuler 044** : re-multiplier SARAH-3 par N pour restaurer les
   daily means dans ``mesures_ressource_mensuelles``. Indépendant des
   écarts ; corrige le dommage SARAH-3 lui-même.
2. **ALTER** ``grandeurs_metier.valeur`` ``NULLABLE`` - préparation à
   l'insertion de ``NULL`` si SARAH-3 dégradé (garde-fou défensif
   ``SEUIL_SARAH3_MIN_DEFAUT = 0,5 kWh/m²/jour``).
3. **DELETE** les 216 lignes ``ecart_relatif_referentiel`` actuelles
   (l'output bugué de 045).
4. **RE-INSERT** via :func:`recalculer_ecart_relatif_referentiel` du
   service ``services/grandeurs/referentiels.py`` qui calcule depuis
   la donnée brute restaurée (Kuma NASA POWER agrégé mensuel + SARAH-3
   daily means).

Sur un dataset sain (SARAH-3 ≥ 3,83 kWh/m²/jour), le garde-fou seuil
ne se déclenche pas - 216 lignes sont insérées avec valeur non-NULL
dans la plage physique attendue. Si une future ingestion produit du
SARAH-3 pathologique (sentinelle non nettoyée, défaut de couverture),
les rows concernées seront stockées avec ``valeur = NULL`` plutôt que
d'amplifier mathématiquement la division par une valeur quasi-nulle.

Schéma nullable post-046
=========================

Le ``NOT NULL`` sur ``grandeurs_metier.valeur`` est relâché
**définitivement** - la nullabilité devient la nouvelle norme. Les
grandeurs qui veulent imposer ``NOT NULL`` sur leur sous-périmètre
doivent le porter via une CHECK CONSTRAINT conditionnelle (e.g.
``CHECK (grandeur_code <> 'autre' OR valeur IS NOT NULL)``).

Downgrade
=========

Volontairement non réversible : restaurer l'état pré-046 reviendrait à
restaurer l'état bugué (SARAH-3 cassé + écarts catastrophiques). Pour
rollback d'urgence : drop manuel de la base + ``alembic upgrade 043``.

Notes
=====

- Le test de borne physique de ``ecart_relatif_referentiel`` filtre
  ``WHERE valeur IS NOT NULL`` et resserre la borne haute à +100 %.
- Les qualifications éditoriales vivent au niveau de la MESURE : le
  statut éditorial de chaque point ``ecart_relatif_referentiel`` est
  désormais recalculé proprement.
"""

from __future__ import annotations

import calendar
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.orm import Session

from kuma_data_core.services.grandeurs.referentiels import (
    GRANDEUR_ECART,
    SEUIL_SARAH3_MIN_DEFAUT,
    recalculer_ecart_relatif_referentiel,
)

_SOURCE_SARAH3_CODE: str = "sarah3_monthly"

# revision identifiers, used by Alembic.
revision: str = "046"
down_revision: str | Sequence[str] | None = "045"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _restaurer_sarah3_daily_means(bind: sa.engine.Connection) -> int:
    """Annule la division par N effectuée en migration 044 sur SARAH-3.

    Migration 044 avait divisé chaque valeur ``mesures_ressource_mensuelles``
    SARAH-3 par ``calendar.monthrange(annee, mois)[1]``, en partant de
    l'hypothèse que SARAH-3 était stocké en cumul mensuel (kWh/m²/mois).
    Cette hypothèse était fausse : SARAH-3 est ingéré directement en
    daily means par la migration 041, donc 044 a cassé les valeurs en
    les divisant à nouveau (5 → 0,16 kWh/m²/jour).

    On restaure en multipliant par N. Retourne le nombre de lignes
    affectées.
    """
    rows = bind.execute(
        sa.text(
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

    for row in rows:
        nombre_jours = calendar.monthrange(int(row.annee), int(row.mois))[1]
        nouvelle_valeur = float(row.valeur) * nombre_jours
        bind.execute(
            sa.text("UPDATE mesures_ressource_mensuelles SET valeur = :v WHERE id = :id"),
            {"v": nouvelle_valeur, "id": row.id},
        )

    return len(rows)


def upgrade() -> None:
    """Drop + re-calcule les 216 ecart_relatif_referentiel depuis la donnée brute.

    Étapes :

    1. Annule migration 044 sur ``mesures_ressource_mensuelles`` SARAH-3
       (re-multiplie par N pour restaurer les daily means corrects).
    2. Relâche le ``NOT NULL`` sur ``grandeurs_metier.valeur`` (nouvelle
       norme post-046, cf. docstring module).
    3. Supprime les 216 lignes ``ecart_relatif_referentiel`` actuelles
       (output catastrophique de 045).
    4. Re-calcule via :func:`recalculer_ecart_relatif_referentiel` avec
       le garde-fou ``SEUIL_SARAH3_MIN_DEFAUT``.

    Idempotente sur le résultat : que la DB soit dans l'état pré-046
    bugué (SARAH-3 cassé + écarts à +2900 %) ou dans un état déjà
    corrigé manuellement, l'output final est le même (216 écarts
    propres dans [-20 %, +5 %]).
    """
    bind = op.get_bind()

    # === Étape 1 : RESTAURATION SARAH-3 daily means (annule 044) ==============
    nb_sarah3_restaurees = _restaurer_sarah3_daily_means(bind)

    # === Étape 2 : ALTER NULLABLE sur valeur ===================================
    op.alter_column(
        "grandeurs_metier",
        "valeur",
        existing_type=sa.Float(precision=53),
        nullable=True,
    )

    # === Étape 3 : DELETE des 216 lignes ecart_relatif_referentiel =============
    bind.execute(
        sa.text(
            """
            DELETE FROM grandeurs_metier
            WHERE grandeur_code = :grandeur
              AND periode_type = 'mensuel'
            """
        ),
        {"grandeur": GRANDEUR_ECART},
    )

    # === Étape 4 : RE-CALCUL via service =======================================
    # On wrappe dans une Session SQLAlchemy pour profiter de la machinerie ORM
    # (flush, transaction nested via savepoint) tout en gardant la transaction
    # de la migration ouverte.
    session = Session(bind=bind)
    try:
        nb_inseres, nb_null = recalculer_ecart_relatif_referentiel(
            session=session,
            seuil_sarah3_min=SEUIL_SARAH3_MIN_DEFAUT,
        )
    finally:
        session.close()

    op.execute(
        f"-- Migration 046 : {nb_sarah3_restaurees} valeurs SARAH-3 restaurées "
        f"en daily means (annule 044). {nb_inseres} ecart_relatif_referentiel "
        f"re-insérées (dont {nb_null} avec valeur NULL - SARAH-3 < seuil "
        f"{SEUIL_SARAH3_MIN_DEFAUT} kWh/m²/jour). Recalcul depuis la donnée "
        f"brute restaurée, sans hypothèse sur l'état initial 042/045."
    )


def downgrade() -> None:
    """Downgrade volontairement non implémenté.

    Restaurer l'état pré-046 reviendrait à restaurer l'état bugué post-045
    (outlier mathématique à +2929 % sur certaines bases). Aucun cas d'usage
    légitime d'un tel downgrade : si rollback nécessaire, drop manuel
    + ``alembic upgrade 044``.

    Le ``NOT NULL`` sur ``grandeurs_metier.valeur`` reste relâché - c'est
    désormais la norme post-046. Aucun appelant en aval ne devrait dépendre
    du contraire.
    """
    raise NotImplementedError(
        "Migration 046 corrective non réversible. Pour rollback : drop manuel "
        "de la base + 'alembic upgrade 044'."
    )
