"""horaire_pilotes_qc

Revision ID: 117
Revises: 116
Create Date: 2026-08-10 13:30:00

Applique le controle qualite algorithmique BSRN (doctrine
``doctrine-qc-horaire.md``, service ``services/qualite/qc_horaire.py``,
pattern des migrations 055/057) aux lignes horaires ``brut``
des 6 villes pilotes (revision precedente : extension 2024-2025 des 6 grandeurs
historiques + vents et precipitation en pleine profondeur). Application
idempotente : l'UPDATE de masse ne cible que les lignes ``brut`` courantes,
les lignes deja qualifiees par les migrations 055-067 sont re-evaluees a
verdict identique (deterministe).

Verdict par ligne (inchange) : tests durs passes -> ``valide_auto`` niveau
B ; echecs souples -> ``valide_auto`` + flag en commentaire ; seuil
« physiquement impossible » -> conserve ``brut`` + motif (non destructif).

Les grandeurs vent_2m / vent_10m / precipitation traversent le QC v1 sans
test de plausibilite dedie (la doctrine v1 couvre le rayonnement, t2m, rh2m
et kt) : elles sont qualifiees ``valide_auto`` par le meme pipeline, la
limite est dite dans leur ``note_publique`` (doctrine v2 a instruire).

Interaction avec le garde-fou de masse : quand
``KUMA_SKIP_INGESTION_MASSE_HORAIRE`` est pose (CI), les series du lot ont 0
ligne ; la migration est un no-op. L'application est idempotente : l'UPDATE
de masse ne cible que les lignes ``brut`` courantes, les verdicts sont
deterministes.

Trigger d'audit : suspendu le temps de la requalification de masse
(decision 2026-08-10, ``docs/architecture/03-audit.md``).
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
revision: str = "117"
down_revision: str | Sequence[str] | None = "116"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_NUMERO_LOT = "pilotes"
# Localite -> prefixe de code de serie (exception Conakry).
_PILOTES: dict[str, str] = {
    "gin_conakry_kaloum": "gin_conakry",
    "gin_kankan": "gin_kankan",
    "gin_kindia": "gin_kindia",
    "gin_labe": "gin_labe",
    "gin_mamou": "gin_mamou",
    "gin_nzerekore": "gin_nzerekore",
}
_GRANDEURS: tuple[str, ...] = (
    "ghi",
    "dni",
    "dhi",
    "t2m",
    "rh2m",
    "kt",
    "vent_2m",
    "vent_10m",
    "precipitation",
)
_COMMENTAIRE_CLEAN: str = f"[QC {VERSION_DOCTRINE_QC}] valide_auto"
_TABLE_MESURES = "mesures_ressource_horaires"
_TRIGGER_AUDIT = "trg_audit_mesures_ressource_horaires"


def _code_serie(prefixe_serie: str, grandeur: str) -> str:
    return f"{prefixe_serie}_{grandeur}_nasa_power_2001_2025"


def upgrade() -> None:
    bind = op.get_bind()

    if not transition_autorisee("brut", "valide_auto"):
        raise RuntimeError("Migration 117 : transition brut -> valide_auto refusee par la matrice.")

    op.execute(f"ALTER TABLE {_TABLE_MESURES} DISABLE TRIGGER {_TRIGGER_AUDIT}")
    session = Session(bind=bind)
    try:
        total_verdicts = 0
        total_valide = 0
        total_flag = 0
        total_rejet = 0
        for commune_code, prefixe_serie in _PILOTES.items():
            ligne_loc = bind.execute(
                sa.text(
                    "SELECT CAST(latitude AS DOUBLE PRECISION) AS lat, "
                    "CAST(longitude AS DOUBLE PRECISION) AS lon "
                    "FROM localites WHERE code = :code"
                ),
                {"code": commune_code},
            ).first()
            if ligne_loc is None:
                raise RuntimeError(f"Migration 117 : localite {commune_code!r} introuvable.")

            serie_ids: dict[str, int] = {}
            for grandeur in _GRANDEURS:
                sid = bind.execute(
                    sa.text("SELECT id FROM series_metadonnees WHERE code = :code"),
                    {"code": _code_serie(prefixe_serie, grandeur)},
                ).scalar_one_or_none()
                if sid is None:
                    raise RuntimeError(
                        f"Migration 117 : serie {_code_serie(commune_code, grandeur)!r} "
                        f"introuvable (migration du lot appliquee ?)."
                    )
                serie_ids[grandeur] = int(sid)

            verdicts = executer_qc_horaire(
                session, serie_ids, float(ligne_loc.lat), float(ligne_loc.lon)
            )

            # 1) Validation en masse des lignes brut courantes de la commune.
            session.execute(
                sa.text(
                    f"""
                    UPDATE {_TABLE_MESURES}
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

            # 2) Corrections : flags (commentaire enrichi) et rejets (retour brut).
            for v in verdicts:
                if v.statut_cible == "brut":
                    total_rejet += 1
                    session.execute(
                        sa.text(
                            f"""
                            UPDATE {_TABLE_MESURES}
                            SET statut = 'brut',
                                commentaire_editorial = :commentaire,
                                modifie_le = now()
                            WHERE id = :id
                            """
                        ),
                        {"commentaire": v.commentaire(), "id": v.row_id},
                    )
                elif v.flags:
                    total_flag += 1
                    session.execute(
                        sa.text(
                            f"""
                            UPDATE {_TABLE_MESURES}
                            SET commentaire_editorial = :commentaire,
                                modifie_le = now()
                            WHERE id = :id
                            """
                        ),
                        {"commentaire": v.commentaire(), "id": v.row_id},
                    )
            total_verdicts += len(verdicts)
            total_valide += sum(1 for v in verdicts if v.statut_cible == "valide_auto")

        session.flush()
        op.execute(
            f"-- Migration 117 : QC {VERSION_DOCTRINE_QC} applique a {total_verdicts} lignes "
            f"horaires (lot {_NUMERO_LOT}, 6 pilotes x 9 grandeurs, trigger d'audit "
            f"suspendu). {total_valide} valide_auto (dont {total_flag} flaggees), "
            f"{total_rejet} rejets conserves brut."
        )
    finally:
        session.close()
        op.execute(f"ALTER TABLE {_TABLE_MESURES} ENABLE TRIGGER {_TRIGGER_AUDIT}")


def downgrade() -> None:
    codes_series = [_code_serie(p, g) for p in _PILOTES.values() for g in _GRANDEURS]
    op.execute(f"ALTER TABLE {_TABLE_MESURES} DISABLE TRIGGER {_TRIGGER_AUDIT}")
    try:
        op.execute(
            sa.text(
                f"""
                UPDATE {_TABLE_MESURES}
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
    finally:
        op.execute(f"ALTER TABLE {_TABLE_MESURES} ENABLE TRIGGER {_TRIGGER_AUDIT}")
