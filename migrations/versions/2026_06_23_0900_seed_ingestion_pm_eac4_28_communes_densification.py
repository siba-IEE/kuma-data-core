"""seed_ingestion_pm_eac4_28_communes_densification

Revision ID: 098
Revises: 097
Create Date: 2026-06-23 09:00:00

Parite - PM EAC4 pm2_5/pm10. Seed des series EAC4
journalier 2 grandeurs (pm2_5/pm10) pour les **28 communes chef-lieu**, depuis le seed committe
DENSIFICATION (``cams_eac4_densification_seed_data``, produit hors-ligne par
``scripts/preparer_seed_cams_eac4.py --densification``).

Meme traitement que les 6 pilotes (migration 081) : source ``cams_eac4`` (ADS
EAC4, **deja declaree** migration 081), unite ``microgramme_par_metre_cube`` et grandeurs brutes
``pm2_5``/``pm10`` (**deja declarees**) -- cette migration ne RE-DECLARE RIEN, elle verifie la
presence. Granularite ``journalier``, **confiance 'B' hardcodee** (mirror 081 l.362 : la
confiance B est *conceptuellement derivee* -- modele satellitaire, la regle R3 ne donne pas A --
mais inscrite en dur, pas calculee au runtime). 28 x 2 x 1704 jours = **95 424 mesures** dans
``mesures_ressource``, 56 series, fenetre reelle 2021-01-01 -> **2025-08-31** (naming
``_2021_2025`` mais ``periode_fin`` borne a la couverture reelle EAC4, latence 10 mois).

DEVERROUILLAGE soiling (point de valeur du lot) : il fournit les PM (entree particules du HSU)
aux 28 communes. Le proxy ``taux_salissure_proxy`` resout la compagne PM10 (meme source EAC4) +
la pluie ``nasa_power`` (resolveur data-driven dedie) par ``localite_id`` -- une
fois les PM-28 seedees, soiling-28 marche SANS modif d'endpoint (verifie en test, commune temoin).

Caveat de resolution grossiere (grille EAC4 0,75 deg) : caveat GENERIQUE niveau grandeur/source,
porte sur les 28 (mirror le commentaire pilote). **PAS data-driven** (aucune degenerescence PM
materialisee ; on n'invente PAS d'equivalent ERA5-ghi -- anti gold-plating).

**BRUTE SEULEMENT** : aucune ``grandeur_metier`` ne reference ``cams_eac4`` (garde anti-ecart en
test). Enumeration DATA-DRIVEN des 28 (NASA daily ghi 2021 PRESENT ET pm2_5 cams_eac4 ABSENT,
garde ``len != 28``), gardes couverture par-commune-grandeur + cap + perimetre. Les 6 pilotes
gardent leur PM (081 immuable, zero retrofit). ``mesures_ressource_mensuelles`` inchange (PM =
journalier).
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date
from typing import Any

import sqlalchemy as sa
from alembic import op

from kuma_data_core.db.seeds.cams_eac4_densification_seed_data import (
    CAMS_EAC4_DENSIFICATION_JOURNALIER_SEED,
)

# revision identifiers, used by Alembic.
revision: str = "098"
down_revision: str | Sequence[str] | None = "097"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# === Constantes (mirror 081 pilote) ========================================
_GRANDEURS: tuple[str, ...] = ("pm2_5", "pm10")
_LIBELLES_GRANDEURS: dict[str, str] = {"pm2_5": "PM2.5 journalier", "pm10": "PM10 journalier"}
_SOURCE_CODE = "cams_eac4"
_PERIODE_DEBUT = date(2021, 1, 1)
_PERIODE_FIN = date(2025, 8, 31)  # couverture reelle EAC4 (latence reanalyse 10 mois)
_GRANULARITE = "journalier"
_METHODE_COLLECTE = "modele_satellitaire"
_METHODE_COLLECTE_DOC = "https://ads.atmosphere.copernicus.eu/datasets/cams-global-reanalysis-eac4"
_URL_DOCUMENTATION = _METHODE_COLLECTE_DOC

_JOURS_FENETRE = 1704  # 2021-01-01 -> 2025-08-31
_CAP_MESURES = 28 * len(_GRANDEURS) * _JOURS_FENETRE  # 95 424 (borne superieure)
_BORNE_DEBUT_MAX = "2021-01-31"  # premiere date <= ce seuil (couverture debut)
_BORNE_FIN_MIN = "2025-08-01"  # derniere date >= ce seuil (couverture fin reelle EAC4)


def _code_serie(commune_code: str, grandeur_code: str) -> str:
    """Convention naming : ``<commune>_<grandeur>_cams_eac4_2021_2025``."""
    return f"{commune_code}_{grandeur_code}_{_SOURCE_CODE}_2021_2025"


def _commentaire(nom: str, grandeur_code: str) -> str:
    """Commentaire editorial mirror du pilote 081, avec caveat de resolution grossiere
    (grille grossiere 0,75 deg), confiance B et attribution CC-BY."""
    return (
        f"Serie EAC4 {grandeur_code.upper()} journalier {nom} (chef-lieu de prefecture), "
        f"Guinee. Reanalyse Copernicus EAC4 (ADS), grille grossiere 0,75 deg (caveat "
        f"L-SOIL-4), concentration de surface (ug/m3, moyenne journaliere du pas 3-horaire). "
        f"Confiance B (modele satellitaire). Densification parite Groupe C lot C-1 (meme "
        f"traitement que les 6 pilotes). Naming _2021_2025 mais couverture reelle bornee au "
        f"2025-08-31 (latence de reanalyse EAC4 10 mois). Entree particules du HSU "
        f"(deverrouille taux_salissure_proxy aux 28 communes). Attribution : Generated using "
        f"Copernicus Atmosphere Monitoring Service Information 2026 (licence CC-BY)."
    )


def _points_pm_eac4(bind: sa.engine.Connection) -> list[tuple[int, str, str]]:
    """Enumeration data-driven des 28 communes : NASA daily ghi 2021 PRESENT (parite B) ET
    PM2.5 cams_eac4 ABSENT. Exclut les 6 pilotes (ils ont deja le PM EAC4, 081)."""
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
                WHERE sm.localite_id = l.id AND s.code = 'cams_eac4'
                  AND sm.grandeur_code = 'pm2_5')
            ORDER BY l.code
            """
        )
    ).all()
    return [(int(r.id), str(r.code), str(r.nom)) for r in rows]


def upgrade() -> None:
    bind = op.get_bind()

    # === 1. Source + grandeurs (deja declarees migration 081, on verifie) ====
    source_id = bind.execute(
        sa.text("SELECT id FROM sources WHERE code = :c"), {"c": _SOURCE_CODE}
    ).scalar_one_or_none()
    if source_id is None:
        raise RuntimeError(f"Migration 098 : source {_SOURCE_CODE!r} introuvable (migration 081).")
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
        raise RuntimeError(f"Migration 098 : grandeur(s) inactive(s) : {sorted(manquantes)}.")

    # === 2. Enumeration data-driven des 28 (garde len != 28) =================
    points = _points_pm_eac4(bind)
    if len(points) != 28:
        raise RuntimeError(f"Migration 098 : attendu 28 communes, enumere {len(points)}.")
    localite_id_par_code = {code: lid for lid, code, _ in points}
    nom_par_code = {code: nom for _, code, nom in points}
    codes_communes = set(localite_id_par_code)

    # === 3. Gardes de couverture du seed =====================================
    seed_codes = {r["localite_code"] for r in CAMS_EAC4_DENSIFICATION_JOURNALIER_SEED}
    if seed_codes - codes_communes:
        raise RuntimeError(
            f"Migration 098 : seed hors perimetre ({sorted(seed_codes - codes_communes)}). "
            f"Re-generer (--densification)."
        )
    if codes_communes - seed_codes:
        raise RuntimeError(
            f"Migration 098 : communes absentes du seed ({sorted(codes_communes - seed_codes)})."
        )
    if len(CAMS_EAC4_DENSIFICATION_JOURNALIER_SEED) > _CAP_MESURES:
        raise RuntimeError(
            f"Migration 098 : {len(CAMS_EAC4_DENSIFICATION_JOURNALIER_SEED)} mesures > cap "
            f"{_CAP_MESURES}."
        )
    bornes: dict[tuple[str, str], tuple[str, str]] = {}
    for r in CAMS_EAC4_DENSIFICATION_JOURNALIER_SEED:
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
                raise RuntimeError(f"Migration 098 : {code}/{grandeur} absent du seed.")
            debut, fin = bornes[(code, grandeur)]
            if debut > _BORNE_DEBUT_MAX or fin < _BORNE_FIN_MIN:
                raise RuntimeError(
                    f"Migration 098 : {code}/{grandeur} couverture incomplete ({debut}..{fin})."
                )

    # === 4. Seed des 56 series (28 communes x 2 grandeurs) ===================
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
                        f"{_LIBELLES_GRANDEURS[grandeur]} {nom_par_code[code]} 2021-2025 (EAC4)"
                    ),
                    "localite_id": localite_id_par_code[code],
                    "grandeur_code": grandeur,
                    "source_id": int(source_id),
                    "periode_debut": _PERIODE_DEBUT,
                    "periode_fin": _PERIODE_FIN,
                    "granularite": _GRANULARITE,
                    "methode_collecte": _METHODE_COLLECTE,
                    "methode_collecte_doc": _METHODE_COLLECTE_DOC,
                    "commentaire_editorial": _commentaire(nom_par_code[code], grandeur),
                    "url_documentation": _URL_DOCUMENTATION,
                }
            )
    assert len(lignes_series) == 56, f"Attendu 56 series, obtenu {len(lignes_series)}"
    op.bulk_insert(series_table, lignes_series)

    serie_id_par_code: dict[str, int] = {
        r.code: int(r.id)
        for r in bind.execute(
            sa.text("SELECT code, id FROM series_metadonnees WHERE code = ANY(:codes)"),
            {"codes": [s["code"] for s in lignes_series]},
        ).all()
    }

    # === 5. Mesures depuis le seed (hardcode B, mirror 081) ==================
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
        for r in CAMS_EAC4_DENSIFICATION_JOURNALIER_SEED
    ]
    op.bulk_insert(mesures_table, lignes_mesures)

    op.execute(
        f"-- Migration 098 : 56 series PM EAC4 (pm2_5/pm10) journalier 2021-2025 (densification "
        f"parite Groupe C lot C-1, OUVERTURE Groupe C) + {len(lignes_mesures)} mesures (offline). "
        f"Caveat L-SOIL-4 generique aux 28. Deverrouille le proxy soiling aux 28."
    )


def downgrade() -> None:
    codes_series = sorted(
        {
            _code_serie(r["localite_code"], r["grandeur_code"])
            for r in CAMS_EAC4_DENSIFICATION_JOURNALIER_SEED
        }
    )
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
