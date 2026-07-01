"""seed_24_series_kuma_calculs

Revision ID: 030
Revises: 029
Create Date: 2026-05-13 10:00:00.000000+00:00

Seed des 24 séries calculées Kuma pour les 4 grandeurs F1 calcul_derive
sur les 6 villes pilotes :

- fraction_diffuse  : 6 séries (DHI/GHI amont, périodes annuel + mensuel)
- humidex           : 6 séries (T2M/RH2M amont, périodes annuel + mensuel)
- productible_specifique_theorique : 6 séries (HEP amont, périodes annuel + mensuel)
- variabilite_journaliere : 6 séries (GHI amont, période annuelle uniquement)

Total : 4 grandeurs × 6 villes = 24 séries calculées.

Toutes partagent :
- source_code = `kuma_calculs` (seedée par la migration 025)
- methode_collecte = `calcul_derive`
- periode_debut = 2021-01-01, periode_fin = 2025-12-31

Pattern hérité de la migration 026 (seed 6 séries HEP) étendu
à 4 grandeurs × 6 villes via boucle.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date
from typing import Any

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "030"
down_revision: str | Sequence[str] | None = "029"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# Énumération exhaustive des 6 villes pilotes.
_LOCALITES_1_6: tuple[str, ...] = (
    "gin_conakry_kaloum",
    "gin_kankan",
    "gin_kindia",
    "gin_labe",
    "gin_mamou",
    "gin_nzerekore",
)

# Énumération exhaustive des 4 grandeurs Kuma F1 calcul_derive.
_GRANDEURS_KUMA_1_6: tuple[str, ...] = (
    "fraction_diffuse",
    "humidex",
    "productible_specifique_theorique",
    "variabilite_journaliere",
)

_SOURCE_CODE: str = "kuma_calculs"
_METHODE_COLLECTE: str = "calcul_derive"
_PERIODE_DEBUT: date = date(2021, 1, 1)
_PERIODE_FIN: date = date(2025, 12, 31)
_URL_DOCUMENTATION_BASE: str = "docs/methodologie/grandeurs"

# Libellés humains des villes.
_LIBELLES_VILLES: dict[str, str] = {
    "gin_conakry_kaloum": "Conakry-Kaloum",
    "gin_kankan": "Kankan",
    "gin_kindia": "Kindia",
    "gin_labe": "Labe",
    "gin_mamou": "Mamou",
    "gin_nzerekore": "Nzerekore",
}

# Libellés humains des grandeurs (pour libelle de série).
_LIBELLES_GRANDEURS: dict[str, str] = {
    "fraction_diffuse": "Fraction diffuse annuelle et mensuelle",
    "humidex": "Humidex moyen annuel et mensuel",
    "productible_specifique_theorique": "Productible specifique theorique annuel et mensuel",
    "variabilite_journaliere": "Variabilite journaliere annuelle (CoV)",
}


def _prefixe_ville_pour_serie(localite_code: str) -> str:
    """Préfixe ville pour code série (cf. migration 028)."""
    if localite_code == "gin_conakry_kaloum":
        return "gin_conakry"
    return localite_code


# Séries amont par grandeur (template `{prefixe_ville}` substitué dynamiquement).
# Format : grandeur -> liste de descriptifs de séries amont (pour
# commentaire_editorial).
_SERIES_AMONT_PAR_GRANDEUR: dict[str, list[str]] = {
    "fraction_diffuse": [
        "{prefixe_ville}_dhi_nasa_power_2021_2025",
        "{prefixe_ville}_ghi_nasa_power_2021_2025",
    ],
    "humidex": [
        "{prefixe_ville}_t2m_nasa_power_2021_2025",
        "{prefixe_ville}_rh2m_nasa_power_2021_2025",
    ],
    "productible_specifique_theorique": [
        "{prefixe_ville}_hep_kuma_calculs_2021_2025",
    ],
    "variabilite_journaliere": [
        "{prefixe_ville}_ghi_nasa_power_2021_2025",
    ],
}


def _code_serie(localite_code: str, grandeur_code: str) -> str:
    """Convention naming : `<prefixe_ville>_<grandeur>_kuma_calculs_2021_2025`."""
    return f"{_prefixe_ville_pour_serie(localite_code)}_{grandeur_code}_{_SOURCE_CODE}_2021_2025"


def _commentaire_editorial(localite_code: str, grandeur_code: str) -> str:
    """Construit le commentaire editorial pour une serie calculee Kuma."""
    prefixe = _prefixe_ville_pour_serie(localite_code)
    series_amont = [
        s.replace("{prefixe_ville}", prefixe) for s in _SERIES_AMONT_PAR_GRANDEUR[grandeur_code]
    ]
    series_amont_str = " + ".join(series_amont)
    return (
        f"Serie {grandeur_code} calculee Kuma a partir de {series_amont_str}. "
        f"Localite : {_LIBELLES_VILLES[localite_code]}, Guinee. Methode : "
        f"calcul_derive Kuma selon module "
        f"src/kuma_data_core/services/grandeurs/{grandeur_code}.py "
        f"(etape 1-6B). Politique de completude stricte 100% jours civils v1. "
        f"Fiche methodologique : {_URL_DOCUMENTATION_BASE}/{grandeur_code}.md. "
        f"Version_formule actuelle : 1. Cohorte 1-6D : 24 series "
        f"(4 grandeurs x 6 villes pilotes phase 1)."
    )


def upgrade() -> None:
    bind = op.get_bind()

    # === Resolution des codes naturels en IDs ===
    # Grandeurs (verifier que les 4 existent)
    grandeurs_trouvees = set(
        bind.execute(
            sa.text("SELECT code FROM grandeurs_referentiel WHERE code = ANY(:codes)"),
            {"codes": list(_GRANDEURS_KUMA_1_6)},
        )
        .scalars()
        .all()
    )
    grandeurs_manquantes = set(_GRANDEURS_KUMA_1_6) - grandeurs_trouvees
    if grandeurs_manquantes:
        raise RuntimeError(
            f"Migration 030 : grandeur_code(s) introuvable(s) dans "
            f"grandeurs_referentiel : {sorted(grandeurs_manquantes)}. "
            "Verifier migration 010 (seed 1-1C)."
        )

    # Source kuma_calculs
    source_id = bind.execute(
        sa.text("SELECT id FROM sources WHERE code = :code"),
        {"code": _SOURCE_CODE},
    ).scalar_one_or_none()
    if source_id is None:
        raise RuntimeError(
            f"Migration 030 : source_code {_SOURCE_CODE!r} introuvable. "
            "Verifier migration 025 (seed 1-5D-i)."
        )

    # Localites
    rows = bind.execute(
        sa.text("SELECT code, id FROM localites WHERE code = ANY(:codes)"),
        {"codes": list(_LOCALITES_1_6)},
    ).all()
    localite_id_par_code: dict[str, int] = {r.code: int(r.id) for r in rows}
    codes_manquants = set(_LOCALITES_1_6) - localite_id_par_code.keys()
    if codes_manquants:
        raise RuntimeError(
            f"Migration 030 : localite_code(s) introuvable(s) : "
            f"{sorted(codes_manquants)}. Verifier migration 011."
        )

    # === Construction des 24 lignes a inserer ===
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
    for grandeur_code in _GRANDEURS_KUMA_1_6:
        for localite_code in _LOCALITES_1_6:
            url_doc = f"{_URL_DOCUMENTATION_BASE}/{grandeur_code}.md"
            libelle = (
                f"{_LIBELLES_GRANDEURS[grandeur_code]} "
                f"{_LIBELLES_VILLES[localite_code]} 2021-2025 (calcul Kuma)"
            )
            lignes_a_inserer.append(
                {
                    "code": _code_serie(localite_code, grandeur_code),
                    "libelle": libelle,
                    "localite_id": localite_id_par_code[localite_code],
                    "grandeur_code": grandeur_code,
                    "source_id": int(source_id),
                    "periode_debut": _PERIODE_DEBUT,
                    "periode_fin": _PERIODE_FIN,
                    "methode_collecte": _METHODE_COLLECTE,
                    "methode_collecte_doc": url_doc,
                    "commentaire_editorial": _commentaire_editorial(localite_code, grandeur_code),
                    "url_documentation": url_doc,
                }
            )

    assert len(lignes_a_inserer) == 24, (
        f"Expected 24 series (4 grandeurs x 6 villes), got {len(lignes_a_inserer)}"
    )
    op.bulk_insert(series_metadonnees_table, lignes_a_inserer)


def downgrade() -> None:
    codes_supprimer = [_code_serie(loc, gr) for gr in _GRANDEURS_KUMA_1_6 for loc in _LOCALITES_1_6]
    op.execute(
        sa.text("DELETE FROM series_metadonnees WHERE code = ANY(:codes)").bindparams(
            sa.bindparam("codes", value=codes_supprimer)
        )
    )
