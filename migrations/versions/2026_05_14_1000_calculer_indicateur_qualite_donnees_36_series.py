"""calculer_indicateur_qualite_donnees_36_series

Revision ID: 038
Revises: 037
Create Date: 2026-05-14 10:00:00.000000+00:00

Calcul et insertion de l'`indicateur_qualite_donnees` (score 1-5) sur
les 36 séries brutes NASA POWER ingérées.

Pre-requis : migration 037 (etendre EXCLUDE par `series_metadonnees_id`)
appliquee - sans elle, l'insertion des 6 lignes par localite (1 par
brute evaluee) entre en collision sur `ex_grandeurs_metier_identite_periode`.

Pour chaque série brute identifiée par
``source_code = 'nasa_power' AND methode_collecte = 'modele_satellitaire'``,
appel à
:func:`kuma_data_core.services.grandeurs.indicateur_qualite_donnees.\
calculer_et_inserer_indicateur_qualite_donnees`
avec ``annee_debut=2021``, ``annee_fin=2025``, ``version_formule=1``.

Ordre d'évaluation : alphabétique stable sur `series_metadonnees.code`
pour reproductibilité.

Volume attendu : 36 lignes dans `grandeurs_metier`, toutes avec
``grandeur_code = 'indicateur_qualite_donnees'``,
``periode_type = 'statique'``, ``mois IS NULL``,
``niveau_confiance_derive = 'B'``, ``valeur ∈ {3, 4, 5}``.

Décompte cumulé post-insertion attendu : 1 614 lignes
``grandeurs_metier`` (= 1 578 + 36).

Exception méthodologique : ``series_metadonnees_id``
pointe vers la **série évaluée** (brute NASA POWER), pas vers une
série calculée propre à l'indicateur (cf. migration 037 corrective
EXCLUDE).

Logging score continu par série via ``op.execute('-- ...')`` :
``(serie_code, c1, c2, c3, score_continu, score_discret)``,
pattern reproduit de la migration 032 (humidex).
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.orm import Session

from kuma_data_core.services.grandeurs.indicateur_qualite_donnees import (
    GRANDEUR_CODE_INDICATEUR,
    calculer_et_inserer_indicateur_qualite_donnees,
)

# revision identifiers, used by Alembic.
revision: str = "038"
down_revision: str | Sequence[str] | None = "037"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


_ANNEE_DEBUT: int = 2021
_ANNEE_FIN: int = 2025
_VERSION_FORMULE: int = 1


def upgrade() -> None:
    bind = op.get_bind()
    session = Session(bind=bind)
    try:
        codes_series_brutes: list[str] = list(
            session.execute(
                sa.text(
                    """
                    SELECT sm.code
                    FROM series_metadonnees sm
                    JOIN sources s ON s.id = sm.source_id
                    WHERE s.code = 'nasa_power'
                      AND sm.methode_collecte = 'modele_satellitaire'
                    ORDER BY sm.code
                    """
                )
            )
            .scalars()
            .all()
        )
        if len(codes_series_brutes) != 36:
            raise RuntimeError(
                f"Migration 038 : 36 series brutes NASA POWER attendues, "
                f"trouvees={len(codes_series_brutes)}. Verifier migrations "
                f"016, 019, 021, 028."
            )

        nb_lignes_total = 0
        logs: list[str] = []
        for code_serie in codes_series_brutes:
            resultat = calculer_et_inserer_indicateur_qualite_donnees(
                session=session,
                code_serie_evaluee=code_serie,
                annee_debut=_ANNEE_DEBUT,
                annee_fin=_ANNEE_FIN,
                version_formule=_VERSION_FORMULE,
            )
            nb_lignes_total += resultat["nb_lignes_inseres"]
            logs.append(
                f"({code_serie!r}, c1={resultat['c1_completude']:.4f}, "
                f"c2={resultat['c2_confiance_moyenne']:.4f}, "
                f"c3={resultat['c3_fiabilite_source']:.4f}, "
                f"score_continu={resultat['score_continu']:.4f}, "
                f"score_discret={resultat['score_discret']})"
            )

        op.execute(
            f"-- Migration 038 : {nb_lignes_total} lignes "
            f"indicateur_qualite_donnees inserees (theorique 36) sur "
            f"plage {_ANNEE_DEBUT}-{_ANNEE_FIN}, version_formule="
            f"{_VERSION_FORMULE}. Decompte cumule grandeurs_metier attendu "
            f"= 1 614 (1 578 pre-1-6bis + 36)."
        )
        for log_ligne in logs:
            op.execute(f"-- Migration 038 : {log_ligne}")
    finally:
        session.close()


def downgrade() -> None:
    op.execute(
        sa.text("DELETE FROM grandeurs_metier WHERE grandeur_code = :grandeur_code").bindparams(
            sa.bindparam("grandeur_code", value=GRANDEUR_CODE_INDICATEUR)
        )
    )
