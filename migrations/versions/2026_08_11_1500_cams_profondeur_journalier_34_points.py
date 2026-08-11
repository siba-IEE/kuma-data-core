"""cams_profondeur_journalier_34_points

Revision ID: 120
Revises: 119
Create Date: 2026-08-11 15:00:00

Chantier profondeur maximale par source, volet CAMS, granularite journaliere :
le pas 1day du service CAMS Radiation n'etait exploite nulle part. Ce lot pose
**ghi, dhi et dni journaliers** aux **34 points**, pleine profondeur
2004-02-01 -> 2025-12-31 : **102 series** (34 x 3) et **815 796 mesures**
(7 998 jours par serie, uniformes sur les 34 points ; le service CAMS compte
7 jours d'interruption sur la fenetre, identiques partout, sentinelles
filtrees a la capture).

Le DNI journalier CAMS devient le deuxieme direct journalier de la base (face
a NASA POWER) : produit aerosol-corrige, utile au diagnostic Harmattan au pas
journalier. BRUTE SEULEMENT : aucun ecart journalier calcule ici.

Pattern NE-OFFLINE : seeds committes ``cams_profondeur_journalier_seed_data_*``
(capture ADS du 2026-08-11, un compagnon par ville, conversion Wh/m2/jour ->
kWh/m2/jour), consommes en streaming deux passes (gardes puis insertion par
lots de 20 000). Confiance 'B' hardcodee, ``note_publique`` a l'insertion.
Caveat D-71 reconduit. Attribution CC-BY Copernicus/CAMS.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date
from typing import Any

import sqlalchemy as sa
from alembic import op

from kuma_data_core.db.seeds.cams_profondeur_journalier_seed_data import (
    iter_blocs_cams_journalier,
)

# revision identifiers, used by Alembic.
revision: str = "120"
down_revision: str | Sequence[str] | None = "119"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


_SOURCE_CODE = "cams_radiation"
_GRANULARITE = "journalier"
_METHODE_COLLECTE = "modele_satellitaire"
_DATASET_URL = "https://ads.atmosphere.copernicus.eu/datasets/cams-solar-radiation-timeseries"
_NB_POINTS = 34
_GRANDEURS = ("ghi", "dhi", "dni")
_PERIODE_DEBUT = date(2004, 2, 1)
_PERIODE_FIN = date(2025, 12, 31)
_JOURS_PAR_SERIE = 7_998
_TOTAL_ATTENDU = _NB_POINTS * len(_GRANDEURS) * _JOURS_PAR_SERIE  # 815 796
_TAILLE_LOT_INSERT = 20_000

_LIBELLES: dict[str, str] = {"ghi": "GHI", "dhi": "DHI", "dni": "DNI"}
_NOTE_DESCRIPTIFS: dict[str, str] = {
    "ghi": "Irradiation solaire globale recue sur un plan horizontal (GHI)",
    "dhi": "Part diffuse de l'irradiation solaire sur plan horizontal (DHI)",
    "dni": "Irradiation solaire directe recue face au soleil (DNI)",
}
_NOTE_CORPS = (
    "Donnees issues du service Copernicus CAMS Radiation (methode Heliosat-4, "
    "prise en compte des aerosols), utilisees en recoupement des autres sources "
    "d'irradiation de la base."
)
_NOTE_CONF_B = (
    "Niveau de confiance B : donnee de modele, non validee par une mesure au sol a ce jour."
)
_NOTE_LACUNES = " Sept jours d'interruption du service sur la fenetre sont absents de la serie."

_COMMENTAIRE_TEMPLATE = (
    "Serie CAMS Radiation {grandeur_upper} all-sky journalier 2004-2025, {ville}, Guinee. "
    "Methode Heliosat-4, aerosols pris en compte. Conversion Wh/m2/jour -> kWh/m2/jour. "
    "Chantier profondeur maximale par source (decision 2026-08-09), volet CAMS : ouverture "
    "du pas journalier du service (aucune granularite journaliere CAMS auparavant). Seed "
    "NE-OFFLINE cams_profondeur_journalier_seed_data (capture ADS 2026-08-11), aucun "
    "reseau au runtime. 7 998 jours par serie (7 jours d'interruption de service sur la "
    "fenetre, uniformes aux 34 points). Caveat D-71 reconduit : produit aerosol-corrige, "
    "reference d'ecart, pas une mesure primaire. Confiance B. Attribution : Generated "
    "using Copernicus Atmosphere Monitoring Service Information 2026 (licence CC-BY)."
)


def _code_serie(localite_code: str, grandeur: str) -> str:
    """``<loc>_<g>_cams_journalier_2004_2025`` : segment distinct du mensuel."""
    return f"{localite_code}_{grandeur}_cams_journalier_2004_2025"


def _note_publique(grandeur: str, ville: str) -> str:
    return (
        f"{_NOTE_DESCRIPTIFS[grandeur]}, en kWh/m2 par jour. Serie journaliere "
        f"2004-2025, {ville}, Guinee. {_NOTE_CORPS} {_NOTE_CONF_B}{_NOTE_LACUNES}"
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
        raise RuntimeError(f"Migration 120 : source {_SOURCE_CODE!r} introuvable (migration 070).")
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
            f"Migration 120 : grandeurs manquantes : {set(_GRANDEURS) - grandeurs_ok}."
        )

    points = _points_cibles(bind)
    if len(points) != _NB_POINTS:
        raise RuntimeError(f"Migration 120 : attendu {_NB_POINTS} points, enumere {len(points)}.")
    localite_id_par_code = {code: lid for lid, code, _ in points}
    nom_par_code = {code: nom for _, code, nom in points}
    codes_cibles = set(localite_id_par_code)

    # === Gardes (passe 1, streaming complet) ==================================
    comptes: dict[tuple[str, str], int] = {}
    total_seed = 0
    for bloc in iter_blocs_cams_journalier():
        loc, grandeur = bloc["localite_code"], bloc["grandeur_code"]
        if loc not in codes_cibles:
            raise RuntimeError(f"Migration 120 : localite hors perimetre au seed : {loc!r}.")
        if grandeur not in _GRANDEURS:
            raise RuntimeError(f"Migration 120 : grandeur inattendue au seed : {grandeur!r}.")
        valeurs: dict[str, float] = bloc["valeurs"]
        d_min, d_max = min(valeurs), max(valeurs)
        if date.fromisoformat(d_min) < _PERIODE_DEBUT or date.fromisoformat(d_max) > _PERIODE_FIN:
            raise RuntimeError(f"Migration 120 : {loc}/{grandeur} hors fenetre ({d_min}..{d_max}).")
        cle = (loc, grandeur)
        comptes[cle] = comptes.get(cle, 0) + len(valeurs)
        total_seed += len(valeurs)
    if total_seed != _TOTAL_ATTENDU:
        raise RuntimeError(
            f"Migration 120 : {total_seed} mesures au seed, attendu {_TOTAL_ATTENDU}."
        )
    for code in sorted(codes_cibles):
        for grandeur in _GRANDEURS:
            if comptes.get((code, grandeur), 0) != _JOURS_PAR_SERIE:
                raise RuntimeError(
                    f"Migration 120 : {code}/{grandeur} : {comptes.get((code, grandeur), 0)} "
                    f"jours au seed, attendu {_JOURS_PAR_SERIE}."
                )

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
            "code": _code_serie(code, grandeur),
            "libelle": f"{_LIBELLES[grandeur]} CAMS Radiation journalier {nom_par_code[code]} 2004-2025",
            "localite_id": localite_id_par_code[code],
            "grandeur_code": grandeur,
            "source_id": int(source_id),
            "periode_debut": _PERIODE_DEBUT,
            "periode_fin": _PERIODE_FIN,
            "granularite": _GRANULARITE,
            "methode_collecte": _METHODE_COLLECTE,
            "methode_collecte_doc": _DATASET_URL,
            "commentaire_editorial": _COMMENTAIRE_TEMPLATE.format(
                grandeur_upper=grandeur.upper(), ville=nom_par_code[code]
            ),
            "note_publique": _note_publique(grandeur, nom_par_code[code]),
            "url_documentation": _DATASET_URL,
        }
        for code in sorted(codes_cibles)
        for grandeur in _GRANDEURS
    ]
    assert len(lignes_series) == 102, f"Attendu 102 series, obtenu {len(lignes_series)}"
    op.bulk_insert(series_table, lignes_series)

    serie_id_par_code: dict[str, int] = {
        str(r.code): int(r.id)
        for r in bind.execute(
            sa.text("SELECT code, id FROM series_metadonnees WHERE code = ANY(:codes)"),
            {"codes": [ligne["code"] for ligne in lignes_series]},
        ).all()
    }

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
    for bloc in iter_blocs_cams_journalier():
        serie_id = serie_id_par_code[_code_serie(bloc["localite_code"], bloc["grandeur_code"])]
        for jour, valeur in bloc["valeurs"].items():
            tampon.append(
                {
                    "serie_id": serie_id,
                    "instant_mesure": date.fromisoformat(jour),
                    "valeur": valeur,
                    "niveau_confiance_derive": "B",
                }
            )
            if len(tampon) >= _TAILLE_LOT_INSERT:
                op.bulk_insert(mesures_table, tampon)
                total_insere += len(tampon)
                tampon = []
    if tampon:
        op.bulk_insert(mesures_table, tampon)
        total_insere += len(tampon)
    if total_insere != _TOTAL_ATTENDU:
        raise RuntimeError(
            f"Migration 120 : {total_insere} mesures inserees, attendu {_TOTAL_ATTENDU}."
        )

    op.execute(
        f"-- Migration 120 : 102 series GHI/DHI/DNI CAMS journalier (34 points, 2004-2025) "
        f"+ {total_insere} mesures (offline, seed profondeur, 7 998 jours/serie)."
    )


def downgrade() -> None:
    codes = sorted(
        {
            _code_serie(bloc["localite_code"], bloc["grandeur_code"])
            for bloc in iter_blocs_cams_journalier()
        }
    )
    op.execute(
        sa.text(
            "DELETE FROM mesures_ressource WHERE serie_id IN "
            "(SELECT id FROM series_metadonnees WHERE code = ANY(:codes))"
        ).bindparams(sa.bindparam("codes", value=codes))
    )
    op.execute(
        sa.text("DELETE FROM series_metadonnees WHERE code = ANY(:codes)").bindparams(
            sa.bindparam("codes", value=codes)
        )
    )
