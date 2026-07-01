"""seed_ingestion_era5_land_mensuel_28_communes_densification

Revision ID: 096
Revises: 095
Create Date: 2026-06-22 14:00:00

Parite - ERA5-Land MENSUEL climato 2001-2020. Seed des series ERA5-Land
mensuel 3 grandeurs (ghi/t2m/vent_10m) pour les **28 communes chef-lieu**, depuis le seed
committe DENSIFICATION (``era5_land_densification_mensuel_seed_data``, produit hors-ligne par
``scripts/preparer_seed_era5_land.py 2001 2020 --densification``).

Meme traitement que les 6 pilotes (migration 069, moitie mensuelle) : source ``ecmwf_era5_land``
(reanalyse 0.1deg 11 km), granularite ``mensuel``, **confiance 'B' hardcodee** (patron
brute-ingestion mirror 069, pas de derivation). 28 x 3 x 240 mois = **20 160 mesures**, 84 series.

ERA5-Land = **raffineur de resolution HORS axe d'incertitude** (le triptyque
NASA/SARAH-3/CAMS reste l'axe). **BRUTE SEULEMENT** : aucun ecart, aucun cablage ERA5 dans
l'axe (garde en test).

Caveats portes (mirror 069) :
- ``vent_10m`` mensuel = module des composantes u10/v10 moyennes (sous-estime legerement) :
  caveat **generique** sur toutes les communes.
- ``ghi`` : caveat de separation geometrique, attribue **DATA-DRIVEN** via la
  degenerescence de pixel (migration 090). Une commune recoit le caveat ssi sa
  ``degenerescence_pixel(nasa, ghi) > 0`` (jumeau CERES 1deg). **Pas de hardcode de villes.**
  Regle systematique (cf. ci-dessous) : 14 des 28 communes co-localisees recoivent le caveat.

**Dette notee (registre)** : le caveat ghi de 069 (pilote, immuable, **anterieur a la
degenerescence systematique**) ne flagge que la co-location Kindia/Mamou, alors que la
degenerescence systematique montre que **les 6 pilotes sont tous jumeaux CERES ghi**
(Conakry/Labe/Kankan/Nzerekore aussi, non caveates par 069). 069 immuable -> non corrige ;
la **regle systematique** ``degenerescence>0`` est adoptee pour la densification. Donc le
caveat ERA5 ghi des 28 est **plus complet** que celui des pilotes (pas de la parite stricte,
mais plus honnete).

Repli pixel terrestre (cotieres) : le preparer plafonne le repli a 0.7 deg (au-dela il leve) ;
``repli_applique`` est surface dans le commentaire de serie (mirror 069). Enumeration DATA-DRIVEN
des 28 (garde ``len != 28``), gardes couverture par-commune-grandeur + cap + perimetre.

Bornes : 28 communes seulement ; les 6 pilotes gardent leur ERA5 (069 immuable, zero retrofit).
Ce lot = mensuel ; le DAILY 2021-2025 est traite separement. ``mesures_ressource`` (daily) inchange.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date
from typing import Any

import sqlalchemy as sa
from alembic import op

from kuma_data_core.db.seeds.era5_land_densification_mensuel_seed_data import (
    ERA5_LAND_DENSIFICATION_MENSUEL_SEED,
    ERA5_LAND_DENSIFICATION_PIXELS,
)

# revision identifiers, used by Alembic.
revision: str = "096"
down_revision: str | Sequence[str] | None = "095"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# === Constantes (mirror 069 mensuel) =======================================
_GRANDEURS: tuple[str, ...] = ("ghi", "t2m", "vent_10m")
_LIBELLES_GRANDEURS: dict[str, str] = {
    "ghi": "GHI",
    "t2m": "Temperature 2m",
    "vent_10m": "Vent 10m",
}
_SOURCE_CODE = "ecmwf_era5_land"
_AN_DEBUT, _AN_FIN = 2001, 2020
_PERIODE_DEBUT = date(2001, 1, 1)
_PERIODE_FIN = date(2020, 12, 31)
_GRANULARITE = "mensuel"
_METHODE_COLLECTE = "modele_satellitaire"
_METHODE_COLLECTE_DOC = "https://confluence.ecmwf.int/display/CKB/ERA5-Land"
_URL_DOCUMENTATION = "https://cds.climate.copernicus.eu/datasets/reanalysis-era5-land"

_MOIS_FENETRE = 240  # 2001-01 -> 2020-12 (20 ans x 12)
_CAP_MESURES = 28 * 3 * _MOIS_FENETRE  # 20 160
_YM_DEBUT = _AN_DEBUT * 100 + 1  # 200101
_YM_FIN = _AN_FIN * 100 + 12  # 202012

_CAVEAT_GHI_D29 = (
    " Caveat D-29 (generalise, regle systematique D-75) : cette localite partage une cellule "
    "CERES 1deg avec d'autres points (degenerescence_pixel > 0) ; ERA5-Land les separe "
    "geometriquement, mais le rayonnement est herite du forcage ERA5 (31 km) - separation "
    "geometrique, realisme du differentiel radiatif limite (resolution complete = calage sol)."
)
_CAVEAT_VENT = (
    " Vent mensuel = module des composantes u10/v10 moyennes (sous-estime legerement la "
    "vitesse moyenne reelle)."
)


def _code_serie(commune_code: str, grandeur_code: str) -> str:
    """Convention naming : ``<commune>_<grandeur>_era5_land_2001_2020``."""
    return f"{commune_code}_{grandeur_code}_era5_land_{_AN_DEBUT}_{_AN_FIN}"


def _commentaire(commune_code: str, nom: str, grandeur_code: str, degenere_ghi: bool) -> str:
    pixel = ERA5_LAND_DENSIFICATION_PIXELS.get(commune_code)
    pixel_txt = (
        f"pixel ({pixel['latitude']:.2f}, {pixel['longitude']:.2f})"
        + (" [repli terrestre, masque ocean ERA5-Land]" if pixel.get("repli_applique") else "")
        if pixel
        else "pixel a renseigner (seed non peuple)"
    )
    caveat = ""
    if grandeur_code == "ghi" and degenere_ghi:
        caveat += _CAVEAT_GHI_D29
    if grandeur_code == "vent_10m":
        caveat += _CAVEAT_VENT
    return (
        f"Serie ERA5-Land {grandeur_code.upper()} {_GRANULARITE} {_AN_DEBUT}-{_AN_FIN}, "
        f"{nom} (chef-lieu de prefecture), Guinee. Reanalyse Copernicus (grille API 0.1deg "
        f"11 km), {pixel_txt}. Niveau de confiance B (reanalyse). Densification parite Groupe "
        f"B lot 3a (meme traitement que les 6 pilotes ; ERA5 = raffineur, hors axe "
        f"d'incertitude).{caveat} Attribution : Generated using Copernicus Climate Change "
        f"Service Information 2026 (licence CC-BY)."
    )


def _points_era5(bind: sa.engine.Connection) -> list[tuple[int, str, str]]:
    """Enumeration data-driven des 28 communes : NASA daily 2021-2025 PRESENT (B-1) ET
    ERA5-Land mensuel 2001-2020 ABSENT. Exclut les pilotes (ils ont deja ERA5, 069)."""
    rows = bind.execute(
        sa.text(
            """
            SELECT l.id, l.code, l.nom FROM localites l
            WHERE EXISTS (
                SELECT 1 FROM series_metadonnees sm JOIN sources s ON s.id = sm.source_id
                WHERE sm.localite_id = l.id AND s.code = 'nasa_power'
                  AND sm.grandeur_code = 'ghi' AND sm.granularite = 'journalier'
                  AND sm.periode_debut = '2021-01-01')
              AND NOT EXISTS (
                SELECT 1 FROM series_metadonnees sm JOIN sources s ON s.id = sm.source_id
                WHERE sm.localite_id = l.id AND s.code = 'ecmwf_era5_land'
                  AND sm.granularite = 'mensuel' AND sm.periode_debut = '2001-01-01')
            ORDER BY l.code
            """
        )
    ).all()
    return [(int(r.id), str(r.code), str(r.nom)) for r in rows]


def _communes_degenerees_ghi(bind: sa.engine.Connection) -> set[str]:
    """Localites avec ``degenerescence_pixel(nasa, ghi) > 0`` (jumeaux CERES 1deg),
    migration 090. Sert l'attribution data-driven du caveat ghi (regle systematique)."""
    rows = bind.execute(
        sa.text(
            """
            SELECT l.code FROM grandeurs_metier gm
            JOIN localites l ON l.id = gm.localite_id
            JOIN series_metadonnees sm ON sm.id = gm.series_metadonnees_id
            JOIN sources s ON s.id = sm.source_id
            WHERE gm.grandeur_code = 'degenerescence_pixel'
              AND s.code = 'nasa_power' AND sm.grandeur_code = 'ghi'
              AND gm.valeur > 0
            """
        )
    ).all()
    return {str(r.code) for r in rows}


def upgrade() -> None:
    bind = op.get_bind()

    # === 1. Source + grandeurs (deja declarees, on verifie) ==================
    source_id = bind.execute(
        sa.text("SELECT id FROM sources WHERE code = :c"), {"c": _SOURCE_CODE}
    ).scalar_one_or_none()
    if source_id is None:
        raise RuntimeError(f"Migration 096 : source {_SOURCE_CODE!r} introuvable (migration 068).")
    actives = set(
        bind.execute(
            sa.text("SELECT code FROM grandeurs_referentiel WHERE code = ANY(:c) AND actif = TRUE"),
            {"c": list(_GRANDEURS)},
        )
        .scalars()
        .all()
    )
    manquantes = set(_GRANDEURS) - actives
    if manquantes:
        raise RuntimeError(f"Migration 096 : grandeur(s) inactive(s) : {sorted(manquantes)}.")

    # === 2. Enumeration data-driven des 28 (garde len != 28) =================
    points = _points_era5(bind)
    if len(points) != 28:
        raise RuntimeError(f"Migration 096 : attendu 28 communes, enumere {len(points)}.")
    localite_id_par_code = {code: lid for lid, code, _ in points}
    nom_par_code = {code: nom for _, code, nom in points}
    codes_communes = set(localite_id_par_code)
    degenerees = _communes_degenerees_ghi(bind) & codes_communes

    # === 3. Gardes de couverture du seed =====================================
    seed_codes = {r["localite_code"] for r in ERA5_LAND_DENSIFICATION_MENSUEL_SEED}
    if seed_codes - codes_communes:
        raise RuntimeError(
            f"Migration 096 : seed hors perimetre ({sorted(seed_codes - codes_communes)}). "
            f"Re-generer (2001 2020 --densification)."
        )
    if codes_communes - seed_codes:
        raise RuntimeError(
            f"Migration 096 : communes absentes du seed ({sorted(codes_communes - seed_codes)})."
        )
    if len(ERA5_LAND_DENSIFICATION_MENSUEL_SEED) > _CAP_MESURES:
        raise RuntimeError(
            f"Migration 096 : {len(ERA5_LAND_DENSIFICATION_MENSUEL_SEED)} mesures > cap {_CAP_MESURES}."
        )
    # couverture par (commune, grandeur) : span 2001-01 -> 2020-12
    bornes: dict[tuple[str, str], tuple[int, int]] = {}
    for r in ERA5_LAND_DENSIFICATION_MENSUEL_SEED:
        cle = (r["localite_code"], r["grandeur_code"])
        ym = int(r["annee"]) * 100 + int(r["mois"])
        if cle in bornes:
            lo, hi = bornes[cle]
            bornes[cle] = (min(lo, ym), max(hi, ym))
        else:
            bornes[cle] = (ym, ym)
    for code in codes_communes:
        for grandeur in _GRANDEURS:
            if (code, grandeur) not in bornes:
                raise RuntimeError(f"Migration 096 : {code}/{grandeur} absent du seed.")
            lo, hi = bornes[(code, grandeur)]
            if lo > _YM_DEBUT or hi < _YM_FIN:
                raise RuntimeError(
                    f"Migration 096 : {code}/{grandeur} couverture incomplete ({lo}..{hi})."
                )

    # === 4. Seed des 84 series ===============================================
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
    for code in sorted(codes_communes):
        for grandeur in _GRANDEURS:
            lignes_series.append(
                {
                    "code": _code_serie(code, grandeur),
                    "libelle": (
                        f"{_LIBELLES_GRANDEURS[grandeur]} ERA5-Land {_GRANULARITE} "
                        f"{nom_par_code[code]} {_AN_DEBUT}-{_AN_FIN}"
                    ),
                    "localite_id": localite_id_par_code[code],
                    "grandeur_code": grandeur,
                    "source_id": int(source_id),
                    "periode_debut": _PERIODE_DEBUT,
                    "periode_fin": _PERIODE_FIN,
                    "granularite": _GRANULARITE,
                    "methode_collecte": _METHODE_COLLECTE,
                    "methode_collecte_doc": _METHODE_COLLECTE_DOC,
                    "commentaire_editorial": _commentaire(
                        code, nom_par_code[code], grandeur, code in degenerees
                    ),
                    "url_documentation": _URL_DOCUMENTATION,
                }
            )
    assert len(lignes_series) == 84, f"Attendu 84 series, obtenu {len(lignes_series)}"
    op.bulk_insert(series_table, lignes_series)

    serie_id_par_code: dict[str, int] = {
        r.code: int(r.id)
        for r in bind.execute(
            sa.text("SELECT code, id FROM series_metadonnees WHERE code = ANY(:codes)"),
            {"codes": [s["code"] for s in lignes_series]},
        ).all()
    }

    # === 5. Mesures depuis le seed (hardcode B, mirror 069) ==================
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
            "serie_id": serie_id_par_code[_code_serie(r["localite_code"], r["grandeur_code"])],
            "annee": r["annee"],
            "mois": r["mois"],
            "valeur": r["valeur"],
            "niveau_confiance_derive": "B",
        }
        for r in ERA5_LAND_DENSIFICATION_MENSUEL_SEED
    ]
    op.bulk_insert(mensuelles_table, lignes_mensuelles)

    op.execute(
        f"-- Migration 096 : 84 series ERA5-Land mensuel 2001-2020 (densification parite B "
        f"lot 3a) + {len(lignes_mensuelles)} mesures mensuelles (offline). Caveat ghi data-driven "
        f"(degenerescence > 0) sur {len(degenerees)} communes. Regle D-75."
    )


def downgrade() -> None:
    codes_series = [
        _code_serie(r["localite_code"], r["grandeur_code"])
        for r in ERA5_LAND_DENSIFICATION_MENSUEL_SEED
    ]
    codes_uniques = sorted(set(codes_series))
    op.execute(
        sa.text(
            "DELETE FROM mesures_ressource_mensuelles WHERE serie_id IN "
            "(SELECT id FROM series_metadonnees WHERE code = ANY(:codes))"
        ).bindparams(sa.bindparam("codes", value=codes_uniques))
    )
    op.execute(
        sa.text("DELETE FROM series_metadonnees WHERE code = ANY(:codes)").bindparams(
            sa.bindparam("codes", value=codes_uniques)
        )
    )
