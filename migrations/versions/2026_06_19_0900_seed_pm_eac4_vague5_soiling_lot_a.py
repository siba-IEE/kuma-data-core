"""seed_pm_eac4_vague5_soiling_lot_a

Revision ID: 081
Revises: 080
Create Date: 2026-06-19 09:00:00.000000+00:00

PM2.5 / PM10 EAC4 (Seed Offline).

Seconde ingestion particules du proxy de salissure HSU.
Inscrit en base, **tout depuis le seed committe** ``cams_eac4_seed_data.py``
(produit hors-ligne par ``scripts/preparer_seed_cams_eac4.py``) :

1. source neuve ``cams_eac4`` (reanalyse EAC4, ADS Copernicus) ;
2. unite ``microgramme_par_metre_cube`` (ug/m3, grandeur ``concentration_massique``,
   nouvelle categorie ; aucun DDL, ``unites.grandeur`` est String sans CHECK) ;
3. grandeurs brutes ``pm2_5`` et ``pm10`` (F1, stockee) ;
4. 12 series journalieres (6 villes x 2 grandeurs) ;
5. 20 448 mesures journalieres, fenetre reelle 2021-01-01 -> **2025-08-31**.

**Aucun reseau ici** (pas de ``cdsapi`` / ``httpx`` ni appel ADS) : discipline
seed-offline, ``alembic upgrade head`` deterministe et offline, ingestion live
en CI non aggravee.

Fenetre : le naming reste ``_2021_2025`` (fenetre demandee) mais
``periode_fin = 2025-08-31`` reflete la couverture **reelle** d'EAC4 (latence de
reanalyse 10 mois en juin 2026). L'intersection PM ∩ pluie du HSU sera
donc 2021-01 a 2025-08.

Confiance **B** derivee (``modele_satellitaire`` ; pas ``mesure_directe`` -> la
regle R3 ne donne pas A). Grille EAC4 grossiere 0,75 deg (caveat de resolution
grossiere).

Pattern : source (migration 074), unite + grandeur + series + mesures depuis seed
(migration 080, tolerant au seed vide). Sur seed vide, les 12 series sont creees
avec 0 mesure (le test d'integration saute alors ses assertions de donnees).
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date
from decimal import Decimal
from typing import Any

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql
from sqlalchemy.dialects.postgresql import ARRAY

from kuma_data_core.db.seeds.cams_eac4_seed_data import CAMS_EAC4_JOURNALIER_SEED

# revision identifiers, used by Alembic.
revision: str = "081"
down_revision: str | Sequence[str] | None = "080"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# === Source cams_eac4 (clone migration 074) ================================

_CODE_SOURCE = "cams_eac4"

_SOURCE: dict[str, Any] = {
    "code": _CODE_SOURCE,
    "titre": (
        "CAMS EAC4 - ECMWF Atmospheric Composition Reanalysis 4 (cams-global-reanalysis-eac4)"
    ),
    "auteurs": None,
    "organisation": "ECMWF / Copernicus Atmosphere Monitoring Service (CAMS)",
    "type_source": "base_donnees",
    "annee_publication": None,  # reanalyse continue, pas d'annee unique (cf. metadonnees)
    "date_consultation": date(2026, 6, 18),
    "url": "https://ads.atmosphere.copernicus.eu/datasets/cams-global-reanalysis-eac4",
    "doi": None,  # DOI dataset ADS non confirme par source autoritaire (ne rien inventer)
    "isbn": None,
    "metadonnees": {
        "dataset_id": "cams-global-reanalysis-eac4",
        "store": "ADS (Atmosphere Data Store, Copernicus)",
        "licence": "Copernicus (CC-BY)",
        "resolution_grille": "0,75 deg",
        "pas_temporel_source": "3-horaire (00/03/06/09/12/15/18/21 UTC)",
        "agregation_kuma": "moyenne journaliere des pas 3-horaires (concentration intensive)",
        "conversion": "kg/m3 (natif) -> ug/m3 (x 1e9)",
        "variables_ingerees": ["pm2.5 (pm2p5)", "pm10"],
        "periode_reelle": "2021-01-01 a 2025-08-31",
        "latence_reanalyse": "10 mois (juin 2026 : EAC4 borne a aout 2025)",
        "note_hsu": "le modele HSU consomme les PM de surface, pas l'AOD",
        "annee_publication_statut": "reanalyse continue ; reference methodologique Inness et al. 2019",
        "reference_methodologique": (
            "Inness, A. et al. (2019), The CAMS reanalysis of atmospheric "
            "composition, Atmos. Chem. Phys. 19, 3515-3556, "
            "doi:10.5194/acp-19-3515-2019"
        ),
    },
    "fiabilite": "haute",
    "langue": "en",
    "notes": (
        "Reanalyse de composition atmospherique EAC4 (ECMWF Atmospheric "
        "Composition Reanalysis 4, CAMS), servie par l'ADS Copernicus. Fournit "
        "PM2.5 et PM10 de surface (kg/m3 natif, converti ug/m3) au pas 3-horaire, "
        "agreges en moyenne journaliere par Kuma. Entree particules du modele de "
        "salissure HSU (proxy taux_salissure_proxy, Vague 5 Lot C) : le HSU "
        "consomme les PM, pas l'AOD. Confiance B derivee (modele satellitaire, pas "
        "mesure directe -> R3 ne donne pas A). Grille grossiere 0,75 deg (caveat "
        "L-SOIL-4). Couverture reelle 2021-01-01 a 2025-08-31 (latence de reanalyse "
        "10 mois). Licence Copernicus (CC-BY) ; attribution : Generated using "
        "Copernicus Atmosphere Monitoring Service Information 2026. DOI dataset et "
        "annee de publication non confirmes (non inventes) ; reference methodologique "
        "Inness et al. 2019 (doi:10.5194/acp-19-3515-2019)."
    ),
}


# === Unite microgramme_par_metre_cube (clone migration 080) ================

_UNITE_CODE = "microgramme_par_metre_cube"

_UNITE_SEED: dict[str, Any] = {
    "code": _UNITE_CODE,
    "libelle": "microgramme par metre cube",
    "symbole": "µg/m³",
    "grandeur": "concentration_massique",
    "systeme": "SI",
    "est_unite_de_base": False,
    "facteur_conversion_si": Decimal("1E-9"),
    "decalage_conversion_si": Decimal("0"),
    "code_unite_si": "kilogramme_par_metre_cube",
    "note_methodologique": (
        "Concentration massique de particules dans l'air (masse de particules par "
        "volume d'air). Sous-multiple decimal du kg/m3 : 1 ug/m3 = 1e-9 kg/m3. "
        "Unite standard de la qualite de l'air (PM2.5 / PM10)."
    ),
    "references_normatives": [
        "BIPM SI Brochure 9eme edition (2019)",
        "WHO Global Air Quality Guidelines (2021)",
    ],
}


# === Grandeurs pm2_5 / pm10 ================================================

_GRANDEURS: list[dict[str, Any]] = [
    {
        "code": "pm2_5",
        "libelle": "Particules fines PM2.5",
        "famille": "F1",
        "strategie_calcul": "stockee",
        "description": (
            "Concentration massique journaliere de particules fines de diametre "
            "<= 2,5 um (ug/m3). Donnee brute EAC4 (ADS Copernicus), moyenne "
            "journaliere du pas 3-horaire. Entree particules du modele de salissure "
            "HSU (pvlib.soiling.hsu) pour la grandeur proxy taux_salissure_proxy "
            "(Vague 5 soiling Lot C). Confiance B (modele satellitaire)."
        ),
    },
    {
        "code": "pm10",
        "libelle": "Particules PM10",
        "famille": "F1",
        "strategie_calcul": "stockee",
        "description": (
            "Concentration massique journaliere de particules de diametre <= 10 um "
            "(ug/m3). Donnee brute EAC4 (ADS Copernicus), moyenne journaliere du pas "
            "3-horaire. Entree particules du modele de salissure HSU "
            "(pvlib.soiling.hsu) pour la grandeur proxy taux_salissure_proxy "
            "(Vague 5 soiling Lot C). Inclut les PM2.5 (PM10 >= PM2.5). Confiance B."
        ),
    },
]
_CODES_GRANDEURS: tuple[str, ...] = tuple(g["code"] for g in _GRANDEURS)


# === Localites / slugs / series (enumeration exhaustive) ===================

_LOCALITES_PILOTES: list[tuple[str, str, str]] = [
    ("gin_conakry_kaloum", "gin_conakry", "Conakry-Kaloum"),
    ("gin_kankan", "gin_kankan", "Kankan"),
    ("gin_kindia", "gin_kindia", "Kindia"),
    ("gin_labe", "gin_labe", "Labe"),
    ("gin_mamou", "gin_mamou", "Mamou"),
    ("gin_nzerekore", "gin_nzerekore", "Nzerekore"),
]

_SOURCE_CODE = "cams_eac4"
_PERIODE_DEBUT: date = date(2021, 1, 1)
_PERIODE_FIN: date = date(2025, 8, 31)  # couverture reelle EAC4 (latence 10 mois)
_GRANULARITE = "journalier"
_METHODE_COLLECTE = "modele_satellitaire"
_METHODE_COLLECTE_DOC = "https://ads.atmosphere.copernicus.eu/datasets/cams-global-reanalysis-eac4"
_URL_DOCUMENTATION = "https://ads.atmosphere.copernicus.eu/datasets/cams-global-reanalysis-eac4"

_LIBELLE_GRANDEUR_SERIE: dict[str, str] = {
    "pm2_5": "PM2.5 journalier",
    "pm10": "PM10 journalier",
}


def _code_serie(slug_serie: str, grandeur_code: str) -> str:
    """Convention naming : ``<slug_serie>_<grandeur>_cams_eac4_2021_2025``."""
    return f"{slug_serie}_{grandeur_code}_{_SOURCE_CODE}_2021_2025"


def _commentaire_serie(ville_libelle: str, grandeur_code: str) -> str:
    return (
        f"Serie EAC4 {grandeur_code.upper()} journalier {ville_libelle}, Guinee. "
        f"Reanalyse Copernicus EAC4 (ADS), grille 0,75 deg, concentration de surface "
        f"(ug/m3, moyenne journaliere du pas 3-horaire). Confiance B (modele "
        f"satellitaire). Vague 5 soiling Lot A. Naming _2021_2025 mais couverture "
        f"reelle bornee au 2025-08-31 (latence de reanalyse EAC4 10 mois). Entree "
        f"particules du HSU (Lot C). Attribution : Generated using Copernicus "
        f"Atmosphere Monitoring Service Information 2026 (licence CC-BY)."
    )


def upgrade() -> None:
    bind = op.get_bind()

    # === Etape 1 : source cams_eac4 ======================================
    sources_table = sa.table(
        "sources",
        sa.column("code", sa.String),
        sa.column("titre", sa.Text),
        sa.column("auteurs", postgresql.ARRAY(sa.Text)),
        sa.column("organisation", sa.String),
        sa.column("type_source", sa.String),
        sa.column("annee_publication", sa.Integer),
        sa.column("date_consultation", sa.Date),
        sa.column("url", sa.Text),
        sa.column("doi", sa.String),
        sa.column("isbn", sa.String),
        sa.column("metadonnees", postgresql.JSONB),
        sa.column("fiabilite", sa.String),
        sa.column("langue", sa.String),
        sa.column("notes", sa.Text),
    )
    op.bulk_insert(sources_table, [_SOURCE])

    # === Etape 2 : unite microgramme_par_metre_cube ======================
    unites_table = sa.table(
        "unites",
        sa.column("code", sa.String),
        sa.column("libelle", sa.Text),
        sa.column("symbole", sa.String),
        sa.column("grandeur", sa.String),
        sa.column("systeme", sa.String),
        sa.column("est_unite_de_base", sa.Boolean),
        sa.column("facteur_conversion_si", sa.Numeric(60, 30)),
        sa.column("decalage_conversion_si", sa.Numeric(60, 30)),
        sa.column("code_unite_si", sa.String),
        sa.column("note_methodologique", sa.Text),
        sa.column("references_normatives", ARRAY(sa.Text())),
    )
    op.bulk_insert(unites_table, [_UNITE_SEED])

    # === Etape 3 : grandeurs pm2_5 / pm10 (resolution unite_id) ===========
    unite_id = bind.execute(
        sa.text("SELECT id FROM unites WHERE code = :code"),
        {"code": _UNITE_CODE},
    ).scalar_one_or_none()
    if unite_id is None:
        raise RuntimeError(f"Migration 081 : unite {_UNITE_CODE!r} introuvable apres insertion.")

    grandeurs_table = sa.table(
        "grandeurs_referentiel",
        sa.column("code", sa.String),
        sa.column("libelle", sa.Text),
        sa.column("unite_id", sa.BigInteger),
        sa.column("famille", sa.String),
        sa.column("strategie_calcul", sa.String),
        sa.column("description", sa.Text),
    )
    op.bulk_insert(
        grandeurs_table,
        [{**g, "unite_id": int(unite_id)} for g in _GRANDEURS],
    )

    # === Etape 4 : 12 series (6 villes x 2 grandeurs) ====================
    codes_localites = [loc[0] for loc in _LOCALITES_PILOTES]
    localite_id: dict[str, int] = {
        r.code: int(r.id)
        for r in bind.execute(
            sa.text("SELECT code, id FROM localites WHERE code = ANY(:codes)"),
            {"codes": codes_localites},
        ).all()
    }
    manquants = set(codes_localites) - localite_id.keys()
    if manquants:
        raise RuntimeError(f"Migration 081 : localite(s) introuvable(s) : {sorted(manquants)}.")

    source_id = bind.execute(
        sa.text("SELECT id FROM sources WHERE code = :code"),
        {"code": _SOURCE_CODE},
    ).scalar_one_or_none()
    if source_id is None:
        raise RuntimeError(f"Migration 081 : source {_SOURCE_CODE!r} introuvable apres insertion.")

    series_table = sa.table(
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
    for localite_code, slug_serie, ville_libelle in _LOCALITES_PILOTES:
        for grandeur_code in _CODES_GRANDEURS:
            lignes_series.append(
                {
                    "code": _code_serie(slug_serie, grandeur_code),
                    "libelle": (
                        f"{_LIBELLE_GRANDEUR_SERIE[grandeur_code]} {ville_libelle} 2021-2025 (EAC4)"
                    ),
                    "localite_id": localite_id[localite_code],
                    "grandeur_code": grandeur_code,
                    "source_id": int(source_id),
                    "periode_debut": _PERIODE_DEBUT,
                    "periode_fin": _PERIODE_FIN,
                    "granularite": _GRANULARITE,
                    "methode_collecte": _METHODE_COLLECTE,
                    "methode_collecte_doc": _METHODE_COLLECTE_DOC,
                    "commentaire_editorial": _commentaire_serie(ville_libelle, grandeur_code),
                    "url_documentation": _URL_DOCUMENTATION,
                }
            )
    assert len(lignes_series) == 12, f"Attendu 12 series, obtenu {len(lignes_series)}"
    op.bulk_insert(series_table, lignes_series)

    # Map (localite_code, grandeur_code) -> serie_id.
    serie_id_par_cle: dict[tuple[str, str], int] = {}
    code_vers_cle = {
        _code_serie(slug, grandeur): (loc, grandeur)
        for loc, slug, _ in _LOCALITES_PILOTES
        for grandeur in _CODES_GRANDEURS
    }
    for r in bind.execute(
        sa.text("SELECT code, id FROM series_metadonnees WHERE code = ANY(:codes)"),
        {"codes": [s["code"] for s in lignes_series]},
    ).all():
        serie_id_par_cle[code_vers_cle[r.code]] = int(r.id)

    # === Etape 5 : mesures depuis le seed ================================
    mesures_table = sa.table(
        "mesures_ressource",
        sa.column("serie_id", sa.BigInteger),
        sa.column("instant_mesure", sa.Date),
        sa.column("valeur", sa.Float),
        sa.column("niveau_confiance_derive", sa.String),
    )
    lignes_mesures = [
        {
            "serie_id": serie_id_par_cle[(r["localite_code"], r["grandeur_code"])],
            "instant_mesure": date.fromisoformat(r["date"]),
            "valeur": r["valeur"],
            "niveau_confiance_derive": "B",
        }
        for r in CAMS_EAC4_JOURNALIER_SEED
    ]
    if lignes_mesures:
        op.bulk_insert(mesures_table, lignes_mesures)

    op.execute(
        f"-- Migration 081 : source cams_eac4 + unite ug/m3 + grandeurs pm2_5/pm10 "
        f"+ 12 series + {len(lignes_mesures)} mesures (seed offline EAC4)."
    )


def downgrade() -> None:
    codes_series = [
        _code_serie(slug, grandeur)
        for _, slug, _ in _LOCALITES_PILOTES
        for grandeur in _CODES_GRANDEURS
    ]
    op.execute(
        sa.text(
            "DELETE FROM mesures_ressource WHERE serie_id IN "
            "(SELECT id FROM series_metadonnees WHERE code = ANY(:codes))"
        ).bindparams(sa.bindparam("codes", value=codes_series))
    )
    op.execute(
        sa.text("DELETE FROM series_metadonnees WHERE code = ANY(:codes)").bindparams(
            sa.bindparam("codes", value=codes_series)
        )
    )
    op.execute(
        sa.text("DELETE FROM grandeurs_referentiel WHERE code = ANY(:codes)").bindparams(
            sa.bindparam("codes", value=list(_CODES_GRANDEURS))
        )
    )
    op.execute(
        sa.text("DELETE FROM unites WHERE code = :code").bindparams(
            sa.bindparam("code", value=_UNITE_CODE)
        )
    )
    op.execute(
        sa.text("DELETE FROM sources WHERE code = :code").bindparams(
            sa.bindparam("code", value=_CODE_SOURCE)
        )
    )
