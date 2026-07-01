"""appliquer_qc_horaire_dni_kankan_esmap_wapp

Revision ID: 078
Revises: 077
Create Date: 2026-06-18 11:00:00.000000+00:00

Calage DNI - applique le contrôle qualité algorithmique BSRN
(doctrine ``doctrine-qc-horaire.md``, service ``services/qualite/qc_horaire.py``)
aux **17 520 lignes horaires brut** de la série DNI sol Kankan (migration 077).

DNI **seul** : seules les bornes de plausibilité DNI (physiquement possible ≤ Sₐ ;
extrêmement rare) s'appliquent ; les tests croisés (fermeture, ratio diffus) sont
**inactifs** faute de GHI/DHI dans la série (``evaluer_instant`` ne les déclenche
qu'avec les 3 composantes). Verdict par ligne :

- plausibilité DNI hors borne possible → ligne **conservée ``brut``** + motif ;
- sinon → ``valide_auto`` (flag « extremement rare » si applicable, fréquent au
  soleil bas où la borne rare DNI est basse).

Le ``niveau_confiance_derive='A'`` posé en 077 (R3) est **préservé** : le QC ne
touche que ``statut`` et ``commentaire_editorial``. Déterministe (pvlib, UTC),
aucun réseau.

Pattern dupliqué de la migration 076 (QC GHI Kankan), grandeur ``dni``.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.orm import Session

from kuma_data_core.editorial.statuts import transition_autorisee
from kuma_data_core.services.qualite.qc_horaire import (
    VERSION_DOCTRINE_QC,
    executer_qc_horaire,
)

# revision identifiers, used by Alembic.
revision: str = "078"
down_revision: str | Sequence[str] | None = "077"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_LOCALITE_CODE: str = "gin_kankan"
_GRANDEUR: str = "dni"
_CODE_SERIE: str = "gin_kankan_dni_esmap_wapp_2021_2023"
_COMMENTAIRE_CLEAN: str = f"[QC {VERSION_DOCTRINE_QC}] valide_auto"


def upgrade() -> None:
    bind = op.get_bind()

    if not transition_autorisee("brut", "valide_auto"):
        raise RuntimeError("Migration 078 : transition brut -> valide_auto refusee par la matrice.")

    ligne_loc = bind.execute(
        sa.text(
            "SELECT CAST(latitude AS DOUBLE PRECISION) AS lat, "
            "CAST(longitude AS DOUBLE PRECISION) AS lon "
            "FROM localites WHERE code = :code"
        ),
        {"code": _LOCALITE_CODE},
    ).first()
    if ligne_loc is None:
        raise RuntimeError(f"Migration 078 : localite {_LOCALITE_CODE!r} introuvable.")
    latitude = float(ligne_loc.lat)
    longitude = float(ligne_loc.lon)

    serie_id = bind.execute(
        sa.text("SELECT id FROM series_metadonnees WHERE code = :code"),
        {"code": _CODE_SERIE},
    ).scalar_one_or_none()
    if serie_id is None:
        raise RuntimeError(
            f"Migration 078 : serie {_CODE_SERIE!r} introuvable (migration 077 appliquee ?)."
        )

    session = Session(bind=bind)
    try:
        verdicts = executer_qc_horaire(session, {_GRANDEUR: int(serie_id)}, latitude, longitude)

        # 1) Validation en masse des lignes brut courantes de la serie.
        session.execute(
            sa.text(
                """
                UPDATE mesures_ressource_horaires
                SET statut = 'valide_auto',
                    commentaire_editorial = :commentaire,
                    modifie_le = now()
                WHERE serie_id = :serie_id
                  AND statut = 'brut'
                  AND valide_au IS NULL
                """
            ),
            {"commentaire": _COMMENTAIRE_CLEAN, "serie_id": int(serie_id)},
        )

        # 2) Corrections : rejets (retour brut) et flags (commentaire enrichi).
        n_flag = 0
        n_rejet = 0
        for v in verdicts:
            if v.statut_cible == "brut":
                n_rejet += 1
                session.execute(
                    sa.text(
                        """
                        UPDATE mesures_ressource_horaires
                        SET statut = 'brut',
                            commentaire_editorial = :commentaire,
                            modifie_le = now()
                        WHERE id = :id
                        """
                    ),
                    {"commentaire": v.commentaire(), "id": v.row_id},
                )
            elif v.flags:
                n_flag += 1
                session.execute(
                    sa.text(
                        """
                        UPDATE mesures_ressource_horaires
                        SET commentaire_editorial = :commentaire,
                            modifie_le = now()
                        WHERE id = :id
                        """
                    ),
                    {"commentaire": v.commentaire(), "id": v.row_id},
                )

        session.flush()

        n_valide = sum(1 for v in verdicts if v.statut_cible == "valide_auto")
        op.execute(
            f"-- Migration 078 : QC {VERSION_DOCTRINE_QC} applique a {len(verdicts)} lignes "
            f"DNI sol Kankan. {n_valide} valide_auto (dont {n_flag} flaggees), "
            f"{n_rejet} rejets conserves brut."
        )
    finally:
        session.close()


def downgrade() -> None:
    op.execute(
        sa.text(
            """
            UPDATE mesures_ressource_horaires
            SET statut = 'brut',
                commentaire_editorial = NULL,
                modifie_le = now()
            WHERE serie_id IN (
                SELECT id FROM series_metadonnees WHERE code = :code
            )
            AND commentaire_editorial LIKE :prefixe
            """
        ).bindparams(
            sa.bindparam("code", value=_CODE_SERIE),
            sa.bindparam("prefixe", value=f"[QC {VERSION_DOCTRINE_QC}]%"),
        )
    )
