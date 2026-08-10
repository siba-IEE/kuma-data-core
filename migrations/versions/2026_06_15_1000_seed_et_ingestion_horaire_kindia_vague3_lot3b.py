"""seed_et_ingestion_horaire_kindia_vague3_lot3b

Revision ID: 056
Revises: 055
Create Date: 2026-06-15 10:00:00.000000+00:00

Ingestion horaire NASA POWER **pleine profondeur**
(2001-2023, 6 grandeurs) pour Kindia (``gin_kindia``), premiere ville
neuve du rollout horaire. Valide le passage a l'echelle (pixel
**interieur**, profondeur 23 ans) avant le rollout des 4 villes
restantes et le backfill Conakry.

Serie **unique pleine profondeur** par grandeur (arbitrage chantier) :
``gin_kindia_<grandeur>_nasa_power_2001_2023`` couvre toute la fenetre,
jamais segmentee. Cette forme preserve sans retouche le lever du passe-plat
(``api/v1/horaire.py::_chercher_serie_horaire_stockee`` : ``LIMIT 1``
+ couverture mono-serie). ``granularite = 'horaire'`` pose explicitement
(non couvert par le backfill 052). Instant ``TIMESTAMPTZ`` UTC.

6 grandeurs (mapping identique au pilote 054) :

| Grandeur Kuma | Parametre NASA POWER |
|---------------|----------------------|
| ghi           | ALLSKY_SFC_SW_DWN    |
| dni           | ALLSKY_SFC_SW_DNI    |
| dhi           | ALLSKY_SFC_SW_DIFF   |
| t2m           | T2M                  |
| rh2m          | RH2M                 |
| kt            | ALLSKY_KT            |

Volume reseau : 6 grandeurs x 23 annees = **138 appels** NASA POWER
hourly (un par grandeur et par annee, borne <= 366 jours).
Volume stocke : ~**1,1 M lignes** brut (extrapolation du pilote 48 k
lignes/an/grandeur-ville apres filtrage des sentinelles nocturnes -999).

Garde-fou d'ingestion de masse : la variable
``KUMA_SKIP_INGESTION_MASSE_HORAIRE`` (truthy) court-circuite la **seule
ingestion** ; les 6 series restent seedees (structure verifiee en CI),
0 mesure ingeree. Posee dans ``ci.yml`` et ``ci-nightly.yml`` : aucun
des deux jobs ne fait les 138 appels live. L'ingestion reelle + la
QC sur les 1,1 M lignes (migration 057) s'executent manuellement hors CI
(``alembic upgrade head`` local sans la variable). Distincte du switch
global ``KUMA_SKIP_NASA_POWER_INGESTION`` (qui skiperait aussi le pilote
054 et casserait les tests d'integration correspondants) ;
``ingerer_serie_horaire`` honore par ailleurs ce switch global, les deux
sont composables.

Pattern reutilise des migrations 054 (seed + ingestion horaire) sans
modification de code applicatif.
"""

from __future__ import annotations

import os
from collections.abc import Sequence
from datetime import date
from typing import Any

import sqlalchemy as sa
from alembic import op
from sqlalchemy.orm import Session

from kuma_data_core.ingestion.nasa_power_hourly import ingerer_serie_horaire

# revision identifiers, used by Alembic.
revision: str = "056"
down_revision: str | Sequence[str] | None = "055"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# === Garde-fou ingestion de masse (CI) ===================================

_VARIABLE_ENV_SKIP_MASSE: str = "KUMA_SKIP_INGESTION_MASSE_HORAIRE"
"""Court-circuite la seule ingestion de masse (les series sont seedees).

Truthy values : '1', 'true', 'yes' (case-insensitive). Posee dans les
deux workflows CI (standard + nightly) pour eviter les 138 appels live
a chaque run. L'ingestion reelle se fait manuellement (alembic upgrade
head local sans cette variable). Distincte du switch global
``KUMA_SKIP_NASA_POWER_INGESTION`` (qui skiperait aussi le pilote 054)."""


def _skip_ingestion_masse() -> bool:
    """Lit la variable d'environnement et retourne True si elle est truthy."""
    return os.environ.get(_VARIABLE_ENV_SKIP_MASSE, "").strip().lower() in ("1", "true", "yes")


# === Énumérations exhaustives ============================================

_LOCALITE_CODE: str = "gin_kindia"
_VILLE_LIBELLE: str = "Kindia"

# Mapping grandeur Kuma -> parametre NASA POWER (hourly). Identique au
# pilote 054 (services/horaire.py).
_MAPPING_GRANDEURS: dict[str, str] = {
    "ghi": "ALLSKY_SFC_SW_DWN",
    "dni": "ALLSKY_SFC_SW_DNI",
    "dhi": "ALLSKY_SFC_SW_DIFF",
    "t2m": "T2M",
    "rh2m": "RH2M",
    "kt": "ALLSKY_KT",
}

_ANNEE_DEBUT: int = 2001
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
    "Serie horaire brute pleine profondeur inscrite en Phase 2 vague 3 "
    "lot 3b. Donnee {grandeur_upper} ingeree depuis NASA POWER endpoint "
    "hourly, parametre {parametre_nasa}, fenetre {annee_debut}-{annee_fin}, "
    "fuseau UTC. Methode satellitaire. Localite : {ville_libelle}, Guinee "
    "(pixel interieur). Statut brut (non validee) : le controle qualite "
    "algorithmique horaire (doctrine QC, migration 057) fera passer les "
    "lignes valides en valide_auto. Niveau de confiance B (modele "
    "satellitaire)."
)


def _code_serie(grandeur_code: str) -> str:
    """Convention de nommage : ``gin_kindia_<grandeur>_nasa_power_2001_2023``."""
    return f"{_LOCALITE_CODE}_{grandeur_code}_nasa_power_{_ANNEE_DEBUT}_{_ANNEE_FIN}"


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
            f"Migration 056 : localite {_LOCALITE_CODE!r} introuvable. "
            f"Verifier la migration 010 (seed 20 localites)."
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
            f"Migration 056 : source_code {_SOURCE_CODE_SQL!r} introuvable. "
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
            f"Migration 056 : grandeur_code(s) introuvable(s) ou inactive(s) : "
            f"{sorted(grandeurs_manquantes)}. Les 6 brutes doivent etre actives."
        )

    # === Étape 3 : seed des 6 séries horaires (granularite='horaire') =====
    # Le seed est inconditionnel (structure verifiee en CI meme quand
    # l'ingestion de masse est court-circuitee).
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

    # === Étape 4 : ingestion horaire des 6 séries (gardée) ================
    if _skip_ingestion_masse():
        op.execute(
            f"-- Migration 056 : ingestion de masse court-circuitee "
            f"({_VARIABLE_ENV_SKIP_MASSE}). 6 series Kindia seedees, 0 mesure "
            f"ingeree. Ingestion reelle a executer manuellement (cf. dette D-64)."
        )
        return

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
            f"-- Migration 056 : {total} lignes inserees dans "
            f"mesures_ressource_horaires (6 grandeurs x Kindia "
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
