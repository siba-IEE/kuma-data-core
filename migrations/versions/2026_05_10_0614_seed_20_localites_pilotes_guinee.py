"""seed_20_localites_pilotes_guinee

Revision ID: 011
Revises: 010
Create Date: 2026-05-10 06:14:39.744125+00:00

Seed des 20 localités pilotes Guinée dans la table ``localites`` (créée
vide en migration 003 ; trigger d'audit ``trg_audit_localites`` posé en
migration 005).

Contenu :

- 1 continent (Afrique)
- 1 pays (Guinée)
- 8 régions administratives (Boké, Conakry, Faranah, Kankan, Kindia,
  Labé, Mamou, Nzérékoré)
- 5 communes pilotes - villes chef-lieu (Kankan, Kindia, Labé, Mamou,
  Nzérékoré)
- 5 communes pilotes - Conakry historiques pré-réforme 2024 (Kaloum,
  Dixinn, Matam, Matoto, Ratoma)

Pattern α-bis : 4 batches ``op.bulk_insert`` par profondeur,
résolution Python ``parent_code -> parent_id`` au fur et à mesure via
bulk fetch après chaque batch. Garde-fou ``RuntimeError`` si un
``parent_code`` est introuvable dans le mapping.

Forme du bulk fetch et du downgrade DELETE strictement dupliquée de
la migration 010 mergée (``sa.text("... = ANY(:codes)")`` +
``.all()``). Trigger d'audit ``trg_audit_localites`` se déclenche
automatiquement à l'INSERT des 20 lignes ; ``auteur_applicatif`` reste
NULL (pas de ``set_config`` dans la migration).

Q-IDs Wikidata stockés dans ``notes`` (pattern ``Q[0-9]+``) - symétrie
référentielle, pas d'ALTER TABLE.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

import sqlalchemy as sa
from alembic import op

from kuma_data_core.db.seeds.localites_seed_data import LOCALITES_SEED

# revision identifiers, used by Alembic.
revision: str = "011"
down_revision: str | Sequence[str] | None = "010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# Codes des 20 localités - utilisés par le downgrade pour cibler les
# lignes à supprimer (la PK BIGINT n'est pas stable entre
# environnements). Pattern identique à la migration 010.
_CODES_LOCALITES: tuple[str, ...] = tuple(entry["code"] for entry in LOCALITES_SEED)


def upgrade() -> None:
    bind = op.get_bind()
    code_to_id: dict[str, int] = {}

    localites_table = sa.table(
        "localites",
        sa.column("code", sa.String),
        sa.column("nom", sa.Text),
        sa.column("type_localite", sa.String),
        sa.column("parent_id", sa.BigInteger),
        sa.column("pays_iso3", sa.String),
        sa.column("latitude", sa.Numeric(11, 8)),
        sa.column("longitude", sa.Numeric(12, 8)),
        sa.column("altitude_metres", sa.Integer),
        sa.column("population_estimee", sa.Integer),
        sa.column("annee_population", sa.Integer),
        sa.column("fuseau_horaire", sa.String),
        sa.column("notes", sa.Text),
    )

    def insert_batch(entries: list[dict[str, Any]]) -> None:
        """Insère un batch et enrichit ``code_to_id`` avec les IDs nouvellement créés.

        Substitution Python ``parent_code -> parent_id`` à partir du
        mapping ``code_to_id`` accumulé par les batches précédents.
        Lève ``RuntimeError`` si un ``parent_code`` est introuvable.
        """
        payload: list[dict[str, Any]] = []
        for entry in entries:
            row = {k: v for k, v in entry.items() if k != "parent_code"}
            parent_code = entry.get("parent_code")
            if parent_code is None:
                row["parent_id"] = None
            else:
                if parent_code not in code_to_id:
                    raise RuntimeError(
                        f"Migration 011 : parent_code introuvable lors du seed "
                        f"localites : {parent_code!r} (entite {entry['code']!r}). "
                        f"Verifier l'ordre topologique dans LOCALITES_SEED."
                    )
                row["parent_id"] = code_to_id[parent_code]
            payload.append(row)

        op.bulk_insert(localites_table, payload)

        codes_inseres = [entry["code"] for entry in entries]
        lignes = bind.execute(
            sa.text("SELECT code, id FROM localites WHERE code = ANY(:codes)"),
            {"codes": codes_inseres},
        ).all()
        code_to_id.update({row.code: row.id for row in lignes})

    # Batch 1 - continent (1 entité, parent_code None)
    insert_batch([e for e in LOCALITES_SEED if e["type_localite"] == "continent"])
    # Batch 2 - pays (1 entité, parent_code 'afrique')
    insert_batch([e for e in LOCALITES_SEED if e["type_localite"] == "pays"])
    # Batch 3 - régions administratives (8 entités, parent_code 'gin')
    insert_batch([e for e in LOCALITES_SEED if e["type_localite"] == "region_administrative"])
    # Batch 4 - communes (10 entités, parent_code variable)
    insert_batch([e for e in LOCALITES_SEED if e["type_localite"] == "commune"])


def downgrade() -> None:
    op.execute(
        sa.text("DELETE FROM localites WHERE code = ANY(:codes)").bindparams(
            sa.bindparam("codes", value=list(_CODES_LOCALITES))
        )
    )
