"""Données de seed pour la densification préfectorale (migration 085).

Référentiel administratif complet des **33 préfectures de Guinée** (la zone
spéciale de Conakry n'est pas une préfecture : elle a des communes directement,
hors périmètre densification). Source des codes 3-lettres : décret guinéen de
codification administrative 2025. Coordonnées : chef-lieu (ville éponyme),
Wikidata P625 recoupée GeoNames/OSM, compilation 2026-06-20 (recherche par
région, recoupement par point, vérification superviseur des 3 corrections).

Modélisation tranchée : chaque préfecture porte DEUX nœuds localités :

* un nœud ``prefecture`` ``gin_<slug>_prefecture`` (parent = région), qui porte
  le ``code_administratif_national`` du décret et les coordonnées du chef-lieu
  (comme les régions) ;
* une commune chef-lieu ``gin_<slug>`` (parent = la préfecture), **point
  d'ingestion solaire uniforme**, mêmes coordonnées.

Pour les **5 préfectures dont le chef-lieu est une capitale régionale déjà
ingérée** (Kankan, Kindia, Labé, Mamou, Nzérékoré - migration 011), seul le
nœud préfecture est créé ; la commune existante est **re-parentée** de la
région vers la préfecture (``REPARENTAGES``), coordonnées verrouillées inchangées.

Démographie : **NULL** pour tous les nouveaux nœuds (``population_estimee``
et ``annee_population`` toutes deux nulles). Les chiffres ville disponibles
mélangent les périmètres (ville / sous-préfecture / préfecture) et les années
(RGPH-3 2014 brut / extrapolations 2016 / RGPH-4 2025 préliminaire) : un seed à
périmètre incohérent serait un passif de qualité silencieux. La démographie sera
sourcée plus tard, homogène, sur le rapport INS RGPH primaire. Les 5 communes
existantes conservent leur démographie sourcée (inchangée).

Codes communes en collision (décision B, pas d'harmonisation) : les régions
``gin_boke`` et ``gin_faranah`` portent déjà le code ``gin_<slug>`` sans suffixe
``_region`` (asymétrie héritée : Boké et Faranah n'étaient pas des villes
pilotes). Plutôt que de re-signifier ces codes existants région -> commune
(anti-pattern : un identifiant ne change pas de sens en silence), les deux
communes chef-lieu en collision prennent le suffixe ``_centre``
(``gin_boke_centre``, ``gin_faranah_centre``), calqué sur la convention INS
« X-Centre » des communes urbaines. Additif, zéro mutation, zéro re-signification.
Les 26 autres communes neuves gardent ``gin_<slug>``.
"""

from __future__ import annotations

import re
from typing import Any

# Codes des régions parentes tels qu'existants en base (migration 011 ; AUCUN
# renommage). Boke et Faranah n'ont pas le suffixe _region (asymétrie héritée :
# pas des villes pilotes) ; on ne les renomme PAS (gestion _centre plus bas).
_R_BOKE = "gin_boke"
_R_FARANAH = "gin_faranah"
_R_KINDIA = "gin_kindia_region"
_R_MAMOU = "gin_mamou_region"
_R_LABE = "gin_labe_region"
_R_KANKAN = "gin_kankan_region"
_R_NZEREKORE = "gin_nzerekore_region"


# Descripteur par préfecture (source de vérité auditable, une ligne par
# préfecture, 33 au total). ``existante`` = code de la commune chef-lieu déjà
# seedée (migration 011) à re-parenter, ou ``None`` si nouvelle commune à créer.
# ``lat`` / ``lon`` = coordonnées chef-lieu retenues (deg. décimaux). ``coord``
# = traçabilité de la coordonnée (Q-ID Wikidata + recoupement, flags inclus).
PREFECTURES_GUINEE: list[dict[str, Any]] = [
    # ===== Région de Boké (5) =====
    {
        "slug": "boffa",
        "nom": "Boffa",
        "region": _R_BOKE,
        "code_admin": "BFA",
        "lat": 10.16667000,
        "lon": -14.03333000,
        "existante": None,
        "coord": "Wikidata Q2908600 (P625, arrondie ~km) ; recoupee GeoNames 2422968.",
    },
    {
        "slug": "boke",
        "nom": "Boke",
        "region": _R_BOKE,
        "code_admin": "BKE",
        "lat": 10.93139000,
        "lon": -14.28917000,
        "existante": None,
        "coord": "Wikidata Q891240 (P625) ; recoupee GeoNames 2422924 (0,2 km).",
    },
    {
        "slug": "fria",
        "nom": "Fria",
        "region": _R_BOKE,
        "code_admin": "FRI",
        "lat": 10.36676000,
        "lon": -13.58253000,
        "existante": None,
        "coord": (
            "Wikidata Q1456064 = GeoNames 2420884 (concordants, 10.3668/-13.5825) ; "
            "valeur Wikipedia 10.45/-13.5333 divergente 9,5 km NON retenue, a lever au sol."
        ),
    },
    {
        "slug": "gaoual",
        "nom": "Gaoual",
        "region": _R_BOKE,
        "code_admin": "GAL",
        "lat": 11.75000000,
        "lon": -13.20000000,
        "existante": None,
        "coord": "Wikidata Q3095240 (P625, arrondie) = GeoNames 2420826.",
    },
    {
        "slug": "koundara",
        "nom": "Koundara",
        "region": _R_BOKE,
        "code_admin": "KDR",
        "lat": 12.48333000,
        "lon": -13.30000000,
        "existante": None,
        "coord": "Wikidata Q985374 (P625, arrondie) = GeoNames 2418596.",
    },
    # ===== Région de Faranah (4) =====
    {
        "slug": "dabola",
        "nom": "Dabola",
        "region": _R_FARANAH,
        "code_admin": "DBL",
        "lat": 10.75000000,
        "lon": -11.11670000,
        "existante": None,
        "coord": "Wikidata Q1100543 (P625) ; recoupee GeoNames 2422442 (1,2 km).",
    },
    {
        "slug": "dinguiraye",
        "nom": "Dinguiraye",
        "region": _R_FARANAH,
        "code_admin": "DGR",
        "lat": 11.29055600,
        "lon": -10.71222200,
        "existante": None,
        "coord": "Wikidata Q1006013 (P625) ; recoupee GeoNames 2421903 (0,06 km).",
    },
    {
        "slug": "faranah",
        "nom": "Faranah",
        "region": _R_FARANAH,
        "code_admin": "FRN",
        "lat": 10.03333300,
        "lon": -10.73333300,
        "existante": None,
        "coord": "Wikidata Q597843 (P625) ; recoupee GeoNames 2421273 (1,35 km).",
    },
    {
        "slug": "kissidougou",
        "nom": "Kissidougou",
        "region": _R_FARANAH,
        "code_admin": "KDG",
        "lat": 9.18333300,
        "lon": -10.10000000,
        "existante": None,
        "coord": "Wikidata Q1358885 (P625) ; recoupee GeoNames 2419472 (0,17 km).",
    },
    # ===== Région de Kindia (5 : 4 nouvelles + Kindia existante) =====
    {
        "slug": "coyah",
        "nom": "Coyah",
        "region": _R_KINDIA,
        "code_admin": "CYA",
        "lat": 9.70000000,
        "lon": -13.38333300,
        "existante": None,
        "coord": "Wikidata Q1021470 (P625) ; recoupee OSM/GeoNames 2422457 (1,2 km).",
    },
    {
        "slug": "dubreka",
        "nom": "Dubreka",
        "region": _R_KINDIA,
        "code_admin": "DBK",
        "lat": 9.78972200,
        "lon": -13.49888900,
        "existante": None,
        "coord": (
            "Wikidata Q985362 (P625) ; recoupee GeoNames 2421535. Ecart 2 km en longitude "
            "vs OSM (-13.5170), a la limite du seuil ; valeur Wikidata retenue."
        ),
    },
    {
        "slug": "forecariah",
        "nom": "Forecariah",
        "region": _R_KINDIA,
        "code_admin": "FRC",
        "lat": 9.43250000,
        "lon": -13.08070000,
        "existante": None,
        "coord": (
            "CORRECTION : coordonnee OSM/Wikipedia EN 9.4325/-13.0807, recoupees concordantes ; "
            "coordonnee Wikidata Q3077142 P625 (9.717/-13.167) REJETEE (erronee 32 km, "
            "verifiee par superviseur 2026-06-20). GeoNames 2420985. Q-ID conserve comme "
            "identifiant d'entite, coordonnee Wikidata invalidee."
        ),
    },
    {
        "slug": "telimele",
        "nom": "Telimele",
        "region": _R_KINDIA,
        "code_admin": "TML",
        "lat": 10.90000000,
        "lon": -13.03330000,
        "existante": None,
        "coord": "Wikidata Q7862201 (P625) ; recoupee OSM/GeoNames 2414926 (0,25 km).",
    },
    {
        "slug": "kindia",
        "nom": "Kindia",
        "region": _R_KINDIA,
        "code_admin": "KDA",
        "lat": 10.04972222,
        "lon": -12.85416667,
        "existante": "gin_kindia",
        "coord": "Chef-lieu deja ingere (migration 011, Wikidata Q997057) ; coordonnees verrouillees.",
    },
    # ===== Région de Mamou (3 : 2 nouvelles + Mamou existante) =====
    {
        "slug": "dalaba",
        "nom": "Dalaba",
        "region": _R_MAMOU,
        "code_admin": "DLB",
        "lat": 10.69167000,
        "lon": -12.25000000,
        "existante": None,
        "coord": "Wikidata Q984798 (P625) = Wikipedia FR ; recoupee GeoNames 2422383.",
    },
    {
        "slug": "pita",
        "nom": "Pita",
        "region": _R_MAMOU,
        "code_admin": "PTA",
        "lat": 11.05960000,
        "lon": -12.39560000,
        "existante": None,
        "coord": "Wikidata Q1152701 (P625) = Wikipedia FR ; recoupee GeoNames 2416444 (0,6 km).",
    },
    {
        "slug": "mamou",
        "nom": "Mamou",
        "region": _R_MAMOU,
        "code_admin": "MMU",
        "lat": 10.38333333,
        "lon": -12.08333333,
        "existante": "gin_mamou",
        "coord": "Chef-lieu deja ingere (migration 011, Wikidata Q644131) ; coordonnees verrouillees.",
    },
    # ===== Région de Labé (5 : 4 nouvelles + Labé existante) =====
    {
        "slug": "koubia",
        "nom": "Koubia",
        "region": _R_LABE,
        "code_admin": "KBA",
        "lat": 11.58333300,
        "lon": -11.90000000,
        "existante": None,
        "coord": "Wikidata Q3199237 (P625) = GeoNames 2418764 (concordants).",
    },
    {
        "slug": "lelouma",
        "nom": "Lelouma",
        "region": _R_LABE,
        "code_admin": "LLM",
        "lat": 11.42570000,
        "lon": -12.68280000,
        "existante": None,
        "coord": (
            "CORRECTION : coordonnee OSM/Nominatim 11.4257/-12.6828 (ville, recoupee GeoNames "
            "2578880) ; coordonnee Wikidata Q3270350 P625 (11.183/-12.933) REJETEE (erronee "
            "38 km, verifiee par superviseur 2026-06-20). Q-ID conserve comme identifiant."
        ),
    },
    {
        "slug": "mali",
        "nom": "Mali",
        "region": _R_LABE,
        "code_admin": "MLI",
        "lat": 12.08333300,
        "lon": -12.30000000,
        "existante": None,
        "coord": (
            "Prefecture guineenne du Fouta-Djalon (PAS le pays Mali). Wikidata Q1019078 "
            "(P625) ; recoupee GeoNames 2417886 (0,5 km)."
        ),
    },
    {
        "slug": "tougue",
        "nom": "Tougue",
        "region": _R_LABE,
        "code_admin": "TGE",
        "lat": 11.44503000,
        "lon": -11.66422000,
        "existante": None,
        "coord": (
            "GeoNames 2414545 (11.44503/-11.66422, valeur fine retenue, concordante OSM 0,6 km) ; "
            "Wikidata Q7828837 P625 arrondie (11.45/-11.6833, 2,15 km) NON retenue."
        ),
    },
    {
        "slug": "labe",
        "nom": "Labe",
        "region": _R_LABE,
        "code_admin": "LBE",
        "lat": 11.31666667,
        "lon": -12.28333333,
        "existante": "gin_labe",
        "coord": "Chef-lieu deja ingere (migration 011, Wikidata Q1020384) ; coordonnees verrouillees.",
    },
    # ===== Région de Kankan (5 : 4 nouvelles + Kankan existante) =====
    {
        "slug": "kerouane",
        "nom": "Kerouane",
        "region": _R_KANKAN,
        "code_admin": "KRN",
        "lat": 9.26667000,
        "lon": -9.01667000,
        "existante": None,
        "coord": "Wikidata Q1152900 (P625) = GeoNames 2419622 (concordants).",
    },
    {
        "slug": "kouroussa",
        "nom": "Kouroussa",
        "region": _R_KANKAN,
        "code_admin": "KRS",
        "lat": 10.65000000,
        "lon": -9.88333000,
        "existante": None,
        "coord": "Wikidata Q731232 (P625) = GeoNames 2418437 (concordants).",
    },
    {
        "slug": "mandiana",
        "nom": "Mandiana",
        "region": _R_KANKAN,
        "code_admin": "MDN",
        "lat": 10.63333000,
        "lon": -8.68333000,
        "existante": None,
        "coord": "Wikidata Q6748057 (P625, entite ville) = GeoNames 2417795 (concordants).",
    },
    {
        "slug": "siguiri",
        "nom": "Siguiri",
        "region": _R_KANKAN,
        "code_admin": "SGR",
        "lat": 11.41889000,
        "lon": -9.16444000,
        "existante": None,
        "coord": "Wikidata Q1100303 (P625) ; recoupee GeoNames 2415703 (0,6 km).",
    },
    {
        "slug": "kankan",
        "nom": "Kankan",
        "region": _R_KANKAN,
        "code_admin": "KKA",
        "lat": 10.38333333,
        "lon": -9.30000000,
        "existante": "gin_kankan",
        "coord": "Chef-lieu deja ingere (migration 011, Wikidata Q874317) ; coordonnees verrouillees.",
    },
    # ===== Région de Nzérékoré (6 : 5 nouvelles + Nzérékoré existante) =====
    {
        "slug": "beyla",
        "nom": "Beyla",
        "region": _R_NZEREKORE,
        "code_admin": "BLA",
        "lat": 8.68981000,
        "lon": -8.64816000,
        "existante": None,
        "coord": (
            "Wikidata Q1076707 : declaration P625 8.68981/-8.64816 RETENUE (= GeoNames 2423126, "
            "0,06 km) ; seconde declaration P625 (8.683/-8.8) REJETEE (erronee 16 km, verifiee)."
        ),
    },
    {
        "slug": "gueckedou",
        "nom": "Gueckedou",
        "region": _R_NZEREKORE,
        "code_admin": "GKD",
        "lat": 8.56667000,
        "lon": -10.13333000,
        "existante": None,
        "coord": "Wikidata Q740687 (P625) ; recoupee GeoNames 2420562 (0,09 km).",
    },
    {
        "slug": "lola",
        "nom": "Lola",
        "region": _R_NZEREKORE,
        "code_admin": "LLA",
        "lat": 7.79970000,
        "lon": -8.52860000,
        "existante": None,
        "coord": (
            "OSM/Nominatim 7.7997/-8.5286 (place=town) retenue ; Wikidata Q1099959 (P625 "
            "arrondie 7.8/-8.533, 0,5 km, concordante). GeoNames non confirme (page 403)."
        ),
    },
    {
        "slug": "macenta",
        "nom": "Macenta",
        "region": _R_NZEREKORE,
        "code_admin": "MCT",
        "lat": 8.55000000,
        "lon": -9.46666700,
        "existante": None,
        "coord": "Wikidata Q1032064 (P625) ; recoupee Wikipedia FR (0,6 km). GeoNames 2417987.",
    },
    {
        "slug": "yomou",
        "nom": "Yomou",
        "region": _R_NZEREKORE,
        "code_admin": "YMU",
        "lat": 7.56600000,
        "lon": -9.25330000,
        "existante": None,
        "coord": "Wikidata Q784157 (P625) = GeoNames 2414077 (concordants).",
    },
    {
        "slug": "nzerekore",
        "nom": "Nzerekore",
        "region": _R_NZEREKORE,
        "code_admin": "ZKR",
        "lat": 7.75222222,
        "lon": -8.82166667,
        "existante": "gin_nzerekore",
        "coord": "Chef-lieu deja ingere (migration 011, Wikidata Q1002799) ; coordonnees verrouillees.",
    },
]


def _commune_code(slug: str, region: str) -> str:
    """Code de la commune chef-lieu.

    Suffixe ``_centre`` si ``gin_<slug>`` entre en collision avec le code de la
    région parente (cas Boke/Faranah, régions sans suffixe ``_region``) : on
    n'écrase jamais ni ne re-signifie un code existant.
    """
    base = f"gin_{slug}"
    return f"{base}_centre" if base == region else base


# Normalisation : code commune effectif par préfecture (commune existante déjà
# ingérée si capitale régionale, sinon code chef-lieu avec gestion de collision).
for _p in PREFECTURES_GUINEE:
    _p["commune_code"] = _p["existante"] or _commune_code(_p["slug"], _p["region"])
del _p


def _note_prefecture(p: dict[str, Any]) -> str:
    """Note du nœud préfecture (code décret + traçabilité coordonnée)."""
    return (
        f"Prefecture de {p['nom']}, code administratif national {p['code_admin']} "
        f"(decret guineen de codification 2025). Coordonnees du chef-lieu (Sec. 5.3), "
        f"identiques a la commune {p['commune_code']}. {p['coord']} "
        f"Demographie NULL (D7) : a sourcer homogene sur rapport INS RGPH primaire. "
        f"Densification prefectorale Etape 1, compile 2026-06-20."
    )


def _note_commune(p: dict[str, Any]) -> str:
    """Note de la commune chef-lieu (point d'ingestion solaire)."""
    return (
        f"Chef-lieu de la prefecture de {p['nom']}, point d'ingestion solaire uniforme "
        f"(modelisation (a), spec Etape 1 Sec. 5.3). {p['coord']} "
        f"Demographie NULL (D7) : perimetres RGPH heterogenes au niveau ville, a sourcer "
        f"homogene ulterieurement. Densification prefectorale Etape 1, compile 2026-06-20."
    )


# Nœuds préfecture à insérer (33). Parent = région (résolu en migration).
PREFECTURE_NODES: list[dict[str, Any]] = [
    {
        "code": f"gin_{p['slug']}_prefecture",
        "nom": f"Prefecture de {p['nom']}",
        "type_localite": "prefecture",
        "parent_code": p["region"],
        "code_administratif_national": p["code_admin"],
        "pays_iso3": "GIN",
        "latitude": p["lat"],
        "longitude": p["lon"],
        "altitude_metres": None,
        "population_estimee": None,
        "annee_population": None,
        "fuseau_horaire": "Africa/Conakry",
        "notes": _note_prefecture(p),
    }
    for p in PREFECTURES_GUINEE
]


# Nouvelles communes chef-lieu à insérer (28). Parent = la préfecture homonyme.
# Code = gin_<slug>, suffixe _centre pour Boke/Faranah (collision région, cf. _commune_code).
NOUVELLES_COMMUNES: list[dict[str, Any]] = [
    {
        "code": p["commune_code"],
        "nom": p["nom"],
        "type_localite": "commune",
        "parent_code": f"gin_{p['slug']}_prefecture",
        "code_administratif_national": None,
        "pays_iso3": "GIN",
        "latitude": p["lat"],
        "longitude": p["lon"],
        "altitude_metres": None,
        "population_estimee": None,
        "annee_population": None,
        "fuseau_horaire": "Africa/Conakry",
        "notes": _note_commune(p),
    }
    for p in PREFECTURES_GUINEE
    if p["existante"] is None
]


# Re-parentage des 5 communes capitales régionales existantes (région -> préfecture).
REPARENTAGES: list[dict[str, str]] = [
    {"commune": p["existante"], "prefecture": f"gin_{p['slug']}_prefecture"}
    for p in PREFECTURES_GUINEE
    if p["existante"] is not None
]


# === Garde-fous de cohérence (exécutés à l'import) ===

assert len(PREFECTURES_GUINEE) == 33, f"Attendu 33 prefectures, obtenu {len(PREFECTURES_GUINEE)}"
assert len(PREFECTURE_NODES) == 33, f"Attendu 33 noeuds prefecture, obtenu {len(PREFECTURE_NODES)}"
assert len(NOUVELLES_COMMUNES) == 28, (
    f"Attendu 28 nouvelles communes, obtenu {len(NOUVELLES_COMMUNES)}"
)
assert len(REPARENTAGES) == 5, f"Attendu 5 re-parentages, obtenu {len(REPARENTAGES)}"

# Codes décret uniques et conformes au format CHECK ^[A-Z]{3}$.
_codes_admin = [p["code_admin"] for p in PREFECTURES_GUINEE]
assert len(set(_codes_admin)) == 33, "Codes administratifs decret dupliques"
for _ca in _codes_admin:
    assert len(_ca) == 3 and _ca.isupper() and _ca.isalpha(), f"Code decret invalide : {_ca!r}"

# Codes localités uniques (33 préfectures + 28 communes) et conformes ^[a-z][a-z0-9_]*$.
_tous_codes = [n["code"] for n in PREFECTURE_NODES] + [c["code"] for c in NOUVELLES_COMMUNES]
assert len(set(_tous_codes)) == len(_tous_codes), "Codes localites dupliques dans le seed"
_motif = re.compile(r"^[a-z][a-z0-9_]*$")
for _code in _tous_codes:
    assert _motif.match(_code), f"Code localite non conforme au CHECK : {_code!r}"

# Décision B : Boke/Faranah en collision sont suffixées _centre, jamais re-signifiées.
_codes_communes = {c["code"] for c in NOUVELLES_COMMUNES}
assert {"gin_boke_centre", "gin_faranah_centre"} <= _codes_communes, (
    "Communes en collision Boke/Faranah doivent etre suffixees _centre"
)
assert not ({"gin_boke", "gin_faranah"} & _codes_communes), (
    "gin_boke / gin_faranah sont des regions : ne jamais les re-signifier en communes"
)

del _codes_admin, _ca, _tous_codes, _motif, _code, _codes_communes
