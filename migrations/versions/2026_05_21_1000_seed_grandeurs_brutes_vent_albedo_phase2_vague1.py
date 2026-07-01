"""seed_grandeurs_brutes_vent_albedo_phase2_vague1

Revision ID: 047
Revises: 046
Create Date: 2026-05-21 10:00:00.000000+00:00

Seed des grandeurs
et des séries vent/albédo journalières 2021-2025 pour les 6 villes
pilotes.

Trois nouvelles grandeurs brutes ingérées depuis NASA POWER (F1
stockée, cohérent avec le pattern des brutes ghi/dni/dhi/t2m/rh2m) :

- ``vent_2m`` (paramètre NASA POWER ``WS2M``, MERRA-2 GMAO, m/s) -
  entrée du modèle thermique Faiman 2008 pour la grandeur F2
  ``productible_correction_thermique``.
- ``vent_10m`` (paramètre NASA POWER ``WS10M``, MERRA-2 GMAO, m/s) -
  cohorte vent complémentaire pour usages potentiels éoliens
  (hors périmètre solaire).
- ``albedo_surface`` (paramètre NASA POWER ``ALLSKY_SRF_ALB``,
  sans dimension) - entrée de la composante réfléchie des modèles
  POA et préparation du bifacial.

Dix-huit nouvelles séries (6 villes × 3 grandeurs), toutes en
``methode_collecte = 'modele_satellitaire'``, ``source = 'nasa_power'``,
``periode_debut = 2021-01-01``, ``periode_fin = 2025-12-31`` (aligné
sur les séries journalières brutes existantes).

Convention de naming reprise des migrations 016, 019, 021 :
``gin_<slug_serie>_<grandeur>_nasa_power_2021_2025``. Les slugs
``conakry`` et ``conakry_kaloum`` co-existent par convention historique :
le slug de série ``conakry`` est utilisé alors que le code localité
DB est ``gin_conakry_kaloum`` (cf. migration 016 pivot).

Pattern hérité de la migration 015 (seed grandeurs brutes inline avec
résolution dynamique ``unite_code -> unite_id``) et de la migration 021
(seed séries pour 5 villes pilotes par produit cartésien). Les unités
``metre_par_seconde`` et ``sans_unite`` existent déjà dans la table
``unites`` (seed initial des unités) : aucune création
d'unité requise.

Aucune ingestion dans cette migration - l'ingestion 6 villes × 3
grandeurs est portée par la migration 048 voisine.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date
from typing import Any

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "047"
down_revision: str | Sequence[str] | None = "046"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# === Nouvelles grandeurs (énumération exhaustive) ===================

_GRANDEURS_VENT_ALBEDO: list[dict[str, Any]] = [
    {
        "code": "vent_2m",
        "libelle": "Vent à 2 mètres",
        "famille": "F1",
        "strategie_calcul": "stockee",
        "unite_code": "metre_par_seconde",
        "description": (
            "Vitesse moyenne journalière du vent à 2 mètres au-dessus "
            "de la surface. Donnée brute ingérée depuis NASA POWER "
            "paramètre WS2M (source MERRA-2 GMAO). Entrée du modèle "
            "Faiman 2008 pour la température cellule de la grandeur F2 "
            "productible_correction_thermique (résorbe la dette D-43)."
        ),
    },
    {
        "code": "vent_10m",
        "libelle": "Vent à 10 mètres",
        "famille": "F1",
        "strategie_calcul": "stockee",
        "unite_code": "metre_par_seconde",
        "description": (
            "Vitesse moyenne journalière du vent à 10 mètres au-dessus "
            "de la surface. Donnée brute ingérée depuis NASA POWER "
            "paramètre WS10M (source MERRA-2 GMAO). Cohorte vent "
            "complémentaire pour usages potentiels éoliens ; hors "
            "périmètre Phase 2 (solaire uniquement)."
        ),
    },
    {
        "code": "albedo_surface",
        "libelle": "Albédo de surface",
        "famille": "F1",
        "strategie_calcul": "stockee",
        "unite_code": "sans_unite",
        "description": (
            "Albédo de surface (réflectivité du sol, sans dimension, "
            "plage théorique [0, 1]). Donnée brute ingérée depuis NASA "
            "POWER paramètre ALLSKY_SRF_ALB. Entrée de la composante "
            "réfléchie pour les modèles POA et préparation du bifacial "
            "(Phase 2 vague 5)."
        ),
    },
]

_CODES_GRANDEURS_VENT_ALBEDO: tuple[str, ...] = tuple(g["code"] for g in _GRANDEURS_VENT_ALBEDO)


# === Localités et slugs de série (énumération exhaustive) ============

# Mapping localite_code DB -> slug utilisé dans le code série (convention
# historique : Conakry-Kaloum utilise le slug court `conakry`, les
# 5 autres villes utilisent leur code localité tel quel).
_LOCALITES_PILOTES: list[tuple[str, str, str]] = [
    # (localite_code, slug_serie, libelle_ville)
    ("gin_conakry_kaloum", "gin_conakry", "Conakry-Kaloum"),
    ("gin_kankan", "gin_kankan", "Kankan"),
    ("gin_kindia", "gin_kindia", "Kindia"),
    ("gin_labe", "gin_labe", "Labe"),
    ("gin_mamou", "gin_mamou", "Mamou"),
    ("gin_nzerekore", "gin_nzerekore", "Nzerekore"),
]

_LIBELLES_GRANDEURS_SERIE: dict[str, str] = {
    "vent_2m": "Vent 2m journalier",
    "vent_10m": "Vent 10m journalier",
    "albedo_surface": "Albedo de surface journalier",
}

_SOURCE_CODE: str = "nasa_power"
_PERIODE_DEBUT: date = date(2021, 1, 1)
_PERIODE_FIN: date = date(2025, 12, 31)
_METHODE_COLLECTE: str = "modele_satellitaire"
_METHODE_COLLECTE_DOC: str = "https://power.larc.nasa.gov/docs/methodology/"
_URL_DOCUMENTATION: str = "https://power.larc.nasa.gov/"

_COMMENTAIRE_EDITORIAL_TEMPLATE: str = (
    "Serie inscrite en Phase 2 vague 1 (chantier A vent/albedo). "
    "Donnee brute {grandeur_upper} ingeree depuis NASA POWER, "
    "methode satellitaire ({source_amont}). Localite : {ville_libelle}, "
    "Guinee. Cohorte vague 1-A : 6 villes x 3 grandeurs = 18 series."
)

_SOURCE_AMONT_PAR_GRANDEUR: dict[str, str] = {
    "vent_2m": "MERRA-2 GMAO",
    "vent_10m": "MERRA-2 GMAO",
    "albedo_surface": "CERES SYN1deg",
}


def _code_serie(slug_serie: str, grandeur_code: str) -> str:
    """Convention de naming : `<slug_serie>_<grandeur>_nasa_power_2021_2025`."""
    return f"{slug_serie}_{grandeur_code}_{_SOURCE_CODE}_2021_2025"


def upgrade() -> None:
    bind = op.get_bind()

    # === Étape 1 : insertion des 3 nouvelles grandeurs ====================
    # Résolution dynamique unite_code -> unite_id (pattern migration 015).
    codes_unites_attendus: set[str] = {entree["unite_code"] for entree in _GRANDEURS_VENT_ALBEDO}
    lignes_unites = bind.execute(
        sa.text("SELECT code, id FROM unites WHERE code = ANY(:codes)"),
        {"codes": list(codes_unites_attendus)},
    ).all()
    unite_id_par_code: dict[str, int] = {row.code: int(row.id) for row in lignes_unites}

    codes_unites_manquants = codes_unites_attendus - unite_id_par_code.keys()
    if codes_unites_manquants:
        raise RuntimeError(
            f"Migration 047 : unite_code(s) introuvable(s) dans unites : "
            f"{sorted(codes_unites_manquants)}. Verifier le seed initial "
            f"des unites (phase 0)."
        )

    grandeurs_referentiel_table = sa.table(
        "grandeurs_referentiel",
        sa.column("code", sa.String),
        sa.column("libelle", sa.Text),
        sa.column("unite_id", sa.BigInteger),
        sa.column("famille", sa.String),
        sa.column("strategie_calcul", sa.String),
        sa.column("description", sa.Text),
    )

    lignes_grandeurs_a_inserer: list[dict[str, Any]] = []
    for entree in _GRANDEURS_VENT_ALBEDO:
        ligne = {**entree, "unite_id": unite_id_par_code[entree["unite_code"]]}
        ligne.pop("unite_code")
        lignes_grandeurs_a_inserer.append(ligne)

    assert len(lignes_grandeurs_a_inserer) == 3, (
        f"Expected 3 grandeurs vent/albedo, got {len(lignes_grandeurs_a_inserer)}"
    )
    op.bulk_insert(grandeurs_referentiel_table, lignes_grandeurs_a_inserer)

    # === Étape 2 : insertion des 18 nouvelles séries (6 villes x 3) =======
    # Résolution dynamique des 6 localite_id.
    codes_localites: list[str] = [loc[0] for loc in _LOCALITES_PILOTES]
    lignes_localites = bind.execute(
        sa.text("SELECT code, id FROM localites WHERE code = ANY(:codes)"),
        {"codes": codes_localites},
    ).all()
    localite_id_par_code: dict[str, int] = {r.code: int(r.id) for r in lignes_localites}

    codes_localites_manquants = set(codes_localites) - localite_id_par_code.keys()
    if codes_localites_manquants:
        raise RuntimeError(
            f"Migration 047 : localite_code(s) introuvable(s) : "
            f"{sorted(codes_localites_manquants)}. Verifier la migration 011 "
            f"(seed 20 localites pilotes Guinee)."
        )

    # Résolution source_id NASA POWER.
    source_id = bind.execute(
        sa.text("SELECT id FROM sources WHERE code = :code"),
        {"code": _SOURCE_CODE},
    ).scalar_one_or_none()
    if source_id is None:
        raise RuntimeError(
            f"Migration 047 : source_code {_SOURCE_CODE!r} introuvable. "
            f"Verifier la migration 012 (seed 9 sources passe 1-1E)."
        )

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

    lignes_series_a_inserer: list[dict[str, Any]] = []
    for localite_code, slug_serie, ville_libelle in _LOCALITES_PILOTES:
        for grandeur_entree in _GRANDEURS_VENT_ALBEDO:
            grandeur_code = grandeur_entree["code"]
            libelle = (
                f"{_LIBELLES_GRANDEURS_SERIE[grandeur_code]} {ville_libelle} 2021-2025 (NASA POWER)"
            )
            commentaire = _COMMENTAIRE_EDITORIAL_TEMPLATE.format(
                grandeur_upper=grandeur_code.upper(),
                source_amont=_SOURCE_AMONT_PAR_GRANDEUR[grandeur_code],
                ville_libelle=ville_libelle,
            )
            lignes_series_a_inserer.append(
                {
                    "code": _code_serie(slug_serie, grandeur_code),
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

    assert len(lignes_series_a_inserer) == 18, (
        f"Expected 18 series (6 villes x 3 grandeurs), got {len(lignes_series_a_inserer)}"
    )
    op.bulk_insert(series_metadonnees_table, lignes_series_a_inserer)


def downgrade() -> None:
    # === Étape 1 : suppression des 18 séries ==============================
    codes_series_supprimer = [
        _code_serie(slug_serie, grandeur_entree["code"])
        for _, slug_serie, _ in _LOCALITES_PILOTES
        for grandeur_entree in _GRANDEURS_VENT_ALBEDO
    ]
    op.execute(
        sa.text("DELETE FROM series_metadonnees WHERE code = ANY(:codes)").bindparams(
            sa.bindparam("codes", value=codes_series_supprimer)
        )
    )

    # === Étape 2 : suppression des 3 grandeurs ============================
    op.execute(
        sa.text("DELETE FROM grandeurs_referentiel WHERE code = ANY(:codes)").bindparams(
            sa.bindparam("codes", value=list(_CODES_GRANDEURS_VENT_ALBEDO))
        )
    )
