"""seed_profondeur_daily_nasa_34_points

Revision ID: 107
Revises: 106
Create Date: 2026-08-09 18:00:00

Chantier profondeur maximale par source, deuxieme volet : backfill journalier
NASA POWER aux **34 points** (6 pilotes + 28 communes chef-lieu), fenetre
**1981 -> 2020**, 10 grandeurs. Borne d'adjacence exacte avec les series daily
2021-2025 en base (018/020/022/029/048/080 pilotes, 086/094 communes) : le
backfill s'arrete au 2020-12-31, aucun chevauchement.

Series longues independantes, jusqu'au plancher reel de la source (sondes API
du 2026-08-09, frontieres verifiees sur fenetres mixtes) :

| Grandeurs                                       | Fenetre                 | Jours/serie |
|-------------------------------------------------|-------------------------|-------------|
| t2m, rh2m, vent_2m, vent_10m, precipitation     | 1981-01-01 a 2020-12-31 | 14 610      |
| ghi, dhi                                        | 1984-01-01 a 2020-12-31 | 13 515      |
| dni, kt, albedo_surface                         | 2001-01-01 a 2020-12-31 | 7 305       |

Volume : 34 x 10 = **340 series**, 34 x 121 995 = **4 147 830 mesures**
attendues dans ``mesures_ressource``. La capture s'est revelee **gapless**
(couverture identique sur les 34 points, verifiee par le preparateur) ->
gardes d'egalite strictes, comptes exacts.

Pattern NE-OFFLINE (mirror 105 mensuel ; prerequis : migration 106, cle UNIQUE
etendue a la granularite) : la migration lit le seed committe
``nasa_power_daily_profondeur_seed_data`` (capture live du 2026-08-09 par
``scripts/preparer_seed_nasa_daily_profondeur.py``, sentinelles -999 deja
filtrees), **aucun reseau au runtime**. Seed **groupe par serie et chunke par
ville x decennie** (136 fichiers), consomme en **streaming deux passes**
(gardes completes puis insertion) : jamais les 4,1 M de lignes en memoire.
Namespace SEPARE du seed daily 2021-2025 (payloads des migrations immuables) :
zero retouche, zero retrofit.

Enumeration DATA-DRIVEN des 34 points, garde ``len != 34``. Confiance **'B'
hardcodee** (patron brute-ingestion). Statut ``brut`` (defaut serveur).
``note_publique`` renseignee a l'insertion.

BRUTE SEULEMENT (anti-scope-creep) : aucun ecart ni grandeur calculee ici ;
les series daily 2021-2025 et leurs consommateurs restent inchanges.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date
from typing import Any

import sqlalchemy as sa
from alembic import op

from kuma_data_core.db.seeds.nasa_power_daily_profondeur_seed_data import (
    iter_blocs_daily_profondeur,
)

# revision identifiers, used by Alembic.
revision: str = "107"
down_revision: str | Sequence[str] | None = "106"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# === Constantes ============================================================
_SOURCE_CODE = "nasa_power"
_GRANULARITE = "journalier"
_METHODE_COLLECTE = "modele_satellitaire"
_METHODE_COLLECTE_DOC = "https://power.larc.nasa.gov/docs/methodology/"
_URL_DOCUMENTATION = "https://power.larc.nasa.gov/"
_PERIODE_FIN = date(2020, 12, 31)
_NB_POINTS = 34
_TAILLE_LOT_INSERT = 20_000

# Grandeur -> (date_debut, jours attendus par serie). Fenetres etablies par les
# sondes API du 2026-08-09 et verifiees gapless sur les 34 points par le
# preparateur ; figees ici avec gardes d'egalite strictes.
_FENETRES: dict[str, tuple[date, int]] = {
    "t2m": (date(1981, 1, 1), 14_610),
    "rh2m": (date(1981, 1, 1), 14_610),
    "vent_2m": (date(1981, 1, 1), 14_610),
    "vent_10m": (date(1981, 1, 1), 14_610),
    "precipitation": (date(1981, 1, 1), 14_610),
    "ghi": (date(1984, 1, 1), 13_515),
    "dhi": (date(1984, 1, 1), 13_515),
    "dni": (date(2001, 1, 1), 7_305),
    "kt": (date(2001, 1, 1), 7_305),
    "albedo_surface": (date(2001, 1, 1), 7_305),
}
_TOTAL_ATTENDU = _NB_POINTS * sum(nb for _, nb in _FENETRES.values())  # 4 147 830

_LIBELLES: dict[str, str] = {
    "ghi": "GHI journalier serie longue",
    "dhi": "DHI journalier serie longue",
    "dni": "DNI journalier serie longue",
    "kt": "Indice de clarte journalier serie longue",
    "albedo_surface": "Albedo de surface journalier serie longue",
    "t2m": "Temperature 2m journaliere serie longue",
    "rh2m": "Humidite relative 2m journaliere serie longue",
    "vent_2m": "Vent 2m journalier serie longue",
    "vent_10m": "Vent 10m journalier serie longue",
    "precipitation": "Precipitations journalieres serie longue",
}

# --- note_publique : meme charpente que le volet mensuel (quoi/ou -> source
# -> confiance -> limites), sans vocabulaire de chantier interne. -----------
_NOTE_DESCRIPTIFS: dict[str, str] = {
    "ghi": "Irradiation solaire globale recue sur un plan horizontal (GHI), en kWh/m2 par jour",
    "dhi": "Part diffuse de l'irradiation solaire sur plan horizontal (DHI), en kWh/m2 par jour",
    "dni": "Irradiation solaire directe recue face au soleil (DNI), en kWh/m2 par jour",
    "kt": (
        "Indice de clarte du ciel : rapport entre le rayonnement recu au sol et le "
        "rayonnement hors atmosphere (sans unite, entre 0 et 1)"
    ),
    "albedo_surface": (
        "Albedo de surface : part du rayonnement solaire reflechie par le sol "
        "(sans unite, entre 0 et 1)"
    ),
    "t2m": "Temperature moyenne quotidienne de l'air a 2 metres du sol, en degres Celsius",
    "rh2m": "Humidite relative moyenne quotidienne de l'air a 2 metres du sol, en pourcentage",
    "vent_2m": "Vitesse moyenne quotidienne du vent a 2 metres du sol, en metres par seconde",
    "vent_10m": "Vitesse moyenne quotidienne du vent a 10 metres du sol, en metres par seconde",
    "precipitation": "Precipitations totales corrigees, en millimetres par jour",
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
    "Serie journaliere longue {grandeur_upper} {annee_debut}-2020, {ville}, Guinee. "
    "Chantier profondeur maximale par source (decision 2026-08-09), volet NASA "
    "journalier. Palier de profondeur {annee_debut} etabli par sonde API du 2026-08-09. "
    "Seed NE-OFFLINE nasa_power_daily_profondeur_seed_data (capture live 2026-08-09, "
    "gapless), aucun reseau au runtime migration. Adjacence exacte avec les series "
    "daily 2021-2025 (zero chevauchement, zero retrofit). Confiance B (modele "
    "satellitaire)."
)


def _prefixe_serie(localite_code: str) -> str:
    """Prefixe du code de serie ; exception Conakry (cf. 01-naming.md)."""
    return "gin_conakry" if localite_code == "gin_conakry_kaloum" else localite_code


def _code_serie(localite_code: str, grandeur_code: str) -> str:
    """Convention de nommage : ``<prefixe>_<grandeur>_nasa_power_journalier_<debut>_2020``.

    Segment ``nasa_power_journalier`` : distinct des codes daily 2021-2025
    (``nasa_power_2021_2025``) et du volet mensuel (``nasa_power_mensuel_*``),
    sans collision avec les motifs de comptage existants.
    """
    debut, _ = _FENETRES[grandeur_code]
    return (
        f"{_prefixe_serie(localite_code)}_{grandeur_code}_nasa_power_journalier_{debut.year}_2020"
    )


def _note_publique(grandeur_code: str, ville: str) -> str:
    debut, _ = _FENETRES[grandeur_code]
    return (
        f"{_NOTE_DESCRIPTIFS[grandeur_code]}. Serie journaliere longue "
        f"{debut.year}-2020, {ville}, Guinee. {_NOTE_CORPS_NASA} "
        f"{_NOTE_CONF_B}{_NOTE_LIMITES_PALIER[debut.year]}{_NOTE_LIMITE_LONGUE}"
    )


def _points_cibles(bind: sa.engine.Connection) -> list[tuple[int, str, str]]:
    """Enumeration data-driven des 34 points : localites ayant une serie NASA
    POWER ghi journaliere 2021-2025 (6 pilotes via 018+, 28 communes via 086)."""
    rows = bind.execute(
        sa.text(
            """
            SELECT l.id, l.code, l.nom FROM localites l
            WHERE EXISTS (
                SELECT 1 FROM series_metadonnees sm JOIN sources s ON s.id = sm.source_id
                WHERE sm.localite_id = l.id AND s.code = 'nasa_power'
                  AND sm.grandeur_code = 'ghi' AND sm.granularite = 'journalier'
                  AND sm.periode_debut = '2021-01-01')
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
        raise RuntimeError(f"Migration 107 : source {_SOURCE_CODE!r} introuvable (migration 012).")
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
            f"Migration 107 : grandeur(s) introuvable(s)/inactive(s) : "
            f"{sorted(grandeurs_manquantes)}."
        )

    # === 2. Enumeration data-driven des 34 points (garde len != 34) ==========
    points = _points_cibles(bind)
    if len(points) != _NB_POINTS:
        raise RuntimeError(f"Migration 107 : attendu {_NB_POINTS} points, enumere {len(points)}.")
    localite_id_par_code = {code: lid for lid, code, _ in points}
    nom_par_code = {code: nom for _, code, nom in points}
    codes_cibles = set(localite_id_par_code)

    # === 3. Gardes de couverture du seed (passe 1, streaming complet) ========
    comptes: dict[tuple[str, str], int] = {}
    total_seed = 0
    for bloc in iter_blocs_daily_profondeur():
        loc = bloc["localite_code"]
        grandeur = bloc["grandeur_code"]
        if loc not in codes_cibles:
            raise RuntimeError(f"Migration 107 : localite hors perimetre au seed : {loc!r}.")
        if grandeur not in _FENETRES:
            raise RuntimeError(f"Migration 107 : grandeur inattendue au seed : {grandeur!r}.")
        debut, _ = _FENETRES[grandeur]
        valeurs: dict[str, float] = bloc["valeurs"]
        d_min, d_max = min(valeurs), max(valeurs)
        if date.fromisoformat(d_min) < debut or date.fromisoformat(d_max) > _PERIODE_FIN:
            raise RuntimeError(
                f"Migration 107 : {loc}/{grandeur} hors fenetre ({d_min}..{d_max}, "
                f"attendu {debut.isoformat()}..{_PERIODE_FIN.isoformat()})."
            )
        cle = (loc, grandeur)
        comptes[cle] = comptes.get(cle, 0) + len(valeurs)
        total_seed += len(valeurs)
    if total_seed != _TOTAL_ATTENDU:
        raise RuntimeError(
            f"Migration 107 : {total_seed} mesures au seed, attendu {_TOTAL_ATTENDU}."
        )
    for code in sorted(codes_cibles):
        for grandeur, (_, nb_attendu) in _FENETRES.items():
            nb = comptes.get((code, grandeur), 0)
            if nb != nb_attendu:
                raise RuntimeError(
                    f"Migration 107 : {code}/{grandeur} : {nb} jours au seed, attendu {nb_attendu}."
                )

    # === 4. Seed des 340 series (note_publique a l'insertion) ================
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
        for grandeur, (debut, _) in _FENETRES.items():
            lignes_series.append(
                {
                    "code": _code_serie(code, grandeur),
                    "libelle": f"{_LIBELLES[grandeur]} {ville} {debut.year}-2020 (NASA POWER)",
                    "localite_id": localite_id_par_code[code],
                    "grandeur_code": grandeur,
                    "source_id": int(source_id),
                    "periode_debut": debut,
                    "periode_fin": _PERIODE_FIN,
                    "granularite": _GRANULARITE,
                    "methode_collecte": _METHODE_COLLECTE,
                    "methode_collecte_doc": _METHODE_COLLECTE_DOC,
                    "commentaire_editorial": _COMMENTAIRE_TEMPLATE.format(
                        grandeur_upper=grandeur.upper(),
                        annee_debut=debut.year,
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

    # === 5. Mesures en streaming (passe 2), lots de 20 000, hardcode B =======
    mesures_table = sa.table(
        "mesures_ressource",
        sa.column("serie_id", sa.BigInteger),
        sa.column("instant_mesure", sa.Date),
        sa.column("valeur", sa.Float),
        sa.column("niveau_confiance_derive", sa.String),
    )
    tampon: list[dict[str, Any]] = []
    total_insere = 0
    for bloc in iter_blocs_daily_profondeur():
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
            f"Migration 107 : {total_insere} mesures inserees, attendu {_TOTAL_ATTENDU}."
        )

    op.execute(
        f"-- Migration 107 : {len(lignes_series)} series journalieres longues NASA POWER "
        f"(34 points x 10 grandeurs, profondeur 1981/1984/2001-2020) + "
        f"{total_insere} mesures (offline, seed profondeur, gapless)."
    )


def downgrade() -> None:
    codes_uniques = sorted(
        {
            _code_serie(bloc["localite_code"], bloc["grandeur_code"])
            for bloc in iter_blocs_daily_profondeur()
        }
    )
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
