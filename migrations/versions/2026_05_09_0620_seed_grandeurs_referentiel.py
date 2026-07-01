"""seed_grandeurs_referentiel

Revision ID: 010
Revises: 009
Create Date: 2026-05-09 06:20:39.927556+00:00

Seed des 15 grandeurs solaires et climatiques dans la
table ``grandeurs_referentiel`` (créée par la migration 007).

Décompte : 8 F1 stockee + 2 F1 calculee_volee + 5 F2 calculee_volee
+ 0 F2 stockee = 15 grandeurs.

Décisions :

- cadence des productibles : journalière pour les grandeurs F2
  (et le productible théorique F1) ; mensuelle figée pour
  ``productible_mensuel`` ;
- codes ASCII strict ;
- HEP regroupé en une entrée (la cadence est portée par la série
  via ``series_metadonnees.periode_debut/fin``) ;
- descriptions courtes rédigées pour les 15 grandeurs,
  ``methode_calcul_doc`` NULL (étape éditoriale ultérieure).

Résolution dynamique des ``unite_id`` : bulk fetch des ``(code, id)``
depuis ``unites`` puis
substitution Python de la clé ``unite_code`` par ``unite_id``. Garde-
fou explicite sur les codes non résolus pour éviter une ``KeyError``
opaque au moment du ``bulk_insert``.

Trigger d'audit : ``kuma_log_audit()`` (créé en migration 005, branché
sur ``grandeurs_referentiel`` par la migration 007) se déclenchera
automatiquement à l'INSERT des 15 lignes. ``auteur_applicatif`` reste
NULL - comportement accepté.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

import sqlalchemy as sa
from alembic import op

from kuma_data_core.db.seeds.grandeurs_referentiel_seed_data import (
    GRANDEURS_REFERENTIEL_SEED,
)

# revision identifiers, used by Alembic.
revision: str = "010"
down_revision: str | Sequence[str] | None = "009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# Codes des 15 grandeurs - utilisés par le downgrade pour cibler les
# lignes à supprimer (la PK BIGINT n'est pas stable entre
# environnements).
_CODES_GRANDEURS: tuple[str, ...] = tuple(entry["code"] for entry in GRANDEURS_REFERENTIEL_SEED)


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
    codes_attendus: set[str] = {entree["unite_code"] for entree in GRANDEURS_REFERENTIEL_SEED}
    lignes_unites = bind.execute(
        sa.text("SELECT code, id FROM unites WHERE code = ANY(:codes)"),
        {"codes": list(codes_attendus)},
    ).all()
    unite_id_par_code: dict[str, int] = {row.code: row.id for row in lignes_unites}

    codes_manquants = codes_attendus - unite_id_par_code.keys()
    if codes_manquants:
        raise RuntimeError(
            f"Migration 010 : unite_code(s) introuvable(s) dans unites : "
            f"{sorted(codes_manquants)}. Verifier que la migration 009 a "
            f"bien ete appliquee."
        )

    # === Transformation du seed (substitution unite_code -> unite_id) ===
    lignes_a_inserer: list[dict[str, Any]] = []
    for entree in GRANDEURS_REFERENTIEL_SEED:
        ligne = {**entree, "unite_id": unite_id_par_code[entree["unite_code"]]}
        ligne.pop("unite_code")
        lignes_a_inserer.append(ligne)

    op.bulk_insert(grandeurs_referentiel_table, lignes_a_inserer)


def downgrade() -> None:
    op.execute(
        sa.text("DELETE FROM grandeurs_referentiel WHERE code = ANY(:codes)").bindparams(
            sa.bindparam("codes", value=list(_CODES_GRANDEURS))
        )
    )
