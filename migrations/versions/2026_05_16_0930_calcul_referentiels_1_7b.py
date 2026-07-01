"""calcul_referentiels_1_7b

Revision ID: 043
Revises: 042
Create Date: 2026-05-16 09:30:00.000000+00:00

Calcul + insertion des 3 grandeurs F1 calculee_volee
referentielles.

Pre-requis :
- Migration 042 corrective grandeurs_referentiel a desactive
  rang_referentiel singulier et insere rang_referentiel_temporel +
  rang_referentiel_spatial.
- ecart_relatif_referentiel deja seedee, compatible.

Perimetre (enumeration exhaustive) :

1. Insertion 18 series calculees dans series_metadonnees (3 grandeurs
   x 6 villes pilotes) selon la convention de naming :
   - 6 series ecart_relatif_referentiel :
     gin_<ville>_ecart_relatif_referentiel_kuma_calculs_2021_2023
   - 6 series rang_referentiel_temporel :
     gin_<ville>_rang_referentiel_temporel_kuma_calculs_2021_2025
   - 6 series rang_referentiel_spatial :
     gin_<ville>_rang_referentiel_spatial_kuma_calculs_2021_2025
   - Exception Conakry-Kaloum via helper _prefixe_ville_pour_serie.

2. Appel orchestrateur calculer_et_inserer_referentiels
   (module services/grandeurs/referentiels.py)
   pour calculer + inserer les 936 lignes attendues :
   - 216 ecart_relatif_referentiel (36 mois x 6 villes, plage 2021-2023
     = chevauchement Kuma/SARAH-3)
   - 360 rang_referentiel_temporel (60 mois x 6 villes, formule type 7
     numpy/R sur distribution 1991-2020 stratifiee mois calendrier)
   - 360 rang_referentiel_spatial (60 mois x 6 villes, rang ordinal
     1-6 dans le pool)

Idempotence : UNIQUE (localite_id, grandeur_code, source_id,
periode_debut, periode_fin) sur series_metadonnees (plage-aware)
garantit la non-doublure. EXCLUDE BTree-GiST grandeurs_metier
(inclut series_metadonnees_id) garantit la non-doublure des
936 lignes vs les 1 614 existantes.

Logging post-ingestion via op.execute('-- ...') (pattern migrations
032, 038, 041).
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date
from typing import Any

import sqlalchemy as sa
from alembic import op
from sqlalchemy.orm import Session

from kuma_data_core.services.grandeurs.referentiels import (
    GRANDEUR_ECART,
    GRANDEUR_RANG_SPATIAL,
    GRANDEUR_RANG_TEMPOREL,
    ContexteVille,
    calculer_et_inserer_referentiels,
)

# revision identifiers, used by Alembic.
revision: str = "043"
down_revision: str | Sequence[str] | None = "042"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# === Enumeration exhaustive ==========================================

_LOCALITES_1_7B: tuple[str, ...] = (
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
    """Prefixe ville pour code serie."""
    if localite_code == "gin_conakry_kaloum":
        return "gin_conakry"
    return localite_code


# === Plages temporelles des 3 grandeurs ==============================

_PLAGE_ECART_DEBUT: date = date(2021, 1, 1)
_PLAGE_ECART_FIN: date = date(2023, 12, 31)
"""Plage ecart_relatif_referentiel = chevauchement Kuma daily (2021-2025)
+ SARAH-3 ICDR (2021-2023 effectif)."""

_PLAGE_RANG_DEBUT: date = date(2021, 1, 1)
_PLAGE_RANG_FIN: date = date(2025, 12, 31)
"""Plage rang_referentiel_temporel et _spatial = couverture Kuma daily."""

_SOURCE_KUMA_CALCULS: str = "kuma_calculs"
_METHODE_COLLECTE_CALCUL: str = "calcul_derive"


def _code_serie_calculee(localite_code: str, grandeur_code: str, plage: str) -> str:
    """`gin_<ville>_<grandeur>_kuma_calculs_<plage>`."""
    return f"{_prefixe_ville_pour_serie(localite_code)}_{grandeur_code}_kuma_calculs_{plage}"


def _code_serie_kuma_daily(localite_code: str) -> str:
    """`gin_<ville>_ghi_nasa_power_2021_2025` (serie brute Kuma deja seedee)."""
    return f"{_prefixe_ville_pour_serie(localite_code)}_ghi_nasa_power_2021_2025"


def _code_serie_sarah3(localite_code: str) -> str:
    """`gin_<ville>_ghi_sarah3_2021_2023` (serie SARAH-3 ICDR)."""
    return f"{_prefixe_ville_pour_serie(localite_code)}_ghi_sarah3_2021_2023"


def _code_serie_power_1991_2020(localite_code: str) -> str:
    """`gin_<ville>_ghi_power_1991_2020` (serie NASA POWER climato)."""
    return f"{_prefixe_ville_pour_serie(localite_code)}_ghi_power_1991_2020"


def upgrade() -> None:
    bind = op.get_bind()

    # === Etape 1 : resolution IDs (localites + source kuma_calculs) ==========
    lignes_localites = bind.execute(
        sa.text("SELECT code, id FROM localites WHERE code = ANY(:codes)"),
        {"codes": list(_LOCALITES_1_7B)},
    ).all()
    localite_id_par_code: dict[str, int] = {r.code: int(r.id) for r in lignes_localites}
    codes_manquants = set(_LOCALITES_1_7B) - localite_id_par_code.keys()
    if codes_manquants:
        raise RuntimeError(
            f"Migration 043 : localite_code(s) introuvable(s) : "
            f"{sorted(codes_manquants)}. Verifier la migration 011."
        )

    source_kuma_calculs_id = bind.execute(
        sa.text("SELECT id FROM sources WHERE code = :code"),
        {"code": _SOURCE_KUMA_CALCULS},
    ).scalar_one()

    # === Etape 2 : insertion 18 series calculees ============================
    series_table = sa.table(
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

    series_a_inserer: list[dict[str, Any]] = []
    grandeurs_et_plages: list[tuple[str, str, date, date]] = [
        (GRANDEUR_ECART, "2021_2023", _PLAGE_ECART_DEBUT, _PLAGE_ECART_FIN),
        (GRANDEUR_RANG_TEMPOREL, "2021_2025", _PLAGE_RANG_DEBUT, _PLAGE_RANG_FIN),
        (GRANDEUR_RANG_SPATIAL, "2021_2025", _PLAGE_RANG_DEBUT, _PLAGE_RANG_FIN),
    ]

    commentaires = {
        GRANDEUR_ECART: (
            "Serie calculee Kuma ecart_relatif_referentiel : divergence inter-source "
            "contemporaine entre NASA POWER Kuma (agrege mensuel) et PVGIS-SARAH3 "
            "ICDR sur plage 2021-2023 (chevauchement effectif post-D-38). "
            "Niveau de confiance derive 'B'. Localite : {ville}. Etape 1-7b."
        ),
        GRANDEUR_RANG_TEMPOREL: (
            "Serie calculee Kuma rang_referentiel_temporel : percentile dans la "
            "climatologie NASA POWER 1991-2020 stratifie par mois calendrier "
            "(formule type 7 numpy/R, n=30, capping [0,100]). Niveau de confiance "
            "derive 'B' (caveat D-35 sur quantile mapping). Localite : {ville}. "
            "Etape 1-7b (decomposition D-39 fermee)."
        ),
        GRANDEUR_RANG_SPATIAL: (
            "Serie calculee Kuma rang_referentiel_spatial : rang ordinal 1-6 dans "
            "le pool des 6 villes pilotes Kuma pour le meme mois. Niveau de "
            "confiance derive 'B' (limite statistique n=6 phase 1). Localite : "
            "{ville}. Etape 1-7b (decomposition D-39 fermee)."
        ),
    }

    for localite_code in _LOCALITES_1_7B:
        libelle_ville = _LIBELLES_VILLES[localite_code]
        for grandeur_code, plage_str, plage_debut, plage_fin in grandeurs_et_plages:
            series_a_inserer.append(
                {
                    "code": _code_serie_calculee(localite_code, grandeur_code, plage_str),
                    "libelle": f"{grandeur_code} mensuel {libelle_ville} {plage_str.replace('_', '-')}",
                    "localite_id": localite_id_par_code[localite_code],
                    "grandeur_code": grandeur_code,
                    "source_id": int(source_kuma_calculs_id),
                    "periode_debut": plage_debut,
                    "periode_fin": plage_fin,
                    "methode_collecte": _METHODE_COLLECTE_CALCUL,
                    "commentaire_editorial": commentaires[grandeur_code].format(
                        ville=libelle_ville
                    ),
                }
            )

    assert len(series_a_inserer) == 18, (
        f"Migration 043 : attendu 18 series, recu {len(series_a_inserer)}"
    )
    op.bulk_insert(series_table, series_a_inserer)

    # === Etape 3 : resolution des series_metadonnees_id post-insertion ======
    rows_series = bind.execute(
        sa.text(
            """
            SELECT id, code, grandeur_code, localite_id
            FROM series_metadonnees
            WHERE grandeur_code IN ('ecart_relatif_referentiel',
                                    'rang_referentiel_temporel',
                                    'rang_referentiel_spatial')
              AND source_id = :source_id
            """
        ),
        {"source_id": int(source_kuma_calculs_id)},
    ).all()
    serie_id_par_grandeur_localite: dict[tuple[str, int], int] = {
        (str(r.grandeur_code), int(r.localite_id)): int(r.id) for r in rows_series
    }
    assert len(serie_id_par_grandeur_localite) == 18, (
        f"Migration 043 : attendu 18 series resolues, recu {len(serie_id_par_grandeur_localite)}"
    )

    # === Etape 4 : appel orchestrateur (936 lignes attendues) ===============
    session = Session(bind=bind)
    try:
        contextes_villes: list[ContexteVille] = [
            {
                "localite_id": localite_id_par_code[loc_code],
                "code_serie_kuma_daily": _code_serie_kuma_daily(loc_code),
                "code_serie_sarah3": _code_serie_sarah3(loc_code),
                "code_serie_power_1991_2020": _code_serie_power_1991_2020(loc_code),
            }
            for loc_code in _LOCALITES_1_7B
        ]

        resultat = calculer_et_inserer_referentiels(
            session=session,
            contextes_villes=contextes_villes,
            serie_id_par_grandeur_localite=serie_id_par_grandeur_localite,
        )

        op.execute(
            f"-- Migration 043 1-7b : {resultat['nb_ecart_insere']} lignes "
            f"ecart_relatif_referentiel (theorique 216, 36 mois x 6 villes, "
            f"plage 2021-2023 D-38) + {resultat['nb_rang_temporel_insere']} "
            f"lignes rang_referentiel_temporel (theorique 360) + "
            f"{resultat['nb_rang_spatial_insere']} lignes rang_referentiel_spatial "
            f"(theorique 360). Total = {resultat['nb_total']} (theorique 936). "
            f"Decompte cumule grandeurs_metier attendu = 2 550 (1 614 + 936)."
        )
    finally:
        session.close()


def downgrade() -> None:
    # Suppression des 936 lignes grandeurs_metier (via les 18 series)
    codes_series = []
    for loc_code in _LOCALITES_1_7B:
        codes_series.append(_code_serie_calculee(loc_code, GRANDEUR_ECART, "2021_2023"))
        codes_series.append(_code_serie_calculee(loc_code, GRANDEUR_RANG_TEMPOREL, "2021_2025"))
        codes_series.append(_code_serie_calculee(loc_code, GRANDEUR_RANG_SPATIAL, "2021_2025"))

    op.execute(
        sa.text(
            """
            DELETE FROM grandeurs_metier
            WHERE series_metadonnees_id IN (
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
