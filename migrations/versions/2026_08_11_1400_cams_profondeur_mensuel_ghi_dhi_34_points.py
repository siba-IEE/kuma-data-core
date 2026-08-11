"""cams_profondeur_mensuel_ghi_dhi_34_points

Revision ID: 119
Revises: 118
Create Date: 2026-08-11 14:00:00

Chantier profondeur maximale par source, volet CAMS : le depot n'exploitait
qu'une colonne du CSV CAMS Radiation (le BNI, soit le DNI all-sky). Ce lot
ouvre le **GHI et le DHI** mensuels aux **34 points**, sur deux fenetres
miroir de l'existant DNI :

| Grandeurs | Fenetre                  | Mois/serie |
|-----------|--------------------------|------------|
| ghi, dhi  | 2004-02 -> 2020-12       | 203        |
| ghi, dhi  | 2021-01 -> 2025-12       | 60         |

Volume : 34 x 2 grandeurs x 2 fenetres = **136 series**, 17 884 mesures
(13 804 climato + 4 080 recentes, jeu fige gapless, gardes strictes). Le GHI
CAMS devient le troisieme membre du triptyque GHI (NASA, SARAH-3) pour
l'ecart inter-source ; aucun ecart calcule ici (brute seulement).

Le DNI mensuel n'est pas touche : ses fenetres existantes (climato 071/095,
recent 2021-2023 073/089 aligne sur l'atlas) restent la reference de l'ecart.
La periode recente des nouvelles series va jusqu'a 2025-12 (pas de contrainte
d'alignement SARAH-3 pour des grandeurs sans ecart calcule).

Pattern NE-OFFLINE : seed committe ``cams_profondeur_mensuel_seed_data``
(capture ADS du 2026-08-11 par ``scripts/preparer_seed_cams_profondeur.py``,
conversion Wh/m2/mois -> kWh/m2/jour), aucun reseau au runtime. Confiance 'B'
hardcodee (patron brute-ingestion 095), ``note_publique`` a l'insertion.
Caveat D-71 reconduit (produit aerosol-correcte, signal de reference).
Attribution CC-BY Copernicus/CAMS.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date
from typing import Any

import sqlalchemy as sa
from alembic import op

from kuma_data_core.db.seeds.cams_profondeur_mensuel_seed_data import (
    CAMS_PROFONDEUR_MENSUEL_SEED,
)

# revision identifiers, used by Alembic.
revision: str = "119"
down_revision: str | Sequence[str] | None = "118"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


_SOURCE_CODE = "cams_radiation"
_GRANULARITE = "mensuel"
_METHODE_COLLECTE = "modele_satellitaire"
_DATASET_URL = "https://ads.atmosphere.copernicus.eu/datasets/cams-solar-radiation-timeseries"
_NB_POINTS = 34
_GRANDEURS = ("ghi", "dhi")

# fenetre -> (periode_debut, periode_fin, ym_debut, ym_fin, mois attendus)
_FENETRES: dict[str, tuple[date, date, int, int, int]] = {
    "2004_2020": (date(2004, 2, 1), date(2020, 12, 31), 200402, 202012, 203),
    "2021_2025": (date(2021, 1, 1), date(2025, 12, 31), 202101, 202512, 60),
}
_TOTAL_ATTENDU = _NB_POINTS * len(_GRANDEURS) * sum(f[4] for f in _FENETRES.values())  # 17 884

_LIBELLES: dict[str, str] = {"ghi": "GHI", "dhi": "DHI"}
_NOTE_DESCRIPTIFS: dict[str, str] = {
    "ghi": "Irradiation solaire globale recue sur un plan horizontal (GHI)",
    "dhi": "Part diffuse de l'irradiation solaire sur plan horizontal (DHI)",
}
_NOTE_CORPS = (
    "Donnees issues du service Copernicus CAMS Radiation (methode Heliosat-4, "
    "prise en compte des aerosols), utilisees en recoupement des autres sources "
    "d'irradiation de la base."
)
_NOTE_CONF_B = (
    "Niveau de confiance B : donnee de modele, non validee par une mesure au sol a ce jour."
)

_COMMENTAIRE_TEMPLATE = (
    "Serie CAMS Radiation {grandeur_upper} all-sky mensuel {fenetre_lisible}, {ville} "
    "(chef-lieu de prefecture ou pilote), Guinee. Methode Heliosat-4, aerosols pris en "
    "compte. Conversion Wh/m2/mois -> kWh/m2/jour. Chantier profondeur maximale par "
    "source (decision 2026-08-09), volet CAMS : ouverture des colonnes GHI/DHI du CSV "
    "CAMS (seul le BNI etait exploite). Seed NE-OFFLINE cams_profondeur_mensuel_seed_data "
    "(capture ADS 2026-08-11), aucun reseau au runtime. Caveat D-71 reconduit : produit "
    "aerosol-corrige, reference d'ecart, pas une mesure primaire. Confiance B. "
    "Attribution : Generated using Copernicus Atmosphere Monitoring Service Information "
    "2026 (licence CC-BY)."
)


def _code_serie(localite_code: str, grandeur: str, fenetre: str) -> str:
    """Mirror des codes DNI existants : ``<loc>_<g>_cams_<debut>_<fin>``."""
    return f"{localite_code}_{grandeur}_cams_{fenetre}"


def _note_publique(grandeur: str, ville: str, fenetre: str) -> str:
    debut, fin = fenetre.split("_")
    return (
        f"{_NOTE_DESCRIPTIFS[grandeur]}, en kWh/m2 par jour (moyenne journaliere du "
        f"mois). Serie mensuelle {debut}-{fin}, {ville}, Guinee. {_NOTE_CORPS} "
        f"{_NOTE_CONF_B}"
    )


def _points_cibles(bind: sa.engine.Connection) -> list[tuple[int, str, str]]:
    """34 points : localites ayant le DNI CAMS mensuel climato (071 pilotes, 095 communes)."""
    rows = bind.execute(
        sa.text(
            """
            SELECT l.id, l.code, l.nom FROM localites l
            WHERE EXISTS (
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

    source_id = bind.execute(
        sa.text("SELECT id FROM sources WHERE code = :c"), {"c": _SOURCE_CODE}
    ).scalar_one_or_none()
    if source_id is None:
        raise RuntimeError(f"Migration 119 : source {_SOURCE_CODE!r} introuvable (migration 070).")
    grandeurs_ok = set(
        bind.execute(
            sa.text("SELECT code FROM grandeurs_referentiel WHERE code = ANY(:c) AND actif = TRUE"),
            {"c": list(_GRANDEURS)},
        )
        .scalars()
        .all()
    )
    if grandeurs_ok != set(_GRANDEURS):
        raise RuntimeError(
            f"Migration 119 : grandeurs manquantes : {set(_GRANDEURS) - grandeurs_ok}."
        )

    points = _points_cibles(bind)
    if len(points) != _NB_POINTS:
        raise RuntimeError(f"Migration 119 : attendu {_NB_POINTS} points, enumere {len(points)}.")
    localite_id_par_code = {code: lid for lid, code, _ in points}
    nom_par_code = {code: nom for _, code, nom in points}
    codes_cibles = set(localite_id_par_code)

    # === Gardes de couverture du seed =========================================
    seed_codes = {r["localite_code"] for r in CAMS_PROFONDEUR_MENSUEL_SEED}
    if seed_codes != codes_cibles:
        raise RuntimeError(
            f"Migration 119 : perimetre du seed errone (hors : {sorted(seed_codes - codes_cibles)}, "
            f"manquants : {sorted(codes_cibles - seed_codes)})."
        )
    if len(CAMS_PROFONDEUR_MENSUEL_SEED) != _TOTAL_ATTENDU:
        raise RuntimeError(
            f"Migration 119 : {len(CAMS_PROFONDEUR_MENSUEL_SEED)} mesures au seed, "
            f"attendu {_TOTAL_ATTENDU}."
        )
    comptes: dict[tuple[str, str, str], int] = {}
    for r in CAMS_PROFONDEUR_MENSUEL_SEED:
        if r["grandeur_code"] not in _GRANDEURS:
            raise RuntimeError(f"Migration 119 : grandeur inattendue {r['grandeur_code']!r}.")
        ym = int(r["annee"]) * 100 + int(r["mois"])
        fenetre = None
        for nom_f, (_, _, ym_lo, ym_hi, _) in _FENETRES.items():
            if ym_lo <= ym <= ym_hi:
                fenetre = nom_f
                break
        if fenetre is None:
            raise RuntimeError(f"Migration 119 : mois hors fenetres : {ym}.")
        cle = (r["localite_code"], r["grandeur_code"], fenetre)
        comptes[cle] = comptes.get(cle, 0) + 1
    for code in sorted(codes_cibles):
        for grandeur in _GRANDEURS:
            for nom_f, (_, _, _, _, nb) in _FENETRES.items():
                if comptes.get((code, grandeur, nom_f), 0) != nb:
                    raise RuntimeError(
                        f"Migration 119 : {code}/{grandeur}/{nom_f} : "
                        f"{comptes.get((code, grandeur, nom_f), 0)} mois, attendu {nb}."
                    )

    # === Series (note_publique a l'insertion) =================================
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
    lignes_series: list[dict[str, Any]] = []
    for code in sorted(codes_cibles):
        ville = nom_par_code[code]
        for grandeur in _GRANDEURS:
            for nom_f, (p_debut, p_fin, _, _, _) in _FENETRES.items():
                fenetre_lisible = nom_f.replace("_", "-")
                lignes_series.append(
                    {
                        "code": _code_serie(code, grandeur, nom_f),
                        "libelle": (
                            f"{_LIBELLES[grandeur]} CAMS Radiation mensuel {ville} "
                            f"{fenetre_lisible}"
                        ),
                        "localite_id": localite_id_par_code[code],
                        "grandeur_code": grandeur,
                        "source_id": int(source_id),
                        "periode_debut": p_debut,
                        "periode_fin": p_fin,
                        "granularite": _GRANULARITE,
                        "methode_collecte": _METHODE_COLLECTE,
                        "methode_collecte_doc": _DATASET_URL,
                        "commentaire_editorial": _COMMENTAIRE_TEMPLATE.format(
                            grandeur_upper=grandeur.upper(),
                            fenetre_lisible=fenetre_lisible,
                            ville=ville,
                        ),
                        "note_publique": _note_publique(grandeur, ville, nom_f),
                        "url_documentation": _DATASET_URL,
                    }
                )
    assert len(lignes_series) == 136, f"Attendu 136 series, obtenu {len(lignes_series)}"
    op.bulk_insert(series_table, lignes_series)

    serie_id_par_cle: dict[tuple[str, str, str], int] = {}
    for r in bind.execute(
        sa.text("SELECT code, id FROM series_metadonnees WHERE code = ANY(:codes)"),
        {"codes": [ligne["code"] for ligne in lignes_series]},
    ).all():
        loc, reste = (
            str(r.code).split("_ghi_cams_")
            if "_ghi_cams_" in str(r.code)
            else (str(r.code).split("_dhi_cams_"))
        )
        grandeur = "ghi" if "_ghi_cams_" in str(r.code) else "dhi"
        serie_id_par_cle[(loc, grandeur, reste)] = int(r.id)

    # === Mesures (hardcode B, decoupees par fenetre) ==========================
    mensuelles_table = sa.table(
        "mesures_ressource_mensuelles",
        sa.column("serie_id", sa.BigInteger),
        sa.column("annee", sa.SmallInteger),
        sa.column("mois", sa.SmallInteger),
        sa.column("valeur", sa.Float),
        sa.column("niveau_confiance_derive", sa.String),
    )
    lignes_mensuelles = []
    for r in CAMS_PROFONDEUR_MENSUEL_SEED:
        ym = int(r["annee"]) * 100 + int(r["mois"])
        nom_f = "2004_2020" if ym <= 202012 else "2021_2025"
        lignes_mensuelles.append(
            {
                "serie_id": serie_id_par_cle[(r["localite_code"], r["grandeur_code"], nom_f)],
                "annee": r["annee"],
                "mois": r["mois"],
                "valeur": r["valeur"],
                "niveau_confiance_derive": "B",
            }
        )
    op.bulk_insert(mensuelles_table, lignes_mensuelles)

    op.execute(
        f"-- Migration 119 : 136 series GHI/DHI CAMS mensuel (34 points x 2 grandeurs x "
        f"2 fenetres) + {len(lignes_mensuelles)} mesures (offline, seed profondeur)."
    )


def downgrade() -> None:
    codes = [
        f"{loc}_{g}_cams_{f}"
        for loc in {r["localite_code"] for r in CAMS_PROFONDEUR_MENSUEL_SEED}
        for g in _GRANDEURS
        for f in _FENETRES
    ]
    op.execute(
        sa.text(
            "DELETE FROM mesures_ressource_mensuelles WHERE serie_id IN "
            "(SELECT id FROM series_metadonnees WHERE code = ANY(:codes))"
        ).bindparams(sa.bindparam("codes", value=sorted(codes)))
    )
    op.execute(
        sa.text("DELETE FROM series_metadonnees WHERE code = ANY(:codes)").bindparams(
            sa.bindparam("codes", value=sorted(codes))
        )
    )
