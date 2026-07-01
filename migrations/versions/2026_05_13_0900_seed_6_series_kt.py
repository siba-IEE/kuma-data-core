"""seed_6_series_kt

Revision ID: 028
Revises: 027
Create Date: 2026-05-13 09:00:00.000000+00:00

Seed des 6 séries `kt` (Indice de clarté) pour les 6 villes guinéennes
pilotes. Pattern hérité des migrations 021 (seed 25 séries)
et 019 (seed 4 séries Conakry).

Particularité : `kt` est une grandeur Kuma traduite **ingérée
directement** depuis NASA POWER (paramètre `ALLSKY_KT`, disponible
nativement - confirmé sur Conakry-Kaloum : 1826 jours retournés,
1 sentinelle, plage [0.060, 0.740] moy 0.536). `methode_collecte
= 'modele_satellitaire'` → stockage `mesures_ressource`.

Cohorte : 6 villes (Conakry-Kaloum **inclus** cette fois, à la
différence de la cohorte précédente qui couvrait uniquement les 5
nouvelles villes).

Toutes les séries partagent :
- `grandeur_code = 'kt'`
- `source_code = 'nasa_power'`
- `periode_debut = 2021-01-01`
- `periode_fin = 2025-12-31`
- `methode_collecte = 'modele_satellitaire'`
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date
from typing import Any

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "028"
down_revision: str | Sequence[str] | None = "027"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# Énumération exhaustive des 6 villes pilotes.
_LOCALITES_1_6A: tuple[str, ...] = (
    "gin_conakry_kaloum",
    "gin_kankan",
    "gin_kindia",
    "gin_labe",
    "gin_mamou",
    "gin_nzerekore",
)

_GRANDEUR_CODE: str = "kt"
_SOURCE_CODE: str = "nasa_power"
_PERIODE_DEBUT: date = date(2021, 1, 1)
_PERIODE_FIN: date = date(2025, 12, 31)
_METHODE_COLLECTE: str = "modele_satellitaire"
_METHODE_COLLECTE_DOC: str = "https://power.larc.nasa.gov/docs/methodology/"
_URL_DOCUMENTATION: str = "https://power.larc.nasa.gov/"

# Libellés humains des villes (pour `series_metadonnees.libelle`).
_LIBELLES_VILLES: dict[str, str] = {
    "gin_conakry_kaloum": "Conakry-Kaloum",
    "gin_kankan": "Kankan",
    "gin_kindia": "Kindia",
    "gin_labe": "Labe",
    "gin_mamou": "Mamou",
    "gin_nzerekore": "Nzerekore",
}

_COMMENTAIRE_EDITORIAL_TEMPLATE: str = (
    "Serie Kt (indice de clarte) ingeree directement depuis NASA POWER "
    "parametre ALLSKY_KT. Localite : {ville_libelle}, Guinee. Methode "
    "satellitaire CERES SYN1deg + FLASHFlux. Spike 1-2a a valide la "
    "disponibilite native et la plage observee [0.06, 0.74] sur "
    "Conakry-Kaloum (moy 0.536). Cohorte 1-6A : 6 villes pilotes phase 1 "
    "(Conakry-Kaloum inclus). Acknowledgement NASA POWER cf. fiche "
    "source seedee en 1-1E."
)


def _prefixe_ville_pour_serie(localite_code: str) -> str:
    """Préfixe ville utilisé dans le code de série, hérité du pattern repo.

    Conakry-Kaloum (localite_code = `gin_conakry_kaloum`) utilise le préfixe
    historique `gin_conakry` dans les codes de série (cf. migrations 016,
    019, 026 : `gin_conakry_ghi_*`, `gin_conakry_dhi_*`, `gin_conakry_hep_*`).
    Les 5 autres villes utilisent leur `localite_code` tel quel.
    """
    if localite_code == "gin_conakry_kaloum":
        return "gin_conakry"
    return localite_code


def _code_serie(localite_code: str) -> str:
    """Convention naming : `<prefixe_ville>_kt_nasa_power_2021_2025`."""
    return f"{_prefixe_ville_pour_serie(localite_code)}_{_GRANDEUR_CODE}_{_SOURCE_CODE}_2021_2025"


def upgrade() -> None:
    bind = op.get_bind()

    # === Résolution des 6 localite_id ===
    lignes_localites = bind.execute(
        sa.text("SELECT code, id FROM localites WHERE code = ANY(:codes)"),
        {"codes": list(_LOCALITES_1_6A)},
    ).all()
    localite_id_par_code: dict[str, int] = {r.code: int(r.id) for r in lignes_localites}
    codes_manquants = set(_LOCALITES_1_6A) - localite_id_par_code.keys()
    if codes_manquants:
        raise RuntimeError(
            f"Migration 028 : localite_code(s) introuvable(s) : "
            f"{sorted(codes_manquants)}. Verifier la migration 011."
        )

    # === Résolution source_id ===
    source_id = bind.execute(
        sa.text("SELECT id FROM sources WHERE code = :code"),
        {"code": _SOURCE_CODE},
    ).scalar_one_or_none()
    if source_id is None:
        raise RuntimeError(
            f"Migration 028 : source_code {_SOURCE_CODE!r} introuvable. Verifier la migration 012."
        )

    # === Vérification que la grandeur kt existe dans grandeurs_referentiel ===
    grandeur_existe = bind.execute(
        sa.text("SELECT 1 FROM grandeurs_referentiel WHERE code = :code"),
        {"code": _GRANDEUR_CODE},
    ).scalar_one_or_none()
    if grandeur_existe is None:
        raise RuntimeError(
            f"Migration 028 : grandeur_code {_GRANDEUR_CODE!r} introuvable "
            "dans grandeurs_referentiel. Verifier la migration 010 (seed 1-1C)."
        )

    # === Construction des 6 lignes à insérer ===
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

    lignes_a_inserer: list[dict[str, Any]] = []
    for localite_code in _LOCALITES_1_6A:
        libelle = f"Kt journalier {_LIBELLES_VILLES[localite_code]} 2021-2025 (NASA POWER)"
        commentaire = _COMMENTAIRE_EDITORIAL_TEMPLATE.format(
            ville_libelle=_LIBELLES_VILLES[localite_code],
        )
        lignes_a_inserer.append(
            {
                "code": _code_serie(localite_code),
                "libelle": libelle,
                "localite_id": localite_id_par_code[localite_code],
                "grandeur_code": _GRANDEUR_CODE,
                "source_id": int(source_id),
                "periode_debut": _PERIODE_DEBUT,
                "periode_fin": _PERIODE_FIN,
                "methode_collecte": _METHODE_COLLECTE,
                "methode_collecte_doc": _METHODE_COLLECTE_DOC,
                "commentaire_editorial": commentaire,
                "url_documentation": _URL_DOCUMENTATION,
            }
        )

    assert len(lignes_a_inserer) == 6, (
        f"Expected 6 series (6 villes x 1 grandeur kt), got {len(lignes_a_inserer)}"
    )
    op.bulk_insert(series_metadonnees_table, lignes_a_inserer)


def downgrade() -> None:
    codes_supprimer = [_code_serie(loc) for loc in _LOCALITES_1_6A]
    op.execute(
        sa.text("DELETE FROM series_metadonnees WHERE code = ANY(:codes)").bindparams(
            sa.bindparam("codes", value=codes_supprimer)
        )
    )
