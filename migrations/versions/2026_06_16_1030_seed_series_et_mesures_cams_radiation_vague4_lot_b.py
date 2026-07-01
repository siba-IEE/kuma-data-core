"""seed_series_et_mesures_cams_radiation_vague4_lot_b

Revision ID: 071
Revises: 070
Create Date: 2026-06-16 10:30:00.000000+00:00

Séries + mesures CAMS Radiation DNI (Seed Offline).

Insère **6 séries** (6 villes × grandeur ``dni`` × granularité ``mensuel``) et
leurs mesures DNI all-sky aérosol-corrigé (``BNI``) depuis le seed committé
``cams_radiation_seed_data.py`` (produit hors-ligne par
``scripts/preparer_seed_cams.py``). **Aucun ``cdsapi`` ni réseau ici** :
discipline α préservée, ``alembic upgrade head`` déterministe et offline
(confirme la voie de résorption offline ouverte précédemment).

- Mensuel **2004-02 → 2020-12** → ``mesures_ressource_mensuelles``
  (granularité ``mensuel``). Fenêtre = début réel du dataset (février 2004).

Naming des series : ``<alias_ville>_dni_cams_2004_2020`` (alias source ``cams``
raccourci de ``cams_radiation``, sur le précédent ``power`` ; exception
``gin_conakry`` via helper local). Confiance ``B``, statut ``brut``
(server_default), ``modele_satellitaire``.

Conversion appliquée dans le script (vérifiée contre l'unité de la grandeur
``dni`` = kWh/m²/jour) : ``Wh/m²/mois ÷ 1000 ÷ nb_jours_du_mois`` → moyenne
quotidienne, alignée sur le DNI NASA POWER mensuel.

**Ordre d'application** : appliquer après peuplement du seed par le script.
Sur seed vide, les 6 séries sont créées avec 0 mesure (le test d'intégration
saute alors ses assertions de données).

Pattern dupliqué de la migration 069 (résolution IDs, ``bulk_insert``,
downgrade DELETE mesures→séries).
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date
from typing import Any

import sqlalchemy as sa
from alembic import op

from kuma_data_core.db.seeds.cams_radiation_seed_data import CAMS_DNI_MENSUEL_SEED

# revision identifiers, used by Alembic.
revision: str = "071"
down_revision: str | Sequence[str] | None = "070"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# === Énumérations exhaustives =============================================

_LOCALITES_PILOTES: tuple[str, ...] = (
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

_GRANDEUR = "dni"
_SOURCE_CODE_SQL = "cams_radiation"

_AN_DEBUT, _AN_FIN = 2004, 2020
_PERIODE_DEBUT = date(2004, 2, 1)  # début réel du dataset CAMS (février 2004)
_PERIODE_FIN = date(2020, 12, 31)

_METHODE_COLLECTE = "modele_satellitaire"
_DATASET_URL = "https://ads.atmosphere.copernicus.eu/datasets/cams-solar-radiation-timeseries"


def _prefixe_ville_pour_serie(localite_code: str) -> str:
    """Préfixe ville pour code série (exception Conakry-Kaloum).

    Dupliqué du helper des migrations 041 / 050 / 069 (immuabilité post-merge :
    pas d'import croisé entre migrations).
    """
    if localite_code == "gin_conakry_kaloum":
        return "gin_conakry"
    return localite_code


def _code_serie(localite_code: str) -> str:
    return f"{_prefixe_ville_pour_serie(localite_code)}_{_GRANDEUR}_cams_{_AN_DEBUT}_{_AN_FIN}"


def _commentaire(localite_code: str) -> str:
    return (
        f"Serie CAMS Radiation DNI all-sky mensuel {_AN_DEBUT}-{_AN_FIN}, "
        f"{_LIBELLES_VILLES[localite_code]}, Guinee. DNI direct normal "
        f"aerosol-corrige (BNI, methode Heliosat-4), ciel reel (all-sky, pas "
        f"clear-sky) - levier Harmattan. Conversion Wh/m2/mois -> kWh/m2/jour "
        f"(moyenne quotidienne, alignee sur le DNI NASA mensuel). Fenetre "
        f"2004-02 -> 2020-12 (debut reel du dataset). Niveau de confiance B. "
        f"Vague 4 Lot B : 3e reference d'ecart inter-source. Attribution : "
        f"Generated using Copernicus Atmosphere Monitoring Service Information "
        f"2026 (licence CC-BY)."
    )


def upgrade() -> None:
    bind = op.get_bind()

    # === Étape 1 : résolution des IDs ====================================
    lignes_localites = bind.execute(
        sa.text("SELECT code, id FROM localites WHERE code = ANY(:codes)"),
        {"codes": list(_LOCALITES_PILOTES)},
    ).all()
    localite_id: dict[str, int] = {r.code: int(r.id) for r in lignes_localites}
    manquants = set(_LOCALITES_PILOTES) - localite_id.keys()
    if manquants:
        raise RuntimeError(f"Migration 071 : localite(s) introuvable(s) : {sorted(manquants)}.")

    source_id = bind.execute(
        sa.text("SELECT id FROM sources WHERE code = :code"),
        {"code": _SOURCE_CODE_SQL},
    ).scalar_one_or_none()
    if source_id is None:
        raise RuntimeError(
            f"Migration 071 : source {_SOURCE_CODE_SQL!r} introuvable (migration 070)."
        )

    grandeur_active = bind.execute(
        sa.text("SELECT code FROM grandeurs_referentiel WHERE code = :code AND actif = TRUE"),
        {"code": _GRANDEUR},
    ).scalar_one_or_none()
    if grandeur_active is None:
        raise RuntimeError(f"Migration 071 : grandeur {_GRANDEUR!r} inactive/absente.")

    # === Étape 2 : 6 séries ==============================================
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
    for localite_code in _LOCALITES_PILOTES:
        lignes_series.append(
            {
                "code": _code_serie(localite_code),
                "libelle": (
                    f"DNI CAMS Radiation mensuel {_LIBELLES_VILLES[localite_code]} "
                    f"{_AN_DEBUT}-{_AN_FIN}"
                ),
                "localite_id": localite_id[localite_code],
                "grandeur_code": _GRANDEUR,
                "source_id": source_id,
                "periode_debut": _PERIODE_DEBUT,
                "periode_fin": _PERIODE_FIN,
                "granularite": "mensuel",
                "methode_collecte": _METHODE_COLLECTE,
                "methode_collecte_doc": _DATASET_URL,
                "commentaire_editorial": _commentaire(localite_code),
                "url_documentation": _DATASET_URL,
            }
        )
    assert len(lignes_series) == 6, f"Attendu 6 séries, obtenu {len(lignes_series)}"
    op.bulk_insert(series_table, lignes_series)

    # Map code_serie -> id (après insert).
    serie_id_par_code: dict[str, int] = {
        r.code: int(r.id)
        for r in bind.execute(
            sa.text("SELECT code, id FROM series_metadonnees WHERE code = ANY(:codes)"),
            {"codes": [s["code"] for s in lignes_series]},
        ).all()
    }

    # === Étape 3 : mesures depuis le seed ================================
    mensuelles_table = sa.table(
        "mesures_ressource_mensuelles",
        sa.column("serie_id", sa.BigInteger),
        sa.column("annee", sa.SmallInteger),
        sa.column("mois", sa.SmallInteger),
        sa.column("valeur", sa.Float),
        sa.column("niveau_confiance_derive", sa.String),
    )

    lignes_mensuelles = [
        {
            "serie_id": serie_id_par_code[_code_serie(r["localite_code"])],
            "annee": r["annee"],
            "mois": r["mois"],
            "valeur": r["valeur"],
            "niveau_confiance_derive": "B",
        }
        for r in CAMS_DNI_MENSUEL_SEED
    ]
    if lignes_mensuelles:
        op.bulk_insert(mensuelles_table, lignes_mensuelles)

    op.execute(
        f"-- Migration 071 : 6 series CAMS Radiation DNI + {len(lignes_mensuelles)} "
        f"mesures mensuelles."
    )


def downgrade() -> None:
    codes_series = [_code_serie(localite_code) for localite_code in _LOCALITES_PILOTES]
    op.execute(
        sa.text(
            "DELETE FROM mesures_ressource_mensuelles WHERE serie_id IN "
            "(SELECT id FROM series_metadonnees WHERE code = ANY(:codes))"
        ).bindparams(sa.bindparam("codes", value=codes_series))
    )
    op.execute(
        sa.text("DELETE FROM series_metadonnees WHERE code = ANY(:codes)").bindparams(
            sa.bindparam("codes", value=codes_series)
        )
    )
