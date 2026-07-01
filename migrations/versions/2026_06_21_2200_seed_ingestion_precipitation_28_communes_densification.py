"""seed_ingestion_precipitation_28_communes_densification

Revision ID: 094
Revises: 093
Create Date: 2026-06-21 22:00:00

Parite - precipitation. Seed des series precipitation journaliere
NASA POWER (PRECTOTCORR, mm/jour) pour les **28 communes chef-lieu**, fenetre 2021-2025,
depuis le seed committe DENSIFICATION (``precipitation_densification_seed_data``, produit
hors-ligne par ``scripts/preparer_seed_precipitation.py --densification``).

Meme traitement que les 6 pilotes (migration 080) : grandeur brute ``precipitation``
(F1 stockee, deja declaree en 080 = immuable, pas de re-declaration), source ``nasa_power``,
granularite ``journalier``, methode ``modele_satellitaire``, **confiance 'B' hardcodee** sur
les mesures (patron brute-ingestion, mirror 080 ; pas de derivation).

Pattern NE-OFFLINE (mirror CAMS densification migration 089) : la migration lit le seed
committe SEPARE des 28 communes (le seed 6-pilotes ``precipitation_seed_data`` reste intact,
ZERO retrofit). **Aucun reseau au runtime** (la capture NASA POWER est faite une fois hors-CI
par le preparer, discipline seed-offline).

Perimetre : 28 communes x 1 grandeur = **28 series** ; journalier 2021-2025, calendrier
complet sans sentinelle = **51 128 mesures** (28 x 1826). Enumeration DATA-DRIVEN depuis la
base (localites ayant le GHI daily 2021-2025 ET sans serie precipitation), garde ``len != 28``.

Gardes de couverture :
- par-commune : chaque commune couvre toute la fenetre (premiere date <= 2021-01-31, derniere
  >= 2025-12-01 ; sentinelles de bord admises) -> une commune vide/tronquee leve.
- cap : ``len(seed) <= 28 x 1826`` (depassement = bug de capture).
- perimetre : aucune localite du seed hors des 28 (mirror garde 089).

Couplage soiling (note de perimetre, anti-scope-creep) : la precipitation est un INTRANT du
proxy HSU ``taux_salissure_proxy`` (resolveur data-driven ``_chercher_serie_pluie_nasa``), mais
l'endpoint exige AUSSI le PM (EAC4, absent aux 28). precip-28 est donc PREREQUIS,
pas suffisant : aucun soiling materialise ici, aucune modif d'endpoint. Le deverrouillage
soiling-28 viendra automatiquement quand le PM-28 arrivera.

Bornes : 28 communes seulement ; les 6 pilotes gardent leurs series (080 immuable, zero retrofit).
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date
from typing import Any

import sqlalchemy as sa
from alembic import op

from kuma_data_core.db.seeds.precipitation_densification_seed_data import (
    PRECIPITATION_DENSIFICATION_SEED,
)

# revision identifiers, used by Alembic.
revision: str = "094"
down_revision: str | Sequence[str] | None = "093"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# === Constantes (mirror 080) ===============================================
_SOURCE_CODE: str = "nasa_power"
_GRANDEUR_CODE: str = "precipitation"
_AN_DEBUT, _AN_FIN = 2021, 2025
_PERIODE_DEBUT: date = date(2021, 1, 1)
_PERIODE_FIN: date = date(2025, 12, 31)
_GRANULARITE: str = "journalier"
_METHODE_COLLECTE: str = "modele_satellitaire"
_METHODE_COLLECTE_DOC: str = "https://power.larc.nasa.gov/docs/methodology/"
_URL_DOCUMENTATION: str = "https://power.larc.nasa.gov/"
_NIVEAU_CONFIANCE: str = "B"  # hardcode mirror 080 (patron brute-ingestion, pas de derivation).

_JOURS_FENETRE: int = 1826  # 2021-2025 calendrier complet (365*4 + 366).
_CAP_MESURES: int = 28 * _JOURS_FENETRE  # 51 128, garde de cap (depassement = bug).
_BORNE_DEBUT_MAX: str = "2021-01-31"  # premiere date <= ce seuil (couverture debut).
_BORNE_FIN_MIN: str = "2025-12-01"  # derniere date >= ce seuil (couverture fin).

_PILOTES: tuple[str, ...] = (
    "gin_conakry_kaloum",
    "gin_kankan",
    "gin_kindia",
    "gin_labe",
    "gin_mamou",
    "gin_nzerekore",
)

_COMMENTAIRE_TEMPLATE: str = (
    "Serie precipitation journaliere brute NASA POWER PRECTOTCORR (methode satellitaire, "
    "MERRA-2 GMAO / IMERG), {ville} (chef-lieu de prefecture), Guinee. Densification parite "
    "Groupe B lot 1 (meme traitement que les 6 pilotes). Entree pluie du proxy de salissure "
    "HSU (Lot C, quand le PM EAC4 sera densifie). Confiance B."
)


def _code_serie(commune_code: str) -> str:
    """Convention naming : ``<commune>_precipitation_nasa_power_2021_2025``."""
    return f"{commune_code}_{_GRANDEUR_CODE}_{_SOURCE_CODE}_{_AN_DEBUT}_{_AN_FIN}"


def _points_precip(bind: sa.engine.Connection) -> list[tuple[int, str, str]]:
    """Enumeration data-driven des 28 communes : GHI daily 2021-2025 ET sans serie
    precipitation (les 6 pilotes en ont deja -> exclus). Robuste a une densification future."""
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
                SELECT 1 FROM series_metadonnees sm WHERE sm.localite_id = l.id
                  AND sm.grandeur_code = 'precipitation')
            ORDER BY l.code
            """
        )
    ).all()
    return [(int(r.id), str(r.code), str(r.nom)) for r in rows]


def upgrade() -> None:
    bind = op.get_bind()

    # === 1. Source + grandeur (deja declarees, on verifie seulement) =========
    source_id = bind.execute(
        sa.text("SELECT id FROM sources WHERE code = :c"), {"c": _SOURCE_CODE}
    ).scalar_one_or_none()
    if source_id is None:
        raise RuntimeError(f"Migration 094 : source {_SOURCE_CODE!r} introuvable.")
    grandeur_ok = bind.execute(
        sa.text("SELECT 1 FROM grandeurs_referentiel WHERE code = :c AND actif = TRUE"),
        {"c": _GRANDEUR_CODE},
    ).scalar_one_or_none()
    if grandeur_ok is None:
        raise RuntimeError(
            f"Migration 094 : grandeur {_GRANDEUR_CODE!r} introuvable/inactive (cf. migration 080)."
        )

    # === 2. Enumeration data-driven des 28 (garde len != 28) =================
    points = _points_precip(bind)
    if len(points) != 28:
        raise RuntimeError(f"Migration 094 : attendu 28 communes, enumere {len(points)}.")
    localite_id_par_code = {code: lid for lid, code, _ in points}
    nom_par_code = {code: nom for _, code, nom in points}
    codes_communes = set(localite_id_par_code)

    # === 3. Gardes de couverture du seed (D1) ================================
    seed_codes = {r["localite_code"] for r in PRECIPITATION_DENSIFICATION_SEED}
    hors_perimetre = seed_codes - codes_communes
    if hors_perimetre:
        raise RuntimeError(
            f"Migration 094 : seed densification contient des localites hors perimetre "
            f"({sorted(hors_perimetre)}). Re-generer le seed (--densification)."
        )
    manquantes = codes_communes - seed_codes
    if manquantes:
        raise RuntimeError(
            f"Migration 094 : communes absentes du seed ({sorted(manquantes)}). Capture incomplete."
        )
    if len(PRECIPITATION_DENSIFICATION_SEED) > _CAP_MESURES:
        raise RuntimeError(
            f"Migration 094 : {len(PRECIPITATION_DENSIFICATION_SEED)} mesures > cap {_CAP_MESURES} "
            f"(28 x {_JOURS_FENETRE}). Seed anormal."
        )
    bornes: dict[str, tuple[str, str]] = {}
    for r in PRECIPITATION_DENSIFICATION_SEED:
        code, jour = r["localite_code"], r["date"]
        if code in bornes:
            bornes[code] = (min(bornes[code][0], jour), max(bornes[code][1], jour))
        else:
            bornes[code] = (jour, jour)
    for code in codes_communes:
        debut, fin = bornes[code]
        if debut > _BORNE_DEBUT_MAX or fin < _BORNE_FIN_MIN:
            raise RuntimeError(
                f"Migration 094 : {code} couverture incomplete ({debut}..{fin}), attendu "
                f"<= {_BORNE_DEBUT_MAX} .. >= {_BORNE_FIN_MIN}."
            )

    # === 4. Seed des 28 series ===============================================
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
    lignes_series: list[dict[str, Any]] = [
        {
            "code": _code_serie(code),
            "libelle": f"Precipitation journaliere {nom_par_code[code]} 2021-2025 (NASA POWER)",
            "localite_id": localite_id_par_code[code],
            "grandeur_code": _GRANDEUR_CODE,
            "source_id": int(source_id),
            "periode_debut": _PERIODE_DEBUT,
            "periode_fin": _PERIODE_FIN,
            "granularite": _GRANULARITE,
            "methode_collecte": _METHODE_COLLECTE,
            "methode_collecte_doc": _METHODE_COLLECTE_DOC,
            "commentaire_editorial": _COMMENTAIRE_TEMPLATE.format(ville=nom_par_code[code]),
            "url_documentation": _URL_DOCUMENTATION,
        }
        for code in sorted(codes_communes)
    ]
    assert len(lignes_series) == 28, f"Attendu 28 series, obtenu {len(lignes_series)}"
    op.bulk_insert(series_table, lignes_series)

    serie_id_par_code: dict[str, int] = {
        r.code: int(r.id)
        for r in bind.execute(
            sa.text("SELECT code, id FROM series_metadonnees WHERE code = ANY(:codes)"),
            {"codes": [_code_serie(c) for c in codes_communes]},
        ).all()
    }

    # === 5. Mesures depuis le seed densification (hardcode B, mirror 080) =====
    mesures_table = sa.table(
        "mesures_ressource",
        sa.column("serie_id", sa.BigInteger),
        sa.column("instant_mesure", sa.Date),
        sa.column("valeur", sa.Float),
        sa.column("niveau_confiance_derive", sa.String),
    )
    lignes_mesures = [
        {
            "serie_id": serie_id_par_code[_code_serie(r["localite_code"])],
            "instant_mesure": date.fromisoformat(r["date"]),
            "valeur": r["valeur"],
            "niveau_confiance_derive": _NIVEAU_CONFIANCE,
        }
        for r in PRECIPITATION_DENSIFICATION_SEED
    ]
    op.bulk_insert(mesures_table, lignes_mesures)

    op.execute(
        f"-- Migration 094 : 28 series precipitation NASA POWER 2021-2025 (densification "
        f"parite B lot 1) + {len(lignes_mesures)} mesures journalieres (offline, seed densif)."
    )


def downgrade() -> None:
    codes_series = [_code_serie(r["localite_code"]) for r in PRECIPITATION_DENSIFICATION_SEED]
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
