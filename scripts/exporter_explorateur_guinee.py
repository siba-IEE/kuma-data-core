"""Export des données du pilote guinéen pour l'explorateur public Kuma Science.

Produit l'arborescence statique attendue par le site Kuma Science :

    out/explorateur-guinee/guinee/
        manifest.json
        <ville>/<grandeur>.csv (ou <grandeur>_<variante>.csv si plusieurs séries)

Périmètre :
- 6 villes pilotes (gin_conakry_kaloum, gin_kankan, gin_kindia,
  gin_labe, gin_mamou, gin_nzerekore).
- Toutes les séries stockées de ces villes (mesures_ressource,
  mesures_ressource_mensuelles, grandeurs_metier via la vue
  v_grandeurs_metier_courantes).
- **Exclut les grandeurs F2 paramétrables** (poa_parametrable, etc.) :
  calculs à la volée, ne sont pas des séries fixes.

Toutes les requêtes lisent directement la base PostgreSQL via la session
SQLAlchemy du projet (pas l'API). Les filtres appliqués miment ceux du
routeur ``/v1/series`` : ``actif=true``, ``valide_au IS NULL``,
``statut <> 'deprecie'``.

Lancement :

    uv run python scripts/exporter_explorateur_guinee.py

Aucun secret n'est jamais lu ni écrit. La DSN PostgreSQL provient
de ``Settings`` (memoizée). Les fichiers CSV ne contiennent que des
données scientifiques publiques (pilote guinéen en accès libre acté).
"""

from __future__ import annotations

import csv
import json
import shutil
import sys
from collections.abc import Sequence
from datetime import date
from pathlib import Path
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from kuma_data_core.api.services.serie_lecture import (
    TableMesures,
    resolve_table_from_series_metadata,
)
from kuma_data_core.db.session import get_session_factory

# === Constantes périmètre ===================================================

_VILLES_PILOTES: tuple[str, ...] = (
    "gin_conakry_kaloum",
    "gin_kankan",
    "gin_kindia",
    "gin_labe",
    "gin_mamou",
    "gin_nzerekore",
)
"""6 villes pilotes (codes localites)."""

# Grandeurs F2 paramétrables - exclues de l'export (calcul à la volée).
_GRANDEURS_F2_EXCLUES: frozenset[str] = frozenset(
    {
        "poa_parametrable",
        "productible_correction_thermique",
        "productible_pr_fourni",
        "energie_utile_ecs",
        "degre_jour_climatisation",
    }
)

# Mapping source -> couche doctrinale Kuma.
#
# Doctrine corrigée (réalignement audit externe) :
#   - Couche A - calibration terrain (mesures sol locales, ANM Guinée à
#     venir). OBJECTIF DE ROADMAP, non intégré → aucune source active
#     en couche A tant qu'aucune mesure terrain n'est ingérée.
#   - Couche B - substrat modélisé + cross-check inter-source : NASA POWER
#     (satellite/réanalyse, source primaire actuelle) et SARAH-3 ICDR
#     (référentiel inter-source).
#   - Couche C - post-traitement éditorial Kuma + conventions normatives
#     (IEC 61724-1, WMO-No.8).
_COUCHE_PAR_SOURCE: dict[str, str] = {
    "nasa_power": "B",
    "sarah3_monthly": "B",
    "kuma_calculs": "C",
}

# Mapping famille de la série selon (source, granularité physique).
# - "brute" : grandeur ingérée depuis source externe, journalier
# - "mensuelle" : ingérée mensuel (SARAH-3, climatologie NASA 1991-2020)
# - "calculee" : grandeur F1 stockée Kuma (grandeurs_metier)
# - "referentielle" : grandeur référentielle Kuma (ecart_relatif, rang_*)
_GRANDEURS_REFERENTIELLES: frozenset[str] = frozenset(
    {
        "ecart_relatif_referentiel",
        "rang_referentiel_temporel",
        "rang_referentiel_spatial",
    }
)


def _slug_ville(code_localite: str) -> str:
    """Slug ville (dossier) : on retire le préfixe pays ``gin_``."""
    return code_localite.removeprefix("gin_")


def _famille_de_serie(
    source_code: str,
    grandeur_code: str,
    table_cible: TableMesures,
) -> str:
    """Détermine la famille doctrinale d'une série pour le manifeste."""
    if grandeur_code in _GRANDEURS_REFERENTIELLES:
        return "referentielle"
    if table_cible == TableMesures.GRANDEURS_METIER:
        return "calculee"
    if table_cible == TableMesures.MENSUEL_RESSOURCE:
        return "mensuelle"
    # mesures_ressource (journalier brut)
    return "brute"


def _granularite_de_table(table_cible: TableMesures) -> str:
    """Convertit la table-cible en label de granularité pour le manifeste."""
    if table_cible == TableMesures.JOURNALIER:
        return "journalier"
    if table_cible == TableMesures.MENSUEL_RESSOURCE:
        return "mensuel"
    # GRANDEURS_METIER - la granularité dépend de periode_type des lignes.
    # On la labellise via la première ligne lue (voir export).
    return "mixte"


# === Lecture catalogue ======================================================


def _charger_localites(session: Session) -> dict[str, dict[str, Any]]:
    """Récupère le détail des 6 villes pilotes (code -> dict)."""
    rows = session.execute(
        text(
            """
            SELECT code, nom, latitude, longitude
            FROM localites
            WHERE code = ANY(:codes)
            """
        ),
        {"codes": list(_VILLES_PILOTES)},
    ).all()
    return {
        r.code: {
            "code": _slug_ville(r.code),
            "code_complet": r.code,
            "nom": r.nom,
            "latitude": float(r.latitude) if r.latitude is not None else None,
            "longitude": float(r.longitude) if r.longitude is not None else None,
        }
        for r in rows
    }


def _charger_series_villes(session: Session) -> list[dict[str, Any]]:
    """Liste les séries actives des 6 villes pilotes, hors F2 paramétrables.

    Filtres alignés sur ``/v1/series`` : ``actif=true``. Les grandeurs F2
    sont écartées (elles sont calculées à la volée, pas stockées).
    """
    rows = session.execute(
        text(
            """
            SELECT
                sm.id,
                sm.code,
                sm.libelle,
                sm.localite_id,
                l.code         AS localite_code,
                l.nom          AS localite_nom,
                sm.grandeur_code,
                gr.libelle     AS grandeur_label,
                u.symbole      AS unite_symbole,
                u.code         AS unite_code,
                sm.source_id,
                s.code         AS source_code,
                s.titre        AS source_label,
                sm.periode_debut,
                sm.periode_fin,
                sm.granularite,
                sm.methode_collecte
            FROM series_metadonnees sm
            JOIN localites l            ON l.id = sm.localite_id
            JOIN sources s              ON s.id = sm.source_id
            JOIN grandeurs_referentiel gr ON gr.code = sm.grandeur_code
            JOIN unites u               ON u.id = gr.unite_id
            WHERE l.code = ANY(:codes_villes)
              AND sm.actif = TRUE
              AND sm.grandeur_code <> ALL(:grandeurs_exclues)
            ORDER BY l.code, sm.grandeur_code, sm.periode_debut
            """
        ),
        {
            "codes_villes": list(_VILLES_PILOTES),
            "grandeurs_exclues": list(_GRANDEURS_F2_EXCLUES),
        },
    ).all()
    return [dict(r._mapping) for r in rows]


# === Lecture mesures par catégorie ==========================================


def _lire_mesures_journalier(session: Session, serie_id: int) -> list[dict[str, Any]]:
    """Lit toutes les mesures journalières courantes d'une série."""
    rows = session.execute(
        text(
            """
            SELECT
                instant_mesure,
                valeur,
                COALESCE(niveau_confiance_override, niveau_confiance_derive) AS niveau_effectif,
                statut
            FROM mesures_ressource
            WHERE serie_id = :serie_id
              AND valide_au IS NULL
              AND statut <> 'deprecie'
            ORDER BY instant_mesure
            """
        ),
        {"serie_id": serie_id},
    ).all()
    return [
        {
            "instant_mesure": r.instant_mesure,
            "valeur": float(r.valeur) if r.valeur is not None else None,
            "niveau_effectif": r.niveau_effectif,
            "statut": r.statut,
        }
        for r in rows
    ]


def _lire_mesures_mensuel(session: Session, serie_id: int) -> list[dict[str, Any]]:
    """Lit toutes les mesures mensuelles courantes d'une série."""
    rows = session.execute(
        text(
            """
            SELECT
                annee,
                mois,
                valeur,
                COALESCE(niveau_confiance_override, niveau_confiance_derive) AS niveau_effectif,
                statut
            FROM mesures_ressource_mensuelles
            WHERE serie_id = :serie_id
              AND valide_au IS NULL
              AND statut <> 'deprecie'
            ORDER BY annee, mois
            """
        ),
        {"serie_id": serie_id},
    ).all()
    return [
        {
            "annee": int(r.annee),
            "mois": int(r.mois),
            "valeur": float(r.valeur) if r.valeur is not None else None,
            "niveau_effectif": r.niveau_effectif,
            "statut": r.statut,
        }
        for r in rows
    ]


def _lire_mesures_grandeurs_metier(session: Session, serie_id: int) -> list[dict[str, Any]]:
    """Lit les valeurs courantes via la vue v_grandeurs_metier_courantes.

    La vue applique nativement ``valide_au IS NULL`` + version courante +
    ``statut <> 'deprecie'``. On expose le triplet (periode_type, annee_debut,
    annee_fin, mois) pour différencier annuel/mensuel/statique côté CSV.
    """
    rows = session.execute(
        text(
            """
            SELECT
                periode_type,
                annee_debut,
                annee_fin,
                mois,
                version_formule,
                valeur,
                niveau_effectif,
                statut
            FROM v_grandeurs_metier_courantes
            WHERE series_metadonnees_id = :serie_id
            ORDER BY annee_debut, mois NULLS FIRST
            """
        ),
        {"serie_id": serie_id},
    ).all()
    return [
        {
            "periode_type": r.periode_type,
            "annee_debut": int(r.annee_debut),
            "annee_fin": int(r.annee_fin),
            "mois": int(r.mois) if r.mois is not None else None,
            "version_formule": int(r.version_formule),
            "valeur": float(r.valeur) if r.valeur is not None else None,
            "niveau_effectif": r.niveau_effectif,
            "statut": r.statut,
        }
        for r in rows
    ]


# === Écriture CSV ===========================================================


def _ecrire_csv_journalier(chemin: Path, mesures: Sequence[dict[str, Any]], unite: str) -> None:
    """CSV journalier : ``date,valeur,unite,niveau_confiance,statut``."""
    with chemin.open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["date", "valeur", "unite", "niveau_confiance", "statut"])
        for m in mesures:
            valeur = "" if m["valeur"] is None else f"{m['valeur']:.6g}"
            instant = m["instant_mesure"]
            iso = instant.isoformat() if isinstance(instant, date) else str(instant)
            w.writerow([iso, valeur, unite, m["niveau_effectif"], m["statut"]])


def _ecrire_csv_mensuel(chemin: Path, mesures: Sequence[dict[str, Any]], unite: str) -> None:
    """CSV mensuel : ``annee,mois,valeur,unite,niveau_confiance,statut``."""
    with chemin.open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["annee", "mois", "valeur", "unite", "niveau_confiance", "statut"])
        for m in mesures:
            valeur = "" if m["valeur"] is None else f"{m['valeur']:.6g}"
            w.writerow([m["annee"], m["mois"], valeur, unite, m["niveau_effectif"], m["statut"]])


def _ecrire_csv_grandeurs_metier(
    chemin: Path, mesures: Sequence[dict[str, Any]], unite: str
) -> None:
    """CSV grandeur_metier : suit la granularité native par ligne.

    En-tête générique couvrant les 3 ``periode_type`` :
    ``periode_type,annee_debut,annee_fin,mois,version_formule,valeur,unite,niveau_confiance,statut``.
    """
    with chemin.open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(
            [
                "periode_type",
                "annee_debut",
                "annee_fin",
                "mois",
                "version_formule",
                "valeur",
                "unite",
                "niveau_confiance",
                "statut",
            ]
        )
        for m in mesures:
            valeur = "" if m["valeur"] is None else f"{m['valeur']:.6g}"
            w.writerow(
                [
                    m["periode_type"],
                    m["annee_debut"],
                    m["annee_fin"],
                    "" if m["mois"] is None else m["mois"],
                    m["version_formule"],
                    valeur,
                    unite,
                    m["niveau_effectif"],
                    m["statut"],
                ]
            )


# === Stats résumé ===========================================================


def _stats_resume(mesures: Sequence[dict[str, Any]]) -> dict[str, Any]:
    """Min, max, moyenne, nb_points sur les valeurs non nulles."""
    valeurs = [m["valeur"] for m in mesures if m["valeur"] is not None]
    if not valeurs:
        return {"min": None, "max": None, "moyenne": None, "nb_points": 0}
    return {
        "min": round(min(valeurs), 6),
        "max": round(max(valeurs), 6),
        "moyenne": round(sum(valeurs) / len(valeurs), 6),
        "nb_points": len(mesures),
    }


def _niveau_confiance_dominant(mesures: Sequence[dict[str, Any]]) -> str | None:
    """Niveau de confiance le plus fréquent (sur niveau_effectif)."""
    compteurs: dict[str, int] = {}
    for m in mesures:
        n = m.get("niveau_effectif")
        if n is not None:
            compteurs[n] = compteurs.get(n, 0) + 1
    if not compteurs:
        return None
    return max(compteurs.items(), key=lambda kv: kv[1])[0]


# === Nom de fichier (gestion collisions par grandeur) =======================


def _suffixe_pour_serie(
    grandeur_code: str,
    table_cible: TableMesures,
    source_code: str,
    periode_debut: date,
) -> str:
    """Renvoie un suffixe optionnel pour différencier plusieurs séries d'une
    même grandeur dans une même ville.

    Convention : ``ghi.csv`` pour la série dominante (journalier NASA POWER
    2021-2025), ``ghi_mensuel_sarah3.csv`` pour la mensuelle SARAH-3,
    ``ghi_climatologie_1991_2020.csv`` pour la climatologie. Pour les
    grandeurs sans collision, suffixe vide.
    """
    if grandeur_code != "ghi":
        return ""
    if source_code == "sarah3_monthly":
        return "_mensuel_sarah3"
    if source_code == "nasa_power" and periode_debut.year < 2021:
        return "_climatologie_1991_2020"
    return ""


# === Programme principal ====================================================


def exporter(racine_sortie: Path) -> dict[str, Any]:
    """Génère l'arborescence guinee/ sous ``racine_sortie``.

    Renvoie un dict de statistiques pour le résumé final.
    """
    racine_guinee = racine_sortie / "guinee"
    if racine_guinee.exists():
        shutil.rmtree(racine_guinee)
    racine_guinee.mkdir(parents=True, exist_ok=True)

    factory = get_session_factory()
    stats_familles: dict[str, int] = {}
    series_ignorees: list[dict[str, Any]] = []
    villes_manifeste: list[dict[str, Any]] = []

    with factory() as session:
        localites = _charger_localites(session)
        series = _charger_series_villes(session)

        # Index : localite_code -> liste de séries
        series_par_ville: dict[str, list[dict[str, Any]]] = {code: [] for code in _VILLES_PILOTES}
        for s in series:
            series_par_ville[s["localite_code"]].append(s)

        for code_ville in _VILLES_PILOTES:
            loc = localites.get(code_ville)
            if loc is None:
                series_ignorees.append({"localite": code_ville, "raison": "localité introuvable"})
                continue

            slug = loc["code"]
            dossier_ville = racine_guinee / slug
            dossier_ville.mkdir(exist_ok=True)

            series_manifeste: list[dict[str, Any]] = []

            for s in series_par_ville[code_ville]:
                table_cible = resolve_table_from_series_metadata(
                    source_code=s["source_code"],
                    granularite=s["granularite"],
                )

                if table_cible == TableMesures.JOURNALIER:
                    mesures = _lire_mesures_journalier(session, int(s["id"]))
                elif table_cible == TableMesures.MENSUEL_RESSOURCE:
                    mesures = _lire_mesures_mensuel(session, int(s["id"]))
                else:
                    mesures = _lire_mesures_grandeurs_metier(session, int(s["id"]))

                if not mesures:
                    series_ignorees.append(
                        {
                            "code_serie": s["code"],
                            "raison": "aucune mesure courante",
                        }
                    )
                    continue

                suffixe = _suffixe_pour_serie(
                    grandeur_code=s["grandeur_code"],
                    table_cible=table_cible,
                    source_code=s["source_code"],
                    periode_debut=s["periode_debut"],
                )
                nom_fichier = f"{s['grandeur_code']}{suffixe}.csv"
                chemin_csv = dossier_ville / nom_fichier

                if table_cible == TableMesures.JOURNALIER:
                    _ecrire_csv_journalier(chemin_csv, mesures, s["unite_symbole"])
                elif table_cible == TableMesures.MENSUEL_RESSOURCE:
                    _ecrire_csv_mensuel(chemin_csv, mesures, s["unite_symbole"])
                else:
                    _ecrire_csv_grandeurs_metier(chemin_csv, mesures, s["unite_symbole"])

                famille = _famille_de_serie(s["source_code"], s["grandeur_code"], table_cible)
                stats_familles[famille] = stats_familles.get(famille, 0) + 1

                granularite = _granularite_de_table(table_cible)
                # Pour les grandeurs_metier, raffiner la granularité d'après
                # les periode_type effectivement présents (annuel / mensuel /
                # statique / mixte).
                if table_cible == TableMesures.GRANDEURS_METIER:
                    types = {m["periode_type"] for m in mesures}
                    if types == {"annuel"}:
                        granularite = "annuel"
                    elif types == {"mensuel"}:
                        granularite = "mensuel"
                    elif types == {"statique"}:
                        granularite = "statique"
                    elif types == {"annuel", "mensuel"}:
                        granularite = "annuel+mensuel"
                    else:
                        granularite = "mixte"

                stats = _stats_resume(mesures)
                niveau_dominant = _niveau_confiance_dominant(mesures)
                couche = _COUCHE_PAR_SOURCE.get(s["source_code"])

                series_manifeste.append(
                    {
                        "code_serie": s["code"],
                        "grandeur_code": s["grandeur_code"],
                        "grandeur_label": s["grandeur_label"],
                        "unite": s["unite_symbole"],
                        "granularite": granularite,
                        "famille": famille,
                        "periode_debut": s["periode_debut"].isoformat(),
                        "periode_fin": (
                            s["periode_fin"].isoformat() if s["periode_fin"] is not None else None
                        ),
                        "nb_points": stats["nb_points"],
                        "source_code": s["source_code"],
                        "source_label": s["source_label"],
                        "methode_collecte": s["methode_collecte"],
                        "couche": couche,
                        "niveau_confiance": niveau_dominant,
                        "stats": {
                            "min": stats["min"],
                            "max": stats["max"],
                            "moyenne": stats["moyenne"],
                        },
                        "fichier": f"{slug}/{nom_fichier}",
                    }
                )

            villes_manifeste.append(
                {
                    "code": slug,
                    "code_complet": code_ville,
                    "nom": loc["nom"],
                    "latitude": loc["latitude"],
                    "longitude": loc["longitude"],
                    "series": series_manifeste,
                }
            )

    manifest: dict[str, Any] = {
        "pays": "Guinée",
        "code_pays": "gin",
        "genere_le": date.today().isoformat(),
        "note_acces": (
            "Données du pilote guinéen en accès libre. "
            "Accès garanti, versionné et programmatique via l'API."
        ),
        "villes": villes_manifeste,
    }

    # Garde-fou doctrine corrigée : tant qu'aucune mesure terrain (ANM Guinée)
    # n'est ingérée, aucune série ne doit sortir en couche A ni en confiance A.
    # Si l'une de ces conditions est violée, l'export échoue fort - c'est le
    # signe qu'une nouvelle source/override a été ajoutée sans mettre à jour
    # _COUCHE_PAR_SOURCE ou sans arbitrer la doctrine.
    series_couche_a = [
        s["code_serie"] for v in villes_manifeste for s in v["series"] if s.get("couche") == "A"
    ]
    series_confiance_a = [
        s["code_serie"]
        for v in villes_manifeste
        for s in v["series"]
        if s.get("niveau_confiance") == "A"
    ]
    if series_couche_a or series_confiance_a:
        raise RuntimeError(
            "Export refusé - la doctrine corrigée interdit couche A et confiance A "
            "tant que les mesures terrain ne sont pas intégrées. "
            f"Séries en couche A : {series_couche_a}. "
            f"Séries en confiance A dominante : {series_confiance_a}."
        )

    chemin_manifest = racine_guinee / "manifest.json"
    chemin_manifest.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    return {
        "nb_villes": len(villes_manifeste),
        "nb_series_par_famille": stats_familles,
        "series_ignorees": series_ignorees,
        "racine_sortie": str(racine_guinee.resolve()),
    }


def main() -> int:
    repo_root = Path(__file__).resolve().parents[1]
    racine_sortie = repo_root / "out" / "explorateur-guinee"
    resume = exporter(racine_sortie)

    print("=" * 72)
    print("Export explorateur guinéen - résumé")
    print("=" * 72)
    print(f"Sortie         : {resume['racine_sortie']}")
    print(f"Villes         : {resume['nb_villes']}")
    print("Séries par famille :")
    for famille, n in sorted(resume["nb_series_par_famille"].items()):
        print(f"  - {famille:15s} {n}")
    if resume["series_ignorees"]:
        print(f"Séries ignorées : {len(resume['series_ignorees'])}")
        for s in resume["series_ignorees"]:
            print(f"  - {s}")
    else:
        print("Séries ignorées : 0")
    print("=" * 72)
    return 0


if __name__ == "__main__":
    sys.exit(main())
