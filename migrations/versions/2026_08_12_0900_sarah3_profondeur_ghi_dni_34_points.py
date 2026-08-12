"""sarah3_profondeur_ghi_dni_34_points

Revision ID: 121
Revises: 120
Create Date: 2026-08-12 09:00:00

Chantier profondeur maximale par source, volet SARAH-3 : la source n'etait
exploitee que sur 36 mois (GHI 2021-2023). Ce lot pose la **pleine profondeur
servie par l'API PVGIS** (plafond ``endyear=2023``, dette D-38 pour
2024-2025) : **GHI et DNI mensuels 2005-2023** aux **34 points**, soit
**68 series** et **15 504 mesures** (228 mois par serie, jeu fige gapless).

Le DNI SARAH-3 (champ ``Hb(n)_m`` de MRcalc, jamais demande auparavant) est
le **troisieme direct mensuel** de la base, face a NASA POWER et CAMS : la
grandeur la plus disputee gagne une troisieme voix pour l'incertitude
inter-source. BRUTE SEULEMENT : aucun ecart calcule ici.

La serie GHI 2021-2023 existante (041 pilotes, 088 communes, reference de
l'atlas et de l'ecart NASA vs SARAH-3) n'est pas touchee ; la serie longue
2005-2023 est un produit distinct, chevauchement 2021-2023 assume (meme
precedent que les normales NASA face aux series longues).

Pattern NE-OFFLINE : seed committe ``sarah3_profondeur_seed_data`` (capture
PVGIS du 2026-08-12 par ``scripts/preparer_seed_sarah3_profondeur.py``,
conversion kWh/m2/mois -> kWh/m2/jour par jours reels du mois), aucun reseau
au runtime. Confiance 'B' hardcodee, ``note_publique`` a l'insertion.
Exception Conakry : prefixe de code ``gin_conakry`` (miroir des series
SARAH-3 existantes).
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date
from typing import Any

import sqlalchemy as sa
from alembic import op

from kuma_data_core.db.seeds.sarah3_profondeur_seed_data import SARAH3_PROFONDEUR_SEED

# revision identifiers, used by Alembic.
revision: str = "121"
down_revision: str | Sequence[str] | None = "120"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


_SOURCE_CODE = "sarah3_monthly"
_GRANULARITE = "mensuel"
_METHODE_COLLECTE = "modele_satellitaire"
_DOC_URL = "https://joint-research-centre.ec.europa.eu/photovoltaic-geographical-information-system-pvgis_en"
_NB_POINTS = 34
_GRANDEURS = ("ghi", "dni")
_PERIODE_DEBUT = date(2005, 1, 1)
_PERIODE_FIN = date(2023, 12, 31)
_MOIS_PAR_SERIE = 228
_TOTAL_ATTENDU = _NB_POINTS * len(_GRANDEURS) * _MOIS_PAR_SERIE  # 15 504

_LIBELLES = {"ghi": "GHI", "dni": "DNI"}
_NOTE_DESCRIPTIFS = {
    "ghi": "Irradiation solaire globale recue sur un plan horizontal (GHI)",
    "dni": "Irradiation solaire directe recue face au soleil (DNI)",
}
_NOTE_CORPS = (
    "Donnees issues du jeu satellitaire SARAH-3 du CM SAF (EUMETSAT), construit "
    "sur les satellites geostationnaires Meteosat, utilise comme source de "
    "recoupement pour l'irradiation."
)
_NOTE_CONF_B = (
    "Niveau de confiance B : donnee de modele, non validee par une mesure au sol a ce jour."
)

_COMMENTAIRE_TEMPLATE = (
    "Serie SARAH-3 {grandeur_upper} mensuel 2005-2023, {ville}, Guinee. Endpoint PVGIS "
    "MRcalc (radiation PVGIS-SARAH3), champ {champ}. Conversion kWh/m2/mois -> "
    "kWh/m2/jour par jours reels du mois. Chantier profondeur maximale par source "
    "(decision 2026-08-09), volet SARAH-3 : pleine profondeur servie par l'API "
    "(plafond endyear=2023, dette D-38 pour 2024-2025). Serie longue distincte de la "
    "serie 2021-2023 (reference d'atlas), chevauchement assume. Seed NE-OFFLINE "
    "sarah3_profondeur_seed_data (capture 2026-08-12), aucun reseau au runtime. "
    "Confiance B (modele satellitaire)."
)
_CHAMPS = {"ghi": "H(h)_m", "dni": "Hb(n)_m"}


def _prefixe_serie(localite_code: str) -> str:
    """Prefixe du code de serie ; exception Conakry (miroir 041/088)."""
    return "gin_conakry" if localite_code == "gin_conakry_kaloum" else localite_code


def _code_serie(localite_code: str, grandeur: str) -> str:
    return f"{_prefixe_serie(localite_code)}_{grandeur}_sarah3_2005_2023"


def _note_publique(grandeur: str, ville: str) -> str:
    return (
        f"{_NOTE_DESCRIPTIFS[grandeur]}, en kWh/m2 par jour (moyenne journaliere du "
        f"mois). Serie mensuelle longue 2005-2023, {ville}, Guinee. {_NOTE_CORPS} "
        f"{_NOTE_CONF_B}"
    )


def _points_cibles(bind: sa.engine.Connection) -> list[tuple[int, str, str]]:
    """34 points : localites ayant la serie SARAH-3 GHI mensuelle 2021-2023."""
    rows = bind.execute(
        sa.text(
            """
            SELECT l.id, l.code, l.nom FROM localites l
            WHERE EXISTS (
                SELECT 1 FROM series_metadonnees sm JOIN sources s ON s.id = sm.source_id
                WHERE sm.localite_id = l.id AND s.code = 'sarah3_monthly'
                  AND sm.grandeur_code = 'ghi' AND sm.granularite = 'mensuel'
                  AND sm.periode_debut = '2021-01-01')
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
        raise RuntimeError(f"Migration 121 : source {_SOURCE_CODE!r} introuvable (migration 041).")
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
            f"Migration 121 : grandeurs manquantes : {set(_GRANDEURS) - grandeurs_ok}."
        )

    points = _points_cibles(bind)
    if len(points) != _NB_POINTS:
        raise RuntimeError(f"Migration 121 : attendu {_NB_POINTS} points, enumere {len(points)}.")
    localite_id_par_code = {code: lid for lid, code, _ in points}
    nom_par_code = {code: nom for _, code, nom in points}
    codes_cibles = set(localite_id_par_code)

    seed_codes = {r["localite_code"] for r in SARAH3_PROFONDEUR_SEED}
    if seed_codes != codes_cibles:
        raise RuntimeError(
            f"Migration 121 : perimetre du seed errone (hors : "
            f"{sorted(seed_codes - codes_cibles)}, manquants : {sorted(codes_cibles - seed_codes)})."
        )
    if len(SARAH3_PROFONDEUR_SEED) != _TOTAL_ATTENDU:
        raise RuntimeError(
            f"Migration 121 : {len(SARAH3_PROFONDEUR_SEED)} mesures au seed, "
            f"attendu {_TOTAL_ATTENDU}."
        )
    comptes: dict[tuple[str, str], int] = {}
    for r in SARAH3_PROFONDEUR_SEED:
        if r["grandeur_code"] not in _GRANDEURS:
            raise RuntimeError(f"Migration 121 : grandeur inattendue {r['grandeur_code']!r}.")
        if not (2005 <= int(r["annee"]) <= 2023):
            raise RuntimeError(f"Migration 121 : annee hors fenetre : {r['annee']}.")
        cle = (r["localite_code"], r["grandeur_code"])
        comptes[cle] = comptes.get(cle, 0) + 1
    for code in sorted(codes_cibles):
        for grandeur in _GRANDEURS:
            if comptes.get((code, grandeur), 0) != _MOIS_PAR_SERIE:
                raise RuntimeError(
                    f"Migration 121 : {code}/{grandeur} : {comptes.get((code, grandeur), 0)} "
                    f"mois au seed, attendu {_MOIS_PAR_SERIE}."
                )

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
            "libelle": f"{_LIBELLES[grandeur]} SARAH-3 mensuel serie longue {nom_par_code[code]} 2005-2023",
            "localite_id": localite_id_par_code[code],
            "grandeur_code": grandeur,
            "source_id": int(source_id),
            "periode_debut": _PERIODE_DEBUT,
            "periode_fin": _PERIODE_FIN,
            "granularite": _GRANULARITE,
            "methode_collecte": _METHODE_COLLECTE,
            "methode_collecte_doc": _DOC_URL,
            "commentaire_editorial": _COMMENTAIRE_TEMPLATE.format(
                grandeur_upper=grandeur.upper(),
                champ=_CHAMPS[grandeur],
                ville=nom_par_code[code],
            ),
            "note_publique": _note_publique(grandeur, nom_par_code[code]),
            "url_documentation": _DOC_URL,
        }
        for code in sorted(codes_cibles)
        for grandeur in _GRANDEURS
    ]
    assert len(lignes_series) == 68, f"Attendu 68 series, obtenu {len(lignes_series)}"
    op.bulk_insert(series_table, lignes_series)

    serie_id_par_cle: dict[tuple[str, str], int] = {}
    codes_vers_cle = {
        _code_serie(code, grandeur): (code, grandeur)
        for code in codes_cibles
        for grandeur in _GRANDEURS
    }
    for r in bind.execute(
        sa.text("SELECT code, id FROM series_metadonnees WHERE code = ANY(:codes)"),
        {"codes": list(codes_vers_cle)},
    ).all():
        serie_id_par_cle[codes_vers_cle[str(r.code)]] = int(r.id)
    if len(serie_id_par_cle) != 68:
        raise RuntimeError(f"Migration 121 : {len(serie_id_par_cle)} series resolues (attendu 68).")

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
            "serie_id": serie_id_par_cle[(r["localite_code"], r["grandeur_code"])],
            "annee": r["annee"],
            "mois": r["mois"],
            "valeur": r["valeur"],
            "niveau_confiance_derive": "B",
        }
        for r in SARAH3_PROFONDEUR_SEED
    ]
    op.bulk_insert(mensuelles_table, lignes_mensuelles)

    op.execute(
        f"-- Migration 121 : 68 series GHI/DNI SARAH-3 mensuel 2005-2023 (34 points) + "
        f"{len(lignes_mensuelles)} mesures (offline, seed profondeur)."
    )


def downgrade() -> None:
    codes = sorted(
        {_code_serie(r["localite_code"], r["grandeur_code"]) for r in SARAH3_PROFONDEUR_SEED}
    )
    op.execute(
        sa.text(
            "DELETE FROM mesures_ressource_mensuelles WHERE serie_id IN "
            "(SELECT id FROM series_metadonnees WHERE code = ANY(:codes))"
        ).bindparams(sa.bindparam("codes", value=codes))
    )
    op.execute(
        sa.text("DELETE FROM series_metadonnees WHERE code = ANY(:codes)").bindparams(
            sa.bindparam("codes", value=codes)
        )
    )
