"""cams_eac4_ozone_surface_journalier_34_points

Revision ID: 124
Revises: 123
Create Date: 2026-11-07 12:00:00.000000+00:00

Ozone de surface EAC4 journalier (``ozone_surface``, moyenne des 8 pas
3-horaires) et diurne (``ozone_surface_diurne``, moyenne des pas 09/12/15 UTC),
en ppb, aux **34 points** (6 pilotes + 28 communes chef-lieu), pleine profondeur
2004-02-01 -> 2025-12-31 : **68 series** (34 x 2) et **544 340 mesures** (8 005
jours par serie, capture sans jour absent ni incomplet).

Grandeur amont : rapport de melange massique d'ozone (go3) au niveau modele 60,
le plus bas d'EAC4 (assimilable a la surface), converti en ppb a la capture
(``kg/kg x (28.9644/47.9982) x 1e9``). La capture et ses metadonnees
(``niveau_modele_ozone``, ``conversion_ozone``) sont verifiees ici.

Caveat public : en fin de saison seche (fevrier-mai, 2006-2019), EAC4 produit
localement des pics d'ozone diurne vers 300 ppb (max ~340, mediane diurne
~27 ppb), probablement des artefacts du modele lies aux feux de vegetation.
Valeurs conservees telles que fournies par la source (decision utilisateur),
caveat porte par ``note_publique`` sur les 68 series.

Source ``cams_eac4`` (migration 081) reutilisee ; grandeurs et unite
``partie_par_milliard`` declarees en 122 (verifiees ici). Periode lue dans
``periode_reelle`` des metadonnees de capture. Meme pattern que la migration 123
(streaming deux passes, lots de 20 000, gardes de comptage exactes, confiance
'B' hardcodee, regle R4). Attribution CC-BY Copernicus/CAMS. BRUTE SEULEMENT.
Aucun reseau.

Codes de serie ``<localite>_<grandeur>_cams_eac4_2004_2025`` (code de localite
tel quel, ``gin_conakry_kaloum`` comme la migration 120).
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from datetime import date
from typing import Any

import sqlalchemy as sa
from alembic import op

from kuma_data_core.db.seeds.cams_eac4_aod_ozone_journalier_seed_data import (
    iter_blocs_cams_eac4_aod_ozone,
    iter_captures_cams_eac4_aod_ozone,
)

# revision identifiers, used by Alembic.
revision: str = "124"
down_revision: str | Sequence[str] | None = "123"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


_SOURCE_CODE = "cams_eac4"
_DATASET = "cams-global-reanalysis-eac4"
_DATASET_URL = "https://ads.atmosphere.copernicus.eu/datasets/cams-global-reanalysis-eac4"
_ATTRIBUTION = (
    "Generated using Copernicus Atmosphere Monitoring Service Information 2026 (licence CC-BY)"
)
_GRANULARITE = "journalier"
_METHODE_COLLECTE = "modele_satellitaire"
_CONFIANCE = "B"

_NB_POINTS = 34
_GRANDEURS: tuple[str, ...] = ("ozone_surface", "ozone_surface_diurne")
_GRANDEURS_SEED: frozenset[str] = frozenset(
    {"aod_550", "aod_poussiere_550", "ozone_surface", "ozone_surface_diurne"}
)
_UNITE_PAR_GRANDEUR: dict[str, str] = {
    "ozone_surface": "partie_par_milliard",
    "ozone_surface_diurne": "partie_par_milliard",
}
_NIVEAU_MODELE_OZONE = "60"
_CONVERSION_OZONE = "kg/kg x (28.9644/47.9982) x 1e9 -> ppb"
_PERIODE_DEBUT_ATTENDUE = date(2004, 2, 1)
_PERIODE_FIN_ATTENDUE = date(2025, 12, 31)
_JOURS_PAR_SERIE = 8_005  # 2004-02-01 -> 2025-12-31, gapless
_NB_SERIES = _NB_POINTS * len(_GRANDEURS)  # 68
_TOTAL_ATTENDU = _NB_SERIES * _JOURS_PAR_SERIE  # 544 340
_TAILLE_LOT_INSERT = 20_000

_LIBELLES: dict[str, str] = {
    "ozone_surface": "Ozone de surface",
    "ozone_surface_diurne": "Ozone de surface diurne",
}
_NOTE_DESCRIPTIFS: dict[str, str] = {
    "ozone_surface": (
        "Fraction molaire d'ozone près de la surface, en parties par milliard (ppb) ; "
        "chaque valeur est la moyenne des huit analyses de la journée, au pas de 3 heures."
    ),
    "ozone_surface_diurne": (
        "Fraction molaire d'ozone près de la surface en journée, en parties par milliard "
        "(ppb) ; chaque valeur est la moyenne des analyses de 09 h, 12 h et 15 h UTC "
        "(heure locale en Guinée)."
    ),
}
_NOTE_PICS = (
    "Mise en garde : en fin de saison sèche (février à mai), sur les années 2006 à "
    "2019, la réanalyse présente localement des pics d'ozone de surface atteignant "
    "environ 300 ppb en moyenne diurne (jusqu'à environ 340 ppb), bien au-dessus des "
    "niveaux habituels (médiane d'environ 27 ppb en moyenne diurne). Il s'agit "
    "probablement d'artefacts du modèle liés aux feux de végétation ; les valeurs sont "
    "conservées telles que fournies par la source."
)
_NOTE_PICS_JOURNALIER: dict[str, str] = {
    "ozone_surface": " Ces épisodes apparaissent aussi, atténués, dans la moyenne journalière.",
    "ozone_surface_diurne": "",
}
_NOTE_PERIODE = "du 1er février 2004 au 31 décembre 2025"
_NOTE_CONF_B = (
    "Niveau de confiance B : donnée de modèle, non validée par une mesure au sol à ce jour."
)


def _code_serie(localite_code: str, grandeur: str) -> str:
    """``<localite>_<grandeur>_cams_eac4_2004_2025`` (code de localite tel quel)."""
    return f"{localite_code}_{grandeur}_{_SOURCE_CODE}_2004_2025"


def _coordonnees(latitude: float, longitude: float) -> str:
    """``9,75° N, 13,50° O`` : coordonnees du point de grille, a la francaise."""
    lat = f"{abs(latitude):.2f}".replace(".", ",") + ("° N" if latitude >= 0 else "° S")
    lon = f"{abs(longitude):.2f}".replace(".", ",") + ("° E" if longitude >= 0 else "° O")
    return f"{lat}, {lon}"


def _note_publique(grandeur: str, ville: str, pixel: dict[str, float]) -> str:
    return (
        f"{_NOTE_DESCRIPTIFS[grandeur]} Série journalière {_NOTE_PERIODE}, {ville}, "
        "Guinée. Données issues de la réanalyse de composition atmosphérique Copernicus "
        "CAMS EAC4, au niveau le plus bas du modèle (assimilable à la surface), "
        "converties en ppb depuis le rapport de mélange massique. Grille de 0,75° "
        "(environ 80 km) : la valeur est celle du point de grille le plus proche "
        f"({_coordonnees(pixel['latitude'], pixel['longitude'])}), représentative de la "
        f"zone environnante et non une mesure de station. {_NOTE_PICS}"
        f"{_NOTE_PICS_JOURNALIER[grandeur]} {_NOTE_CONF_B}"
    )


def _commentaire(grandeur: str, ville: str, pixel: dict[str, float], date_capture: str) -> str:
    pas = (
        "moyenne des 8 pas 3-horaires (00-21 UTC)"
        if grandeur == "ozone_surface"
        else "moyenne des pas 09, 12 et 15 UTC"
    )
    return (
        f"Serie CAMS EAC4 {grandeur} journalier 2004-02-01 -> 2025-12-31, {ville}, Guinee. "
        f"Reanalyse {_DATASET} (ADS), grille 0,75 deg, point de grille le plus proche "
        f"(lat {pixel['latitude']}, lon {pixel['longitude']}). Ozone go3 au niveau modele "
        f"{_NIVEAU_MODELE_OZONE} (le plus bas), {pas}, conversion {_CONVERSION_OZONE}. "
        "Seed NE-OFFLINE cams_eac4_aod_ozone_journalier_seed_data (capture ADS "
        f"{date_capture}, scripts/preparer_seed_cams_eac4_aod_ozone.py), aucun reseau au "
        "runtime. 8 005 jours par serie, aucun jour absent ni incomplet. Pics fin de saison "
        "seche 2006-2019 (diurne ~300 ppb, max ~340, mediane diurne ~27 ppb), artefacts "
        "probables du modele lies aux feux de vegetation, conserves tels que fournis (garde "
        "anti-corruption du preparateur a 500 ppb). Confiance B (modele_satellitaire, source "
        "de fiabilite haute : regle R4). "
        f"Attribution : {_ATTRIBUTION}."
    )


def _capture_commune() -> tuple[date, date, str]:
    """Periode reelle et date de capture, identiques aux 34 compagnons (sinon echec)."""
    periodes: set[tuple[str, str]] = set()
    dates_capture: set[str] = set()
    localites: set[str] = set()
    for localite, capture in iter_captures_cams_eac4_aod_ozone():
        if capture.get("dataset") != _DATASET:
            raise RuntimeError(f"Migration 124 : {localite} : dataset {capture.get('dataset')!r}.")
        if capture.get("attribution") != _ATTRIBUTION:
            raise RuntimeError(f"Migration 124 : {localite} : attribution inattendue.")
        if capture.get("niveau_modele_ozone") != _NIVEAU_MODELE_OZONE:
            raise RuntimeError(f"Migration 124 : {localite} : niveau modele ozone inattendu.")
        if capture.get("conversion_ozone") != _CONVERSION_OZONE:
            raise RuntimeError(f"Migration 124 : {localite} : conversion ozone inattendue.")
        for grandeur in _GRANDEURS:
            for rubrique in ("jours_absents", "jours_incomplets"):
                if capture[rubrique][grandeur]["nombre"] != 0:
                    raise RuntimeError(f"Migration 124 : {localite}/{grandeur} : {rubrique}.")
        reelle = capture["periode_reelle"]
        periodes.add((str(reelle["debut"]), str(reelle["fin"])))
        dates_capture.add(str(capture["date_capture"]))
        localites.add(localite)
    if len(localites) != _NB_POINTS:
        raise RuntimeError(
            f"Migration 124 : {len(localites)} compagnons de capture, attendu {_NB_POINTS}."
        )
    if len(periodes) != 1 or len(dates_capture) != 1:
        raise RuntimeError(
            f"Migration 124 : captures heterogenes (periodes {periodes}, dates {dates_capture})."
        )
    (debut_txt, fin_txt) = periodes.pop()
    debut, fin = date.fromisoformat(debut_txt), date.fromisoformat(fin_txt)
    if (debut, fin) != (_PERIODE_DEBUT_ATTENDUE, _PERIODE_FIN_ATTENDUE):
        raise RuntimeError(f"Migration 124 : periode reelle {debut}..{fin} inattendue.")
    return debut, fin, dates_capture.pop()


def upgrade() -> None:
    bind = op.get_bind()

    # === Referentiel (source 081, grandeurs et unites 122) ====================
    source_id = bind.execute(
        sa.text("SELECT id FROM sources WHERE code = :c"), {"c": _SOURCE_CODE}
    ).scalar_one_or_none()
    if source_id is None:
        raise RuntimeError(f"Migration 124 : source {_SOURCE_CODE!r} introuvable (migration 081).")
    unites = {
        str(r.code): str(r.unite)
        for r in bind.execute(
            sa.text(
                "SELECT gr.code, u.code AS unite FROM grandeurs_referentiel gr "
                "JOIN unites u ON u.id = gr.unite_id "
                "WHERE gr.code = ANY(:c) AND gr.actif = TRUE"
            ),
            {"c": list(_GRANDEURS)},
        ).all()
    }
    if unites != _UNITE_PAR_GRANDEUR:
        raise RuntimeError(
            f"Migration 124 : grandeurs/unites {unites}, attendu {_UNITE_PAR_GRANDEUR}."
        )

    periode_debut, periode_fin, date_capture = _capture_commune()

    # === Gardes (passe 1, streaming complet) ==================================
    comptes: dict[tuple[str, str], int] = {}
    pixels: dict[tuple[str, str], dict[str, float]] = {}
    for bloc in iter_blocs_cams_eac4_aod_ozone():
        loc, grandeur = str(bloc["localite_code"]), str(bloc["grandeur_code"])
        if grandeur not in _GRANDEURS_SEED:
            raise RuntimeError(f"Migration 124 : grandeur inattendue au seed : {grandeur!r}.")
        if grandeur not in _GRANDEURS:
            continue
        cle = (loc, grandeur)
        if cle in comptes:
            raise RuntimeError(f"Migration 124 : bloc en double au seed : {loc}/{grandeur}.")
        valeurs: dict[str, float] = bloc["valeurs"]
        if not valeurs:
            raise RuntimeError(f"Migration 124 : {loc}/{grandeur} sans valeur au seed.")
        d_min, d_max = date.fromisoformat(min(valeurs)), date.fromisoformat(max(valeurs))
        if (d_min, d_max) != (periode_debut, periode_fin):
            raise RuntimeError(f"Migration 124 : {loc}/{grandeur} couvre {d_min}..{d_max}.")
        for jour, valeur in valeurs.items():
            if not isinstance(valeur, float) or not math.isfinite(valeur) or valeur < 0:
                raise RuntimeError(f"Migration 124 : {loc}/{grandeur} {jour} : {valeur!r}.")
        comptes[cle] = len(valeurs)
        pixels[cle] = {
            "latitude": float(bloc["pixel"]["latitude"]),
            "longitude": float(bloc["pixel"]["longitude"]),
        }

    codes_localites = sorted({loc for loc, _ in comptes})
    if len(codes_localites) != _NB_POINTS:
        raise RuntimeError(
            f"Migration 124 : {len(codes_localites)} localites au seed, attendu {_NB_POINTS}."
        )
    for loc in codes_localites:
        for grandeur in _GRANDEURS:
            if comptes.get((loc, grandeur), 0) != _JOURS_PAR_SERIE:
                raise RuntimeError(
                    f"Migration 124 : {loc}/{grandeur} : {comptes.get((loc, grandeur), 0)} "
                    f"jours au seed, attendu {_JOURS_PAR_SERIE}."
                )
    if sum(comptes.values()) != _TOTAL_ATTENDU:
        raise RuntimeError(
            f"Migration 124 : {sum(comptes.values())} mesures au seed, attendu {_TOTAL_ATTENDU}."
        )

    localites = {
        str(r.code): (int(r.id), str(r.nom))
        for r in bind.execute(
            sa.text("SELECT id, code, nom FROM localites WHERE code = ANY(:c)"),
            {"c": codes_localites},
        ).all()
    }
    manquantes = set(codes_localites) - set(localites)
    if manquantes:
        raise RuntimeError(f"Migration 124 : localites introuvables : {sorted(manquantes)}.")

    # === Series ===============================================================
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
        sa.column("note_publique", sa.Text),
        sa.column("url_documentation", sa.Text),
    )
    lignes_series: list[dict[str, Any]] = [
        {
            "code": _code_serie(loc, grandeur),
            "libelle": f"{_LIBELLES[grandeur]} CAMS EAC4 journalier {localites[loc][1]} 2004-2025",
            "localite_id": localites[loc][0],
            "grandeur_code": grandeur,
            "source_id": int(source_id),
            "periode_debut": periode_debut,
            "periode_fin": periode_fin,
            "granularite": _GRANULARITE,
            "methode_collecte": _METHODE_COLLECTE,
            "methode_collecte_doc": _DATASET_URL,
            "commentaire_editorial": _commentaire(
                grandeur, localites[loc][1], pixels[(loc, grandeur)], date_capture
            ),
            "note_publique": _note_publique(grandeur, localites[loc][1], pixels[(loc, grandeur)]),
            "url_documentation": _DATASET_URL,
        }
        for loc in codes_localites
        for grandeur in _GRANDEURS
    ]
    if len(lignes_series) != _NB_SERIES:
        raise RuntimeError(
            f"Migration 124 : {len(lignes_series)} series preparees, attendu {_NB_SERIES}."
        )
    op.bulk_insert(series_table, lignes_series)

    serie_id_par_code: dict[str, int] = {
        str(r.code): int(r.id)
        for r in bind.execute(
            sa.text("SELECT code, id FROM series_metadonnees WHERE code = ANY(:codes)"),
            {"codes": [ligne["code"] for ligne in lignes_series]},
        ).all()
    }
    if len(serie_id_par_code) != _NB_SERIES:
        raise RuntimeError(
            f"Migration 124 : {len(serie_id_par_code)} series inserees, attendu {_NB_SERIES}."
        )

    # === Mesures en streaming (passe 2), lots de 20 000 =======================
    mesures_table = sa.table(
        "mesures_ressource",
        sa.column("serie_id", sa.BigInteger),
        sa.column("instant_mesure", sa.Date),
        sa.column("valeur", sa.Float),
        sa.column("niveau_confiance_derive", sa.String),
    )
    tampon: list[dict[str, Any]] = []
    total_insere = 0
    for bloc in iter_blocs_cams_eac4_aod_ozone():
        if bloc["grandeur_code"] not in _GRANDEURS:
            continue
        serie_id = serie_id_par_code[_code_serie(bloc["localite_code"], bloc["grandeur_code"])]
        for jour, valeur in bloc["valeurs"].items():
            tampon.append(
                {
                    "serie_id": serie_id,
                    "instant_mesure": date.fromisoformat(jour),
                    "valeur": valeur,
                    "niveau_confiance_derive": _CONFIANCE,
                }
            )
            if len(tampon) >= _TAILLE_LOT_INSERT:
                op.bulk_insert(mesures_table, tampon)
                total_insere += len(tampon)
                tampon = []
    if tampon:
        op.bulk_insert(mesures_table, tampon)
        total_insere += len(tampon)
    n_base = bind.execute(
        sa.text("SELECT COUNT(*) FROM mesures_ressource WHERE serie_id = ANY(:ids)"),
        {"ids": list(serie_id_par_code.values())},
    ).scalar_one()
    if total_insere != _TOTAL_ATTENDU or int(n_base) != _TOTAL_ATTENDU:
        raise RuntimeError(
            f"Migration 124 : {total_insere} mesures envoyees, {n_base} en base, "
            f"attendu {_TOTAL_ATTENDU}."
        )

    op.execute(
        f"-- Migration 124 : {_NB_SERIES} series ozone de surface EAC4 journalier (34 points, "
        f"2004-2025) + {total_insere} mesures (offline, 8 005 jours/serie)."
    )


def downgrade() -> None:
    bind = op.get_bind()
    codes = sorted(
        {
            _code_serie(bloc["localite_code"], bloc["grandeur_code"])
            for bloc in iter_blocs_cams_eac4_aod_ozone()
            if bloc["grandeur_code"] in _GRANDEURS
        }
    )
    if len(codes) != _NB_SERIES:
        raise RuntimeError(f"Migration 124 : {len(codes)} codes au seed, attendu {_NB_SERIES}.")
    n_mesures = bind.execute(
        sa.text(
            "DELETE FROM mesures_ressource WHERE serie_id IN "
            "(SELECT id FROM series_metadonnees WHERE code = ANY(:codes))"
        ),
        {"codes": codes},
    ).rowcount
    if n_mesures != _TOTAL_ATTENDU:
        raise RuntimeError(
            f"Migration 124 : {n_mesures} mesures supprimees, attendu {_TOTAL_ATTENDU}."
        )
    n_series = bind.execute(
        sa.text("DELETE FROM series_metadonnees WHERE code = ANY(:codes)"), {"codes": codes}
    ).rowcount
    if n_series != _NB_SERIES:
        raise RuntimeError(f"Migration 124 : {n_series} series supprimees, attendu {_NB_SERIES}.")
