"""Données de seed pour la table ``localites`` (migration 011).

20 entités hiérarchiques compilées par Siba Kalivogui en mai 2026
(passe 2 de compilation, livrable v2 validé post-audit).
"""

from __future__ import annotations

from typing import Any

LOCALITES_SEED: list[dict[str, Any]] = [
    # ===== Continent (1) =====
    {
        "code": "afrique",
        "nom": "Afrique",
        "type_localite": "continent",
        "parent_code": None,
        "pays_iso3": None,
        "latitude": None,
        "longitude": None,
        "altitude_metres": None,
        "population_estimee": 1_515_140_849,
        "annee_population": 2024,
        "fuseau_horaire": None,
        "notes": (
            "Population UN World Population Prospects 2024 (medium-fertility variant), "
            "date de référence 2024-07-01. Coordonnées centroid non renseignées : entité "
            "structurelle racine, pas d'usage opérationnel NASA POWER prévu. "
            "Wikidata Q15. Source : https://population.un.org/wpp/. Cross-check "
            "StatisticsTimes.com. UN WPP consulté le 2026-05-09."
        ),
    },
    # ===== Pays (1) =====
    {
        "code": "gin",
        "nom": "Guinée",
        "type_localite": "pays",
        "parent_code": "afrique",
        "pays_iso3": "GIN",
        "latitude": 9.93280000,
        "longitude": -11.35800000,
        "altitude_metres": None,
        "population_estimee": 17_521_167,
        "annee_population": 2025,
        "fuseau_horaire": "Africa/Conakry",
        "notes": (
            "Wikidata Q1006. Coordonnées centroid géométrique calculé par Latitude.to "
            "(/map/gn/guinea), méthode explicite retenue ; Wikidata Q1006 P625 "
            "et Wikipedia Geography of Guinea donnent 11.000 / -10.000 = centre conventionnel "
            "arrondi au degré entier, convention différente. Population RGPH-4 résultats "
            "préliminaires (date de référence 2025-07-16, publication 2026-02-25, "
            "officialisation décret présidentiel 2026-03-06). Source : "
            "https://www.stat-guinee.org/.../Resultats_preliminaires_rgph_4.pdf. "
            "Latitude.to et INS-Guinée consultés le 2026-05-09."
        ),
    },
    # ===== Régions administratives (8) =====
    {
        "code": "gin_boke",
        "nom": "Région de Boké",
        "type_localite": "region_administrative",
        "parent_code": "gin",
        "pays_iso3": "GIN",
        "latitude": 10.93139000,
        "longitude": -14.28917000,
        "altitude_metres": None,
        "population_estimee": 1_628_656,
        "annee_population": 2025,
        "fuseau_horaire": "Africa/Conakry",
        "notes": (
            "Wikidata Q862611. Coordonnées du chef-lieu Boké ville (Wikidata Q891240, "
            "10°55'53\"N 14°17'21\"W), pas du centroid régional - convention CdC § 5.3. "
            "Population RGPH-4 préliminaires (référence 2025-07-16, publication "
            "2026-02-25, décret 2026-03-06). Source : "
            "https://fr.wikipedia.org/wiki/Région_de_Boké. Cross-check guineenews.org, "
            "guinee360.com, lindependant.org. Consulté le 2026-05-09."
        ),
    },
    {
        "code": "gin_conakry",
        "nom": "Région de Conakry",
        "type_localite": "region_administrative",
        "parent_code": "gin",
        "pays_iso3": "GIN",
        "latitude": 9.50917000,
        "longitude": -13.71222000,
        "altitude_metres": None,
        "population_estimee": 3_407_327,
        "annee_population": 2025,
        "fuseau_horaire": "Africa/Conakry",
        "notes": (
            "Wikidata Q1373230. Région-ville : coordonnées du centre administratif Kaloum "
            "(la région-ville n'a pas de ville chef-lieu distincte, CdC § 4.6 / E.15). "
            "Identiques à gin_conakry_kaloum, intentionnel. Population RGPH-4 préliminaires. "
            "Réforme du 18 janvier 2024 (loi L/2024/003/CNT) porte Conakry de 5 à 13 "
            "communes ; périmètre régional total inchangé, RGPH-4 couvre l'ensemble. "
            "Source : https://fr.wikipedia.org/wiki/Région_de_Conakry. Consulté le 2026-05-09."
        ),
    },
    {
        "code": "gin_faranah",
        "nom": "Région de Faranah",
        "type_localite": "region_administrative",
        "parent_code": "gin",
        "pays_iso3": "GIN",
        "latitude": 10.03333333,
        "longitude": -10.73333333,
        "altitude_metres": None,
        "population_estimee": 1_460_931,
        "annee_population": 2025,
        "fuseau_horaire": "Africa/Conakry",
        "notes": (
            "Wikidata Q870166. Coordonnées du chef-lieu Faranah ville (Wikidata Q597843, "
            "10°2'N 10°44'W), pas du centroid régional - CdC § 5.3. Wikipedia FR cite "
            "explicitement « 1 460 931 hab » avec source RGPH-4. Population RGPH-4 "
            "préliminaires. Source : https://fr.wikipedia.org/wiki/Région_de_Faranah. "
            "Cross-check presse guinéenne. Consulté le 2026-05-09."
        ),
    },
    {
        "code": "gin_kankan_region",
        "nom": "Région de Kankan",
        "type_localite": "region_administrative",
        "parent_code": "gin",
        "pays_iso3": "GIN",
        "latitude": 10.38333333,
        "longitude": -9.30000000,
        "altitude_metres": None,
        "population_estimee": 4_110_215,
        "annee_population": 2025,
        "fuseau_horaire": "Africa/Conakry",
        "notes": (
            "Wikidata Q870191. Coordonnées du chef-lieu Kankan ville (Wikidata Q874317, "
            "10°23'N 9°18'W) - CdC § 5.3. Identiques à gin_kankan, intentionnel. Région "
            "la plus peuplée de Guinée : 23,5 % de la population nationale, devant Conakry "
            "au RGPH-4 2025. Source : https://fr.wikipedia.org/wiki/Région_de_Kankan. "
            "Consulté le 2026-05-09."
        ),
    },
    {
        "code": "gin_kindia_region",
        "nom": "Région de Kindia",
        "type_localite": "region_administrative",
        "parent_code": "gin",
        "pays_iso3": "GIN",
        "latitude": 10.04972222,
        "longitude": -12.85416667,
        "altitude_metres": None,
        "population_estimee": 2_275_620,
        "annee_population": 2025,
        "fuseau_horaire": "Africa/Conakry",
        "notes": (
            "Wikidata Q868520. Coordonnées du chef-lieu Kindia ville (Wikidata Q997057, "
            "10°2'59\"N 12°51'15\"W) - CdC § 5.3. Identiques à gin_kindia, intentionnel. "
            "Population RGPH-4 préliminaires. Source : "
            "https://fr.wikipedia.org/wiki/Région_de_Kindia. Consulté le 2026-05-09."
        ),
    },
    {
        "code": "gin_labe_region",
        "nom": "Région de Labé",
        "type_localite": "region_administrative",
        "parent_code": "gin",
        "pays_iso3": "GIN",
        "latitude": 11.31666667,
        "longitude": -12.28333333,
        "altitude_metres": None,
        "population_estimee": 1_239_897,
        "annee_population": 2025,
        "fuseau_horaire": "Africa/Conakry",
        "notes": (
            "Wikidata Q868515. Coordonnées du chef-lieu Labé ville (Wikidata Q1020384, "
            "11°19'N 12°17'W) - CdC § 5.3. Identiques à gin_labe, intentionnel. Région "
            "située sur le massif du Fouta-Djalon (chef-lieu Labé à 1025 m, altitude "
            "détaillée dans gin_labe). Population RGPH-4 préliminaires. Source : "
            "https://fr.wikipedia.org/wiki/Région_de_Labé. Consulté le 2026-05-09."
        ),
    },
    {
        "code": "gin_mamou_region",
        "nom": "Région de Mamou",
        "type_localite": "region_administrative",
        "parent_code": "gin",
        "pays_iso3": "GIN",
        "latitude": 10.38333333,
        "longitude": -12.08333333,
        "altitude_metres": None,
        "population_estimee": 916_535,
        "annee_population": 2025,
        "fuseau_horaire": "Africa/Conakry",
        "notes": (
            "Wikidata Q1043650. Coordonnées du chef-lieu Mamou ville (Wikidata Q644131, "
            "10°23'N 12°5'W) - CdC § 5.3. Identiques à gin_mamou, intentionnel. Région la "
            "moins peuplée de Guinée : 5,2 % de la population nationale. Massif du "
            "Fouta-Djalon (chef-lieu à 746 m). Population RGPH-4 préliminaires. Source : "
            "https://fr.wikipedia.org/wiki/Région_de_Mamou. Consulté le 2026-05-09."
        ),
    },
    {
        "code": "gin_nzerekore_region",
        "nom": "Région de Nzérékoré",
        "type_localite": "region_administrative",
        "parent_code": "gin",
        "pays_iso3": "GIN",
        "latitude": 7.75222222,
        "longitude": -8.82166667,
        "altitude_metres": None,
        "population_estimee": 2_481_986,
        "annee_population": 2025,
        "fuseau_horaire": "Africa/Conakry",
        "notes": (
            "Wikidata Q870146. Coordonnées du chef-lieu Nzérékoré ville (Wikidata Q1002799, "
            "7°45'08\"N 8°49'18\"W) - CdC § 5.3. Identiques à gin_nzerekore, intentionnel. "
            "3e région la plus peuplée : 14,1 % de la population nationale, devant Kindia. "
            "Région forestière du sud-est, frontalière du Liberia, de la Côte d'Ivoire et "
            "de la Sierra Leone. Population RGPH-4 préliminaires. Source : "
            "https://fr.wikipedia.org/wiki/Région_de_Nzérékoré. Consulté le 2026-05-09."
        ),
    },
    # ===== Communes pilotes - villes chef-lieu (5) =====
    {
        "code": "gin_kankan",
        "nom": "Kankan",
        "type_localite": "commune",
        "parent_code": "gin_kankan_region",
        "pays_iso3": "GIN",
        "latitude": 10.38333333,
        "longitude": -9.30000000,
        "altitude_metres": 381,
        "population_estimee": 190_772,
        "annee_population": 2014,
        "fuseau_horaire": "Africa/Conakry",
        "notes": (
            "Wikidata Q874317. Population RGPH-3 2014 = 190 772 hab (Wikidata sourçant "
            "citypopulation.info → INS-Guinée). 4 valeurs documentées en compilation : "
            "190 772 RETENU (traçabilité INS), 193 830 (Larousse, périmètre sous-préfectoral), "
            "198 013 (Wikipedia EN, projection mal étiquetée), 198 717 (CdC v3.3 § 4.5, "
            "valeur non corroborée par les sources accessibles). Aire urbaine 2014 = 472 112 (Wikimonde) - NE PAS "
            "confondre avec commune. Coordonnées identiques à gin_kankan_region (CdC § 5.3). "
            "Note RGPH-4 : Wikipedia EN cite 410 542 pour 2026, NON retenu (CdC § 4.8.2). "
            "Altitude 381 m (CdC Annexe B + Kankan Airport 376 m). Source : "
            "https://www.wikidata.org/wiki/Q874317. Consulté le 2026-05-09."
        ),
    },
    {
        "code": "gin_kindia",
        "nom": "Kindia",
        "type_localite": "commune",
        "parent_code": "gin_kindia_region",
        "pays_iso3": "GIN",
        "latitude": 10.04972222,
        "longitude": -12.85416667,
        "altitude_metres": 368,
        "population_estimee": 169_119,
        "annee_population": 2014,
        "fuseau_horaire": "Africa/Conakry",
        "notes": (
            "Wikidata Q997057. Population RGPH-3 2014 = 169 119 hab (Larousse, citation "
            "directe « recensement de 2014 »). Wikidata P1082 sans valeur datée 2014. "
            "Cross-check : Wikimonde 182 280 = extrapolation 2016 NON retenu ; Wikipedia "
            "EN 181 126 = estimation 2008 NON retenu. Source officielle cukindia.org "
            "confirme « 10°03 lat N et 12°52 long W » (concordant à l'arrondi). "
            "Coordonnées identiques à gin_kindia_region (CdC § 5.3). Altitude 368 m "
            "(topographic-map.com, moyenne polygone). Mont Gangan (1 117 m) hors périmètre "
            "central. Source : https://www.larousse.fr/encyclopedie/ville/Kindia/127509. "
            "Consulté le 2026-05-09."
        ),
    },
    {
        "code": "gin_labe",
        "nom": "Labé",
        "type_localite": "commune",
        "parent_code": "gin_labe_region",
        "pays_iso3": "GIN",
        "latitude": 11.31666667,
        "longitude": -12.28333333,
        "altitude_metres": 1025,  # source primaire ANM Guinée station LABE WMO 61809 (1025,36 m)
        "population_estimee": 141_375,
        "annee_population": 2014,
        "fuseau_horaire": "Africa/Conakry",
        "notes": (
            "[v3 post-clôture phase 1-1D : intégration source ANM Guinée découverte hors "
            "mission de compilation, GF-7]. "
            "Wikidata Q1020384. Population RGPH-3 2014 = 141 375 hab (Plan de Développement "
            "Local de la commune urbaine de Labé, PDL 2020-2024, citation directe : « selon "
            "le dernier recensement national de la population et de l'habitat de 2014, la "
            "population globale de la Commune est de 141 375 habitants dont 67 219 hommes "
            "et 74 156 femmes »). Source primaire commune urbaine officielle, plus fiable "
            "que Wikidata Q1020384 (107 695 sans année, possiblement RGPH-2 1996). "
            "Coordonnées identiques à gin_labe_region (CdC § 5.3). PDL cite 11°19' N, "
            "12°18' W - divergence d'1' sur lon vs Wikidata 12°17' = 1.8 km, dans la marge. "
            "Altitude 1025 m source primaire ANM Guinée station LABE (WMO 61809), valeur "
            "précise 1025,36 m, concordance à 0,36 m près avec valeur consensuelle "
            "précédente (Wikipedia EN « over 1,000 metres », Britannica 1 050 m, CdC v3.3 "
            "§ 4.7 1 025 m). Massif du Fouta-Djalon. Source : "
            "https://www.communelabe.org/web/pdl/. communelabe.org consulté le 2026-05-09 ; "
            "ANM Guinée consulté le 2026-05-09 (post-clôture phase 1-1D, cf. tag début de "
            "note)."
        ),
    },
    {
        "code": "gin_mamou",
        "nom": "Mamou",
        "type_localite": "commune",
        "parent_code": "gin_mamou_region",
        "pays_iso3": "GIN",
        "latitude": 10.38333333,
        "longitude": -12.08333333,
        "altitude_metres": 746,
        "population_estimee": 68_139,
        "annee_population": 2014,
        "fuseau_horaire": "Africa/Conakry",
        "notes": (
            "Wikidata Q644131. Population RGPH-3 2014 brut = 68 139 hab (Wikipedia FR Mamou, "
            "citation directe « Le troisième recensement, en 2014 (RGPH3), en dénombre "
            "68 139 »). [v2 corrigée post-audit : v1 retenait 93 304 = projection RGPH-3 à "
            "2017 publiée dans Annuaire stat INS-Guinée 2016 (nov 2017), confondue avec brut "
            "à cause du breakdown homme/femme]. 4 valeurs alternatives NON retenues : 88 670 "
            "(projection 2016), 93 304 (projection 2017), 318 981 [PIÈGE] = préfecture, "
            "731 188 [PIÈGE] = région. Altitude 746 m (Wikipedia FR explicite). Coordonnées "
            "identiques à gin_mamou_region (CdC § 5.3). Région la moins peuplée. Mamou "
            "ville-carrefour aux abords du Fouta-Djalon, mont Séré (950 m), mont Banga "
            "(1 176 m). Source : https://fr.wikipedia.org/wiki/Mamou_(Guinée). Consulté le "
            "2026-05-09."
        ),
    },
    {
        "code": "gin_nzerekore",
        "nom": "Nzérékoré",
        "type_localite": "commune",
        "parent_code": "gin_nzerekore_region",
        "pays_iso3": "GIN",
        "latitude": 7.75222222,
        "longitude": -8.82166667,
        "altitude_metres": 480,
        "population_estimee": 195_027,
        "annee_population": 2014,
        "fuseau_horaire": "Africa/Conakry",
        "notes": (
            "Wikidata Q1002799. Population RGPH-3 2014 = 195 027 hab (Wikipedia EN « 2014 "
            "census population was 195,027 »). 3 sources concordantes : Wikipedia EN, "
            "handwiki.org, archive Wikipedia EN 2020. Cross-check historique : 107 329 hab "
            "au recensement 1996 ; croissance attribuée aux réfugiés des guerres civiles "
            "voisines. Coordonnées identiques à gin_nzerekore_region (CdC § 5.3). Altitude "
            "480 m (Wikipedia FR ; cross-checks Maptons 479 m, en-academic 482 m, Météo La "
            "Chaîne 485 m). Ville la plus peuplée de Guinée forestière ; relief accidenté "
            "(monts Götö 450 m, Hononye, Kwéléyé 350 m). Note : Nzérékoré plus peuplée que "
            "Kankan au RGPH-3 2014 (195 027 vs 190 772) ; hiérarchie inversée au RGPH-4 "
            "2025. Source : https://en.wikipedia.org/wiki/Nzérékoré. Consulté le 2026-05-09."
        ),
    },
    # ===== Communes pilotes - Conakry historiques pré-réforme 2024 (5) =====
    {
        "code": "gin_conakry_kaloum",
        "nom": "Kaloum",
        "type_localite": "commune",
        "parent_code": "gin_conakry",
        "pays_iso3": "GIN",
        "latitude": 9.50917000,
        "longitude": -13.71222000,
        "altitude_metres": 6,  # [À VÉRIFIER] - presqu'île de Tombo niveau mer
        "population_estimee": 62_675,
        "annee_population": 2014,
        "fuseau_horaire": "Africa/Conakry",
        "notes": (
            "Périmètre des 5 communes historiques pré-réforme 2024, choix de modélisation "
            "pilote phase 1. La réforme du 18 janvier 2024 porte Conakry à 13 communes ; "
            "intégration prévue en phase 2. "
            "Wikidata Q3192252. Population RGPH-3 2014 = 62 675 hab (Wikipedia EN, cross-check "
            "guineematin.com 2014). Coordonnées identiques à gin_conakry (CdC § 4.6 / E.15). "
            "Périmètre stable post-réforme 2024 (loi L/2024/003/CNT ne modifie pas son "
            "territoire, contrairement à Matoto/Ratoma). Toutefois le périmètre 2014 inclut "
            "l'île de Kassa par convention historique : Kassa était quartier de Kaloum lors "
            "du RGPH-3 ; érigée en 6e commune urbaine par loi du 16 mars 2021 (sources : "
            "guinee360.com, guineematin.com, Wikipedia FR Île de Kassa, INS-Guinée Annuaire "
            "stat 2022 nov 2023, SNG-WOFI). Impact mineur sur 62 675 (Kassa sparsely "
            "populated en 2014, 35 000 hab estimés en 2023). Pour représentation post-2021, "
            "créer gin_conakry_kassa en phase 2. Altitude 6 m [À VÉRIFIER] - presqu'île "
            "de Tombo, niveau mer. Source : https://en.wikipedia.org/wiki/Kaloum. Consulté "
            "le 2026-05-09."
        ),
    },
    {
        "code": "gin_conakry_dixinn",
        "nom": "Dixinn",
        "type_localite": "commune",
        "parent_code": "gin_conakry",
        "pays_iso3": "GIN",
        "latitude": 9.55111000,
        "longitude": -13.67306000,
        "altitude_metres": 7,
        "population_estimee": 137_287,
        "annee_population": 2014,
        "fuseau_horaire": "Africa/Conakry",
        "notes": (
            "Périmètre des 5 communes historiques pré-réforme 2024, choix de modélisation "
            "pilote phase 1. La réforme du 18 janvier 2024 porte Conakry à 13 communes ; "
            "intégration prévue en phase 2. "
            "Wikidata Q3032606. Population RGPH-3 2014 = 137 287 hab (guineematin.com "
            "analyse RGPH-3, octobre 2014 ; Mapcarta confirme sourçant Wikipedia EN). "
            "Coordonnées Wikidata P625 non exposées dans snippets accessibles ; Mapcarta/OSM "
            "retenu (9°33'4\"N 13°40'23\"W). Périmètre 2014 inchangé par la réforme 2024 "
            "(Dixinn n'a pas été scindée). Comprend Université Gamal Abdel Nasser, Stade du "
            "28 Septembre, hôpital Donka. Altitude 7 m (Mapcarta). Source : "
            "https://mapcarta.com/17189318. Consulté le 2026-05-09."
        ),
    },
    {
        "code": "gin_conakry_matam",
        "nom": "Matam",
        "type_localite": "commune",
        "parent_code": "gin_conakry",
        "pays_iso3": "GIN",
        "latitude": 9.57631000,
        "longitude": -13.63411000,
        "altitude_metres": 27,
        "population_estimee": 143_658,
        "annee_population": 2014,
        "fuseau_horaire": "Africa/Conakry",
        "notes": (
            "Périmètre des 5 communes historiques pré-réforme 2024, choix de modélisation "
            "pilote phase 1. La réforme du 18 janvier 2024 porte Conakry à 13 communes ; "
            "intégration prévue en phase 2. "
            "Wikidata Q3298195. Population RGPH-3 2014 = 143 658 hab (Wikipedia EN, "
            "cross-check guineematin.com 2014). PIÈGE MÉTHODO ÉVITÉ : Wikipedia FR mentionne "
            "« extrapolation du recensement de 2014 » à 153 210 hab en 2016 - projection NON "
            "RETENUE (CdC § 4.8.2 RGPH-3 brut strict). Coordonnées Wikidata P625 précises "
            "(cebuano source, 9°34'34.7\"N 13°38'2.8\"W) ; Mapcarta donne 9.55206/-13.64958 "
            "(centre OSM différent, 3 km), Wikidata retenu pour homogénéité. Périmètre 2014 "
            "inchangé par la réforme 2024. Comprend marché Madina (le plus grand de "
            "Conakry). Altitude 27 m (Mapcarta). [v2 corrigée post-audit superviseur : "
            "ajout mention modélisation pilote § 2.1 manquante du CSV v1 - leçon GF-6]. "
            "Source : https://en.wikipedia.org/wiki/Matam,_Guinea. Consulté le 2026-05-09."
        ),
    },
    {
        "code": "gin_conakry_matoto",
        "nom": "Matoto",
        "type_localite": "commune",
        "parent_code": "gin_conakry",
        "pays_iso3": "GIN",
        "latitude": 9.57283000,
        "longitude": -13.60716000,
        "altitude_metres": 26,  # source primaire ANM Guinée station CONAKRY/GBESSIA WMO 61832 (25,79 m)
        "population_estimee": 670_310,
        "annee_population": 2014,
        "fuseau_horaire": "Africa/Conakry",
        "notes": (
            "[v3 post-clôture phase 1-1D : intégration source ANM Guinée découverte hors "
            "mission de compilation, GF-7]. "
            "Périmètre des 5 communes historiques pré-réforme 2024, choix de modélisation "
            "pilote phase 1. La réforme du 18 janvier 2024 porte Conakry à 13 communes ; "
            "intégration prévue en phase 2. "
            "Cette commune a été scindée par la réforme 2024 (Matoto → Matoto/Gbéssia/"
            "Tombolia) ; les données 2014 ici reflètent l'ancien périmètre élargi. "
            "Wikidata Q3299209. Population RGPH-3 2014 = 670 310 hab (Wikipedia EN + "
            "guineematin.com 2014). Loi L/2024/003/CNT du 18 janvier 2024 art. 2 : Matoto → "
            "Matoto (réduite) + Gbéssia + Tombolia. Pour représentation post-2024, créer 3 "
            "entités enfants en phase 2. Coordonnées Wikidata P625 non exposées ; "
            "latitude.to retenu (9°34'22.19\"N 13°36'25.79\"W). Matoto historique incluait "
            "l'aéroport Gbessia (depuis scission, Gbessia est commune autonome et abrite "
            "l'aéroport). Altitude 26 m source primaire ANM Guinée station CONAKRY/GBESSIA "
            "(WMO 61832, située à l'aéroport Gbessia, en plein dans le périmètre Matoto "
            "historique), valeur précise 25,79 m, concordance à 1,21 m près avec ancienne "
            "estimation par similarité Matam (27 m). Source : https://focusguinee.info/"
            "2024/01/19/scission-des-communes-de-ratoma-matoto-et-cie-que-dit-la-nouvelle-"
            "loi-adoptee-par-le-cnt/. focusguinee.info consulté le 2026-05-09 ; ANM Guinée "
            "consulté le 2026-05-09 (post-clôture phase 1-1D, cf. tag début de note)."
        ),
    },
    {
        "code": "gin_conakry_ratoma",
        "nom": "Ratoma",
        "type_localite": "commune",
        "parent_code": "gin_conakry",
        "pays_iso3": "GIN",
        "latitude": 9.58917000,
        "longitude": -13.65571000,
        "altitude_metres": 57,
        "population_estimee": 653_934,
        "annee_population": 2014,
        "fuseau_horaire": "Africa/Conakry",
        "notes": (
            "Périmètre des 5 communes historiques pré-réforme 2024, choix de modélisation "
            "pilote phase 1. La réforme du 18 janvier 2024 porte Conakry à 13 communes ; "
            "intégration prévue en phase 2. "
            "Cette commune a été scindée par la réforme 2024 (Ratoma → Ratoma/Lambanyi/"
            "Sonfonia) ; les données 2014 ici reflètent l'ancien périmètre élargi. "
            "Wikidata Q3420127. Population RGPH-3 2014 = 653 934 hab (Wikipedia EN, infobox "
            "citant « INS Guinea, accessed via Geohive » ; cross-check guineematin.com 2014). "
            "Loi L/2024/003/CNT du 18 janvier 2024 art. 2 : Ratoma → Ratoma (réduite) + "
            "Lambanyi + Sonfonia. Pour représentation post-2024, créer 3 entités enfants en "
            "phase 2. Coordonnées Mapcarta/OSM (9°35'21\"N 13°39'21\"W) plus précises "
            "que Wikipedia EN infobox (9.583/-13.650 arrondi à la minute). Centre dynamique "
            "ouest Conakry (vie nocturne, plage de Rogbane, marchés Cosa/Kipé). Altitude "
            "57 m (Mapcarta), cross-check Maptons 61 m. Source : "
            "https://en.wikipedia.org/wiki/Ratoma. Consulté le 2026-05-09."
        ),
    },
]


assert len(LOCALITES_SEED) == 20, f"Expected 20 localites, got {len(LOCALITES_SEED)}"

_codes_seen: set[str] = set()
for _entry in LOCALITES_SEED:
    _code = _entry["code"]
    assert _code not in _codes_seen, f"Code dupliqué dans LOCALITES_SEED : {_code!r}"
    _codes_seen.add(_code)
del _codes_seen, _entry, _code
