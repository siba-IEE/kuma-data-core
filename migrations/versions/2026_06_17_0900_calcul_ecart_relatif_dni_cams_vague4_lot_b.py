"""calcul_ecart_relatif_dni_cams_vague4_lot_b

Revision ID: 072
Revises: 071
Create Date: 2026-06-17 09:00:00.000000+00:00

Grandeur d'écart inter-source
``ecart_relatif_dni_cams`` (DNI NASA POWER vs CAMS Radiation, iso-période
2004-2020). **Migration unique atomique** (grandeur + 6 séries + 1 218 valeurs)
- miroir des migrations 042 (insert grandeur) / 043 (séries calculées +
orchestrateur). **Calcul intégralement déterministe depuis la base, AUCUN
réseau** (≠ ingestion : ne dépend pas d'API externe).

Périmètre (énumération exhaustive) :

1. Enregistre la grandeur ``ecart_relatif_dni_cams`` dans
   ``grandeurs_referentiel`` (famille F1, strategie ``calculee_volee``, unité
   ``pourcent`` résolue par code).
2. Crée **6 séries calculées** ``kuma_calculs`` (naming miroir des séries
   calculées, ``methode_collecte='calcul_derive'``, ``granularite`` NULL) :
   ``gin_<ville>_ecart_relatif_dni_cams_kuma_calculs_2004_2020``.
3. Appelle l'orchestrateur dédié
   :func:`calculer_et_inserer_ecart_dni_cams` (réutilise les helpers purs de
   ``referentiels.py`` sans le modifier) : **1 218 lignes** ``grandeurs_metier``
   (203 mois communs × 6 villes), orientation ``(nasa − cams)/cams × 100``,
   confiance dérivée ``B``.

Signe de l'écart = **résultat empirique** documenté (commentaire_editorial),
pas un choix de design.

Downgrade : DELETE des 1 218 lignes (via séries) → DELETE séries → DELETE
grandeur.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date
from typing import Any

import sqlalchemy as sa
from alembic import op
from sqlalchemy.orm import Session

from kuma_data_core.services.grandeurs.ecart_dni_cams import (
    GRANDEUR_ECART_DNI_CAMS,
    ContexteVilleEcartDniCams,
    calculer_et_inserer_ecart_dni_cams,
)

# revision identifiers, used by Alembic.
revision: str = "072"
down_revision: str | Sequence[str] | None = "071"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# === Énumération exhaustive ===============================================

_LOCALITES: tuple[str, ...] = (
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

_SOURCE_KUMA_CALCULS = "kuma_calculs"
_METHODE_COLLECTE_CALCUL = "calcul_derive"
_PLAGE = "2004_2020"
_PERIODE_DEBUT = date(2004, 2, 1)  # début réel de la fenêtre commune (CAMS 2004-02)
_PERIODE_FIN = date(2020, 12, 31)


def _prefixe_ville_pour_serie(localite_code: str) -> str:
    """Préfixe ville pour code série (exception Conakry-Kaloum, miroir 043)."""
    if localite_code == "gin_conakry_kaloum":
        return "gin_conakry"
    return localite_code


def _code_serie_calculee(localite_code: str) -> str:
    return (
        f"{_prefixe_ville_pour_serie(localite_code)}_{GRANDEUR_ECART_DNI_CAMS}"
        f"_kuma_calculs_{_PLAGE}"
    )


def _code_serie_nasa(localite_code: str) -> str:
    return f"{_prefixe_ville_pour_serie(localite_code)}_dni_power_2001_2020"


def _code_serie_cams(localite_code: str) -> str:
    return f"{_prefixe_ville_pour_serie(localite_code)}_dni_cams_2004_2020"


def _commentaire(localite_code: str) -> str:
    return (
        f"Serie calculee Kuma ecart_relatif_dni_cams : ecart relatif inter-source "
        f"du DNI entre NASA POWER (primaire, numerateur) et CAMS Radiation "
        f"(reference d'ecart aerosol-corrigee, denominateur), formule "
        f"(nasa - cams)/cams x 100, iso-periode 2004-2020 mois-a-mois. Localite : "
        f"{_LIBELLES_VILLES[localite_code]}. Niveau de confiance derive 'B' "
        f"(signal indirect par construction). CAVEAT : l'offset moyen observe "
        f"(-26 %, NASA lit moins de DNI que CAMS) est un ecart de FOND entre "
        f"produits (NASA/CERES vs CAMS/Heliosat-4), PAS la correction Harmattan ; "
        f"le signal aerosol releve de la SAISONNALITE de l'ecart, a analyser "
        f"ulterieurement. Ne pas sur-interpreter le signe (resultat empirique, "
        f"non recherche). Vague 4 Lot B sous-etape B-ecart."
    )


def upgrade() -> None:
    bind = op.get_bind()

    # === Étape 1 : enregistrement de la grandeur =========================
    unite_pourcent_id = bind.execute(
        sa.text("SELECT id FROM unites WHERE code = :code"),
        {"code": "pourcent"},
    ).scalar_one_or_none()
    if unite_pourcent_id is None:
        raise RuntimeError("Migration 072 : unite 'pourcent' introuvable (migration 009).")

    grandeurs_table = sa.table(
        "grandeurs_referentiel",
        sa.column("code", sa.String),
        sa.column("libelle", sa.Text),
        sa.column("famille", sa.String),
        sa.column("strategie_calcul", sa.String),
        sa.column("unite_id", sa.BigInteger),
        sa.column("description", sa.Text),
    )
    op.bulk_insert(
        grandeurs_table,
        [
            {
                "code": GRANDEUR_ECART_DNI_CAMS,
                "libelle": "Ecart relatif DNI CAMS vs NASA POWER",
                "famille": "F1",
                "strategie_calcul": "calculee_volee",
                "unite_id": int(unite_pourcent_id),
                "description": (
                    "Ecart relatif inter-source du DNI entre NASA POWER (primaire) "
                    "et CAMS Radiation (reference d'ecart aerosol-corrigee), formule "
                    "(nasa - cams)/cams x 100, en pourcent signe. Calculee a la volee, "
                    "materialisee dans grandeurs_metier par (annee, mois) sur la "
                    "fenetre commune 2004-2020 (6 villes pilotes). Famille F1."
                    ""
                ),
            }
        ],
    )

    # === Étape 2 : résolution des IDs (localités + source kuma_calculs) ==
    lignes_localites = bind.execute(
        sa.text("SELECT code, id FROM localites WHERE code = ANY(:codes)"),
        {"codes": list(_LOCALITES)},
    ).all()
    localite_id_par_code: dict[str, int] = {r.code: int(r.id) for r in lignes_localites}
    manquants = set(_LOCALITES) - localite_id_par_code.keys()
    if manquants:
        raise RuntimeError(f"Migration 072 : localite(s) introuvable(s) : {sorted(manquants)}.")

    source_kuma_calculs_id = bind.execute(
        sa.text("SELECT id FROM sources WHERE code = :code"),
        {"code": _SOURCE_KUMA_CALCULS},
    ).scalar_one()

    # === Étape 3 : insertion des 6 séries calculées ======================
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
    series_a_inserer: list[dict[str, Any]] = [
        {
            "code": _code_serie_calculee(localite_code),
            "libelle": (
                f"ecart_relatif_dni_cams mensuel {_LIBELLES_VILLES[localite_code]} "
                f"{_PLAGE.replace('_', '-')}"
            ),
            "localite_id": localite_id_par_code[localite_code],
            "grandeur_code": GRANDEUR_ECART_DNI_CAMS,
            "source_id": int(source_kuma_calculs_id),
            "periode_debut": _PERIODE_DEBUT,
            "periode_fin": _PERIODE_FIN,
            "methode_collecte": _METHODE_COLLECTE_CALCUL,
            "commentaire_editorial": _commentaire(localite_code),
        }
        for localite_code in _LOCALITES
    ]
    assert len(series_a_inserer) == 6, f"Attendu 6 séries, obtenu {len(series_a_inserer)}"
    op.bulk_insert(series_table, series_a_inserer)

    serie_id_par_localite: dict[int, int] = {
        int(r.localite_id): int(r.id)
        for r in bind.execute(
            sa.text(
                "SELECT id, localite_id FROM series_metadonnees "
                "WHERE grandeur_code = :g AND source_id = :sid"
            ),
            {"g": GRANDEUR_ECART_DNI_CAMS, "sid": int(source_kuma_calculs_id)},
        ).all()
    }
    if len(serie_id_par_localite) != 6:
        raise RuntimeError(
            f"Migration 072 : {len(serie_id_par_localite)} séries résolues (attendu 6)."
        )

    # === Étape 4 : calcul + insertion (1 218 lignes attendues) ===========
    session = Session(bind=bind)
    try:
        contextes: list[ContexteVilleEcartDniCams] = [
            {
                "localite_id": localite_id_par_code[loc],
                "code_serie_nasa": _code_serie_nasa(loc),
                "code_serie_cams": _code_serie_cams(loc),
                "series_metadonnees_id": serie_id_par_localite[localite_id_par_code[loc]],
            }
            for loc in _LOCALITES
        ]
        resultat = calculer_et_inserer_ecart_dni_cams(session=session, contextes_villes=contextes)
        op.execute(
            f"-- Migration 072 B-ecart : grandeur ecart_relatif_dni_cams + 6 series "
            f"kuma_calculs + {resultat['nb_insere']} lignes grandeurs_metier "
            f"(theorique 1218, 203 mois communs x 6 villes)."
        )
    finally:
        session.close()


def downgrade() -> None:
    codes_series = [_code_serie_calculee(loc) for loc in _LOCALITES]
    op.execute(
        sa.text(
            "DELETE FROM grandeurs_metier WHERE series_metadonnees_id IN "
            "(SELECT id FROM series_metadonnees WHERE code = ANY(:codes))"
        ).bindparams(sa.bindparam("codes", value=codes_series))
    )
    op.execute(
        sa.text("DELETE FROM series_metadonnees WHERE code = ANY(:codes)").bindparams(
            sa.bindparam("codes", value=codes_series)
        )
    )
    op.execute(
        sa.text("DELETE FROM grandeurs_referentiel WHERE code = :code").bindparams(
            code=GRANDEUR_ECART_DNI_CAMS
        )
    )
