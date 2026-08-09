"""seed_profondeur_mensuelle_nasa_34_points

Revision ID: 105
Revises: 104
Create Date: 2026-08-09 12:00:00

Chantier profondeur maximale par source (decision 2026-08-09) - premier
volet : series mensuelles longues NASA POWER aux **34 points** (6 pilotes +
28 communes chef-lieu), pleine profondeur historique, 10 grandeurs.

Le parc mensuel NASA existant est constitue de normales climato a fenetres
figees (041/050 pilotes, 087 communes : 1991-2020 et 2001-2020). Ce lot pose
des **series longues independantes**, sans fenetre de normale, jusqu'au
plancher reel de la source (sonde API du 2026-08-09) :

| Grandeurs                                       | Fenetre        | Mois/serie |
|-------------------------------------------------|----------------|------------|
| t2m, rh2m, vent_2m, vent_10m, precipitation     | 1981-01/2025-12| 540        |
| ghi, dhi                                        | 1984-01/2025-12| 504        |
| dni, kt, albedo_surface                         | 2001-01/2025-12| 300        |

``precipitation`` mensuelle est inedite (la grandeur n'existait qu'en
journalier, 080/094). Volume : 34 x 10 = **340 series**, 34 x 4 608 =
**156 672 mesures** attendues dans ``mesures_ressource_mensuelles``
(jeu fige, comptes exacts, gardes dures).

Pattern NE-OFFLINE (mirror 089/094-098) : la migration lit le seed committe
``nasa_power_monthly_profondeur_seed_data`` (capture live du 2026-08-09 par
``scripts/preparer_seed_nasa_monthly_profondeur.py``, sentinelles -999 et
cles annuelles YYYY13 deja filtrees), **aucun reseau au runtime**. Namespace
SEPARE du seed climato ``nasa_power_monthly_seed_data`` (payloads 1991-2020
des migrations immuables 041/050/087) : zero retouche du snapshot existant,
zero retrofit des series climato.

Enumeration DATA-DRIVEN des 34 points (localites ayant une serie NASA POWER
``ghi`` journaliere), garde ``len != 34``. Confiance **'B' hardcodee**
(patron brute-ingestion, mirror 095/071). Statut ``brut`` (defaut serveur).
``note_publique`` renseignee a l'insertion (doctrine 099).

BRUTE SEULEMENT (anti-scope-creep) : aucun ecart ni grandeur calculee ici ;
les normales climato existantes et leurs consommateurs (P50/P90, rangs)
restent strictement inchanges.

Prerequis : migration 104 (CHECK ``annee`` elargi a 1981).
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date
from typing import Any

import sqlalchemy as sa
from alembic import op

from kuma_data_core.db.seeds.nasa_power_monthly_profondeur_seed_data import (
    NASA_MONTHLY_PROFONDEUR_SEED,
)

# revision identifiers, used by Alembic.
revision: str = "105"
down_revision: str | Sequence[str] | None = "104"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# === Constantes ============================================================
_SOURCE_CODE = "nasa_power"
_GRANULARITE = "mensuel"
_METHODE_COLLECTE = "modele_satellitaire"
_METHODE_COLLECTE_DOC = "https://power.larc.nasa.gov/docs/methodology/"
_URL_DOCUMENTATION = "https://power.larc.nasa.gov/"
_ANNEE_FIN = 2025
_NB_POINTS = 34

# Grandeur -> (annee_debut, mois attendus par serie). Fenetres decouvertes par
# la sonde API du 2026-08-09 et verifiees uniformes sur les 34 points par le
# preparateur (garde d'uniformite) ; figees ici avec gardes dures.
_FENETRES: dict[str, tuple[int, int]] = {
    "t2m": (1981, 540),
    "rh2m": (1981, 540),
    "vent_2m": (1981, 540),
    "vent_10m": (1981, 540),
    "precipitation": (1981, 540),
    "ghi": (1984, 504),
    "dhi": (1984, 504),
    "dni": (2001, 300),
    "kt": (2001, 300),
    "albedo_surface": (2001, 300),
}
_TOTAL_ATTENDU = _NB_POINTS * sum(nb for _, nb in _FENETRES.values())

_LIBELLES: dict[str, str] = {
    "ghi": "GHI mensuel serie longue",
    "dhi": "DHI mensuel serie longue",
    "dni": "DNI mensuel serie longue",
    "kt": "Indice de clarte mensuel serie longue",
    "albedo_surface": "Albedo de surface mensuel serie longue",
    "t2m": "Temperature 2m mensuelle serie longue",
    "rh2m": "Humidite relative 2m mensuelle serie longue",
    "vent_2m": "Vent 2m mensuel serie longue",
    "vent_10m": "Vent 10m mensuel serie longue",
    "precipitation": "Precipitations mensuelles serie longue",
}

# --- note_publique : charpente du corpus valide (quoi/ou -> source -> confiance
# -> limites), sans vocabulaire de chantier interne. -----------------------
_NOTE_DESCRIPTIFS: dict[str, str] = {
    "ghi": (
        "Irradiation solaire globale recue sur un plan horizontal (GHI), en kWh/m2 "
        "par jour (moyenne journaliere du mois)"
    ),
    "dhi": (
        "Part diffuse de l'irradiation solaire sur plan horizontal (DHI), en kWh/m2 "
        "par jour (moyenne journaliere du mois)"
    ),
    "dni": (
        "Irradiation solaire directe recue face au soleil (DNI), en kWh/m2 par jour "
        "(moyenne journaliere du mois)"
    ),
    "kt": (
        "Indice de clarte du ciel : rapport entre le rayonnement recu au sol et le "
        "rayonnement hors atmosphere (sans unite, entre 0 et 1)"
    ),
    "albedo_surface": (
        "Albedo de surface : part du rayonnement solaire reflechie par le sol "
        "(sans unite, entre 0 et 1)"
    ),
    "t2m": "Temperature moyenne de l'air a 2 metres du sol, en degres Celsius",
    "rh2m": "Humidite relative moyenne de l'air a 2 metres du sol, en pourcentage",
    "vent_2m": "Vitesse moyenne du vent a 2 metres du sol, en metres par seconde",
    "vent_10m": "Vitesse moyenne du vent a 10 metres du sol, en metres par seconde",
    "precipitation": (
        "Precipitations totales corrigees, en millimetres par jour (moyenne journaliere du mois)"
    ),
}
_NOTE_CORPS_NASA = (
    "Donnees ingerees depuis NASA POWER, le service de donnees solaires et "
    "meteorologiques de la NASA (rayonnement du modele satellitaire CERES SYN1deg, "
    "variables meteo de la reanalyse MERRA-2)."
)
_NOTE_CONF_B = (
    "Niveau de confiance B : donnee de modele, non validee par une mesure au sol a ce jour."
)
_NOTE_LIMITES_PALIER: dict[int, str] = {
    1981: "",
    1984: (
        " Les premieres annees (avant 2001) reposent sur des jeux satellitaires plus "
        "anciens, moins bien contraints que la periode recente."
    ),
    2001: " Serie disponible a partir de 2001, debut des observations du capteur CERES.",
}
_NOTE_LIMITE_LONGUE = (
    " L'homogeneite d'une serie longue repose sur l'harmonisation interne du "
    "producteur, documentee comme limite connue."
)

_COMMENTAIRE_TEMPLATE = (
    "Serie mensuelle longue {grandeur_upper} {annee_debut}-{annee_fin}, {ville}, Guinee. "
    "Chantier profondeur maximale par source (decision 2026-08-09), volet NASA mensuel. "
    "Palier de profondeur {annee_debut} etabli par sonde API du 2026-08-09. Seed "
    "NE-OFFLINE nasa_power_monthly_profondeur_seed_data (capture live 2026-08-09), "
    "aucun reseau au runtime migration. Series independantes des normales climato "
    "041/050/087 (fenetres 1991/2001-2020), zero retrofit. Confiance B (modele "
    "satellitaire)."
)


def _prefixe_serie(localite_code: str) -> str:
    """Prefixe du code de serie ; exception Conakry (cf. 01-naming.md)."""
    return "gin_conakry" if localite_code == "gin_conakry_kaloum" else localite_code


def _code_serie(localite_code: str, grandeur_code: str) -> str:
    """Convention de nommage : ``<prefixe>_<grandeur>_nasa_power_mensuel_<debut>_<fin>``.

    Segment ``nasa_power_mensuel`` : distinct de ``power_<fenetre>`` (normales
    climato 041/050/087) et de ``nasa_power_<fenetre>`` (journalier), et sans
    collision avec les motifs de comptage ``%power_1991%`` / ``%power_2001%``.
    """
    annee_debut, _ = _FENETRES[grandeur_code]
    return (
        f"{_prefixe_serie(localite_code)}_{grandeur_code}"
        f"_nasa_power_mensuel_{annee_debut}_{_ANNEE_FIN}"
    )


def _note_publique(grandeur_code: str, ville: str) -> str:
    annee_debut, _ = _FENETRES[grandeur_code]
    return (
        f"{_NOTE_DESCRIPTIFS[grandeur_code]}. Serie mensuelle longue "
        f"{annee_debut}-{_ANNEE_FIN}, {ville}, Guinee. {_NOTE_CORPS_NASA} "
        f"{_NOTE_CONF_B}{_NOTE_LIMITES_PALIER[annee_debut]}{_NOTE_LIMITE_LONGUE}"
    )


def _points_cibles(bind: sa.engine.Connection) -> list[tuple[int, str, str]]:
    """Enumeration data-driven des 34 points : localites ayant une serie NASA
    POWER ghi journaliere (6 pilotes via 018+, 28 communes via 086)."""
    rows = bind.execute(
        sa.text(
            """
            SELECT l.id, l.code, l.nom FROM localites l
            WHERE EXISTS (
                SELECT 1 FROM series_metadonnees sm JOIN sources s ON s.id = sm.source_id
                WHERE sm.localite_id = l.id AND s.code = 'nasa_power'
                  AND sm.grandeur_code = 'ghi' AND sm.granularite = 'journalier')
            ORDER BY l.code
            """
        )
    ).all()
    return [(int(r.id), str(r.code), str(r.nom)) for r in rows]


def upgrade() -> None:
    bind = op.get_bind()

    # === 1. Source + 10 grandeurs (deja declarees, on verifie seulement) =====
    source_id = bind.execute(
        sa.text("SELECT id FROM sources WHERE code = :c"), {"c": _SOURCE_CODE}
    ).scalar_one_or_none()
    if source_id is None:
        raise RuntimeError(f"Migration 102 : source {_SOURCE_CODE!r} introuvable (migration 012).")
    grandeurs_trouvees = set(
        bind.execute(
            sa.text(
                "SELECT code FROM grandeurs_referentiel WHERE code = ANY(:codes) AND actif = TRUE"
            ),
            {"codes": list(_FENETRES)},
        )
        .scalars()
        .all()
    )
    grandeurs_manquantes = set(_FENETRES) - grandeurs_trouvees
    if grandeurs_manquantes:
        raise RuntimeError(
            f"Migration 102 : grandeur(s) introuvable(s)/inactive(s) : "
            f"{sorted(grandeurs_manquantes)}."
        )

    # === 2. Enumeration data-driven des 34 points (garde len != 34) ==========
    points = _points_cibles(bind)
    if len(points) != _NB_POINTS:
        raise RuntimeError(f"Migration 102 : attendu {_NB_POINTS} points, enumere {len(points)}.")
    localite_id_par_code = {code: lid for lid, code, _ in points}
    nom_par_code = {code: nom for _, code, nom in points}
    codes_cibles = set(localite_id_par_code)

    # === 3. Gardes de couverture du seed ======================================
    seed_codes = {r["localite_code"] for r in NASA_MONTHLY_PROFONDEUR_SEED}
    hors_perimetre = seed_codes - codes_cibles
    if hors_perimetre:
        raise RuntimeError(
            f"Migration 102 : seed profondeur contient des localites hors perimetre "
            f"({sorted(hors_perimetre)}). Re-generer le seed."
        )
    manquantes = codes_cibles - seed_codes
    if manquantes:
        raise RuntimeError(
            f"Migration 102 : localites absentes du seed ({sorted(manquantes)}). "
            f"Capture incomplete."
        )
    if len(NASA_MONTHLY_PROFONDEUR_SEED) != _TOTAL_ATTENDU:
        raise RuntimeError(
            f"Migration 102 : {len(NASA_MONTHLY_PROFONDEUR_SEED)} mesures au seed, attendu "
            f"{_TOTAL_ATTENDU} ({_NB_POINTS} points x {sum(nb for _, nb in _FENETRES.values())} "
            f"mois). Seed anormal."
        )
    comptes: dict[tuple[str, str], int] = {}
    for r in NASA_MONTHLY_PROFONDEUR_SEED:
        grandeur = r["grandeur_code"]
        if grandeur not in _FENETRES:
            raise RuntimeError(f"Migration 102 : grandeur inattendue au seed : {grandeur!r}.")
        annee_debut, _ = _FENETRES[grandeur]
        annee, mois = int(r["annee"]), int(r["mois"])
        if not (annee_debut * 100 + 1 <= annee * 100 + mois <= _ANNEE_FIN * 100 + 12):
            raise RuntimeError(
                f"Migration 102 : mesure hors fenetre pour {grandeur!r} : {annee}-{mois:02d} "
                f"(attendu {annee_debut}-01 .. {_ANNEE_FIN}-12)."
            )
        cle = (r["localite_code"], grandeur)
        comptes[cle] = comptes.get(cle, 0) + 1
    for code in sorted(codes_cibles):
        for grandeur, (_, nb_attendu) in _FENETRES.items():
            nb = comptes.get((code, grandeur), 0)
            if nb != nb_attendu:
                raise RuntimeError(
                    f"Migration 102 : {code}/{grandeur} : {nb} mois au seed, attendu {nb_attendu}."
                )

    # === 4. Seed des 340 series (note_publique a l'insertion, doctrine 099) ===
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
        for grandeur, (annee_debut, _) in _FENETRES.items():
            lignes_series.append(
                {
                    "code": _code_serie(code, grandeur),
                    "libelle": (
                        f"{_LIBELLES[grandeur]} {ville} {annee_debut}-{_ANNEE_FIN} (NASA POWER)"
                    ),
                    "localite_id": localite_id_par_code[code],
                    "grandeur_code": grandeur,
                    "source_id": int(source_id),
                    "periode_debut": date(annee_debut, 1, 1),
                    "periode_fin": date(_ANNEE_FIN, 12, 31),
                    "granularite": _GRANULARITE,
                    "methode_collecte": _METHODE_COLLECTE,
                    "methode_collecte_doc": _METHODE_COLLECTE_DOC,
                    "commentaire_editorial": _COMMENTAIRE_TEMPLATE.format(
                        grandeur_upper=grandeur.upper(),
                        annee_debut=annee_debut,
                        annee_fin=_ANNEE_FIN,
                        ville=ville,
                    ),
                    "note_publique": _note_publique(grandeur, ville),
                    "url_documentation": _URL_DOCUMENTATION,
                }
            )
    assert len(lignes_series) == _NB_POINTS * len(_FENETRES), (
        f"Attendu {_NB_POINTS * len(_FENETRES)} series, obtenu {len(lignes_series)}"
    )
    op.bulk_insert(series_table, lignes_series)

    serie_id_par_code: dict[str, int] = {
        r.code: int(r.id)
        for r in bind.execute(
            sa.text("SELECT code, id FROM series_metadonnees WHERE code = ANY(:codes)"),
            {"codes": [ligne["code"] for ligne in lignes_series]},
        ).all()
    }

    # === 5. Mesures depuis le seed (hardcode B, mirror 095 ; chunks) ==========
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
        for r in NASA_MONTHLY_PROFONDEUR_SEED
    ]
    taille_chunk = 20_000
    for debut in range(0, len(lignes_mensuelles), taille_chunk):
        op.bulk_insert(mensuelles_table, lignes_mensuelles[debut : debut + taille_chunk])

    op.execute(
        f"-- Migration 102 : {len(lignes_series)} series mensuelles longues NASA POWER "
        f"(34 points x 10 grandeurs, profondeur 1981/1984/2001-2025) + "
        f"{len(lignes_mensuelles)} mesures (offline, seed profondeur)."
    )


def downgrade() -> None:
    codes_uniques = sorted(
        {_code_serie(r["localite_code"], r["grandeur_code"]) for r in NASA_MONTHLY_PROFONDEUR_SEED}
    )
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
