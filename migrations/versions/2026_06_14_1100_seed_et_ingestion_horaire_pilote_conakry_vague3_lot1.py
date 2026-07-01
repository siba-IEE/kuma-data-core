"""seed_et_ingestion_horaire_pilote_conakry_vague3_lot1

Revision ID: 054
Revises: 053
Create Date: 2026-06-14 11:00:00.000000+00:00

Ingestion **pilote** des donnees horaires NASA POWER
pour Conakry-Kaloum (ville pilote n°1), fenetre 2021-2023, 6 grandeurs.
But : valider de bout en bout la table ``mesures_ressource_horaires``,
le module d'ingestion et le routage, sur un echantillon inspectable qui
chevauche le journalier deja valide (cross-check ulterieur). Les 5 autres
villes et la profondeur 2001-2020 suivent ensuite.

Donnees ingerees en statut **``brut``** : le controle qualite
algorithmique (doctrine ``doctrine-qc-horaire.md``) intervient ensuite et fera
passer les lignes valides en ``valide_auto``. Tant que ce QC n'a pas
bascule, l'horaire reste accessible via le passe-plat ``/v1/horaire`` et
n'est pas expose via ``/v1/series`` (garde explicite cote API).

6 grandeurs (arbitrage chantier ; coherent avec le passe-plat) :

| Grandeur Kuma | Parametre NASA POWER |
|---------------|----------------------|
| ghi           | ALLSKY_SFC_SW_DWN    |
| dni           | ALLSKY_SFC_SW_DNI    |
| dhi           | ALLSKY_SFC_SW_DIFF   |
| t2m           | T2M                  |
| rh2m          | RH2M                 |
| kt            | ALLSKY_KT            |

Naming des series : ``gin_conakry_<grandeur>_nasa_power_2021_2023``
(exception Conakry-Kaloum : prefixe ``gin_conakry`` sans ``_kaloum``).
``granularite = 'horaire'`` pose explicitement sur chaque serie (les
nouvelles series ne sont pas couvertes par le backfill de la migration
052). Instant en ``TIMESTAMPTZ`` UTC (cf. doctrine QC).

Volume reseau : 6 grandeurs x 3 annees = 18 appels NASA POWER hourly
(un par grandeur et par annee, borne <= 366 jours).
Volume stocke : 150 000 lignes (24 h x 365 j x 3 ans x 6 grandeurs,
moins les sentinelles nocturnes -999 filtrees, notamment KT).

Variable d'environnement court-circuit (pattern CI sans reseau) :
``KUMA_SKIP_NASA_POWER_INGESTION=1`` court-circuite l'ingestion (les 6
series restent inserees, aucune mesure ingeree).

Pattern reutilise des migrations 041 / 050 (seed + ingestion par
migration, aucune modification de code applicatif).
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date
from typing import Any

import sqlalchemy as sa
from alembic import op
from sqlalchemy.orm import Session

from kuma_data_core.ingestion.nasa_power_hourly import ingerer_serie_horaire

# revision identifiers, used by Alembic.
revision: str = "054"
down_revision: str | Sequence[str] | None = "053"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# === Énumérations exhaustives ============================================

_LOCALITE_CODE: str = "gin_conakry_kaloum"
_VILLE_LIBELLE: str = "Conakry-Kaloum"

# Mapping grandeur Kuma -> parametre NASA POWER (hourly). Coherent avec
# le mapping du passe-plat (services/horaire.py).
_MAPPING_GRANDEURS: dict[str, str] = {
    "ghi": "ALLSKY_SFC_SW_DWN",
    "dni": "ALLSKY_SFC_SW_DNI",
    "dhi": "ALLSKY_SFC_SW_DIFF",
    "t2m": "T2M",
    "rh2m": "RH2M",
    "kt": "ALLSKY_KT",
}

_ANNEE_DEBUT: int = 2021
_ANNEE_FIN: int = 2023

_SOURCE_CODE_SQL: str = "nasa_power"
_METHODE_COLLECTE: str = "modele_satellitaire"
_METHODE_COLLECTE_DOC: str = "https://power.larc.nasa.gov/docs/methodology/"
_URL_DOCUMENTATION: str = "https://power.larc.nasa.gov/"
_GRANULARITE: str = "horaire"

_LIBELLES_GRANDEURS_SERIE: dict[str, str] = {
    "ghi": "GHI horaire brut",
    "dni": "DNI horaire brut",
    "dhi": "DHI horaire brut",
    "t2m": "Temperature 2m horaire brute",
    "rh2m": "Humidite relative 2m horaire brute",
    "kt": "Indice de clarte horaire brut",
}

_COMMENTAIRE_EDITORIAL_TEMPLATE: str = (
    "Serie horaire brute pilote inscrite en Phase 2 vague 3 lot 1. Donnee "
    "{grandeur_upper} ingeree depuis NASA POWER endpoint hourly, parametre "
    "{parametre_nasa}, fenetre {annee_debut}-{annee_fin}, fuseau UTC. "
    "Methode satellitaire. Localite : {ville_libelle}, Guinee. Statut brut "
    "(non validee) : le controle qualite algorithmique horaire (doctrine "
    "QC, lot 2) fera passer les lignes valides en valide_auto. Niveau de "
    "confiance B (modele satellitaire). Non exposee via /v1/series tant "
    "que le lot 3 n'a pas leve passe_plat_non_valide."
)


def _code_serie(grandeur_code: str) -> str:
    """Convention de nommage : ``gin_conakry_<grandeur>_nasa_power_2021_2023``."""
    return f"gin_conakry_{grandeur_code}_nasa_power_{_ANNEE_DEBUT}_{_ANNEE_FIN}"


def upgrade() -> None:
    bind = op.get_bind()

    # === Étape 1 : résolution localité (id + lat/lon) + source ============
    ligne_localite = bind.execute(
        sa.text(
            "SELECT id, "
            "CAST(latitude AS DOUBLE PRECISION) AS lat, "
            "CAST(longitude AS DOUBLE PRECISION) AS lon "
            "FROM localites WHERE code = :code"
        ),
        {"code": _LOCALITE_CODE},
    ).first()
    if ligne_localite is None:
        raise RuntimeError(
            f"Migration 054 : localite {_LOCALITE_CODE!r} introuvable. "
            f"Verifier la migration 011 (seed localites)."
        )
    localite_id = int(ligne_localite.id)
    latitude = float(ligne_localite.lat)
    longitude = float(ligne_localite.lon)

    source_id = bind.execute(
        sa.text("SELECT id FROM sources WHERE code = :code"),
        {"code": _SOURCE_CODE_SQL},
    ).scalar_one_or_none()
    if source_id is None:
        raise RuntimeError(
            f"Migration 054 : source_code {_SOURCE_CODE_SQL!r} introuvable. "
            f"Verifier la migration 012 (seed sources)."
        )

    # === Étape 2 : vérification des 6 grandeurs cibles actives ============
    codes_grandeurs = sorted(_MAPPING_GRANDEURS.keys())
    grandeurs_trouvees = set(
        bind.execute(
            sa.text(
                "SELECT code FROM grandeurs_referentiel WHERE code = ANY(:codes) AND actif = TRUE"
            ),
            {"codes": codes_grandeurs},
        )
        .scalars()
        .all()
    )
    grandeurs_manquantes = set(codes_grandeurs) - grandeurs_trouvees
    if grandeurs_manquantes:
        raise RuntimeError(
            f"Migration 054 : grandeur_code(s) introuvable(s) ou inactive(s) : "
            f"{sorted(grandeurs_manquantes)}. Les 6 brutes doivent etre actives."
        )

    # === Étape 3 : seed des 6 séries horaires (granularite='horaire') =====
    series_metadonnees_table = sa.table(
        "series_metadonnees",
        sa.column("code", sa.String),
        sa.column("libelle", sa.Text),
        sa.column("localite_id", sa.BigInteger),
        sa.column("grandeur_code", sa.String),
        sa.column("source_id", sa.BigInteger),
        sa.column("periode_debut", sa.Date),
        sa.column("periode_fin", sa.Date),
        sa.column("granularite", sa.String),
        sa.column("methode_collecte", sa.String),
        sa.column("methode_collecte_doc", sa.Text),
        sa.column("commentaire_editorial", sa.Text),
        sa.column("url_documentation", sa.Text),
    )

    lignes_series: list[dict[str, Any]] = []
    for grandeur_code, parametre_nasa in _MAPPING_GRANDEURS.items():
        libelle = (
            f"{_LIBELLES_GRANDEURS_SERIE[grandeur_code]} {_VILLE_LIBELLE} "
            f"{_ANNEE_DEBUT}-{_ANNEE_FIN} (NASA POWER hourly, UTC)"
        )
        commentaire = _COMMENTAIRE_EDITORIAL_TEMPLATE.format(
            grandeur_upper=grandeur_code.upper(),
            parametre_nasa=parametre_nasa,
            annee_debut=_ANNEE_DEBUT,
            annee_fin=_ANNEE_FIN,
            ville_libelle=_VILLE_LIBELLE,
        )
        lignes_series.append(
            {
                "code": _code_serie(grandeur_code),
                "libelle": libelle,
                "localite_id": localite_id,
                "grandeur_code": grandeur_code,
                "source_id": source_id,
                "periode_debut": date(_ANNEE_DEBUT, 1, 1),
                "periode_fin": date(_ANNEE_FIN, 12, 31),
                "granularite": _GRANULARITE,
                "methode_collecte": _METHODE_COLLECTE,
                "methode_collecte_doc": _METHODE_COLLECTE_DOC,
                "commentaire_editorial": commentaire,
                "url_documentation": _URL_DOCUMENTATION,
            }
        )

    assert len(lignes_series) == 6, (
        f"Expected 6 series (6 grandeurs x 1 ville), got {len(lignes_series)}"
    )
    op.bulk_insert(series_metadonnees_table, lignes_series)

    # === Étape 4 : ingestion horaire des 6 séries =========================
    session = Session(bind=bind)
    try:
        decomptes_totaux: dict[str, int] = {}
        for grandeur_code, parametre_nasa in _MAPPING_GRANDEURS.items():
            code_serie = _code_serie(grandeur_code)
            n_lignes = ingerer_serie_horaire(
                session=session,
                code_serie=code_serie,
                parametre_nasa=parametre_nasa,
                latitude=latitude,
                longitude=longitude,
                annee_debut=_ANNEE_DEBUT,
                annee_fin=_ANNEE_FIN,
            )
            decomptes_totaux[code_serie] = n_lignes

        total = sum(decomptes_totaux.values())
        op.execute(
            f"-- Migration 054 : {total} lignes inserees dans "
            f"mesures_ressource_horaires (6 grandeurs x Conakry-Kaloum "
            f"{_ANNEE_DEBUT}-{_ANNEE_FIN}). Decompte par serie : {decomptes_totaux}"
        )
    finally:
        session.close()


def downgrade() -> None:
    codes_series = [_code_serie(grandeur_code) for grandeur_code in _MAPPING_GRANDEURS]

    # Suppression des mesures (FK RESTRICT sur serie_id) avant les series.
    op.execute(
        sa.text(
            """
            DELETE FROM mesures_ressource_horaires
            WHERE serie_id IN (
                SELECT id FROM series_metadonnees WHERE code = ANY(:codes)
            )
            """
        ).bindparams(sa.bindparam("codes", value=codes_series))
    )
    op.execute(
        sa.text("DELETE FROM series_metadonnees WHERE code = ANY(:codes)").bindparams(
            sa.bindparam("codes", value=codes_series)
        )
    )
