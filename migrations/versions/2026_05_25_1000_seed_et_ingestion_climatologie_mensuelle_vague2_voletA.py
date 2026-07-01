"""seed_et_ingestion_climatologie_mensuelle_vague2_voletA

Revision ID: 050
Revises: 049
Create Date: 2026-05-25 10:00:00.000000+00:00

Climatologie mensuelle long-terme pour le
media. Donne aux 8 grandeurs brutes restantes la profondeur que seul
le GHI possedait (migration 041).

Periodes (fenetres heterogenes, asymetrie source assumee, miroir
mensuel de l'asymetrie de couverture des parametres secondaires ;
verifie empiriquement + validation
croisee climato vs journalier 2021-2025) :

| Grandeur Kuma  | Parametre NASA POWER  | Fenetre   | Lignes/serie |
|----------------|-----------------------|-----------|--------------|
| t2m            | T2M                   | 1991-2020 | 360          |
| rh2m           | RH2M                  | 1991-2020 | 360          |
| vent_2m        | WS2M                  | 1991-2020 | 360          |
| vent_10m       | WS10M                 | 1991-2020 | 360          |
| dhi            | ALLSKY_SFC_SW_DIFF    | 2001-2020 | 240          |
| dni            | ALLSKY_SFC_SW_DNI     | 2001-2020 | 240          |
| kt             | ALLSKY_KT             | 2001-2020 | 240          |
| albedo_surface | ALLSKY_SRF_ALB        | 2001-2020 | 240          |

DNI, KT et albedo_surface ne remontent qu'a 2001 en mensuel : SRB 4.x
(1984-2000) ne fournit pas ces 3 parametres ; CERES SYN1deg demarre en
mars 2000 (plage complete 2001+). Cause structurelle identique a
l'asymetrie intra-daily, pas une nouvelle limite.

DHI ramene a 2001-2020 (au lieu de 1991-2020) malgre sa disponibilite
SRB pre-2001 : la validation croisee climato vs journalier 2021-2025
a revele un biais systematique -9 a -17 % par ville du DHI 1991-2020
vs le journalier recent, attribue au composite SRB 4.x / CERES SYN1deg
non homogeneise pour la diffuse (la calibration quantile mapping POWER
de Khadka et al. 2023 etant illustree publiquement sur le longwave
mais non sur le shortwave/diffuse). Restriction a la
fenetre pure CERES 2001-2020 pour eviter ce biais en API mensuelle ;
range DHI avec ses freres radiatifs CERES (DNI, KT, albedo).

Volume cible : 48 series (8 grandeurs x 6 villes) ; 14 400 lignes
mensuelles (4 grandeurs x 360 x 6 + 4 grandeurs x 240 x 6 =
8 640 + 5 760).

Naming heterogene assume : `gin_<ville>_<grandeur>_power_
<an_debut>_<an_fin>`. Le code source ``power`` est un raccourci de
naming pour la climato mensuelle ; la source SQL referencee reste
``nasa_power`` (cf. seed initial des sources). Exception Conakry-Kaloum :
prefixe `gin_conakry` sans `_kaloum` via helper local
`_prefixe_ville_pour_serie` (pattern duplique de la migration 041).

Pattern integral reutilise de la migration 041 :

- Client `external/nasa_power.py::fetch_monthly` (parametres dynamiques).
- Ingestion `ingestion/nasa_power_monthly.py::ingerer_serie_monthly` :
  filtrage automatique des sentinelles -999.0 (essentiel pour DNI/KT/
  ALB qui peuvent en avoir avant 2001 si la fenetre s'etend par
  erreur), tri des cles `YYYY13` (moyennes annuelles).
- Resolution table-cible `serie_lecture.py::resolve_table_from_series
  _metadata('nasa_power', date(YYYY,1,1))` -> `mesures_ressource_
  mensuelles` (frontiere 2021 stable, aucun ajustement).

Aucune modification de code applicatif requise.

Variable d'environnement court-circuit (pattern CI sans reseau) :

- ``KUMA_SKIP_NASA_POWER_INGESTION=1`` court-circuite l'ingestion
  NASA POWER monthly (les 48 series restent inserees, mais aucune
  mesure ingeree).

Volume reseau : 48 appels NASA POWER monthly multi-parametre 1 (1 par
serie, sequentiels). Latence attendue 1-2 minutes total.

Logging post-ingestion via ``op.execute('-- ...')`` (pattern migration
041 / 048).

Hors scope : recalcul des grandeurs calculees Kuma (hep,
fraction_diffuse, humidex, productible_specifique_theorique,
variabilite_journaliere) sur la nouvelle profondeur 1991-2020 - chantier
separe eventuel.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date
from typing import Any

import sqlalchemy as sa
from alembic import op
from sqlalchemy.orm import Session

from kuma_data_core.ingestion.nasa_power_monthly import ingerer_serie_monthly

# revision identifiers, used by Alembic.
revision: str = "050"
down_revision: str | Sequence[str] | None = "049"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# === Énumérations exhaustives =====================================

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

# Mapping grandeur Kuma -> (parametre NASA POWER, annee de debut de la
# fenetre disponible en monthly). L'annee de fin est commune (2020,
# climatologie OMM 30 ans pour les 5 grandeurs en couverture complete,
# 20 ans pour les 3 grandeurs CERES SYN1deg).
_MAPPING_GRANDEURS: dict[str, tuple[str, int]] = {
    "t2m": ("T2M", 1991),
    "rh2m": ("RH2M", 1991),
    "vent_2m": ("WS2M", 1991),
    "vent_10m": ("WS10M", 1991),
    "dhi": ("ALLSKY_SFC_SW_DIFF", 2001),
    "dni": ("ALLSKY_SFC_SW_DNI", 2001),
    "kt": ("ALLSKY_KT", 2001),
    "albedo_surface": ("ALLSKY_SRF_ALB", 2001),
}

_ANNEE_FIN_CLIMATO: int = 2020

_LIBELLES_GRANDEURS_SERIE: dict[str, str] = {
    "dhi": "DHI mensuel climato",
    "dni": "DNI mensuel climato",
    "t2m": "Temperature 2m mensuelle climato",
    "rh2m": "Humidite relative 2m mensuelle climato",
    "vent_2m": "Vent 2m mensuel climato",
    "vent_10m": "Vent 10m mensuel climato",
    "kt": "Indice de clarte mensuel climato",
    "albedo_surface": "Albedo de surface mensuel climato",
}

_SOURCE_CODE_SQL: str = "nasa_power"
"""Code SQL reel de la source dans la table ``sources`` (raccourci
'power' utilise uniquement dans le naming des codes serie)."""

_METHODE_COLLECTE: str = "modele_satellitaire"
_METHODE_COLLECTE_DOC: str = "https://power.larc.nasa.gov/docs/methodology/"
_URL_DOCUMENTATION: str = "https://power.larc.nasa.gov/"

_COMMENTAIRE_EDITORIAL_TEMPLATE: str = (
    "Serie climato mensuelle long-terme inscrite en Phase 2 vague 1 "
    "(chantier vague 2 volet A : enrichissement media). Donnee brute "
    "{grandeur_upper} ingeree depuis NASA POWER endpoint monthly, "
    "parametre {parametre_nasa}, fenetre {annee_debut}-{annee_fin}. "
    "Methode satellitaire ({source_amont}). Localite : {ville_libelle}, "
    "Guinee. Niveau de confiance B (modele satellitaire). Donne au media "
    "la profondeur climatologique attendue par les plateformes de "
    "reference type Global Solar Atlas / PVGIS."
)

# Source amont par grandeur pour le commentaire editorial.
_SOURCE_AMONT_PAR_GRANDEUR: dict[str, str] = {
    "dhi": "SRB 4.x puis CERES SYN1deg",
    "dni": "CERES SYN1deg",
    "t2m": "MERRA-2 GMAO",
    "rh2m": "MERRA-2 GMAO",
    "vent_2m": "MERRA-2 GMAO",
    "vent_10m": "MERRA-2 GMAO",
    "kt": "CERES SYN1deg",
    "albedo_surface": "CERES SYN1deg",
}


def _prefixe_ville_pour_serie(localite_code: str) -> str:
    """Prefixe ville pour code serie (exception Conakry-Kaloum).

    Duplique du helper de la migration 041 (immuabilite post-merge des
    migrations : pas d'import croise entre migrations).
    """
    if localite_code == "gin_conakry_kaloum":
        return "gin_conakry"
    return localite_code


def _code_serie(localite_code: str, grandeur_code: str, annee_debut: int) -> str:
    """Convention de naming : `gin_<ville>_<grandeur>_power_<an_debut>_<an_fin>`.

    Le segment `power` est un raccourci de naming pour la climato
    mensuelle (la source SQL referencee est `nasa_power`).
    """
    return (
        f"{_prefixe_ville_pour_serie(localite_code)}_{grandeur_code}_power_"
        f"{annee_debut}_{_ANNEE_FIN_CLIMATO}"
    )


def upgrade() -> None:
    bind = op.get_bind()

    # === Étape 1 : résolution des IDs (localites + source nasa_power) =====
    lignes_localites = bind.execute(
        sa.text(
            "SELECT code, id, "
            "CAST(latitude AS DOUBLE PRECISION) AS lat, "
            "CAST(longitude AS DOUBLE PRECISION) AS lon "
            "FROM localites WHERE code = ANY(:codes)"
        ),
        {"codes": list(_LOCALITES_PILOTES)},
    ).all()
    localite_info: dict[str, dict[str, Any]] = {
        r.code: {"id": int(r.id), "lat": float(r.lat), "lon": float(r.lon)}
        for r in lignes_localites
    }
    codes_manquants = set(_LOCALITES_PILOTES) - localite_info.keys()
    if codes_manquants:
        raise RuntimeError(
            f"Migration 050 : localite_code(s) introuvable(s) : "
            f"{sorted(codes_manquants)}. Verifier la migration 011."
        )

    source_id = bind.execute(
        sa.text("SELECT id FROM sources WHERE code = :code"),
        {"code": _SOURCE_CODE_SQL},
    ).scalar_one_or_none()
    if source_id is None:
        raise RuntimeError(
            f"Migration 050 : source_code {_SOURCE_CODE_SQL!r} introuvable. "
            f"Verifier la migration 012 (seed 9 sources passe 1-1E)."
        )

    # === Étape 2 : vérification des 8 grandeurs cibles actives ============
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
            f"Migration 050 : grandeur_code(s) cible(s) introuvable(s) ou "
            f"inactive(s) : {sorted(grandeurs_manquantes)}. Les 8 brutes "
            f"doivent etre actives (seedees 1-1C, 1-2b, vague 1 chantier A)."
        )

    # === Étape 3 : seed des 48 nouvelles séries dans series_metadonnees ===
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

    lignes_series: list[dict[str, Any]] = []
    for localite_code in _LOCALITES_PILOTES:
        info = localite_info[localite_code]
        for grandeur_code, (parametre_nasa, annee_debut) in _MAPPING_GRANDEURS.items():
            libelle = (
                f"{_LIBELLES_GRANDEURS_SERIE[grandeur_code]} "
                f"{_LIBELLES_VILLES[localite_code]} {annee_debut}-{_ANNEE_FIN_CLIMATO} "
                f"(NASA POWER monthly)"
            )
            commentaire = _COMMENTAIRE_EDITORIAL_TEMPLATE.format(
                grandeur_upper=grandeur_code.upper(),
                parametre_nasa=parametre_nasa,
                annee_debut=annee_debut,
                annee_fin=_ANNEE_FIN_CLIMATO,
                source_amont=_SOURCE_AMONT_PAR_GRANDEUR[grandeur_code],
                ville_libelle=_LIBELLES_VILLES[localite_code],
            )
            lignes_series.append(
                {
                    "code": _code_serie(localite_code, grandeur_code, annee_debut),
                    "libelle": libelle,
                    "localite_id": info["id"],
                    "grandeur_code": grandeur_code,
                    "source_id": source_id,
                    "periode_debut": date(annee_debut, 1, 1),
                    "periode_fin": date(_ANNEE_FIN_CLIMATO, 12, 31),
                    "methode_collecte": _METHODE_COLLECTE,
                    "methode_collecte_doc": _METHODE_COLLECTE_DOC,
                    "commentaire_editorial": commentaire,
                    "url_documentation": _URL_DOCUMENTATION,
                }
            )

    assert len(lignes_series) == 48, (
        f"Expected 48 series (8 grandeurs x 6 villes), got {len(lignes_series)}"
    )
    op.bulk_insert(series_metadonnees_table, lignes_series)

    # === Étape 4 : ingestion mensuelle des 48 séries ======================
    session = Session(bind=bind)
    try:
        decomptes_totaux: dict[str, int] = {}
        for localite_code in _LOCALITES_PILOTES:
            info = localite_info[localite_code]
            for grandeur_code, (parametre_nasa, annee_debut) in _MAPPING_GRANDEURS.items():
                code_serie = _code_serie(localite_code, grandeur_code, annee_debut)
                n_lignes = ingerer_serie_monthly(
                    session=session,
                    code_serie=code_serie,
                    parametre_nasa=parametre_nasa,
                    latitude=info["lat"],
                    longitude=info["lon"],
                    annee_debut=annee_debut,
                    annee_fin=_ANNEE_FIN_CLIMATO,
                )
                decomptes_totaux[code_serie] = n_lignes

        total = sum(decomptes_totaux.values())
        op.execute(
            f"-- Migration 050 : {total} lignes inserees dans "
            f"mesures_ressource_mensuelles sur 8 grandeurs x 6 villes. "
            f"Decompte par serie : {decomptes_totaux}"
        )
    finally:
        session.close()


def downgrade() -> None:
    # Construction des 48 codes série a supprimer (deterministe).
    codes_series: list[str] = []
    for localite_code in _LOCALITES_PILOTES:
        for grandeur_code, (_, annee_debut) in _MAPPING_GRANDEURS.items():
            codes_series.append(_code_serie(localite_code, grandeur_code, annee_debut))

    # Suppression des mesures (FK RESTRICT sur serie_id) avant les series.
    op.execute(
        sa.text(
            """
            DELETE FROM mesures_ressource_mensuelles
            WHERE serie_id IN (
                SELECT id FROM series_metadonnees WHERE code = ANY(:codes)
            )
            """
        ).bindparams(codes=codes_series)
    )
    op.execute(
        sa.text("DELETE FROM series_metadonnees WHERE code = ANY(:codes)").bindparams(
            sa.bindparam("codes", value=codes_series)
        )
    )
