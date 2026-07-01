"""seed_6_series_hep

Revision ID: 026
Revises: 025
Create Date: 2026-05-12 10:30:00.000000+00:00

Seed des 6 séries HEP calculées Kuma dans
``series_metadonnees``. Une série par ville pilote, toutes avec :

- ``grandeur_code='hep'``
- ``source.code='kuma_calculs'`` (source synthétique seedée en 025)
- ``methode_collecte='calcul_derive'``
- ``periode 2021-2025``
- ``commentaire_editorial`` standardisé citant la série GHI amont
- ``url_documentation`` et ``methode_collecte_doc`` pointant vers la fiche
  méthodologique HEP v1.

Pattern de résolution dynamique des codes naturels en IDs hérité des
migrations 010, 011, 012, 016, 019, 021.

Pré-requis :

- table ``series_metadonnees`` (migration 008) ;
- 6 localités ``gin_conakry_kaloum`` / ``gin_kindia`` / ``gin_mamou`` /
  ``gin_labe`` / ``gin_kankan`` / ``gin_nzerekore`` (migration 011) ;
- grandeur ``hep`` (migration 010) ;
- source ``kuma_calculs`` (migration 025).
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date
from typing import Any

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "026"
down_revision: str | Sequence[str] | None = "025"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# Convention commune aux 6 séries HEP calculées Kuma.
_PERIODE_DEBUT: date = date(2021, 1, 1)
_PERIODE_FIN: date = date(2025, 12, 31)
_GRANDEUR_CODE: str = "hep"
_SOURCE_CODE: str = "kuma_calculs"
_METHODE_COLLECTE: str = "calcul_derive"
_URL_DOCUMENTATION: str = "docs/methodologie/grandeurs/hep.md"
_METHODE_COLLECTE_DOC: str = "docs/methodologie/grandeurs/hep.md"


def _commentaire_editorial(code_serie_ghi_amont: str) -> str:
    """Construit le commentaire editorial standardise pour une serie HEP.

    Discipline editoriale : le commentaire trace la
    serie GHI amont, la methode de calcul, la politique de completude,
    la fiche methodologique, et l'origine d'ingestion des donnees amont.
    """
    return (
        f"Serie HEP calculee Kuma a partir de {code_serie_ghi_amont}. "
        "Methode : agregation cumulative journaliere du GHI, conversion "
        "implicite 1 kWh/m2/j = 1 h_eq/j a 1 kW/m2 STC. Politique de "
        "completude stricte 100% jours civils v1. Fiche methodologique : "
        "docs/methodologie/grandeurs/hep.md. Version_formule actuelle : 1. "
        "Series GHI amont ingerees en 1-2b/1-3/1-4 (Conakry-Kaloum par la "
        "migration 018, 5 autres villes par la migration 022)."
    )


# Énumération exhaustive des 6 séries HEP. Pattern symétrique
# aux migrations 016 (série unique), 019 (4 séries Conakry), 021
# (25 séries 5 villes).
_SERIES_HEP_KUMA: list[dict[str, Any]] = [
    {
        "code": "gin_conakry_hep_kuma_calculs_2021_2025",
        "libelle": "HEP Conakry-Kaloum 2021-2025 (calcul Kuma)",
        "localite_code": "gin_conakry_kaloum",
        "code_serie_ghi_amont": "gin_conakry_ghi_nasa_power_2021_2025",
    },
    {
        "code": "gin_kindia_hep_kuma_calculs_2021_2025",
        "libelle": "HEP Kindia 2021-2025 (calcul Kuma)",
        "localite_code": "gin_kindia",
        "code_serie_ghi_amont": "gin_kindia_ghi_nasa_power_2021_2025",
    },
    {
        "code": "gin_mamou_hep_kuma_calculs_2021_2025",
        "libelle": "HEP Mamou 2021-2025 (calcul Kuma)",
        "localite_code": "gin_mamou",
        "code_serie_ghi_amont": "gin_mamou_ghi_nasa_power_2021_2025",
    },
    {
        "code": "gin_labe_hep_kuma_calculs_2021_2025",
        "libelle": "HEP Labe 2021-2025 (calcul Kuma)",
        "localite_code": "gin_labe",
        "code_serie_ghi_amont": "gin_labe_ghi_nasa_power_2021_2025",
    },
    {
        "code": "gin_kankan_hep_kuma_calculs_2021_2025",
        "libelle": "HEP Kankan 2021-2025 (calcul Kuma)",
        "localite_code": "gin_kankan",
        "code_serie_ghi_amont": "gin_kankan_ghi_nasa_power_2021_2025",
    },
    {
        "code": "gin_nzerekore_hep_kuma_calculs_2021_2025",
        "libelle": "HEP Nzerekore 2021-2025 (calcul Kuma)",
        "localite_code": "gin_nzerekore",
        "code_serie_ghi_amont": "gin_nzerekore_ghi_nasa_power_2021_2025",
    },
]

CODES_SERIES_HEP_1_5: tuple[str, ...] = tuple(s["code"] for s in _SERIES_HEP_KUMA)
"""Codes naturels des 6 séries HEP, exposés pour réutilisation en
migration 027 (ingestion) et tests d'intégration."""


def upgrade() -> None:
    bind = op.get_bind()

    # === 1. Résolution dynamique des codes naturels en IDs ===
    # Grandeur (cle naturelle UNIQUE non-PK) : vérification de presence.
    grandeur_existe = bind.execute(
        sa.text("SELECT 1 FROM grandeurs_referentiel WHERE code = :code"),
        {"code": _GRANDEUR_CODE},
    ).scalar_one_or_none()
    if grandeur_existe is None:
        raise RuntimeError(
            f"Migration 026 : grandeur_code {_GRANDEUR_CODE!r} introuvable "
            "dans grandeurs_referentiel. Verifier la migration 010."
        )

    source_id = bind.execute(
        sa.text("SELECT id FROM sources WHERE code = :code"),
        {"code": _SOURCE_CODE},
    ).scalar_one_or_none()
    if source_id is None:
        raise RuntimeError(
            f"Migration 026 : source_code {_SOURCE_CODE!r} introuvable dans "
            "sources. Verifier la migration 025."
        )

    localite_codes = [s["localite_code"] for s in _SERIES_HEP_KUMA]
    rows = bind.execute(
        sa.text("SELECT code, id FROM localites WHERE code = ANY(:codes)"),
        {"codes": localite_codes},
    ).all()
    localite_id_par_code: dict[str, int] = {row.code: int(row.id) for row in rows}

    codes_manquants = set(localite_codes) - localite_id_par_code.keys()
    if codes_manquants:
        raise RuntimeError(
            f"Migration 026 : localite_code(s) introuvable(s) dans "
            f"localites : {sorted(codes_manquants)}. Verifier la "
            "migration 011 (seed 20 localites pilotes Guinee)."
        )

    # === 2. Construction des lignes à insérer ===
    series_metadonnees_table = sa.table(
        "series_metadonnees",
        sa.column("code", sa.String),
        sa.column("libelle", sa.Text),
        sa.column("localite_id", sa.BigInteger),
        sa.column("grandeur_code", sa.String),
        sa.column("source_id", sa.BigInteger),
        sa.column("periode_debut", sa.Date),
        sa.column("periode_fin", sa.Date),
        sa.column("methode_collecte", sa.String),
        sa.column("methode_collecte_doc", sa.Text),
        sa.column("commentaire_editorial", sa.Text),
        sa.column("url_documentation", sa.Text),
    )

    lignes_a_inserer: list[dict[str, Any]] = [
        {
            "code": serie["code"],
            "libelle": serie["libelle"],
            "localite_id": localite_id_par_code[serie["localite_code"]],
            "grandeur_code": _GRANDEUR_CODE,
            "source_id": int(source_id),
            "periode_debut": _PERIODE_DEBUT,
            "periode_fin": _PERIODE_FIN,
            "methode_collecte": _METHODE_COLLECTE,
            "methode_collecte_doc": _METHODE_COLLECTE_DOC,
            "commentaire_editorial": _commentaire_editorial(serie["code_serie_ghi_amont"]),
            "url_documentation": _URL_DOCUMENTATION,
        }
        for serie in _SERIES_HEP_KUMA
    ]

    op.bulk_insert(series_metadonnees_table, lignes_a_inserer)


def downgrade() -> None:
    # DELETE des 6 séries HEP par code naturel. La migration 027 d'ingestion
    # aura déjà été annulée en cascade par la procédure downgrade : aucune
    # ligne grandeurs_metier ne référence ces series_metadonnees_id.
    op.execute(
        sa.text("DELETE FROM series_metadonnees WHERE code = ANY(:codes)").bindparams(
            sa.bindparam("codes", value=list(CODES_SERIES_HEP_1_5))
        )
    )
