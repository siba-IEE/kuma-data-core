"""appliquer_qc_horaire_conakry_2001_2020_vague3_lot3d

Revision ID: 067
Revises: 066
Create Date: 2026-06-15 15:30:00.000000+00:00

QC BSRN des lignes horaires Conakry **2001-2020**
(backfill, migration 066). Point de surete : l'application est **scopee a
instant < 2021-01-01**. Les lignes 2021-2023 (dont les 29 rejets DHI
conserves ``brut`` par le QC anterieur, migration 055) ne sont **jamais
retouchees**.

Le runner ``executer_qc_horaire`` lit toutes les lignes courantes de la
serie (necessaire pour la fermeture cross-variable par instant ; pour
2001-2020 les 3 radiatives sont toutes ``brut`` -> instants complets),
mais le caller n'applique les verdicts qu'aux ``row_id`` de la fenetre
2001-2020.

No-op quand le garde-fou de masse a court-circuite l'ingestion (CI) :
aucune ligne 2001-2020 -> ensemble scope vide. Clot le rollout horaire
(6 villes, 2001-2023, QC).
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date

import sqlalchemy as sa
from alembic import op
from sqlalchemy.orm import Session

from kuma_data_core.editorial.statuts import transition_autorisee
from kuma_data_core.services.qualite.qc_horaire import (
    VERSION_DOCTRINE_QC,
    executer_qc_horaire,
)

# revision identifiers, used by Alembic.
revision: str = "067"
down_revision: str | Sequence[str] | None = "066"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


_LOCALITE_CODE: str = "gin_conakry_kaloum"
_GRANDEURS: tuple[str, ...] = ("ghi", "dni", "dhi", "t2m", "rh2m", "kt")
_COMMENTAIRE_CLEAN: str = f"[QC {VERSION_DOCTRINE_QC}] valide_auto"
_BORNE_SCOPE: date = date(2021, 1, 1)  # exclusif : seules les lignes < 2021 sont traitees


def _code_serie(grandeur: str) -> str:
    return f"gin_conakry_{grandeur}_nasa_power_2001_2023"


def upgrade() -> None:
    bind = op.get_bind()

    if not transition_autorisee("brut", "valide_auto"):
        raise RuntimeError("Migration 067 : transition brut -> valide_auto refusee par la matrice.")

    ligne_loc = bind.execute(
        sa.text(
            "SELECT CAST(latitude AS DOUBLE PRECISION) AS lat, "
            "CAST(longitude AS DOUBLE PRECISION) AS lon "
            "FROM localites WHERE code = :code"
        ),
        {"code": _LOCALITE_CODE},
    ).first()
    if ligne_loc is None:
        raise RuntimeError(f"Migration 067 : localite {_LOCALITE_CODE!r} introuvable.")
    latitude = float(ligne_loc.lat)
    longitude = float(ligne_loc.lon)

    serie_ids: dict[str, int] = {}
    for grandeur in _GRANDEURS:
        sid = bind.execute(
            sa.text("SELECT id FROM series_metadonnees WHERE code = :code"),
            {"code": _code_serie(grandeur)},
        ).scalar_one_or_none()
        if sid is None:
            raise RuntimeError(
                f"Migration 067 : serie {_code_serie(grandeur)!r} introuvable "
                f"(migration 066 appliquee ?)."
            )
        serie_ids[grandeur] = int(sid)

    ids = list(serie_ids.values())

    session = Session(bind=bind)
    try:
        verdicts = executer_qc_horaire(session, serie_ids, latitude, longitude)

        # Ensemble scope : les seules lignes neuves (2001-2020).
        ids_neufs = set(
            session.execute(
                sa.text(
                    """
                    SELECT id FROM mesures_ressource_horaires
                    WHERE serie_id = ANY(:ids)
                      AND valide_au IS NULL
                      AND (instant_mesure AT TIME ZONE 'UTC')::date < :borne
                    """
                ),
                {"ids": ids, "borne": _BORNE_SCOPE},
            )
            .scalars()
            .all()
        )

        # 1) Validation en masse des lignes brut **2001-2020 uniquement**
        #    (les 29 rejets DHI 2021-2023 du QC anterieur sont exclus par la borne).
        session.execute(
            sa.text(
                """
                UPDATE mesures_ressource_horaires
                SET statut = 'valide_auto',
                    commentaire_editorial = :commentaire,
                    modifie_le = now()
                WHERE serie_id = ANY(:ids)
                  AND statut = 'brut'
                  AND valide_au IS NULL
                  AND (instant_mesure AT TIME ZONE 'UTC')::date < :borne
                """
            ),
            {"commentaire": _COMMENTAIRE_CLEAN, "ids": ids, "borne": _BORNE_SCOPE},
        )

        # 2) Corrections (flags / rejets), **uniquement sur les lignes 2001-2020**.
        n_flag = 0
        n_rejet = 0
        for v in verdicts:
            if v.row_id not in ids_neufs:
                continue
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

        n_traitees = len(ids_neufs)
        op.execute(
            f"-- Migration 067 : QC {VERSION_DOCTRINE_QC} applique a {n_traitees} lignes "
            f"horaires Conakry 2001-2020 (scope instant < {_BORNE_SCOPE}). "
            f"{n_traitees - n_rejet} valide_auto (dont {n_flag} flaggees), "
            f"{n_rejet} rejets conserves brut. Lignes 2021-2023 (lot 2) preservees."
        )
    finally:
        session.close()


def downgrade() -> None:
    # Retour a brut non commente des seules lignes 2001-2020 QC-traitees
    # (les lignes 2021-2023 ne sont pas touchees).
    codes_series = [_code_serie(g) for g in _GRANDEURS]
    op.execute(
        sa.text(
            """
            UPDATE mesures_ressource_horaires
            SET statut = 'brut',
                commentaire_editorial = NULL,
                modifie_le = now()
            WHERE serie_id IN (
                SELECT id FROM series_metadonnees WHERE code = ANY(:codes)
            )
            AND (instant_mesure AT TIME ZONE 'UTC')::date < :borne
            AND commentaire_editorial LIKE :prefixe
            """
        ).bindparams(
            sa.bindparam("codes", value=codes_series),
            sa.bindparam("borne", value=_BORNE_SCOPE),
            sa.bindparam("prefixe", value=f"[QC {VERSION_DOCTRINE_QC}]%"),
        )
    )
