"""appliquer_qc_horaire_mamou_vague3_lot3c

Revision ID: 059
Revises: 058
Create Date: 2026-06-15 11:30:00.000000+00:00

QC BSRN des lignes horaires brut de Mamou (migration
058). Clone du patron de la migration 057, reutilise integralement
``services/qualite/qc_horaire.py``.

No-op quand le garde-fou de masse (KUMA_SKIP_INGESTION_MASSE_HORAIRE) a
court-circuite l'ingestion (CI) : 0 ligne -> verdicts vides.
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
revision: str = "059"
down_revision: str | Sequence[str] | None = "058"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


_LOCALITE_CODE: str = "gin_mamou"
_GRANDEURS: tuple[str, ...] = ("ghi", "dni", "dhi", "t2m", "rh2m", "kt")
_COMMENTAIRE_CLEAN: str = f"[QC {VERSION_DOCTRINE_QC}] valide_auto"


def _code_serie(grandeur: str) -> str:
    return f"{_LOCALITE_CODE}_{grandeur}_nasa_power_2001_2023"


def upgrade() -> None:
    bind = op.get_bind()

    if not transition_autorisee("brut", "valide_auto"):
        raise RuntimeError("Migration 059 : transition brut -> valide_auto refusee par la matrice.")

    ligne_loc = bind.execute(
        sa.text(
            "SELECT CAST(latitude AS DOUBLE PRECISION) AS lat, "
            "CAST(longitude AS DOUBLE PRECISION) AS lon "
            "FROM localites WHERE code = :code"
        ),
        {"code": _LOCALITE_CODE},
    ).first()
    if ligne_loc is None:
        raise RuntimeError(f"Migration 059 : localite {_LOCALITE_CODE!r} introuvable.")
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
                f"Migration 059 : serie {_code_serie(grandeur)!r} introuvable "
                f"(migration 058 appliquee ?)."
            )
        serie_ids[grandeur] = int(sid)

    session = Session(bind=bind)
    try:
        verdicts = executer_qc_horaire(session, serie_ids, latitude, longitude)

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
                """
            ),
            {"commentaire": _COMMENTAIRE_CLEAN, "ids": list(serie_ids.values())},
        )

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
            f"-- Migration 059 : QC {VERSION_DOCTRINE_QC} applique a {len(verdicts)} lignes "
            f"horaires Mamou. {n_valide} valide_auto (dont {n_flag} flaggees), "
            f"{n_rejet} rejets conserves brut."
        )
    finally:
        session.close()


def downgrade() -> None:
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
            AND commentaire_editorial LIKE :prefixe
            """
        ).bindparams(
            sa.bindparam("codes", value=codes_series),
            sa.bindparam("prefixe", value=f"[QC {VERSION_DOCTRINE_QC}]%"),
        )
    )
