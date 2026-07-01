"""seed_densification_prefectorale_33_prefectures

Revision ID: 085
Revises: 084
Create Date: 2026-06-20 10:00:00

Densification prefectorale - seed + re-parentage.
Peuple le niveau ``prefecture`` ouvert par la migration 084 (CHECK + colonne
``code_administratif_national`` + trigger ``valider_hierarchie_localites``).

Decision B (pas d'harmonisation) : aucun code region n'est renomme. ``gin_boke``
et ``gin_faranah`` restent des regions (re-signifier un identifiant existant est
un anti-pattern) ; les deux communes chef-lieu en collision prennent le suffixe
``_centre`` (``gin_boke_centre``, ``gin_faranah_centre``).

Trois operations, dans l'ordre :

1. **Insert des 33 noeuds ``prefecture``** ``gin_<slug>_prefecture`` (parent =
   region), portant le ``code_administratif_national`` du decret 2025 et les
   coordonnees du chef-lieu (convention Sec. 5.3).

2. **Insert des 28 nouvelles communes chef-lieu** (parent = la prefecture
   homonyme), points d'ingestion solaire ; code ``gin_<slug>`` (ou
   ``gin_<slug>_centre`` pour Boke/Faranah). Les 5 chefs-lieux qui sont des
   capitales regionales (Kankan, Kindia, Labe, Mamou, Nzerekore) existent deja
   (migration 011) et ne sont PAS recrees.

3. **Re-parentage des 5 communes existantes** : ``parent_id`` deplace de la
   region vers la prefecture nouvellement creee. Coordonnees verrouillees
   inchangees.

Demographie de TOUS les nouveaux noeuds : NULL. Les chiffres ville
disponibles melangent perimetres (ville / sous-prefecture / prefecture) et
annees (RGPH-3 2014 / extrapolations 2016 / RGPH-4 2025 preliminaire) ; sourcage
homogene differe sur rapport INS RGPH primaire.

Pattern d'insertion calque sur la migration 011 (resolution Python
``parent_code -> parent_id`` via mapping accumule), avec le mapping pre-amorce
par les IDs des regions deja presentes. Triggers actifs : ``trg_audit_localites``
(audit, auteur NULL) et ``trg_valider_hierarchie_localites`` (084, valide
chaque ligne : prefecture->region, commune->prefecture, re-parent commune->prefecture).

Donnees : ``src/kuma_data_core/db/seeds/localites_prefectures_seed_data.py``.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

import sqlalchemy as sa
from alembic import op
from sqlalchemy.engine import Connection

from kuma_data_core.db.seeds.localites_prefectures_seed_data import (
    NOUVELLES_COMMUNES,
    PREFECTURE_NODES,
    PREFECTURES_GUINEE,
    REPARENTAGES,
)

# revision identifiers, used by Alembic.
revision: str = "085"
down_revision: str | Sequence[str] | None = "084"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


_localites_table = sa.table(
    "localites",
    sa.column("code", sa.String),
    sa.column("nom", sa.Text),
    sa.column("type_localite", sa.String),
    sa.column("parent_id", sa.BigInteger),
    sa.column("code_administratif_national", sa.String),
    sa.column("pays_iso3", sa.String),
    sa.column("latitude", sa.Numeric(11, 8)),
    sa.column("longitude", sa.Numeric(12, 8)),
    sa.column("altitude_metres", sa.Integer),
    sa.column("population_estimee", sa.Integer),
    sa.column("annee_population", sa.Integer),
    sa.column("fuseau_horaire", sa.String),
    sa.column("notes", sa.Text),
)


def _codes_vers_ids(bind: Connection, codes: Sequence[str]) -> dict[str, int]:
    """Mappe une liste de codes localites vers leurs ``id`` (bulk fetch)."""
    rows = bind.execute(
        sa.text("SELECT code, id FROM localites WHERE code = ANY(:codes)"),
        {"codes": list(codes)},
    ).all()
    return {row.code: row.id for row in rows}


def upgrade() -> None:
    bind = op.get_bind()

    # === 1. Resolution des IDs regions (parents des noeuds prefecture) ===
    regions_attendues = {p["region"] for p in PREFECTURES_GUINEE}
    code_to_id = _codes_vers_ids(bind, sorted(regions_attendues))
    manquantes = regions_attendues - set(code_to_id)
    if manquantes:
        raise RuntimeError(
            f"Migration 085 : regions parentes introuvables : {sorted(manquantes)}. "
            f"Verifier que la migration 011 (seed des 20 localites) est appliquee."
        )

    def insert_batch(entries: list[dict[str, Any]]) -> None:
        """Insere un batch et enrichit ``code_to_id`` avec les nouveaux IDs."""
        payload: list[dict[str, Any]] = []
        for entry in entries:
            row = {k: v for k, v in entry.items() if k != "parent_code"}
            parent_code = entry["parent_code"]
            if parent_code not in code_to_id:
                raise RuntimeError(
                    f"Migration 085 : parent_code introuvable : {parent_code!r} "
                    f"(entite {entry['code']!r}). Verifier l'ordre des batches."
                )
            row["parent_id"] = code_to_id[parent_code]
            payload.append(row)
        op.bulk_insert(_localites_table, payload)
        code_to_id.update(_codes_vers_ids(bind, [e["code"] for e in entries]))

    # === 2. Insert des 33 noeuds prefecture (parent = region) ===
    insert_batch(PREFECTURE_NODES)
    # === 3. Insert des 28 nouvelles communes chef-lieu (parent = prefecture) ===
    insert_batch(NOUVELLES_COMMUNES)

    # === 4. Re-parentage des 5 communes existantes (region -> prefecture) ===
    for rp in REPARENTAGES:
        res = bind.execute(
            sa.text("UPDATE localites SET parent_id = :pid WHERE code = :code"),
            {"pid": code_to_id[rp["prefecture"]], "code": rp["commune"]},
        )
        if res.rowcount != 1:
            raise RuntimeError(
                f"Migration 085 : re-parentage {rp['commune']!r} a touche "
                f"{res.rowcount} ligne(s), attendu 1."
            )


def downgrade() -> None:
    bind = op.get_bind()

    # 4'. Re-parentage inverse : communes existantes -> leur region d'origine.
    #     (Avant suppression des noeuds prefecture : la FK parent_id l'exige.)
    region_ids = _codes_vers_ids(bind, sorted({p["region"] for p in PREFECTURES_GUINEE}))
    for p in PREFECTURES_GUINEE:
        if p["existante"] is None:
            continue
        res = bind.execute(
            sa.text("UPDATE localites SET parent_id = :pid WHERE code = :code"),
            {"pid": region_ids[p["region"]], "code": p["existante"]},
        )
        if res.rowcount != 1:
            raise RuntimeError(
                f"Migration 085 downgrade : re-parentage inverse {p['existante']!r} a touche "
                f"{res.rowcount} ligne(s), attendu 1."
            )

    # 3' + 2'. Suppression des nouvelles communes puis des noeuds prefecture.
    bind.execute(
        sa.text("DELETE FROM localites WHERE code = ANY(:codes)"),
        {"codes": [c["code"] for c in NOUVELLES_COMMUNES]},
    )
    bind.execute(
        sa.text("DELETE FROM localites WHERE code = ANY(:codes)"),
        {"codes": [n["code"] for n in PREFECTURE_NODES]},
    )
