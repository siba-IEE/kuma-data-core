"""seed_ingestion_cams_dni_climato_28_communes_densification

Revision ID: 095
Revises: 094
Create Date: 2026-06-22 10:00:00

Parite - CAMS Radiation DNI climato 2004-2020. Seed des series CAMS
Radiation DNI all-sky **climato mensuel 2004-2020** pour les **28 communes chef-lieu**,
depuis le seed committe DENSIFICATION (``cams_radiation_2004_2020_densification_seed_data``,
produit hors-ligne par ``scripts/preparer_seed_cams.py 2004 2020 --densification``).

Meme traitement que les 6 pilotes (migration 071) : grandeur brute ``dni``, source
``cams_radiation``, granularite ``mensuel``, methode ``modele_satellitaire``, **confiance
'B' hardcodee** (patron brute-ingestion mirror 071, pas de derivation). Le dataset CAMS
demarre en **fevrier 2004** -> fenetre 2004-02 a 2020-12 = **203 mois/serie**.

Pattern NE-OFFLINE (mirror CAMS densification recente, migration 089) : la migration lit le
seed committe SEPARE des 28 communes (le seed climato 6-pilotes ``cams_radiation_seed_data``
reste intact, ZERO retrofit ; la migration 071 immuable itere tout son seed). **Aucun reseau
au runtime** (la capture ADS est faite une fois hors-CI par le preparer, discipline seed-offline).

Perimetre : 28 communes x 1 grandeur (DNI climato) = **28 series** ; 203 mois ->
**5 684 mesures** (28 x 203, jeu CAMS fige). Enumeration DATA-DRIVEN depuis la base
(localites ayant le CAMS DNI recent 2021-2023 ET sans CAMS DNI climato 2004-2020), garde
``len != 28``.

BRUTE SEULEMENT (anti-scope-creep) : aucun ecart calcule ici. L'ecart DNI climato
(``ecart_relatif_dni_cams`` 2004-2020) est une grandeur calculee SEPAREE (migration 072 pour
les pilotes ; un lot parite-ecart distinct si jamais voulu). L'atlas utilise l'ecart recent
2021-2023 (migration 091), pas ce climato. Ce lot pose seulement le substrat brut.

Caveat conserve : CAMS DNI all-sky sur-estime le DNI decompose (+28 %), signal de
reference d'ecart, pas une mesure primaire. Attribution CC-BY Copernicus/CAMS.

Bornes : 28 communes seulement ; les 6 pilotes gardent leur climato (071 immuable, zero
retrofit). Recent 2021-2023 (089) inchange.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date
from typing import Any

import sqlalchemy as sa
from alembic import op

from kuma_data_core.db.seeds.cams_radiation_2004_2020_densification_seed_data import (
    CAMS_DNI_MENSUEL_2004_2020_DENSIFICATION_SEED,
)

# revision identifiers, used by Alembic.
revision: str = "095"
down_revision: str | Sequence[str] | None = "094"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# === Constantes (mirror 071 climato) =======================================
_GRANDEUR = "dni"
_SOURCE_CODE = "cams_radiation"
_AN_DEBUT, _AN_FIN = 2004, 2020
_PERIODE_DEBUT = date(2004, 2, 1)  # debut reel du dataset CAMS (fevrier 2004)
_PERIODE_FIN = date(2020, 12, 31)
_GRANULARITE = "mensuel"
_METHODE_COLLECTE = "modele_satellitaire"
_DATASET_URL = "https://ads.atmosphere.copernicus.eu/datasets/cams-solar-radiation-timeseries"

_YM_DEBUT = _AN_DEBUT * 100 + 2  # 200402, premiere date attendue <= ce seuil
_YM_FIN = _AN_FIN * 100 + 12  # 202012, derniere date attendue >= ce seuil
_MOIS_FENETRE = 203  # fev 2004 -> dec 2020
_CAP_MESURES = 28 * _MOIS_FENETRE  # 5 684, garde couverture (depassement = bug)

_COMMENTAIRE_TEMPLATE = (
    "Serie CAMS Radiation DNI all-sky climato mensuel 2004-2020, {ville} (chef-lieu de "
    "prefecture), Guinee. DNI direct normal aerosol-corrige (BNI, methode Heliosat-4), ciel "
    "reel (all-sky), levier Harmattan. Conversion Wh/m2/mois -> kWh/m2/jour. Fenetre "
    "2004-02 -> 2020-12 (debut reel du dataset). Densification parite Groupe B lot 2 (meme "
    "traitement que les 6 pilotes). Caveat D-71 : CAMS DNI all-sky sur-estime le DNI decompose "
    "(+28 %), signal de reference d'ecart, pas une mesure primaire. Niveau de confiance B. "
    "Attribution : Generated using Copernicus Atmosphere Monitoring Service Information 2026 "
    "(licence CC-BY, DOI 10.24381/5cab0912)."
)


def _code_serie(commune_code: str) -> str:
    """Convention naming : ``<commune>_dni_cams_2004_2020``."""
    return f"{commune_code}_{_GRANDEUR}_cams_{_AN_DEBUT}_{_AN_FIN}"


def _points_climato(bind: sa.engine.Connection) -> list[tuple[int, str, str]]:
    """Enumeration data-driven des 28 communes : CAMS DNI recent 2021-2023 (089) PRESENT
    ET CAMS DNI climato 2004-2020 ABSENT. Exclut les pilotes (ils ont deja le climato 071)."""
    rows = bind.execute(
        sa.text(
            """
            SELECT l.id, l.code, l.nom FROM localites l
            WHERE EXISTS (
                SELECT 1 FROM series_metadonnees sm JOIN sources s ON s.id = sm.source_id
                WHERE sm.localite_id = l.id AND s.code = 'cams_radiation'
                  AND sm.grandeur_code = 'dni' AND sm.granularite = 'mensuel'
                  AND sm.periode_debut = '2021-01-01')
              AND NOT EXISTS (
                SELECT 1 FROM series_metadonnees sm JOIN sources s ON s.id = sm.source_id
                WHERE sm.localite_id = l.id AND s.code = 'cams_radiation'
                  AND sm.grandeur_code = 'dni' AND sm.granularite = 'mensuel'
                  AND sm.periode_debut = '2004-02-01')
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
        raise RuntimeError(f"Migration 095 : source {_SOURCE_CODE!r} introuvable (migration 070).")
    grandeur_ok = bind.execute(
        sa.text("SELECT 1 FROM grandeurs_referentiel WHERE code = :c AND actif = TRUE"),
        {"c": _GRANDEUR},
    ).scalar_one_or_none()
    if grandeur_ok is None:
        raise RuntimeError(f"Migration 095 : grandeur {_GRANDEUR!r} introuvable/inactive.")

    # === 2. Enumeration data-driven des 28 (garde len != 28) =================
    points = _points_climato(bind)
    if len(points) != 28:
        raise RuntimeError(f"Migration 095 : attendu 28 communes, enumere {len(points)}.")
    localite_id_par_code = {code: lid for lid, code, _ in points}
    nom_par_code = {code: nom for _, code, nom in points}
    codes_communes = set(localite_id_par_code)

    # === 3. Gardes de couverture du seed =====================================
    seed_codes = {r["localite_code"] for r in CAMS_DNI_MENSUEL_2004_2020_DENSIFICATION_SEED}
    hors_perimetre = seed_codes - codes_communes
    if hors_perimetre:
        raise RuntimeError(
            f"Migration 095 : seed densification contient des localites hors perimetre "
            f"({sorted(hors_perimetre)}). Re-generer (2004 2020 --densification)."
        )
    manquantes = codes_communes - seed_codes
    if manquantes:
        raise RuntimeError(
            f"Migration 095 : communes absentes du seed ({sorted(manquantes)}). Capture incomplete."
        )
    if len(CAMS_DNI_MENSUEL_2004_2020_DENSIFICATION_SEED) > _CAP_MESURES:
        raise RuntimeError(
            f"Migration 095 : {len(CAMS_DNI_MENSUEL_2004_2020_DENSIFICATION_SEED)} mesures > cap "
            f"{_CAP_MESURES} (28 x {_MOIS_FENETRE}). Seed anormal."
        )
    bornes: dict[str, tuple[int, int]] = {}
    for r in CAMS_DNI_MENSUEL_2004_2020_DENSIFICATION_SEED:
        ym = int(r["annee"]) * 100 + int(r["mois"])
        if r["localite_code"] in bornes:
            lo, hi = bornes[r["localite_code"]]
            bornes[r["localite_code"]] = (min(lo, ym), max(hi, ym))
        else:
            bornes[r["localite_code"]] = (ym, ym)
    for code in codes_communes:
        lo, hi = bornes[code]
        if lo > _YM_DEBUT or hi < _YM_FIN:
            raise RuntimeError(
                f"Migration 095 : {code} couverture incomplete ({lo}..{hi}), attendu "
                f"<= {_YM_DEBUT} .. >= {_YM_FIN}."
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
            "libelle": f"DNI CAMS Radiation climato mensuel {nom_par_code[code]} 2004-2020",
            "localite_id": localite_id_par_code[code],
            "grandeur_code": _GRANDEUR,
            "source_id": int(source_id),
            "periode_debut": _PERIODE_DEBUT,
            "periode_fin": _PERIODE_FIN,
            "granularite": _GRANULARITE,
            "methode_collecte": _METHODE_COLLECTE,
            "methode_collecte_doc": _DATASET_URL,
            "commentaire_editorial": _COMMENTAIRE_TEMPLATE.format(ville=nom_par_code[code]),
            "url_documentation": _DATASET_URL,
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

    # === 5. Mesures depuis le seed densification (hardcode B, mirror 071) =====
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
        for r in CAMS_DNI_MENSUEL_2004_2020_DENSIFICATION_SEED
    ]
    op.bulk_insert(mensuelles_table, lignes_mensuelles)

    op.execute(
        f"-- Migration 095 : 28 series CAMS Radiation DNI climato 2004-2020 (densification "
        f"parite B lot 2) + {len(lignes_mensuelles)} mesures mensuelles (offline, seed densif)."
    )


def downgrade() -> None:
    codes_series = [
        _code_serie(r["localite_code"]) for r in CAMS_DNI_MENSUEL_2004_2020_DENSIFICATION_SEED
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
