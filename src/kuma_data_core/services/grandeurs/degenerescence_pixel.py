"""Dégénérescence de pixel : nombre d'autres localités qui partagent la cellule source d'un point.

Sur une grille fixe (NASA POWER), deux points d'une même cellule ont des
séries mensuelles strictement identiques : on groupe les localités par
vecteur identique (égalité exacte), sans supposer de définition de grille.
Les services interpolés au point (SARAH-3, CAMS 5 km) donnent 0 par
construction ; un caveat de résolution porte alors le sens.

Une ligne statique par (localité, source, paramètre), valeur = nombre de
jumeaux. Confiance fixe ``B``, exemptée de la propagation : voir
:mod:`kuma_data_core.editorial.niveaux_confiance`.
"""

from __future__ import annotations

from collections import defaultdict
from typing import TypedDict

from sqlalchemy import text
from sqlalchemy.orm import Session

from kuma_data_core.editorial.niveaux_confiance import NIVEAU_CONFIANCE_DEGENERESCENCE_PIXEL
from kuma_data_core.editorial.statuts import filtre_mesure_utilisable
from kuma_data_core.services.grandeurs._commun import inserer_lignes_grandeurs_metier

# === Constantes module =====================================================

GRANDEUR_DEGENERESCENCE: str = "degenerescence_pixel"
VERSION_FORMULE: int = 1

# Texte d'origine de la migration 090, retiré ensuite des textes publiés sous
# garde md5 ; aucun nouveau texte ne le porte.
_MENTION_HISTORIQUE_090: str = " (D-29 generalise)"

# Le fait est exact, mais A reste réservé aux mesures au sol.
_CAVEAT_CONFIANCE: str = (
    " Indicateur exact (identite structurelle observee, non modelise), tague confiance B : "
    "A est reservee aux mesures terrain et l'echelle A/B/C classe la fiabilite d'une mesure "
    "de substrat, pas la certitude d'un fait structurel."
)


class _ConfigSource(TypedDict):
    """Un (source, parametre) dont on mesure la degenerescence de pixel."""

    source_code: str
    grandeur_code: str
    periode_debut: str  # borne de la serie climato mensuelle a comparer
    grille: str
    resolution: str
    grille_fixe: bool


# Epine radiative posee aux 33 localites. Radiation NASA = CERES SYN1deg 1deg ;
# meteo NASA = MERRA-2 0.5deg (grille deux fois plus fine, donc moins de
# degenerescence) ; SARAH-3 / CAMS = services interpoles 5 km (compte 0 + caveat).
_CERES = ("CERES SYN1deg", "1 deg (110 km)")
_MERRA = ("MERRA-2", "0.5 deg (55 km)")
_INTERP = "5 km"

_CONFIG: tuple[_ConfigSource, ...] = (
    # NASA radiation (CERES 1deg) : ghi sur 1991-2020, les 4 autres sur 2001-2020.
    {
        "source_code": "nasa_power",
        "grandeur_code": "ghi",
        "periode_debut": "1991-01-01",
        "grille": _CERES[0],
        "resolution": _CERES[1],
        "grille_fixe": True,
    },
    {
        "source_code": "nasa_power",
        "grandeur_code": "dni",
        "periode_debut": "2001-01-01",
        "grille": _CERES[0],
        "resolution": _CERES[1],
        "grille_fixe": True,
    },
    {
        "source_code": "nasa_power",
        "grandeur_code": "dhi",
        "periode_debut": "2001-01-01",
        "grille": _CERES[0],
        "resolution": _CERES[1],
        "grille_fixe": True,
    },
    {
        "source_code": "nasa_power",
        "grandeur_code": "kt",
        "periode_debut": "2001-01-01",
        "grille": _CERES[0],
        "resolution": _CERES[1],
        "grille_fixe": True,
    },
    {
        "source_code": "nasa_power",
        "grandeur_code": "albedo_surface",
        "periode_debut": "2001-01-01",
        "grille": _CERES[0],
        "resolution": _CERES[1],
        "grille_fixe": True,
    },
    # NASA meteo (MERRA-2 0.5deg), tout sur 1991-2020.
    {
        "source_code": "nasa_power",
        "grandeur_code": "t2m",
        "periode_debut": "1991-01-01",
        "grille": _MERRA[0],
        "resolution": _MERRA[1],
        "grille_fixe": True,
    },
    {
        "source_code": "nasa_power",
        "grandeur_code": "rh2m",
        "periode_debut": "1991-01-01",
        "grille": _MERRA[0],
        "resolution": _MERRA[1],
        "grille_fixe": True,
    },
    {
        "source_code": "nasa_power",
        "grandeur_code": "vent_2m",
        "periode_debut": "1991-01-01",
        "grille": _MERRA[0],
        "resolution": _MERRA[1],
        "grille_fixe": True,
    },
    {
        "source_code": "nasa_power",
        "grandeur_code": "vent_10m",
        "periode_debut": "1991-01-01",
        "grille": _MERRA[0],
        "resolution": _MERRA[1],
        "grille_fixe": True,
    },
    # Services interpoles 5 km (compte 0 naturel + caveat de resolution).
    {
        "source_code": "sarah3_monthly",
        "grandeur_code": "ghi",
        "periode_debut": "2021-01-01",
        "grille": "PVGIS-SARAH3 (interpole)",
        "resolution": _INTERP,
        "grille_fixe": False,
    },
    {
        "source_code": "cams_radiation",
        "grandeur_code": "dni",
        "periode_debut": "2021-01-01",
        "grille": "CAMS Heliosat-4 (interpole)",
        "resolution": _INTERP,
        "grille_fixe": False,
    },
)


# === Fonction pure =========================================================


def _grouper_par_pixel(vecteurs: dict[int, tuple[float, ...]]) -> dict[int, list[int]]:
    """``{localite_id: [autres localités au vecteur identique]}`` (vide = point résolu).

    Égalité exacte : sur grille fixe, l'identité est binaire ; un quasi-égal
    relève de l'écart inter-source.
    """
    groupes: dict[tuple[float, ...], list[int]] = defaultdict(list)
    for loc_id, vec in vecteurs.items():
        groupes[vec].append(loc_id)
    jumeaux: dict[int, list[int]] = {}
    for membres in groupes.values():
        for loc_id in membres:
            jumeaux[loc_id] = sorted(m for m in membres if m != loc_id)
    return jumeaux


def _commentaire(
    cfg: _ConfigSource,
    grandeur: str,
    codes_jumeaux: list[str],
    *,
    texte_historique_090: bool = False,
) -> str:
    """Groupe de jumeaux (grille fixe) ou caveat de résolution (source interpolée).

    ``texte_historique_090`` reproduit à l'octet le texte de la migration 090.
    """
    if not cfg["grille_fixe"]:
        base = (
            f"Source interpolee au point ({cfg['grille']}, {cfg['resolution']}) : valeurs "
            f"distinctes par construction. Resolution reelle {cfg['resolution']} -> finesse "
            f"sub-maille illusoire (caveat de resolution, pas une degenerescence mesurable)."
        )
    elif codes_jumeaux:
        liste = ", ".join(codes_jumeaux)
        base = (
            f"Degenerescence de pixel : partage la cellule {cfg['grille']} ({cfg['resolution']}) "
            f"avec {len(codes_jumeaux)} autre(s) point(s) ({liste}). Series {grandeur} identiques "
            f"(meme pixel source) -> ne pas presenter comme des mesures independantes"
            f"{_MENTION_HISTORIQUE_090 if texte_historique_090 else ''}."
        )
    else:
        base = (
            f"Point resolu sur {cfg['grille']} ({cfg['resolution']}) : aucun autre point "
            f"partageant la cellule pour {grandeur}."
        )
    return base + _CAVEAT_CONFIANCE


# === Orchestrateur I/O =====================================================


def calculer_et_inserer_degenerescence_pixel(session: Session) -> int:
    """Insère une ligne par localité et (source, paramètre) ; renvoie le nombre de lignes."""
    return _calculer_et_inserer(session, texte_historique_090=False)


def calculer_et_inserer_degenerescence(session: Session) -> int:
    """Variante importée par la migration 090 (immuable), avec son texte d'origine.

    Une base reconstruite doit passer par l'état que les migrations suivantes
    attendent. Tout nouvel appel utilise :func:`calculer_et_inserer_degenerescence_pixel`.
    """
    return _calculer_et_inserer(session, texte_historique_090=True)


def _calculer_et_inserer(session: Session, *, texte_historique_090: bool) -> int:
    """Corps commun des deux orchestrateurs (seul le commentaire differe)."""
    nb_insere = 0
    for cfg in _CONFIG:
        rows = session.execute(
            text(
                f"""
                SELECT l.id AS loc_id, l.code AS loc_code, sm.id AS serie_id,
                       EXTRACT(YEAR FROM sm.periode_debut)::int AS an_deb,
                       EXTRACT(YEAR FROM sm.periode_fin)::int AS an_fin,
                       m.annee, m.mois, m.valeur
                FROM mesures_ressource_mensuelles m
                JOIN series_metadonnees sm ON sm.id = m.serie_id
                JOIN sources s ON s.id = sm.source_id
                JOIN localites l ON l.id = sm.localite_id
                WHERE s.code = :src AND sm.grandeur_code = :g
                  AND sm.granularite = 'mensuel' AND sm.periode_debut = :pdeb
                  AND {filtre_mesure_utilisable("m")}
                ORDER BY l.code, m.annee, m.mois
                """
            ),
            {"src": cfg["source_code"], "g": cfg["grandeur_code"], "pdeb": cfg["periode_debut"]},
        ).all()

        # Reconstruit, par localite : id, code, serie source, fenetre, vecteur de valeurs.
        vecteurs: dict[int, tuple[float, ...]] = {}
        meta: dict[int, dict[str, object]] = {}
        accum: dict[int, list[float]] = defaultdict(list)
        for r in rows:
            accum[int(r.loc_id)].append(float(r.valeur))
            meta.setdefault(
                int(r.loc_id),
                {
                    "code": r.loc_code,
                    "serie_id": int(r.serie_id),
                    "an_deb": int(r.an_deb),
                    "an_fin": int(r.an_fin),
                },
            )
        for loc_id, vals in accum.items():
            vecteurs[loc_id] = tuple(vals)

        if not vecteurs:
            continue  # source/parametre absent (garde defensive)

        jumeaux = _grouper_par_pixel(vecteurs)
        code_par_id = {loc_id: str(m["code"]) for loc_id, m in meta.items()}

        lignes: list[dict[str, object]] = []
        for loc_id, ids_jumeaux in jumeaux.items():
            m = meta[loc_id]
            codes_jumeaux = sorted(code_par_id[j] for j in ids_jumeaux)
            lignes.append(
                {
                    "grandeur_code": GRANDEUR_DEGENERESCENCE,
                    "localite_id": loc_id,
                    "series_metadonnees_id": m["serie_id"],
                    "periode_type": "statique",
                    "annee_debut": m["an_deb"],
                    "annee_fin": m["an_fin"],
                    "mois": None,
                    "version_formule": VERSION_FORMULE,
                    "valeur": float(len(ids_jumeaux)),
                    "niveau_confiance_derive": NIVEAU_CONFIANCE_DEGENERESCENCE_PIXEL,
                    "commentaire_editorial": _commentaire(
                        cfg,
                        cfg["grandeur_code"],
                        codes_jumeaux,
                        texte_historique_090=texte_historique_090,
                    ),
                }
            )

        inserer_lignes_grandeurs_metier(
            session, lignes, colonnes_supplementaires=("commentaire_editorial",)
        )
        nb_insere += len(lignes)

    session.flush()
    return nb_insere
