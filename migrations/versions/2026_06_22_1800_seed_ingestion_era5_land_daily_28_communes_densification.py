"""seed_ingestion_era5_land_daily_28_communes_densification

Revision ID: 097
Revises: 096
Create Date: 2026-06-22 18:00:00

Parite - ERA5-Land DAILY 2021-2025. Seed des series
ERA5-Land journalier 3 grandeurs (ghi/t2m/vent_10m) pour les **28 communes chef-lieu**, depuis
le seed committe DENSIFICATION CHUNKE par-ville (``era5_land_densification_journalier_seed_data``,
produit hors-ligne par ``scripts/preparer_seed_era5_land.py 2021 2025 --densification``).

Meme traitement que les 6 pilotes (migration 069, moitie journaliere) : source
``ecmwf_era5_land`` (dataset **timeseries** = meme methode que les pilotes daily, ``ssrd``
de-accumule, t2m/vent moyennes quotidiennes), granularite ``journalier``, **confiance 'B'
hardcodee** (mirror 069). 28 x 3 x 1826 jours = **153 384 mesures** dans ``mesures_ressource``,
84 series. Le seed daily est CHUNKE par-ville (153k mesures depasseraient le hook 1 Mo en un
fichier ; mirror NASA daily). Pixels REUTILISES du seed mensuel 3a (zero re-resolution ocean).

ERA5-Land = raffineur de resolution HORS axe d'incertitude. **BRUTE SEULEMENT** :
aucun ecart, aucun cablage ERA5 dans l'axe (garde en test).

Caveats (mirror 069) :
- ``ghi`` : caveat de separation geometrique, attribue **DATA-DRIVEN** via la
  ``degenerescence_pixel(nasa, ghi) > 0`` (migration 090) -> **memes 14 communes** que le lot
  mensuel (la degenerescence est geometrique, stable cross-fenetre/granularite). Regle
  systematique (cf. docstring 096), pas de hardcode de villes.
- ``vent_10m`` : **PAS de caveat en daily** (le caveat module ne concerne que le mensuel =
  module des moyennes ; le daily est moyenne des modules horaires). Mirror 069 (l.130).

Enumeration DATA-DRIVEN des 28 (garde ``len != 28``), gardes couverture par-commune-grandeur
(1826 j) + cap + perimetre. Bornes : 28 communes ; les 6 pilotes gardent leur ERA5 daily (069
immuable, zero retrofit). ``mesures_ressource_mensuelles`` inchange (ce lot = daily).
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date
from typing import Any

import sqlalchemy as sa
from alembic import op

from kuma_data_core.db.seeds.era5_land_densification_journalier_seed_data import (
    ERA5_LAND_DENSIFICATION_JOURNALIER_SEED,
)
from kuma_data_core.db.seeds.era5_land_densification_mensuel_seed_data import (
    ERA5_LAND_DENSIFICATION_PIXELS,
)

# revision identifiers, used by Alembic.
revision: str = "097"
down_revision: str | Sequence[str] | None = "096"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# === Constantes (mirror 069 journalier) ====================================
_GRANDEURS: tuple[str, ...] = ("ghi", "t2m", "vent_10m")
_LIBELLES_GRANDEURS: dict[str, str] = {
    "ghi": "GHI",
    "t2m": "Temperature 2m",
    "vent_10m": "Vent 10m",
}
_SOURCE_CODE = "ecmwf_era5_land"
_AN_DEBUT, _AN_FIN = 2021, 2025
_PERIODE_DEBUT = date(2021, 1, 1)
_PERIODE_FIN = date(2025, 12, 31)
_GRANULARITE = "journalier"
_METHODE_COLLECTE = "modele_satellitaire"
_METHODE_COLLECTE_DOC = "https://confluence.ecmwf.int/display/CKB/ERA5-Land"
_URL_DOCUMENTATION = "https://cds.climate.copernicus.eu/datasets/reanalysis-era5-land"

_JOURS_FENETRE = 1826  # 2021-2025 calendrier complet
_CAP_MESURES = 28 * 3 * _JOURS_FENETRE  # 153 384
_BORNE_DEBUT_MAX = "2021-01-31"  # premiere date <= ce seuil (couverture debut)
_BORNE_FIN_MIN = "2025-12-01"  # derniere date >= ce seuil (couverture fin)

_CAVEAT_GHI_D29 = (
    " Caveat D-29 (generalise, regle systematique D-75) : cette localite partage une cellule "
    "CERES 1deg avec d'autres points (degenerescence_pixel > 0) ; ERA5-Land les separe "
    "geometriquement, mais le rayonnement est herite du forcage ERA5 (31 km) - separation "
    "geometrique, realisme du differentiel radiatif limite (resolution complete = calage sol)."
)


def _code_serie(commune_code: str, grandeur_code: str) -> str:
    """Convention naming : ``<commune>_<grandeur>_era5_land_2021_2025``."""
    return f"{commune_code}_{grandeur_code}_era5_land_{_AN_DEBUT}_{_AN_FIN}"


def _commentaire(commune_code: str, nom: str, grandeur_code: str, degenere_ghi: bool) -> str:
    pixel = ERA5_LAND_DENSIFICATION_PIXELS.get(commune_code)
    pixel_txt = (
        f"pixel ({pixel['latitude']:.2f}, {pixel['longitude']:.2f})"
        + (" [repli terrestre, masque ocean ERA5-Land]" if pixel.get("repli_applique") else "")
        if pixel
        else "pixel a renseigner (seed non peuple)"
    )
    caveat = _CAVEAT_GHI_D29 if (grandeur_code == "ghi" and degenere_ghi) else ""
    return (
        f"Serie ERA5-Land {grandeur_code.upper()} {_GRANULARITE} {_AN_DEBUT}-{_AN_FIN}, "
        f"{nom} (chef-lieu de prefecture), Guinee. Reanalyse Copernicus (grille API 0.1deg "
        f"11 km), {pixel_txt}. Niveau de confiance B (reanalyse). Densification parite Groupe "
        f"B lot 3b (meme traitement que les 6 pilotes ; ERA5 = raffineur, hors axe "
        f"d'incertitude).{caveat} Attribution : Generated using Copernicus Climate Change "
        f"Service Information 2026 (licence CC-BY)."
    )


def _points_era5_daily(bind: sa.engine.Connection) -> list[tuple[int, str, str]]:
    """Enumeration data-driven des 28 communes : NASA daily 2021-2025 PRESENT (B-1) ET
    ERA5-Land daily 2021-2025 ABSENT. Exclut les pilotes (ils ont deja l'ERA5 daily, 069)."""
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
                  AND sm.granularite = 'journalier' AND sm.periode_debut = '2021-01-01')
            ORDER BY l.code
            """
        )
    ).all()
    return [(int(r.id), str(r.code), str(r.nom)) for r in rows]


def _communes_degenerees_ghi(bind: sa.engine.Connection) -> set[str]:
    """Localites avec ``degenerescence_pixel(nasa, ghi) > 0`` (jumeaux CERES 1deg),
    migration 090. Attribution data-driven du caveat ghi (regle systematique), memes 14 que le lot mensuel."""
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
        raise RuntimeError(f"Migration 097 : source {_SOURCE_CODE!r} introuvable (migration 068).")
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
        raise RuntimeError(f"Migration 097 : grandeur(s) inactive(s) : {sorted(manquantes)}.")

    # === 2. Enumeration data-driven des 28 (garde len != 28) =================
    points = _points_era5_daily(bind)
    if len(points) != 28:
        raise RuntimeError(f"Migration 097 : attendu 28 communes, enumere {len(points)}.")
    localite_id_par_code = {code: lid for lid, code, _ in points}
    nom_par_code = {code: nom for _, code, nom in points}
    codes_communes = set(localite_id_par_code)
    degenerees = _communes_degenerees_ghi(bind) & codes_communes

    # === 3. Gardes de couverture du seed =====================================
    seed_codes = {r["localite_code"] for r in ERA5_LAND_DENSIFICATION_JOURNALIER_SEED}
    if seed_codes - codes_communes:
        raise RuntimeError(
            f"Migration 097 : seed hors perimetre ({sorted(seed_codes - codes_communes)}). "
            f"Re-generer (2021 2025 --densification)."
        )
    if codes_communes - seed_codes:
        raise RuntimeError(
            f"Migration 097 : communes absentes du seed ({sorted(codes_communes - seed_codes)})."
        )
    if len(ERA5_LAND_DENSIFICATION_JOURNALIER_SEED) > _CAP_MESURES:
        raise RuntimeError(
            f"Migration 097 : {len(ERA5_LAND_DENSIFICATION_JOURNALIER_SEED)} mesures > cap "
            f"{_CAP_MESURES}."
        )
    bornes: dict[tuple[str, str], tuple[str, str]] = {}
    for r in ERA5_LAND_DENSIFICATION_JOURNALIER_SEED:
        cle = (r["localite_code"], r["grandeur_code"])
        jour = r["date"]
        if cle in bornes:
            lo, hi = bornes[cle]
            bornes[cle] = (min(lo, jour), max(hi, jour))
        else:
            bornes[cle] = (jour, jour)
    for code in codes_communes:
        for grandeur in _GRANDEURS:
            if (code, grandeur) not in bornes:
                raise RuntimeError(f"Migration 097 : {code}/{grandeur} absent du seed.")
            debut, fin = bornes[(code, grandeur)]
            if debut > _BORNE_DEBUT_MAX or fin < _BORNE_FIN_MIN:
                raise RuntimeError(
                    f"Migration 097 : {code}/{grandeur} couverture incomplete ({debut}..{fin})."
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

    # === 5. Mesures depuis le seed chunke (hardcode B, mirror 069) ===========
    mesures_table = sa.table(
        "mesures_ressource",
        sa.column("serie_id", sa.BigInteger),
        sa.column("instant_mesure", sa.Date),
        sa.column("valeur", sa.Float),
        sa.column("niveau_confiance_derive", sa.String),
    )
    lignes_mesures = [
        {
            "serie_id": serie_id_par_code[_code_serie(r["localite_code"], r["grandeur_code"])],
            "instant_mesure": date.fromisoformat(r["date"]),
            "valeur": r["valeur"],
            "niveau_confiance_derive": "B",
        }
        for r in ERA5_LAND_DENSIFICATION_JOURNALIER_SEED
    ]
    op.bulk_insert(mesures_table, lignes_mesures)

    op.execute(
        f"-- Migration 097 : 84 series ERA5-Land daily 2021-2025 (densification parite B lot 3b, "
        f"CLOTURE Groupe B) + {len(lignes_mesures)} mesures journalieres (offline, seed chunke). "
        f"Caveat ghi data-driven sur {len(degenerees)} communes. Regle D-75."
    )


def downgrade() -> None:
    codes_series = [
        _code_serie(r["localite_code"], r["grandeur_code"])
        for r in ERA5_LAND_DENSIFICATION_JOURNALIER_SEED
    ]
    codes_uniques = sorted(set(codes_series))
    op.execute(
        sa.text(
            "DELETE FROM mesures_ressource WHERE serie_id IN "
            "(SELECT id FROM series_metadonnees WHERE code = ANY(:codes))"
        ).bindparams(sa.bindparam("codes", value=codes_uniques))
    )
    op.execute(
        sa.text("DELETE FROM series_metadonnees WHERE code = ANY(:codes)").bindparams(
            sa.bindparam("codes", value=codes_uniques)
        )
    )
