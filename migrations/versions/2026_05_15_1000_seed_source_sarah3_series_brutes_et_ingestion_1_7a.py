"""seed_source_sarah3_series_brutes_et_ingestion_1_7a

Revision ID: 041
Revises: 040
Create Date: 2026-05-15 10:00:00.000000+00:00

Suite des migrations 039 et 040 préalables :
- Migration 039 a posé la table ``mesures_ressource_mensuelles``.
- Migration 040 a posé la migration corrective UNIQUE sur
  ``series_metadonnees`` (drift résolu pré-ingestion : passage de
  ``(localite_id, grandeur_code, source_id)`` à
  ``(localite_id, grandeur_code, source_id, periode_debut, periode_fin)``
  pour permettre les 2 séries NASA POWER GHI distinctes par localité).

Périmètre (énumération exhaustive) :

1. Insertion de la source ``sarah3_monthly`` dans ``sources``
   (institution CM SAF / EUMETSAT, méthode MAGICSOL, fiabilité
   ``'haute'``, plage ICDR 2021-présent).

2. Insertion de 12 séries brutes dans ``series_metadonnees`` selon
   la convention de naming :
   - 6 séries SARAH-3 ICDR : ``gin_<ville>_ghi_sarah3_2021_2023``
     (plage ramenée de 2025 à 2023).
   - 6 séries NASA POWER 1991-2020 : ``gin_<ville>_ghi_power_1991_2020``.
   - Exception Conakry-Kaloum via helper ``_prefixe_ville_pour_serie``
     (préfixe ``gin_conakry`` sans suffixe ``_kaloum``).

3. Ingestion de 2 376 lignes dans ``mesures_ressource_mensuelles`` :
   - 216 valeurs SARAH-3 ICDR (36 mois × 6 villes, plage 2021-2023)
     via ``ingerer_serie_sarah3_monthly`` (module
     ``ingestion/sarah3_monthly.py``).
   - 2 160 valeurs NASA POWER 1991-2020 (30 ans × 12 mois × 6 villes)
     via ``ingerer_serie_monthly`` (module
     ``ingestion/nasa_power_monthly.py``).

Limite API : PVGIS-SARAH3 ICDR v5.3 expose 2005-2023 à la date
d'exécution 2026-05 (retard de publication ICDR 3 ans). Plage
SARAH-3 ramenée à 2021-2023. Mitigation : ré-ingestion future
2024-2025 dès publication par JRC.

Idempotence : insertion source via ``ON CONFLICT DO NOTHING``
sur ``sources.code``. Insertion séries via ``bulk_insert``
(s'appuiera sur la contrainte UNIQUE de ``series_metadonnees.code``
en cas de rejouage). Insertion mesures protégée par la contrainte
EXCLUDE BTree-GiST de ``mesures_ressource_mensuelles`` (migration 039).

Variables d'environnement court-circuit (pattern CI sans réseau) :

- ``KUMA_SKIP_NASA_POWER_INGESTION=1`` court-circuite l'ingestion
  NASA POWER monthly (les 12 séries restent insérées).
- ``KUMA_SKIP_SARAH3_INGESTION=1`` court-circuite l'ingestion
  PVGIS-SARAH3.

Logging post-ingestion via ``op.execute('-- ...')`` (pattern migration
032 humidex) pour traçabilité.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date
from typing import Any

import sqlalchemy as sa
from alembic import op
from sqlalchemy.orm import Session

from kuma_data_core.ingestion.nasa_power_monthly import ingerer_serie_monthly
from kuma_data_core.ingestion.sarah3_monthly import ingerer_serie_sarah3_monthly

# revision identifiers, used by Alembic.
revision: str = "041"
down_revision: str | Sequence[str] | None = "040"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# === Énumérations exhaustives =====================================

_LOCALITES_1_7A: tuple[str, ...] = (
    "gin_conakry_kaloum",
    "gin_kankan",
    "gin_kindia",
    "gin_labe",
    "gin_mamou",
    "gin_nzerekore",
)

_LIBELLES_VILLES: dict[str, str] = {
    "gin_conakry_kaloum": "Conakry-Kaloum",
    "gin_kankan": "Kankan",
    "gin_kindia": "Kindia",
    "gin_labe": "Labe",
    "gin_mamou": "Mamou",
    "gin_nzerekore": "Nzerekore",
}


def _prefixe_ville_pour_serie(localite_code: str) -> str:
    """Préfixe ville pour code série (cf. migration 028)."""
    if localite_code == "gin_conakry_kaloum":
        return "gin_conakry"
    return localite_code


# === Source SARAH-3 monthly ================================================

_SOURCE_SARAH3_CODE: str = "sarah3_monthly"
_SOURCE_SARAH3_TITRE: str = (
    "PVGIS-SARAH3 ICDR : Surface Solar Radiation Data Set - Heliosat, "
    "chaine MAGICSOL CM SAF / EUMETSAT (Edition 3)"
)
_SOURCE_SARAH3_AUTEURS: tuple[str, ...] = ("CM SAF / EUMETSAT",)
_SOURCE_SARAH3_ORGANISATION: str = (
    "Satellite Application Facility on Climate Monitoring (CM SAF), "
    "EUMETSAT ; portage applicatif PVGIS par le Joint Research Centre "
    "(JRC) de la Commission europeenne."
)
_SOURCE_SARAH3_URL: str = "https://re.jrc.ec.europa.eu/api/v5_3/MRcalc"
_SOURCE_SARAH3_FIABILITE: str = "haute"
_SOURCE_SARAH3_NOTES: str = (
    "Chaine de retrieval MAGICSOL (Heliosat modifie Hammer et al. 2003 + "
    "gnu-MAGIC Mueller et al. 2009 + SPECMAGIC Mueller et al. 2012). "
    "Validee Afrique de l'Ouest par Sawadogo et al. 2023 (Renewable "
    "Energy 216:119066) et Kakou et al. 2025 (Remote Sensing 17(6):998). "
    "Validation Europe par Urraca et al. 2017, 2018. Edition 3 deployee "
    "depuis 2024 ; ICDR (Interim CDR) couvre 2021-present, complement de "
    "CDR (Climate Data Record) 1983-2020. Retenue en 1-7a comme source de "
    "reference inter-source pour ecart_relatif_referentiel "
    "(cf. note methodologique amont PR #53)."
)

# === Séries brutes 1-7α (12 entrées) =======================================

_GRANDEUR_GHI: str = "ghi"
_METHODE_COLLECTE: str = "modele_satellitaire"

# Plages temporelles distinctes par source
_PLAGE_SARAH3_DEBUT: date = date(2021, 1, 1)
_PLAGE_SARAH3_FIN: date = date(2023, 12, 31)
# Plage SARAH-3 ramenee a 2021-2023 (au lieu de 2021-2025
# initialement prevus) : drift atrape pre-implementation, API
# PVGIS-SARAH3 v5.3 expose 2005-2023 a la date d'execution 2026-05
# (retard de publication ICDR 3 ans). Mitigation : re-ingestion future
# 2024-2025 des publication par JRC.
_PLAGE_POWER_DEBUT: date = date(1991, 1, 1)
_PLAGE_POWER_FIN: date = date(2020, 12, 31)

_PARAMETRE_NASA_GHI: str = "ALLSKY_SFC_SW_DWN"


def _code_serie_sarah3(localite_code: str) -> str:
    """`gin_<ville>_ghi_sarah3_2021_2023` (plage ICDR effective)."""
    return f"{_prefixe_ville_pour_serie(localite_code)}_ghi_sarah3_2021_2023"


def _code_serie_power_1991_2020(localite_code: str) -> str:
    """`gin_<ville>_ghi_power_1991_2020`."""
    return f"{_prefixe_ville_pour_serie(localite_code)}_ghi_power_1991_2020"


def upgrade() -> None:
    bind = op.get_bind()

    # === Étape 1 : insertion source sarah3_monthly =========================
    bind.execute(
        sa.text(
            """
            INSERT INTO sources (
                code, titre, auteurs, organisation, type_source,
                url, fiabilite, langue, notes
            )
            VALUES (
                :code, :titre, :auteurs, :organisation, 'base_donnees',
                :url, :fiabilite, 'en', :notes
            )
            ON CONFLICT (code) DO NOTHING
            """
        ),
        {
            "code": _SOURCE_SARAH3_CODE,
            "titre": _SOURCE_SARAH3_TITRE,
            "auteurs": list(_SOURCE_SARAH3_AUTEURS),
            "organisation": _SOURCE_SARAH3_ORGANISATION,
            "url": _SOURCE_SARAH3_URL,
            "fiabilite": _SOURCE_SARAH3_FIABILITE,
            "notes": _SOURCE_SARAH3_NOTES,
        },
    )

    # === Étape 2 : résolution des IDs (localites + sources) =================
    lignes_localites = bind.execute(
        sa.text("SELECT code, id, latitude, longitude FROM localites WHERE code = ANY(:codes)"),
        {"codes": list(_LOCALITES_1_7A)},
    ).all()
    localite_par_code: dict[str, dict[str, Any]] = {
        r.code: {
            "id": int(r.id),
            "latitude": float(r.latitude),
            "longitude": float(r.longitude),
        }
        for r in lignes_localites
    }
    codes_manquants = set(_LOCALITES_1_7A) - localite_par_code.keys()
    if codes_manquants:
        raise RuntimeError(
            f"Migration 040 : localite_code(s) introuvable(s) : "
            f"{sorted(codes_manquants)}. Verifier la migration 011."
        )

    source_sarah3_id = bind.execute(
        sa.text("SELECT id FROM sources WHERE code = :code"),
        {"code": _SOURCE_SARAH3_CODE},
    ).scalar_one()
    source_nasa_power_id = bind.execute(
        sa.text("SELECT id FROM sources WHERE code = :code"),
        {"code": "nasa_power"},
    ).scalar_one()

    # === Étape 3 : insertion 12 séries brutes ==============================
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
        sa.column("commentaire_editorial", sa.Text),
    )

    lignes_series: list[dict[str, Any]] = []
    for localite_code in _LOCALITES_1_7A:
        ctx = localite_par_code[localite_code]
        libelle_ville = _LIBELLES_VILLES[localite_code]

        # Série SARAH-3 ICDR 2021-2023 (plage effective API JRC)
        lignes_series.append(
            {
                "code": _code_serie_sarah3(localite_code),
                "libelle": (f"GHI mensuel {libelle_ville} 2021-2023 (PVGIS-SARAH3 ICDR)"),
                "localite_id": int(ctx["id"]),
                "grandeur_code": _GRANDEUR_GHI,
                "source_id": int(source_sarah3_id),
                "periode_debut": _PLAGE_SARAH3_DEBUT,
                "periode_fin": _PLAGE_SARAH3_FIN,
                "methode_collecte": _METHODE_COLLECTE,
                "commentaire_editorial": (
                    f"Serie GHI mensuel ingeree depuis PVGIS-SARAH3 ICDR "
                    f"(chaine MAGICSOL CM SAF). Localite : {libelle_ville}, "
                    f"Guinee. Source de reference inter-source pour "
                    f"ecart_relatif_referentiel (cf. note methodologique "
                    f"amont PR #53 et spec 1-7 § 2). Etape 1-7a."
                ),
            }
        )

        # Série NASA POWER 1991-2020
        lignes_series.append(
            {
                "code": _code_serie_power_1991_2020(localite_code),
                "libelle": (
                    f"GHI mensuel {libelle_ville} 1991-2020 "
                    f"(NASA POWER, fenetre climatologique OMM)"
                ),
                "localite_id": int(ctx["id"]),
                "grandeur_code": _GRANDEUR_GHI,
                "source_id": int(source_nasa_power_id),
                "periode_debut": _PLAGE_POWER_DEBUT,
                "periode_fin": _PLAGE_POWER_FIN,
                "methode_collecte": _METHODE_COLLECTE,
                "commentaire_editorial": (
                    f"Serie GHI mensuel ingeree depuis NASA POWER sur la "
                    f"fenetre climatologique OMM 1991-2020. Localite : "
                    f"{libelle_ville}, Guinee. Source pour la distribution "
                    f"de reference de rang_referentiel_temporel "
                    f"(cf. note methodologique amont PR #53 et spec 1-7 "
                    f"§ 2). Coherence longitudinale assuree par quantile "
                    f"mapping interne POWER (Khadka et al. 2023) avec "
                    f"caveat documente limitation #15 note amont. "
                    f"Etape 1-7a."
                ),
            }
        )

    assert len(lignes_series) == 12, f"Migration 040 : attendu 12 series, recu {len(lignes_series)}"
    op.bulk_insert(series_metadonnees_table, lignes_series)

    # === Étape 4 : ingestion 2 520 lignes dans mesures_ressource_mensuelles =
    session = Session(bind=bind)
    try:
        total_sarah3 = 0
        total_power = 0
        decompte_par_ville: dict[str, dict[str, int]] = {}
        for localite_code in _LOCALITES_1_7A:
            ctx = localite_par_code[localite_code]

            n_sarah3 = ingerer_serie_sarah3_monthly(
                session=session,
                code_serie=_code_serie_sarah3(localite_code),
                latitude=ctx["latitude"],
                longitude=ctx["longitude"],
                annee_debut=2021,
                annee_fin=2023,
            )
            total_sarah3 += n_sarah3

            n_power = ingerer_serie_monthly(
                session=session,
                code_serie=_code_serie_power_1991_2020(localite_code),
                parametre_nasa=_PARAMETRE_NASA_GHI,
                latitude=ctx["latitude"],
                longitude=ctx["longitude"],
                annee_debut=1991,
                annee_fin=2020,
            )
            total_power += n_power

            decompte_par_ville[localite_code] = {
                "sarah3": n_sarah3,
                "power_1991_2020": n_power,
            }

        op.execute(
            f"-- Migration 041 1-7a : {total_sarah3} lignes SARAH-3 ICDR "
            f"(theorique 216, 36 mois x 6 villes ; plage 2021-2023 D-38) "
            f"+ {total_power} lignes NASA POWER 1991-2020 (theorique "
            f"2 160, 30 ans x 12 mois x 6 villes). Total = "
            f"{total_sarah3 + total_power} (theorique 2 376). Decompte "
            f"par ville : {decompte_par_ville!r}"
        )
    finally:
        session.close()


def downgrade() -> None:
    codes_series = [_code_serie_sarah3(loc) for loc in _LOCALITES_1_7A] + [
        _code_serie_power_1991_2020(loc) for loc in _LOCALITES_1_7A
    ]

    # Suppression des mesures via leur serie_id
    op.execute(
        sa.text(
            """
            DELETE FROM mesures_ressource_mensuelles
            WHERE serie_id IN (
                SELECT id FROM series_metadonnees WHERE code = ANY(:codes)
            )
            """
        ).bindparams(sa.bindparam("codes", value=codes_series))
    )

    # Suppression des 12 series
    op.execute(
        sa.text("DELETE FROM series_metadonnees WHERE code = ANY(:codes)").bindparams(
            sa.bindparam("codes", value=codes_series)
        )
    )

    # Suppression de la source sarah3_monthly
    op.execute(
        sa.text("DELETE FROM sources WHERE code = :code").bindparams(
            sa.bindparam("code", value=_SOURCE_SARAH3_CODE)
        )
    )
