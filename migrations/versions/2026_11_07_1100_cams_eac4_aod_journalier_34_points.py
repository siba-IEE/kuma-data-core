"""cams_eac4_aod_journalier_34_points

Revision ID: 123
Revises: 122
Create Date: 2026-11-07 11:00:00.000000+00:00

Epaisseur optique des aerosols a 550 nm (``aod_550``) et sa part poussieres
(``aod_poussiere_550``), journalieres, aux **34 points** (6 pilotes + 28 communes
chef-lieu), pleine profondeur EAC4 2004-02-01 -> 2025-12-31 : **68 series**
(34 x 2) et **544 340 mesures** (8 005 jours par serie, capture sans jour absent
ni incomplet).

Source ``cams_eac4`` (reanalyse EAC4, migration 081) **reutilisee** ; grandeurs
et unite ``sans_unite`` declarees en 122 (verifiees ici, rien n'est re-declare).
La periode des series est lue dans les metadonnees de capture
(``periode_reelle``) et doit valoir 2004-02-01 / 2025-12-31.

Pattern migration 120 : seed NE-OFFLINE
``cams_eac4_aod_ozone_journalier_seed_data_*`` (capture ADS du 2026-11-07, un
compagnon par localite, ``scripts/preparer_seed_cams_eac4_aod_ozone.py``),
consomme en streaming deux passes (gardes puis insertion par lots de 20 000),
gardes de comptage exactes. Confiance 'B' hardcodee (modele_satellitaire sur
source de fiabilite haute : regle R4). ``note_publique`` a l'insertion.
Attribution CC-BY Copernicus/CAMS. BRUTE SEULEMENT. Aucun reseau.

Codes de serie ``<localite>_<grandeur>_cams_eac4_2004_2025`` : code de localite
tel quel (``gin_conakry_kaloum``, comme la migration 120), pas l'alias
historique ``gin_conakry``.
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
revision: str = "123"
down_revision: str | Sequence[str] | None = "122"
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
_GRANDEURS: tuple[str, ...] = ("aod_550", "aod_poussiere_550")
_GRANDEURS_SEED: frozenset[str] = frozenset(
    {"aod_550", "aod_poussiere_550", "ozone_surface", "ozone_surface_diurne"}
)
_UNITE_PAR_GRANDEUR: dict[str, str] = {
    "aod_550": "sans_unite",
    "aod_poussiere_550": "sans_unite",
}
_PERIODE_DEBUT_ATTENDUE = date(2004, 2, 1)
_PERIODE_FIN_ATTENDUE = date(2025, 12, 31)
_JOURS_PAR_SERIE = 8_005  # 2004-02-01 -> 2025-12-31, gapless
_NB_SERIES = _NB_POINTS * len(_GRANDEURS)  # 68
_TOTAL_ATTENDU = _NB_SERIES * _JOURS_PAR_SERIE  # 544 340
_TAILLE_LOT_INSERT = 20_000

_LIBELLES: dict[str, str] = {
    "aod_550": "AOD 550 nm",
    "aod_poussiere_550": "AOD poussières 550 nm",
}
_NOTE_DESCRIPTIFS: dict[str, str] = {
    "aod_550": (
        "Épaisseur optique totale des aérosols à 550 nm, grandeur sans dimension qui "
        "mesure l'atténuation de la lumière solaire par l'ensemble des particules en "
        "suspension sur toute la colonne atmosphérique."
    ),
    "aod_poussiere_550": (
        "Part de l'épaisseur optique des aérosols à 550 nm due aux poussières "
        "minérales, grandeur sans dimension portant sur toute la colonne "
        "atmosphérique ; elle ne dépasse pas l'épaisseur optique totale."
    ),
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
        "Guinée : chaque valeur est la moyenne des huit analyses de la journée, au pas "
        "de 3 heures. Données issues de la réanalyse de composition atmosphérique "
        "Copernicus CAMS EAC4, sur une grille de 0,75° (environ 80 km) : la valeur est "
        "celle du point de grille le plus proche "
        f"({_coordonnees(pixel['latitude'], pixel['longitude'])}), représentative de la "
        f"zone environnante et non une mesure de station. {_NOTE_CONF_B}"
    )


def _commentaire(grandeur: str, ville: str, pixel: dict[str, float], date_capture: str) -> str:
    return (
        f"Serie CAMS EAC4 {grandeur} journalier 2004-02-01 -> 2025-12-31, {ville}, Guinee. "
        f"Reanalyse {_DATASET} (ADS), grille 0,75 deg, point de grille le plus proche "
        f"(lat {pixel['latitude']}, lon {pixel['longitude']}). Moyenne journaliere des 8 pas "
        "3-horaires (00-21 UTC), sans dimension. Seed NE-OFFLINE "
        f"cams_eac4_aod_ozone_journalier_seed_data (capture ADS {date_capture}, "
        "scripts/preparer_seed_cams_eac4_aod_ozone.py), aucun reseau au runtime. "
        "8 005 jours par serie, aucun jour absent ni incomplet. Confiance B "
        "(modele_satellitaire, source de fiabilite haute : regle R4). "
        f"Attribution : {_ATTRIBUTION}."
    )


def _capture_commune() -> tuple[date, date, str]:
    """Periode reelle et date de capture, identiques aux 34 compagnons (sinon echec)."""
    periodes: set[tuple[str, str]] = set()
    dates_capture: set[str] = set()
    localites: set[str] = set()
    for localite, capture in iter_captures_cams_eac4_aod_ozone():
        if capture.get("dataset") != _DATASET:
            raise RuntimeError(f"Migration 123 : {localite} : dataset {capture.get('dataset')!r}.")
        if capture.get("attribution") != _ATTRIBUTION:
            raise RuntimeError(f"Migration 123 : {localite} : attribution inattendue.")
        for grandeur in _GRANDEURS:
            for rubrique in ("jours_absents", "jours_incomplets"):
                if capture[rubrique][grandeur]["nombre"] != 0:
                    raise RuntimeError(f"Migration 123 : {localite}/{grandeur} : {rubrique}.")
        reelle = capture["periode_reelle"]
        periodes.add((str(reelle["debut"]), str(reelle["fin"])))
        dates_capture.add(str(capture["date_capture"]))
        localites.add(localite)
    if len(localites) != _NB_POINTS:
        raise RuntimeError(
            f"Migration 123 : {len(localites)} compagnons de capture, attendu {_NB_POINTS}."
        )
    if len(periodes) != 1 or len(dates_capture) != 1:
        raise RuntimeError(
            f"Migration 123 : captures heterogenes (periodes {periodes}, dates {dates_capture})."
        )
    (debut_txt, fin_txt) = periodes.pop()
    debut, fin = date.fromisoformat(debut_txt), date.fromisoformat(fin_txt)
    if (debut, fin) != (_PERIODE_DEBUT_ATTENDUE, _PERIODE_FIN_ATTENDUE):
        raise RuntimeError(f"Migration 123 : periode reelle {debut}..{fin} inattendue.")
    return debut, fin, dates_capture.pop()


def upgrade() -> None:
    bind = op.get_bind()

    # === Referentiel (source 081, grandeurs et unites 122) ====================
    source_id = bind.execute(
        sa.text("SELECT id FROM sources WHERE code = :c"), {"c": _SOURCE_CODE}
    ).scalar_one_or_none()
    if source_id is None:
        raise RuntimeError(f"Migration 123 : source {_SOURCE_CODE!r} introuvable (migration 081).")
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
            f"Migration 123 : grandeurs/unites {unites}, attendu {_UNITE_PAR_GRANDEUR}."
        )

    periode_debut, periode_fin, date_capture = _capture_commune()

    # === Gardes (passe 1, streaming complet) ==================================
    comptes: dict[tuple[str, str], int] = {}
    pixels: dict[tuple[str, str], dict[str, float]] = {}
    for bloc in iter_blocs_cams_eac4_aod_ozone():
        loc, grandeur = str(bloc["localite_code"]), str(bloc["grandeur_code"])
        if grandeur not in _GRANDEURS_SEED:
            raise RuntimeError(f"Migration 123 : grandeur inattendue au seed : {grandeur!r}.")
        if grandeur not in _GRANDEURS:
            continue
        cle = (loc, grandeur)
        if cle in comptes:
            raise RuntimeError(f"Migration 123 : bloc en double au seed : {loc}/{grandeur}.")
        valeurs: dict[str, float] = bloc["valeurs"]
        if not valeurs:
            raise RuntimeError(f"Migration 123 : {loc}/{grandeur} sans valeur au seed.")
        d_min, d_max = date.fromisoformat(min(valeurs)), date.fromisoformat(max(valeurs))
        if (d_min, d_max) != (periode_debut, periode_fin):
            raise RuntimeError(f"Migration 123 : {loc}/{grandeur} couvre {d_min}..{d_max}.")
        for jour, valeur in valeurs.items():
            if not isinstance(valeur, float) or not math.isfinite(valeur) or valeur < 0:
                raise RuntimeError(f"Migration 123 : {loc}/{grandeur} {jour} : {valeur!r}.")
        comptes[cle] = len(valeurs)
        pixels[cle] = {
            "latitude": float(bloc["pixel"]["latitude"]),
            "longitude": float(bloc["pixel"]["longitude"]),
        }

    codes_localites = sorted({loc for loc, _ in comptes})
    if len(codes_localites) != _NB_POINTS:
        raise RuntimeError(
            f"Migration 123 : {len(codes_localites)} localites au seed, attendu {_NB_POINTS}."
        )
    for loc in codes_localites:
        for grandeur in _GRANDEURS:
            if comptes.get((loc, grandeur), 0) != _JOURS_PAR_SERIE:
                raise RuntimeError(
                    f"Migration 123 : {loc}/{grandeur} : {comptes.get((loc, grandeur), 0)} "
                    f"jours au seed, attendu {_JOURS_PAR_SERIE}."
                )
    if sum(comptes.values()) != _TOTAL_ATTENDU:
        raise RuntimeError(
            f"Migration 123 : {sum(comptes.values())} mesures au seed, attendu {_TOTAL_ATTENDU}."
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
        raise RuntimeError(f"Migration 123 : localites introuvables : {sorted(manquantes)}.")

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
            f"Migration 123 : {len(lignes_series)} series preparees, attendu {_NB_SERIES}."
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
            f"Migration 123 : {len(serie_id_par_code)} series inserees, attendu {_NB_SERIES}."
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
            f"Migration 123 : {total_insere} mesures envoyees, {n_base} en base, "
            f"attendu {_TOTAL_ATTENDU}."
        )

    op.execute(
        f"-- Migration 123 : {_NB_SERIES} series AOD 550 nm EAC4 journalier (34 points, "
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
        raise RuntimeError(f"Migration 123 : {len(codes)} codes au seed, attendu {_NB_SERIES}.")
    n_mesures = bind.execute(
        sa.text(
            "DELETE FROM mesures_ressource WHERE serie_id IN "
            "(SELECT id FROM series_metadonnees WHERE code = ANY(:codes))"
        ),
        {"codes": codes},
    ).rowcount
    if n_mesures != _TOTAL_ATTENDU:
        raise RuntimeError(
            f"Migration 123 : {n_mesures} mesures supprimees, attendu {_TOTAL_ATTENDU}."
        )
    n_series = bind.execute(
        sa.text("DELETE FROM series_metadonnees WHERE code = ANY(:codes)"), {"codes": codes}
    ).rowcount
    if n_series != _NB_SERIES:
        raise RuntimeError(f"Migration 123 : {n_series} series supprimees, attendu {_NB_SERIES}.")
