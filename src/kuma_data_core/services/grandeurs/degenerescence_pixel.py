"""Calcul de la grandeur ``degenerescence_pixel``.

Pour chaque (localité, source, grandeur), dit si le point partage sa cellule source
avec d'autres localités (la donnée se répète) ou s'il y est seul.

Méthode empirique : sur une grille fixe (NASA POWER), deux points de la même cellule
lisent la valeur de la cellule, donc leurs séries mensuelles sont strictement
identiques. Les localités sont groupées par vecteur de valeurs identique (égalité
exacte) ; un groupe de plus d'un point est un groupe de jumeaux. Aucune définition
de grille n'est supposée.

- Grille fixe (rayonnement NASA : CERES 1°, météo NASA : MERRA-2 0,5°) : le nombre
  de jumeaux est mesuré.
- Service interpolé au point (SARAH-3, CAMS, 5 km) : les valeurs diffèrent par
  construction, le compte vaut 0 ; le commentaire signale alors que la finesse
  sous la maille est illusoire.

Sortie : une ligne ``grandeurs_metier`` par (localité, source, grandeur),
``periode_type='statique'``, ``valeur`` = nombre de jumeaux (0 = point seul dans sa
cellule), rattachée à la série climatologique mensuelle comparée. Confiance B et non
A : la dégénérescence est un fait exact, mais A est réservée aux mesures au sol. Le
groupe de jumeaux et les mises en garde sont dans ``commentaire_editorial``.

Calcul déterministe depuis la base, sans appel réseau.
"""

from __future__ import annotations

from collections import defaultdict
from typing import TypedDict

from sqlalchemy import text
from sqlalchemy.orm import Session

GRANDEUR_DEGENERESCENCE: str = "degenerescence_pixel"
NIVEAU_CONFIANCE_DERIVE: str = "B"
VERSION_FORMULE: int = 1

# Ajouté à chaque commentaire : l'indicateur est exact, mais reste en confiance B
# parce que A est réservée aux mesures au sol.
_CAVEAT_CONFIANCE: str = (
    " Indicateur exact (identite structurelle observee, non modelise), tague confiance B : "
    "A est reservee aux mesures terrain et l'echelle A/B/C classe la fiabilite d'une mesure "
    "de substrat, pas la certitude d'un fait structurel."
)


class _ConfigSource(TypedDict):
    """Un couple (source, grandeur) dont on mesure la dégénérescence de pixel."""

    source_code: str
    grandeur_code: str
    periode_debut: str  # début de la série climatologique mensuelle à comparer
    grille: str
    resolution: str
    grille_fixe: bool


# Rayonnement NASA : CERES SYN1deg 1° ; météo NASA : MERRA-2 0,5° (grille deux fois
# plus fine, donc moins de jumeaux) ; SARAH-3 et CAMS : services interpolés à 5 km
# (compte 0 et mise en garde de résolution).
_CERES = ("CERES SYN1deg", "1 deg (110 km)")
_MERRA = ("MERRA-2", "0.5 deg (55 km)")
_INTERP = "5 km"

_CONFIG: tuple[_ConfigSource, ...] = (
    # Rayonnement NASA (CERES 1°) : ghi sur 1991-2020, les quatre autres sur 2001-2020.
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
    # Météo NASA (MERRA-2 0,5°), tout sur 1991-2020.
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
    # Services interpolés à 5 km (compte 0 et mise en garde de résolution).
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


def _grouper_par_pixel(vecteurs: dict[int, tuple[float, ...]]) -> dict[int, list[int]]:
    """Pour chaque localité, les identifiants triés des autres localités au vecteur identique.

    Égalité exacte : deux séries presque égales sont deux points distincts. Une
    liste vide signifie que le point est seul dans sa cellule.
    """
    groupes: dict[tuple[float, ...], list[int]] = defaultdict(list)
    for loc_id, vec in vecteurs.items():
        groupes[vec].append(loc_id)
    jumeaux: dict[int, list[int]] = {}
    for membres in groupes.values():
        for loc_id in membres:
            jumeaux[loc_id] = sorted(m for m in membres if m != loc_id)
    return jumeaux


# Texte figé à l'octet près : les migrations qui ont créé ces lignes le rejouent sur une base
# neuve ; la migration ``reecrire_commentaires_degenerescence_pixel`` le réécrit ensuite en clair.
def _commentaire(cfg: _ConfigSource, grandeur: str, codes_jumeaux: list[str]) -> str:
    """Commentaire éditorial de la ligne : groupe de jumeaux sur grille fixe, mise en
    garde de résolution pour une source interpolée."""
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
            f"(meme pixel source) -> ne pas presenter comme des mesures independantes "
            f"(D-29 generalise)."
        )
    else:
        base = (
            f"Point resolu sur {cfg['grille']} ({cfg['resolution']}) : aucun autre point "
            f"partageant la cellule pour {grandeur}."
        )
    return base + _CAVEAT_CONFIANCE


def calculer_et_inserer_degenerescence(session: Session) -> int:
    """Calcule ``degenerescence_pixel`` et l'insère dans ``grandeurs_metier``.

    Pour chaque couple (source, grandeur) de ``_CONFIG``, lit les séries
    climatologiques mensuelles de toutes les localités, les groupe par vecteur
    identique et insère une ligne statique par localité. Renvoie le nombre de lignes
    insérées. Flush sans commit : l'appelant valide la transaction.
    """
    nb_insere = 0
    for cfg in _CONFIG:
        rows = session.execute(
            text(
                """
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
                  AND m.valide_au IS NULL AND m.statut <> 'deprecie'
                ORDER BY l.code, m.annee, m.mois
                """
            ),
            {"src": cfg["source_code"], "g": cfg["grandeur_code"], "pdeb": cfg["periode_debut"]},
        ).all()

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
            continue  # aucune série pour ce couple

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
                    "niveau_confiance_derive": NIVEAU_CONFIANCE_DERIVE,
                    "commentaire": _commentaire(cfg, cfg["grandeur_code"], codes_jumeaux),
                }
            )

        if lignes:
            session.execute(
                text(
                    """
                    INSERT INTO grandeurs_metier
                        (grandeur_code, localite_id, series_metadonnees_id,
                         periode_type, annee_debut, annee_fin, mois,
                         version_formule, valeur, niveau_confiance_derive,
                         commentaire_editorial)
                    VALUES
                        (:grandeur_code, :localite_id, :series_metadonnees_id,
                         :periode_type, :annee_debut, :annee_fin, :mois,
                         :version_formule, :valeur, :niveau_confiance_derive,
                         :commentaire)
                    """
                ),
                lignes,
            )
            nb_insere += len(lignes)

    session.flush()
    return nb_insere
