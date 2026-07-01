"""seed_grandeurs_brutes_1_2b

Revision ID: 015
Revises: 014
Create Date: 2026-05-11 13:00:00.000000+00:00

Étend le référentiel ``grandeurs_referentiel`` avec 5 grandeurs brutes
ingérées depuis sources externes (`ghi`, `dni`, `dhi`, `t2m`, `rh2m`).

Disambiguation des grandeurs
brutes vs traduites via la convention de mapping
``methode_collecte → table physique`` au niveau série, pas via attribut
intrinsèque au niveau grandeur.

Le commentaire de table ``grandeurs_referentiel`` est amendé pour acter
le scope étendu : 15 grandeurs Kuma traduites + 5 grandeurs brutes
ingérées = 20 entrées.

Pattern hérité de la migration 010 (résolution dynamique
``unite_code -> unite_id``) appliqué au sous-ensemble des brutes uniquement.

Forme du downgrade ``DELETE WHERE code = ANY(:codes)`` strictement
dupliquée des migrations 010, 011, 012 mergées.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

import sqlalchemy as sa
from alembic import op

from kuma_data_core.db.seeds.grandeurs_referentiel_seed_data import (
    CODES_BRUTES_INGESTION_1_2B,
    GRANDEURS_REFERENTIEL_SEED_BRUTES_1_2B,
)

# revision identifiers, used by Alembic.
revision: str = "015"
down_revision: str | Sequence[str] | None = "014"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    grandeurs_referentiel_table = sa.table(
        "grandeurs_referentiel",
        sa.column("code", sa.String),
        sa.column("libelle", sa.Text),
        sa.column("unite_id", sa.BigInteger),
        sa.column("famille", sa.String),
        sa.column("strategie_calcul", sa.String),
        sa.column("description", sa.Text),
    )

    # === Résolution dynamique unite_code -> unite_id ===
    bind = op.get_bind()
    codes_attendus: set[str] = {
        entree["unite_code"] for entree in GRANDEURS_REFERENTIEL_SEED_BRUTES_1_2B
    }
    lignes_unites = bind.execute(
        sa.text("SELECT code, id FROM unites WHERE code = ANY(:codes)"),
        {"codes": list(codes_attendus)},
    ).all()
    unite_id_par_code: dict[str, int] = {row.code: row.id for row in lignes_unites}

    codes_manquants = codes_attendus - unite_id_par_code.keys()
    if codes_manquants:
        raise RuntimeError(
            f"Migration 015 : unite_code(s) introuvable(s) dans unites : "
            f"{sorted(codes_manquants)}. Verifier la migration 009 (seed "
            f"unites complementaires)."
        )

    # === Transformation du seed (substitution unite_code -> unite_id) ===
    lignes_a_inserer: list[dict[str, Any]] = []
    for entree in GRANDEURS_REFERENTIEL_SEED_BRUTES_1_2B:
        ligne = {**entree, "unite_id": unite_id_par_code[entree["unite_code"]]}
        ligne.pop("unite_code")
        lignes_a_inserer.append(ligne)

    op.bulk_insert(grandeurs_referentiel_table, lignes_a_inserer)

    # === Amendement commentaire de table ===
    op.execute(
        "COMMENT ON TABLE grandeurs_referentiel IS "
        "'Referentiel des grandeurs Kuma. 15 grandeurs traduites (1-1C) + "
        "5 grandeurs brutes ingerees (1-2b) = 20 entrees post-1-2b. "
        "Le lieu de stockage physique d''une F1 stockee est determine par "
        "series_metadonnees.methode_collecte (cadrage Q7 v1.3).'"
    )


def downgrade() -> None:
    op.execute(
        sa.text("DELETE FROM grandeurs_referentiel WHERE code = ANY(:codes)").bindparams(
            sa.bindparam("codes", value=list(CODES_BRUTES_INGESTION_1_2B))
        )
    )
    op.execute(
        "COMMENT ON TABLE grandeurs_referentiel IS "
        "'Referentiel statique des grandeurs traduites Kuma (15 entrees en phase 1).'"
    )
