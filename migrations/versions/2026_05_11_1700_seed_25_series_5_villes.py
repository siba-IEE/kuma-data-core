"""seed_25_series_5_villes_guineennes_pilotes

Revision ID: 021
Revises: 020
Create Date: 2026-05-11 17:00:00.000000+00:00

Seed des 25 nouvelles séries pour les 5 villes guinéennes pilotes
restantes. Élargit le périmètre qui couvrait
uniquement Conakry-Kaloum (5 séries).

Pattern hérité des migrations 016 (1 série Conakry GHI) et 019
(4 séries Conakry DNI/DHI/T2M/RH2M). Boucle Python sur le produit
cartésien 5 villes × 5 grandeurs.

5 nouvelles localités : Kankan, Kindia, Labé, Mamou, Nzérékoré
5 grandeurs : GHI, DNI, DHI, T2M, RH2M
Total : 25 nouvelles séries (Conakry déjà couvert).

Toutes les séries partagent :
- source_code = ``nasa_power``
- periode_debut = 2021-01-01
- periode_fin = 2025-12-31
- methode_collecte = ``modele_satellitaire``
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date
from typing import Any

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "021"
down_revision: str | Sequence[str] | None = "020"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# Énumération exhaustive des 5 nouvelles localités pilotes.
_LOCALITES_1_4: tuple[str, ...] = (
    "gin_kankan",
    "gin_kindia",
    "gin_labe",
    "gin_mamou",
    "gin_nzerekore",
)

# Énumération exhaustive des 5 grandeurs brutes.
_GRANDEURS: tuple[str, ...] = ("ghi", "dni", "dhi", "t2m", "rh2m")

# Libellés humains pour la grandeur (utilisés dans series_metadonnees.libelle).
_LIBELLES_GRANDEURS: dict[str, str] = {
    "ghi": "GHI journalier",
    "dni": "DNI journalier",
    "dhi": "DHI journalier",
    "t2m": "Temperature 2m journaliere",
    "rh2m": "Humidite relative 2m journaliere",
}

# Libellés humains des villes (utilisés dans series_metadonnees.libelle).
_LIBELLES_VILLES: dict[str, str] = {
    "gin_kankan": "Kankan",
    "gin_kindia": "Kindia",
    "gin_labe": "Labe",
    "gin_mamou": "Mamou",
    "gin_nzerekore": "Nzerekore",
}

_SOURCE_CODE: str = "nasa_power"
_PERIODE_DEBUT: date = date(2021, 1, 1)
_PERIODE_FIN: date = date(2025, 12, 31)
_METHODE_COLLECTE: str = "modele_satellitaire"
_METHODE_COLLECTE_DOC: str = "https://power.larc.nasa.gov/docs/methodology/"
_URL_DOCUMENTATION: str = "https://power.larc.nasa.gov/"

_COMMENTAIRE_EDITORIAL_TEMPLATE: str = (
    "Serie etendue en etape 1-4 (elargissement aux 6 villes guineennes "
    "pilotes). Donnee brute {grandeur_upper} ingeree depuis NASA POWER, "
    "methode satellitaire (CERES SYN1deg pour solaire / MERRA-2 GMAO "
    "pour climat). Localite : {ville_libelle}, Guinee. Cohorte 1-4 :"
    " 5 villes x 5 grandeurs = 25 series."
)


def _code_serie(localite_code: str, grandeur_code: str) -> str:
    """Convention naming : `<localite>_<grandeur>_<source>_2021_2025`."""
    return f"{localite_code}_{grandeur_code}_{_SOURCE_CODE}_2021_2025"


def upgrade() -> None:
    bind = op.get_bind()

    # === Résolution des 5 localite_id ===
    lignes_localites = bind.execute(
        sa.text("SELECT code, id FROM localites WHERE code = ANY(:codes)"),
        {"codes": list(_LOCALITES_1_4)},
    ).all()
    localite_id_par_code: dict[str, int] = {r.code: int(r.id) for r in lignes_localites}
    codes_manquants = set(_LOCALITES_1_4) - localite_id_par_code.keys()
    if codes_manquants:
        raise RuntimeError(
            f"Migration 021 : localite_code(s) introuvable(s) : "
            f"{sorted(codes_manquants)}. Verifier la migration 011."
        )

    # === Résolution source_id ===
    source_id = bind.execute(
        sa.text("SELECT id FROM sources WHERE code = :code"),
        {"code": _SOURCE_CODE},
    ).scalar_one_or_none()
    if source_id is None:
        raise RuntimeError(
            f"Migration 021 : source_code {_SOURCE_CODE!r} introuvable. Verifier la migration 012."
        )

    # === Vérification que les 5 grandeurs existent ===
    grandeurs_trouvees = set(
        bind.execute(
            sa.text("SELECT code FROM grandeurs_referentiel WHERE code = ANY(:codes)"),
            {"codes": list(_GRANDEURS)},
        )
        .scalars()
        .all()
    )
    grandeurs_manquantes = set(_GRANDEURS) - grandeurs_trouvees
    if grandeurs_manquantes:
        raise RuntimeError(
            f"Migration 021 : grandeur_code(s) introuvable(s) : "
            f"{sorted(grandeurs_manquantes)}. Verifier la migration 015."
        )

    # === Construction des 25 lignes à insérer (5 villes x 5 grandeurs) ===
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
    for localite_code in _LOCALITES_1_4:
        for grandeur_code in _GRANDEURS:
            libelle = (
                f"{_LIBELLES_GRANDEURS[grandeur_code]} {_LIBELLES_VILLES[localite_code]} "
                f"2021-2025 (NASA POWER)"
            )
            commentaire = _COMMENTAIRE_EDITORIAL_TEMPLATE.format(
                grandeur_upper=grandeur_code.upper(),
                ville_libelle=_LIBELLES_VILLES[localite_code],
            )
            lignes_a_inserer.append(
                {
                    "code": _code_serie(localite_code, grandeur_code),
                    "libelle": libelle,
                    "localite_id": localite_id_par_code[localite_code],
                    "grandeur_code": grandeur_code,
                    "source_id": source_id,
                    "periode_debut": _PERIODE_DEBUT,
                    "periode_fin": _PERIODE_FIN,
                    "methode_collecte": _METHODE_COLLECTE,
                    "methode_collecte_doc": _METHODE_COLLECTE_DOC,
                    "commentaire_editorial": commentaire,
                    "url_documentation": _URL_DOCUMENTATION,
                }
            )

    assert len(lignes_a_inserer) == 25, (
        f"Expected 25 series (5 villes x 5 grandeurs), got {len(lignes_a_inserer)}"
    )
    op.bulk_insert(series_metadonnees_table, lignes_a_inserer)


def downgrade() -> None:
    codes_supprimer = [_code_serie(loc, gr) for loc in _LOCALITES_1_4 for gr in _GRANDEURS]
    op.execute(
        sa.text("DELETE FROM series_metadonnees WHERE code = ANY(:codes)").bindparams(
            sa.bindparam("codes", value=codes_supprimer)
        )
    )
