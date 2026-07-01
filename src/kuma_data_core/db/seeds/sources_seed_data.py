"""Données de seed pour la table ``sources`` (migration 012).

9 sources éditoriales compilées par Siba Kalivogui en mai 2026
(livrable v4.2 figé).

Composition :
- 3 bases de données opérationnelles (nasa_power, ecmwf_era5,
  anm_guinee_stations)
- 2 normes techniques opérationnelles (iec_61724_1_2021,
  wmo_8_2024)
- 4 sources hydro structurelles (wmo_grdc, wwf_hydrosheds,
  iec_60041_1991, wmo_168_2008)

Conventions appliquées :
- Mention structurelle normée octet-à-octet identique sur les 4 sources
  hydro structurelles (constante ``_MENTION_BETA2_NORMEE`` factorisée).
- ISBN natifs IEC inscrits pour ``iec_60041_1991`` (283182222X,
  format ISBN-10 pré-2007) et ``iec_61724_1_2021`` (9782832210025,
  vérifié sur le webstore IEC le 2026-05-10).
- Acknowledgement formalisé dans notes pour les 9 sources
  (citation canonique / officielle / suggérée selon publication).
- Année dans le code pour les 4 normes éditées, sans année pour
  les 5 bases continues / référentiels évolutifs.
- Scope Volume I retenu pour ``wmo_8_2024`` (DOI suffixe ``/1``)
  et ``wmo_168_2008`` (ISBN Vol I distinct).
"""

from __future__ import annotations

from datetime import date
from typing import Any

# Mention structurelle normée : paragraphe canonique à propager
# octet-à-octet identique sur les 4 sources hydro structurelles
# (wmo_grdc, wwf_hydrosheds, iec_60041_1991, wmo_168_2008). Toute
# modification ici doit être propagée en simultané sur les 4 sources.
_MENTION_BETA2_NORMEE: str = (
    "Source de référence structurelle (hydrologie) : schéma de validation "
    "conçu, population effective différée. Le pipeline hydro (ingestion des "
    "débits, calculs de productible, endpoints) n'est pas encore actif."
)

_DATE_CONSULTATION_1_1E: date = date(2026, 5, 10)


SOURCES_SEED: list[dict[str, Any]] = [
    # ===== Bases de données opérationnelles (3) =====
    {
        "code": "nasa_power",
        "titre": (
            "NASA POWER - Prediction Of Worldwide Energy Resources : Solar and "
            "Meteorological Data Archive"
        ),
        "auteurs": None,
        "organisation": "NASA Langley Research Center (LaRC)",
        "type_source": "base_donnees",
        "annee_publication": None,
        "date_consultation": _DATE_CONSULTATION_1_1E,
        "url": "https://power.larc.nasa.gov/",
        "doi": None,
        "isbn": None,
        "metadonnees": {
            "granularite_spatiale": (
                "0.5° × 0.625° (météorologie, MERRA-2) ; 1° × 1° (solaire, CERES SYN1deg)"
            ),
            "granularite_temporelle": "horaire | journalier | mensuel | climatologique",
            "couverture_temporelle_debut": "1984-01-01",
            "couverture_temporelle_fin": "ongoing (NRT, climat-quality après 2-3 mois)",
            "acces": (
                "API REST publique gratuite (rate-limited), Data Access Viewer "
                "(DAV), AWS Open Data Registry"
            ),
        },
        "fiabilite": "haute",
        "langue": "en",
        "notes": (
            "Source primaire du substrat physique guinéen. "
            "Objet calibré au sens des 3 couches Kuma (couche A - calibration). "
            "NASA Langley Research Center (LaRC) opérateur, programme NASA Earth "
            "Science Division. Version actuelle : POWER Data v10. "
            "Bifurcation des couvertures temporelles selon la communauté de "
            "paramètres : (a) Météorologie 1981-01-01 → présent (source amont : "
            "NASA GMAO MERRA-2) ; (b) Solaire 1984-01-01 → présent (sources amont : "
            "NASA SRB 4.0-IP 1984-2000, puis CERES SYN1deg + FLASHFlux à partir de "
            "2001). La valeur couverture_temporelle_debut du JSONB retient "
            "1984-01-01, valeur effective pour la communauté Kuma phase 1 = RE "
            "(Renewable Energy, focus solaire). Communautés exposées par NASA POWER : "
            "AG (Agroclimatology), RE (Renewable Energy), SB (Sustainable Buildings). "
            "Convention de communauté Kuma à acter en spec préparatoire 1-2a. "
            "Méthodologie publique documentée sur `power.larc.nasa.gov/docs/methodology/`. "
            "Convention de code DT-1 : `nasa_power` retient l'organisme producteur "
            "scientifique (NASA LaRC) + thème (POWER, nom du projet). Pas d'année "
            "dans le code : la base évolue par versions glissantes (v10 actuelle), "
            "sans rupture éditoriale justifiant un nouveau code par millésime. "
            "Acknowledgement officiel (cf. `power.larc.nasa.gov/docs/referencing/`) "
            "à inclure dans toute publication exploitant les données : « The data "
            "was obtained from National Aeronautics and Space Administration (NASA) "
            "Langley Research Center's Prediction Of Worldwide Energy Resources "
            "(POWER) project funded through the NASA Earth Science Division. » "
            "NASA POWER demande également de spécifier le triplet service name + "
            "version number + date accessed (exemple : « obtained from the POWER "
            "Project's Hourly 2.x.x version on 2026-05-10 »). Cette exigence se "
            "traduira en convention applicative phase 1-2b pour les réponses API "
            "Kuma qui exposent des données dérivées de NASA POWER. "
            "Pas de mention β2 normée DT-8 (source primaire phase 1 du substrat "
            "physique guinéen, opérationnelle phase 1 pour solaire + climat, hors "
            "liste des 4 sources hydro structurelles). "
            "Consulté le 2026-05-10."
        ),
    },
    {
        "code": "ecmwf_era5",
        "titre": (
            "ECMWF ERA5 - Fifth Generation Atmospheric Reanalysis of the Global "
            "Climate (Copernicus Climate Change Service)"
        ),
        "auteurs": None,
        "organisation": "European Centre for Medium-Range Weather Forecasts (ECMWF)",
        "type_source": "base_donnees",
        "annee_publication": 2018,
        "date_consultation": _DATE_CONSULTATION_1_1E,
        "url": "https://cds.climate.copernicus.eu/datasets/reanalysis-era5-single-levels",
        "doi": "10.24381/cds.adbb2d47",
        "isbn": None,
        "metadonnees": {
            "granularite_spatiale": (
                "0.25° × 0.25° (CDS regridded) ; 31 km natif (grille gaussienne "
                "réduite TCo639) ; 137 niveaux verticaux jusqu'à 0.01 hPa (80 km)"
            ),
            "granularite_temporelle": (
                "horaire (native) | journalier (statistiques pré-calculées) | "
                "mensuel (moyennes pré-calculées)"
            ),
            "couverture_temporelle_debut": "1940-01-01",
            "couverture_temporelle_fin": (
                "ongoing (latence 5 jours ; release préliminaire ERA5T pouvant "
                "différer de la version finale 2-3 mois plus tard)"
            ),
            "acces": (
                "Copernicus Climate Data Store (CDS) API + portail web, gratuit "
                "avec inscription, licence Copernicus (acknowledgment requis)"
            ),
        },
        "fiabilite": "haute",
        "langue": "en",
        "notes": (
            "Source de cross-check principal au sens des 3 couches Kuma (couche B). "
            "Compatible solaire + climat (opérationnel phase 1) ; paramètres hydro "
            "(precipitation, évapotranspiration, runoff via ERA5-Land) conçus pour "
            "cross-check β2 mais non activés en phase 1 (cf. CdC § 4.1). "
            "Producteur scientifique : ECMWF, organisation intergouvernementale "
            "européenne (32 États membres et coopérants), opérant pour le Copernicus "
            "Climate Change Service (C3S) financé par l'Union européenne. "
            "Distribution publique via la Climate Data Store (CDS, "
            "`cds.climate.copernicus.eu`). Article scientifique de référence : "
            "Hersbach, H. et al. (2020), « The ERA5 global reanalysis », Q.J.R. "
            "Meteorol. Soc., 146: 1999-2049, DOI : 10.1002/qj.3803. Article "
            "extension à 1940 : Bell, B. et al. (2021), « The ERA5 global "
            "reanalysis: Preliminary extension to 1950 », Q.J.R. Meteorol. Soc., "
            "147(741): 4186-4227, DOI : 10.1002/qj.4174. "
            "Convention de code DT-1 : `ecmwf_era5` retient le producteur "
            "scientifique (ECMWF, tutelle internationale). Le distributeur public "
            "(Copernicus C3S) est un programme opéré par ECMWF, donc pas de tutelle "
            "distincte. Code conforme à l'ordre DT-1 : tutelle internationale > "
            "responsable actuel > producteur historique. "
            "Variantes ERA5 disponibles sur le CDS, chacune avec DOI distinct : "
            "single levels (DOI retenu, dataset pivot Kuma phase 1), pressure "
            "levels, monthly means, daily statistics, time-series, ensemble. Pour "
            "1-1E, fiche pivot = single levels (couverture paramètres la plus large "
            "incluant radiation solaire, températures, vents, humidité). "
            "ERA5-Land (variante land-only haute résolution : 9 km natif / 0.1° × "
            "0.1° regridded, couverture 1950-présent, 50 variables surface dont "
            "runoff, soil moisture, evaporation) : non seedée dans la présente "
            "fiche. À acter potentiellement comme source distincte `ecmwf_era5_land` "
            "en future passe (passe complémentaire 1-1E ou phase 2+) pour appui "
            "spécifique sur le vecteur hydro β2 (DOI ERA5-Land monthly : "
            "10.24381/cds.68d2bb30 ; cf. Muñoz Sabater 2019). Décision technique à "
            "acter (DT-X potentielle) si besoin avéré phase 2+. En 1-1E, périmètre "
            "source = ERA5 atmospheric reanalysis uniquement. "
            "Acknowledgement requis (licence Copernicus) : « Generated using "
            "Copernicus Climate Change Service Information [Year] ». À intégrer en "
            "convention applicative phase 1-2b pour les réponses API Kuma exposant "
            "des données dérivées d'ERA5. "
            "Pas de mention β2 normée DT-8 (ERA5 n'appartient pas à la liste des 4 "
            "sources hydro structurelles ; il est multi-vecteurs et opérationnel "
            "phase 1 pour solaire + climat). L'usage hydro d'ERA5 est cependant "
            "conçu pour cross-check référentiel sans activation phase 1. "
            "Consulté le 2026-05-10."
        ),
    },
    {
        "code": "anm_guinee_stations",
        "titre": (
            "ANM Guinée - Réseau d'observation météorologique national (stations "
            "synoptiques, agrométéorologiques, climatologiques)"
        ),
        "auteurs": None,
        "organisation": "Agence Nationale de la Météorologie de Guinée (ANM)",
        "type_source": "base_donnees",
        "annee_publication": None,
        "date_consultation": _DATE_CONSULTATION_1_1E,
        "url": "https://anmeteo.gov.gn/",
        "doi": None,
        "isbn": None,
        "metadonnees": {
            "granularite_spatiale": (
                "ponctuelle (stations) - réseau national couvrant les 4 régions "
                "naturelles (Basse Guinée, Moyenne Guinée, Haute Guinée, Guinée "
                "Forestière) ; 28 stations identifiées avec WIGOS, à confirmer "
                "en demande officielle ANM (cf. notes)"
            ),
            "granularite_temporelle": (
                "horaire | journalier | mensuel selon paramètre ; observations "
                "synoptiques typiques aux heures standards WMO (00, 06, 12, 18 UTC)"
            ),
            "couverture_temporelle_debut": None,
            "couverture_temporelle_fin": "ongoing",
            "acces": (
                "demande officielle requise (pas d'API publique de données brutes) ; "
                "site anmeteo.gov.gn diffuse bulletins agrégés, alertes CAP, "
                "prévisions"
            ),
        },
        "fiabilite": "haute",
        "langue": "fr",
        "notes": (
            "Calibreur principal météo locale au sens des 3 couches Kuma (couche A "
            "- calibration : référence terrain pour ajuster NASA POWER et ERA5 par "
            "confrontation aux observations sol guinéennes). Source la plus "
            "stratégique du substrat physique guinéen pour la spécificité projet "
            "Kuma - sans calibration locale, NASA POWER et ERA5 restent des modèles "
            "globaux non ajustés au contexte ouest-africain (humidité, brume sèche, "
            "harmattan, mousson). "
            "Établissement Public Administratif sous tutelle du Ministère des "
            "Transports, doté de la personnalité juridique et d'autonomie "
            "financière et de gestion. Mission : météorologie, climatologie, "
            "astronomie. Couvre observation, traitement, analyse, diffusion. "
            "Bulletin Agrométéorologique Mensuel comme produit phare (analyse "
            "répartition précipitations, humidité du sol, satisfaction hydrique "
            "cultures, évolution saison). "
            "Réseau de stations : 28 stations avec identifiants WIGOS et altitudes "
            "officielles ont été recensées en mission 1-1D (mai 2026) lors d'une "
            "trouvaille post-clôture (cf. spec 1-1D, ANM 2 concordances actées : "
            "Labé station 61809, Matoto station 61832 ; cas Kindia/Mamou laissés en "
            "convention non tranchée). Liste exhaustive et coordonnées précises à "
            "confirmer en demande officielle ANM. Représentation Guinée via WMO "
            "World Weather Information Service couvre quelques villes (Conakry "
            "notamment). "
            "Convention de code DT-1 : `anm_guinee_stations` retient l'organisme "
            "producteur national (ANM, responsable actuel depuis l'érection en "
            "Agence post-2022, suite au décret consécutif au conseil des ministres "
            "du 8 septembre 2022 ; mission héritée de l'ancienne Direction "
            "Nationale de la Météorologie - DNM) + thème (stations = réseau "
            "d'observation). Pas d'année dans le code (référentiel évolutif, "
            "pattern NASA POWER / ECMWF ERA5). Pas de tutelle internationale dans "
            "le code parce que l'ANM est l'agence nationale guinéenne (les "
            "standards WMO/WIGOS sont des cadres techniques externes, pas des "
            "tutelles administratives - distinction conforme au principe DT-1 qui "
            "privilégie la tutelle administrative effective). "
            "GF-1 fortement applicable : pas d'API publique de données brutes "
            "(séries temporelles GHI, température, humidité, vent, précipitations). "
            "Métadonnées du réseau (liste stations, identifiants WIGOS, altitudes) "
            "partiellement publiques via WMO WIGOS. Données mesurées accessibles "
            "uniquement par demande officielle, partenariat institutionnel, ou "
            "potentiellement via projets bilatéraux (ex. coopération ANM avec "
            "partenaires nationaux et internationaux mentionnée sur le site). "
            "Direction Générale et tutelle ministérielle (mai 2026) - utiles pour "
            "contact officiel : DG actuel Dr René Tato Loua ; Ministre de tutelle "
            "Ousmane Gaoual Diallo, Ministre des Transports. "
            "Projet CLIMAGUI (Climat et Météorologie pour la Guinée), lancé en "
            "octobre 2025, financé par l'Agence Française de Développement (AFD) à "
            "hauteur de 6 millions d'euros sur 5 ans, coordonné par l'ANM. Vise le "
            "développement de services digitaux adaptés aux besoins des acteurs "
            "économiques guinéens (secteurs portuaires, aéronautiques, agricoles). "
            "Fenêtre d'opportunité potentielle pour partenariat Kuma ou accès "
            "facilité aux données ANM dans le cadre du volet digital de CLIMAGUI. "
            "À évaluer en passe de contact officiel. "
            "Dettes éditoriales projet (à résoudre par contact officiel ANM "
            "Guinée) : couverture temporelle_debut effective des séries de stations "
            "principales (a priori plusieurs décennies pour les stations "
            "synoptiques historiques de Conakry, Labé, Kankan, Faranah, Nzérékoré, "
            "Boké, Kindia) ; liste exhaustive et à jour des stations actives avec "
            "coordonnées, identifiants WIGOS, altitude, paramètres mesurés, "
            "fréquence d'échantillonnage ; conditions de licence et usage des "
            "données pour projet privé ; modalités d'accès (frais, conventions, "
            "partenariats). "
            "Engagement WMO actif : la Guinée a fourni des commentaires officiels "
            "sur Volume I Chapitres 6 et 7 + Volume III Chapitre 5 de la "
            "Preliminary 2024 Edition de WMO-No.8 (cf. fiche `wmo_8_2024`). "
            "Confirme l'alignement éditorial Kuma sur des normes que la Guinée "
            "elle-même contribue à établir. "
            "Contact officiel : `guineametservice@gmail.com` - email officiel "
            "exposé via le flux CAP RSS du domaine institutionnel anmeteo.gov.gn "
            "(vérifié 2026-05-10). Domaine de messagerie gmail.com reflet du "
            "contexte des NMHS (National Meteorological and Hydrological Services) "
            "africains qui n'ont pas systématiquement d'infrastructure email "
            "institutionnelle propre - non anormal. "
            "Pas de mention β2 normée DT-8 (calibreur multi-vecteurs météo, hors "
            "liste des 4 sources hydro structurelles). Note implicite : si une "
            "mission hydro β2 future nécessite des observations de débits ou de "
            "précipitations stationnelles, l'ANM Guinée pourrait être un calibreur "
            "secondaire, à acter en future passe. "
            "Citation suggérée : « Agence Nationale de la Météorologie de Guinée "
            "(ANM), Réseau national d'observation météorologique. Conakry, Guinée. "
            "Site : anmeteo.gov.gn ». "
            "Convention applicative phase 1-2b : exposer la traçabilité des données "
            "ANM Guinée (organisme producteur, identifiant station WIGOS lorsque "
            "disponible, date d'observation, paramètre mesuré) dans les réponses "
            "API Kuma exposant des données calibrées par les stations sol "
            "guinéennes (couche A - calibration). "
            "Consulté le 2026-05-10."
        ),
    },
    # ===== Normes techniques opérationnelles (2) =====
    {
        "code": "iec_61724_1_2021",
        "titre": (
            "IEC 61724-1:2021 - Photovoltaic system performance - Part 1: Monitoring (Edition 2.0)"
        ),
        "auteurs": None,
        "organisation": "International Electrotechnical Commission (IEC)",
        "type_source": "norme_technique",
        "annee_publication": 2021,
        "date_consultation": _DATE_CONSULTATION_1_1E,
        "url": "https://webstore.iec.ch/en/publication/65561",
        "doi": None,
        "isbn": "9782832210025",
        "metadonnees": {
            "editeur": "International Electrotechnical Commission (IEC)",
            "comite_technique": "TC 82 - Solar photovoltaic energy systems",
            "edition_millesimee": "2021 (Edition 2.0)",
        },
        "fiabilite": "haute",
        "langue": "en",
        "notes": (
            "Norme opérationnelle phase 1 pour le vecteur solaire. Couche C des 3 "
            "couches Kuma (post-traitement éditorial Kuma : conventions "
            "méthodologiques IEC appliquées aux données brutes pour produire les "
            "grandeurs métier finales - performance ratio, yield, irradiance "
            "d'incidence, etc.). Définit la terminologie, les équipements, les "
            "méthodes de monitoring et d'analyse de la performance des systèmes "
            "photovoltaïques. Définit deux classes d'exactitude pour les systèmes "
            "de monitoring (Class A et Class B) à partir de la 2ème édition "
            "(l'ancienne Class C de l'édition 2017 est renommée Class B en 2021, "
            "l'ancienne Class B 2017 étant durcie). "
            "ICS code : 27.160 (Solar energy engineering). Comité technique : IEC "
            "TC 82 (Solar photovoltaic energy systems). Édition 2.0 publiée le "
            "2021-07-21, annule et remplace l'édition 1.0 de 2017. Évolutions "
            "techniques majeures 2021 vs 2017 : introduction du monitoring des "
            "systèmes bifaciaux, mise à jour des exigences sur les capteurs "
            "d'irradiance, mise à jour des mesures de salissure (soiling) basée sur "
            "nouvelles technologies, passage de 3 à 2 classes d'exactitude (Class A "
            "et Class B) - l'ancienne Class C de 2017 est renommée en nouvelle "
            "Class B de 2021, l'ancienne Class B 2017 étant durcie. "
            "Convention de code DT-1 : `iec_61724_1_2021` retient l'organisme "
            "producteur (IEC, tutelle internationale), la référence (61724 = "
            "série « PV system performance », couvrant Part 1 Monitoring + Part 2 "
            "Capacity evaluation method TS:2016 + Part 3 Energy evaluation method "
            "TS:2016 ; Part 1 traite spécifiquement du monitoring opérationnel), la "
            "partie (1 = Monitoring), et l'édition millésimée (2021). Présence de "
            "l'année dans le code, contrairement à `nasa_power` ou `ecmwf_era5` : "
            "justifiée parce que les éditions de normes sont des ruptures "
            "éditoriales avec changements techniques significatifs (2017 → 2021 "
            "ci-dessus), qui justifient un code distinct par millésime. Convention "
            "transverse normes éditées initialisée par cette fiche (1ère "
            "occurrence), confirmée sur les 3 normes éditées suivantes de la passe "
            "(`wmo_8_2024`, `iec_60041_1991`, `wmo_168_2008`). Cohérent avec DT-7 "
            "où metadonnees->>'edition_millesimee' peut spécifier des amendements "
            "ultérieurs sans changer le code (par exemple « 2021+A1:YYYY » si "
            "amendement ultérieur, code stable). "
            "ISBN natif IEC `9782832210025` (vérifié par consultation du webstore "
            "IEC le 2026-05-10 : page produit officielle "
            "https://webstore.iec.ch/en/publication/65561 expose l'ISBN dans la "
            "fiche produit). Les dérivées nationales BSI EN IEC 61724-1:2021 ont un "
            "ISBN distinct `978-0-539-06005-8` mais sortent du périmètre source IEC "
            "(cf. DT-9 du CdC v2.2). "
            "Accès au texte intégral : paywall IEC Webstore (478 USD pour la "
            "version standard, 635 USD pour la version Redline avec changements "
            "2017→2021 trackés). Page produit IEC publique fournit les métadonnées "
            "canoniques (titre, abstract, comité, ICS, ISBN, édition). GF-1 "
            "applicable : source primaire (texte intégral) inatteignable sans "
            "achat ; métadonnées vérifiables publiquement. "
            "Citation canonique : « IEC 61724-1:2021, Photovoltaic system "
            "performance - Part 1: Monitoring, International Electrotechnical "
            "Commission, Edition 2.0, July 2021 ». "
            "Convention applicative phase 1-2b : application des conventions PV "
            "monitoring IEC 61724-1:2021 (Class A/B, exigences irradiance, mesures "
            "soiling, calcul performance ratio) à propager dans les réponses API "
            "Kuma calculant des grandeurs métier solaires (couche C - "
            "post-traitement éditorial). "
            "Pas de mention β2 normée DT-8 (norme solaire opérationnelle phase 1, "
            "hors liste des 4 sources hydro structurelles). "
            "Consulté le 2026-05-10."
        ),
    },
    {
        "code": "wmo_8_2024",
        "titre": (
            "WMO-No.8 (CIMO Guide) - Guide to Instruments and Methods of "
            "Observation, Volume I - Measurement of Meteorological Variables, "
            "2024 edition"
        ),
        "auteurs": None,
        "organisation": "World Meteorological Organization (WMO)",
        "type_source": "norme_technique",
        "annee_publication": 2024,
        "date_consultation": _DATE_CONSULTATION_1_1E,
        "url": "https://library.wmo.int/idurl/4/68695",
        "doi": "10.59327/WMO/CIMO/1",
        "isbn": "9789263100085",
        "metadonnees": {
            "editeur": "World Meteorological Organization (WMO)",
            "comite_technique": (
                "INFCOM/SC-MINT (Standing Committee on Measurements, "
                "Instrumentation and Traceability) - Editorial Board ; "
                "anciennement CIMO (Commission for Instruments and Methods of "
                "Observation)"
            ),
            "edition_millesimee": (
                "2024 edition (digital, 601 pages - chiffre attribué au "
                "Volume I, à reconfirmer en passe 2 ; 5 volumes depuis 2018, "
                "scope fiche = Volume I)"
            ),
        },
        "fiabilite": "haute",
        "langue": "en",
        "notes": (
            "Méta-norme métrologique météo opérationnelle phase 1 (vecteur solaire "
            "+ climat de base). Couche C des 3 couches Kuma (post-traitement "
            "éditorial Kuma : conventions WMO appliquées aux mesures météo pour "
            "produire les grandeurs métier conformes aux usages internationaux). "
            "Surnommé « CIMO Guide » (héritage du nom historique de la Commission "
            "for Instruments and Methods of Observation, désormais INFCOM/SC-MINT "
            "depuis la réforme WMO 2019). "
            "Scope de la présente fiche : Volume I - Measurement of Meteorological "
            "Variables (température, pression, humidité, vent surface, "
            "précipitations), édition 2024 finalisée. C'est le volume pertinent "
            "pour Kuma phase 1 (mesures météo de surface). Le DOI "
            "`10.59327/WMO/CIMO/1` et l'ISBN `978-92-63-10008-5` sont scope "
            "Volume I uniquement (le suffixe `/1` du DOI WMO/CIMO suit probablement "
            "le numéro de volume - à confirmer comme pattern transverse). "
            "Les autres volumes ont des éditions distinctes au moment de la "
            "compilation (mai 2026) : Volumes II-III « Provisional 2024 Edition » "
            "en cours de validation INFCOM-3 (Members' review en novembre 2025) ; "
            "Volume IV édition 2021 ; Volume V à confirmer. Si un usage Kuma futur "
            "nécessite un de ces autres volumes, créer une fiche dédiée avec ses "
            "identifiants propres (DT-X potentielle). "
            "Multilingue officiel : anglais (texte de référence), arabe, chinois, "
            "français, espagnol, russe - versions traduites disponibles via la WMO "
            "Library. "
            "Topics indexés : GSICS (Global Space-based Inter-Calibration System), "
            "AWOS (Automated Weather Observing System), WIGOS (WMO Integrated "
            "Global Observing System), Hydrometeorological/Meteorological "
            "instruments, Methodology. "
            "Convention de code DT-1 : `wmo_8_2024` retient l'organisme (WMO, "
            "tutelle internationale), la référence (8 = numéro de publication "
            "officielle WMO), l'édition millésimée (2024). Présence de l'année dans "
            "le code : justifiée parce que les éditions WMO sont des ruptures "
            "éditoriales avec changements techniques significatifs, cohérent avec "
            "la convention déjà appliquée à `iec_61724_1_2021`. Convention "
            "transverse normes éditées confirmée par 2ème occurrence. "
            "Accès : libre et gratuit, PDF téléchargeable directement depuis "
            "library.wmo.int - contraste majeur avec IEC 61724-1:2021 (paywall "
            "478 USD). Aucun GF-1 applicable. Anciennes éditions accessibles sur "
            "demande à `library@wmo.int`. "
            "DOI canonique : `10.59327/WMO/CIMO/1` - première source structurelle "
            "de la passe disposant d'un DOI canonique fiable (à la différence de "
            "NASA POWER qui utilise une citation textuelle, et IEC 61724-1:2021 "
            "qui s'identifie par son code IEC sans DOI). Pattern transverse à "
            "observer : les publications WMO modernes (post-2018) sont "
            "systématiquement DOI'ées via Crossref. "
            "Drift par rapport au CdC § 2.2 : le CdC énumère le code `wmo_8_2023` "
            "(provisoire à la date de cadrage initial mai 2026). L'édition publiée "
            "effective est 2024. Code corrigé en `wmo_8_2024` dans la présente "
            "fiche. Amendement CdC § 2.2 acté en passe consolidation "
            "post-compilation. Aucun impact doctrinal - seul le millésime du code "
            "change, l'identité de la source et son rôle dans la cartographie § 4.2 "
            "sont inchangés. "
            "Anecdote projet : la consultation Members' review de la Preliminary "
            "2024 Edition (novembre 2023 - mars 2024) a inclus des commentaires "
            "officiels de la Guinée sur Volume I Chapitres 6 et 7 et Volume III "
            "Chapitre 5, parmi un petit groupe de pays (Chine, Allemagne, "
            "Hong Kong, Italie, Japon, Corée du Sud, UK). Confirme l'engagement "
            "actif de l'ANM Guinée auprès de la WMO et l'alignement éditorial Kuma "
            "sur des normes que la Guinée elle-même contribue à établir. "
            "Citation canonique : « WMO, 2024 : Guide to Instruments and Methods "
            "of Observation (WMO-No. 8), 2024 edition. World Meteorological "
            "Organization, Geneva. ISBN 978-92-63-10008-5. DOI : "
            "10.59327/WMO/CIMO/1 ». "
            "Convention applicative phase 1-2b : la citation canonique de "
            "WMO-No.8 ci-dessus est à propager dans les réponses API Kuma "
            "exposant des données traitées selon les conventions du CIMO Guide "
            "(calibrations d'instruments météo, méthodes d'observation standards "
            "WMO). "
            "Pas de mention β2 normée DT-8 (méta-norme météo opérationnelle phase "
            "1, hors liste des 4 sources hydro structurelles). "
            "Consulté le 2026-05-10."
        ),
    },
    # ===== Sources hydro structurelles (4) =====
    {
        "code": "wmo_grdc",
        "titre": "WMO/GRDC - Global Runoff Data Centre (Global Runoff Database)",
        "auteurs": None,
        "organisation": (
            "Global Runoff Data Centre (GRDC), opéré par le Federal Institute of "
            "Hydrology (Bundesanstalt für Gewässerkunde - BfG), Koblenz, "
            "Allemagne, sous mandat de la World Meteorological Organization (WMO)"
        ),
        "type_source": "base_donnees",
        "annee_publication": None,
        "date_consultation": _DATE_CONSULTATION_1_1E,
        "url": "https://grdc.bafg.de/",
        "doi": None,
        "isbn": None,
        "metadonnees": {
            "granularite_spatiale": (
                "ponctuelle (gauging stations) ; > 11 000 stations à décembre "
                "2025 (10 836 en janvier 2025, croissance soutenue avec 1772 "
                "stations mises à jour en 2024) ; 43 pays ont contribué en 2025, "
                "44 en 2024 selon GRDC reviews ; durée moyenne par station 40 "
                "ans selon historique GRDC ; en Guinée stations attendues sur "
                "Niger, Sénégal, Gambie, Konkouré. Détails complémentaires "
                "(nombre cumulé exact de pays contributeurs, durée moyenne "
                "précise, stations Guinée) à confirmer en passe 2 via database "
                "statistics GRDC ; cf. notes."
            ),
            "granularite_temporelle": (
                "journalier (mean daily discharge) | mensuel (mean monthly discharge)"
            ),
            "couverture_temporelle_debut": (
                "1807 (la plus ancienne série en service est dans le bassin de "
                "la mer Baltique, selon paper BALTEX dataset Frontiers 2025 ; "
                "pays exact à confirmer en passe 2) ; couverture Guinée à "
                "confirmer en passe 2 (cf. notes)"
            ),
            "couverture_temporelle_fin": (
                "ongoing (mises à jour continues, lag inhérent à la soumission "
                "par services hydrologiques nationaux)"
            ),
            "acces": (
                "demande via Data Portal `grdc.bafg.de/data/data_portal/` "
                "(formulaire + agreement Terms of Use + Data Sharing "
                "Conditions) ; download link envoyé sous 24h par mail ; usage "
                "non-commercial uniquement ; non-redistribution ; format "
                "WaterML2 (standard WMO/OGC) parmi autres formats"
            ),
        },
        "fiabilite": "haute",
        "langue": "en",
        "notes": (
            _MENTION_BETA2_NORMEE + " "
            "Calibreur hydro principal au sens des 3 couches Kuma (couche A - "
            "calibration : référence terrain pour les modèles globaux de débit) ; "
            "rôle β2 phase 1 = référentiel uniquement, validation effective phase "
            "2+. Source hydro structurelle 1/4 du périmètre β2 phase 1 (les 3 "
            "autres : `wwf_hydrosheds`, `iec_60041_1991`, `wmo_168_2008`). "
            "Histoire et gouvernance : GRDC créé officiellement opérationnel le "
            "1988-11-14 ; lignée historique : Decade Hydrologique Internationale "
            "UNESCO (1965) → publication monumentale « The Discharge of Selected "
            "Rivers of the World » (1969-1984, avec mises à jour 1988 incorporant "
            "les nouvelles données dans la base GRDC opérationnelle) → Institute "
            "for Bioclimatology and Applied Meteorology, Université de Munich "
            "(1982) → transfert au BfG, Koblenz (1984) → opérationnel (1988). "
            "Mandat WMO acté par les Résolutions WMO Congress XII n° 21 (1995) et "
            "WMO Congress XIII n° 25 (1999). Endorsement WMO Climate Data Catalogue "
            "acté au Cg-18. "
            "Steering committee international encadrant les activités GRDC : WMO, "
            "UNESCO, UNEP, IAHS (International Association of Hydrological "
            "Sciences), partner data centres. "
            "Activité récente documentée : 15ème réunion du Steering Committee "
            "international tenue en juin 2024 (cf. GRDC Happy New Year 2025). WMO "
            "State of Global Water Resources reports (annuels, dernier publié le "
            "18 septembre 2025 pour le millésime 2024) : GRDC en pilier de "
            "production. Croissance documentée du périmètre des rapports : 713 "
            "stations dans 26 pays en 2023 ; 2777 stations dans 41 pays en 2024. "
            "Datasets dérivés notables (cf. GRDC review 2025) : GRDC-Caravan "
            "extension (data paper 2025), BALTEX dataset (Frontiers 2025, "
            "extension régionale Baltique). Hors périmètre direct Kuma (régionaux "
            "européens) mais cités pour traçabilité - fiches Kuma futures possibles "
            "si pertinence avérée. "
            "Réseaux dérivés et programmes contributifs : GTN-R (Global Terrestrial "
            "Network for River Discharge) - composante hydro de GTN-H, "
            "officiellement accréditée « GCOS affiliated network » depuis mars "
            "2025 ; GCOS Baseline River Network - > 300 gauging stations près des "
            "embouchures des grands fleuves mondiaux ; contributions à GEWEX "
            "(Global Energy and Water Exchanges Project), CliC (Climate and "
            "Cryosphere) du WCRP, GTN-H, GEOSS. "
            "Convention de code DT-1 : `wmo_grdc` retient la tutelle internationale "
            "(WMO, mandat scientifique supérieur acté par résolutions Cg) + "
            "thème (grdc). Le BfG (responsable opérationnel actuel) n'apparaît pas "
            "dans le code parce qu'il est opérateur technique sous mandat WMO. "
            "Cohérent avec l'ordre DT-1 : tutelle internationale > responsable "
            "actuel > producteur historique. Pattern transverse confirmé : pour les "
            "centres opérant sous auspices WMO/UNESCO/etc. avec hébergement "
            "national, retenir la tutelle internationale dans le code. "
            "Pas de DOI canonique pour la base GRDC. Pattern WMO post-2018 DOI'é "
            "(observé sur `wmo_8_2024` Volume I) non appliqué au GRDC - la base "
            "utilise une citation textuelle référencée comme NASA POWER. Ce "
            "contraste confirme que le pattern « DOI WMO post-2018 » est restreint "
            "aux publications-guides (CIMO Guide, etc.) et non aux bases de "
            "données opérationnelles. "
            "Citation officielle requise (Terms of Use GRDC) : « Global Runoff "
            "Data Centre of WMO. 56068 Koblenz, Germany: Federal Institute of "
            "Hydrology (BfG), [Date of retrieval: YYYY-MM-DD] ». Cette exigence se "
            "traduira en convention applicative phase 2+ pour les réponses API "
            "Kuma exposant des données dérivées du GRDC. "
            "Licence d'usage : non-commercial uniquement, non-redistribution à des "
            "tiers ou au grand public (y compris via Internet), citation requise. "
            "Conditions à vérifier précisément avec le projet Kuma au moment de "
            "l'activation phase 2+ (le statut de Kuma - média éditorial vs "
            "commercial - peut affecter l'éligibilité). "
            "GF-1 modéré : pas de paywall financier mais accès conditionnel à un "
            "agreement formel et un délai de 24h. Métadonnées du réseau "
            "(catalogue stations) accessibles via le portail. Données mesurées "
            "(séries de débits) accessibles via demande conforme. "
            "GF-4 non applicable : pas de millésime éditorial (base évolutive, "
            "contrastant avec normes IEC/WMO). "
            "Adresse postale : 56068 Koblenz, Germany. Email contact : "
            "`grdc@bafg.de`. Page contact officielle : `grdc.bafg.de/contact/`. "
            "Consulté le 2026-05-10."
        ),
    },
    {
        "code": "wwf_hydrosheds",
        "titre": (
            "WWF/HydroSHEDS - Hydrological data and maps based on SHuttle "
            "Elevation Derivatives at multiple Scales (réseaux fluviaux, "
            "bassins versants, MNT hydrologiquement conditionné)"
        ),
        "auteurs": None,
        "organisation": "World Wildlife Fund (WWF) - WWF US Conservation Science Program",
        "type_source": "base_donnees",
        "annee_publication": 2008,
        "date_consultation": _DATE_CONSULTATION_1_1E,
        "url": "https://www.hydrosheds.org/",
        "doi": None,
        "isbn": None,
        "metadonnees": {
            "granularite_spatiale": (
                "raster + vector multi-résolution : 3 arc-seconds (90 m à "
                "l'équateur) à 5 minutes (10 km) ; couverture globale à "
                "l'exception des régions > 60°N (qualité dégradée pour cause "
                "d'absence de données SRTM, fallback HYDRO1k USGS) ; couverture "
                "pleinement nominale pour la Guinée et l'Afrique de l'Ouest"
            ),
            "granularite_temporelle": (
                "snapshot non temporel (référentiel topologique-hydrologique "
                "dérivé du DEM SRTM 2000-02-11/22, donc topologie représentative "
                "de l'état observé en février 2000)"
            ),
            "couverture_temporelle_debut": "2000-02-11 (acquisition SRTM)",
            "couverture_temporelle_fin": (
                "2000-02-22 (snapshot SRTM ; représentativité topologique stable "
                "post-acquisition pour les bassins guinéens, hors aménagements "
                "hydroélectriques majeurs récents - Kaléta 2015, Souapiti 2020+, "
                "Amaria en construction - qui peuvent avoir modifié localement "
                "la topologie post-SRTM)"
            ),
            "acces": (
                "libre (free for both non-commercial and commercial use) ; "
                "download direct via data.hydrosheds.org ; alternative "
                "programmatique via Google Earth Engine (catalogue "
                "`WWF/HydroSHEDS/...` : 03VFDEM, 03CONDEM, 03DIR à 3 arc-sec ; "
                "30CONDEM, 30DIR à 30 arc-sec ; HydroBASINS niveaux 9 et 12) ; "
                "License Agreement annexée à la Technical Documentation v1.4"
            ),
        },
        "fiabilite": "haute",
        "langue": "en",
        "notes": (
            _MENTION_BETA2_NORMEE + " "
            "Topologie hydro principale au sens des 3 couches Kuma (couche C - "
            "post-traitement éditorial : référentiel structurel raster + vector "
            "pour réseau fluvial, bassins versants, ordres de Strahler, flow "
            "directions, flow accumulations) ; rôle β2 phase 1 = référentiel "
            "uniquement, validation effective phase 2+. Source hydro structurelle "
            "2/4 du périmètre β2 phase 1 (les 3 autres : `wmo_grdc`, "
            "`iec_60041_1991`, `wmo_168_2008`). Distinction avec GRDC : "
            "HydroSHEDS = topologie sans mesures, GRDC = mesures stationnelles "
            "ponctuelles. Complémentaires. "
            "Datasets fournis (suite intégrée) : Core data products v1 (DEM "
            "original, DEM hydrologiquement conditionné, flow directions, flow "
            "accumulations, land mask, sink grids) ; Secondary data products "
            "(HydroBASINS - sous-bassins emboîtés hiérarchiques selon codification "
            "Pfafstetter ; HydroRIVERS - réseau fluvial vectorisé ; HydroLAKES - "
            "lacs et réservoirs globaux ; HydroATLAS - 50+ attributs "
            "hydro-environnementaux par tronçon de fleuve et sous-bassin) ; "
            "Produit dérivé récent (2025) : GLWD v2 (Global Lakes and Wetlands "
            "Database v2, Lehner et al. 2025), successeur de GLWD v1 (Lehner & "
            "Döll 2004), couvrant 18.2 millions de km² de zones humides à 15 "
            "arc-seconds (500 m à l'équateur). Hors scope phase 1 mais pertinent "
            "pour Kuma futur si extension agro-écologie / plaines inondables / "
            "mangroves côtières guinéennes (sous-mission potentielle phase 2+, à "
            "acter si besoin avéré). Hébergé sur hydrosheds.org. "
            "Versions : v1.1 (version courante effective phase 1) - Technical "
            "Documentation v1.4 (avril 2022) ; basée sur la mission Shuttle Radar "
            "Topography Mission (SRTM) 2000 à 3 arc-seconds (90 m) ; lignée 2008 "
            "publication initiale → améliorations itératives → v1.1 stable. v2.0 "
            "(en développement, release graduelle débutant en 2025 selon "
            "`hydrosheds.org/about`) - basée sur TanDEM-X (DLR) à résolution "
            "native 12 m, processed à 1 arc-seconde (30 m à l'équateur) - gain "
            "de résolution majeur vs v1 (3 arc-seconds = 90 m). Production en "
            "collaboration DLR + McGill University + Confluvio Consulting + WWF "
            "(calendrier initial 2024 dans certaines pages partenaires non "
            "actualisées). Régions > 60°N released en premier (zones les plus "
            "défaillantes en v1). Pour Kuma phase 1, v1.1 reste pleinement "
            "opérationnel sur la Guinée. v2 pourrait justifier une fiche distincte "
            "ou un amendement de fiche en passe ultérieure si la couverture "
            "Afrique de l'Ouest est released avec changements significatifs. "
            "Partenaires historiques v1 : WWF US, U.S. Geological Survey (USGS), "
            "International Centre for Tropical Agriculture (CIAT), The Nature "
            "Conservancy (TNC), Center for Environmental Systems Research, "
            "University of Kassel (Germany). "
            "Convention de code DT-1 : `wwf_hydrosheds` retient l'organisme "
            "producteur principal (WWF, responsable actuel et historique du "
            "programme HydroSHEDS) + thème (hydrosheds, nom du produit). Pas de "
            "tutelle internationale formelle (WWF est une ONG internationale mais "
            "pas une organisation intergouvernementale au sens strict de DT-1). "
            "Pas d'année dans le code (base évolutive par versions glissantes, "
            "pattern NASA POWER / ECMWF ERA5 / WMO-GRDC). v2 future ne justifiera "
            "probablement pas un nouveau code projet : la fiche métadonnée "
            "distinguera les versions. "
            "Citations scientifiques fondatrices (DOI requis si Kuma cite "
            "académiquement) : Lehner, B., Verdin, K., Jarvis, A. (2008). « New "
            "global hydrography derived from spaceborne elevation data. » Eos, "
            "Transactions American Geophysical Union, 89(10): 93-94. DOI : "
            "`10.1029/2008EO100001` (confirmé via AGU/Wiley page formelle Eos). "
            "Lehner, B., Grill, G. (2013). « Global river hydrography and network "
            "routing: baseline data and new approaches to study the world's large "
            "river systems. » Hydrological Processes 27(15): 2171-2186 "
            "(HydroBASINS / HydroRIVERS) [DOI à confirmer en passe 2]. "
            "Licence : free for non-commercial and commercial use - contraste "
            "majeur avec WMO/GRDC qui interdit l'usage commercial. License "
            "Agreement annexée à la Technical Documentation v1.4 (Annexe A). Pour "
            "Kuma (statut éditorial à clarifier), la permissivité HydroSHEDS "
            "facilite l'usage transverse sans contrainte de licence. "
            "Citation suggérée (acknowledgement) : « HydroSHEDS database, World "
            "Wildlife Fund (WWF), version 1.1, accessed via hydrosheds.org on "
            "2026-05-10. Lehner, B., Verdin, K., Jarvis, A. (2008). New global "
            "hydrography derived from spaceborne elevation data. Eos 89(10): "
            "93-94. » "
            "Convention applicative phase 2+ : exposer la traçabilité des éléments "
            "topologiques hydro HydroSHEDS (réseau fluvial, bassins versants, "
            "ordres de Strahler, identifiants HydroBASINS Pfafstetter) dans les "
            "réponses API Kuma exposant des données hydrologiques structurées "
            "(couche C - post-traitement éditorial). Différé cohérent avec le "
            "statut β2 du vecteur hydro phase 1. "
            "GF-1 non applicable (accès libre direct via portail). GF-4 non "
            "applicable au code (base évolutive sans année), mais à appliquer à "
            "la version en métadonnées (v1.1 actuel à confirmer en passe 2). "
            "Spécificité Guinée : couverture pleinement nominale en v1.1 (3 "
            "arc-seconds), région < 60°N. Topologie représentative bonne pour les "
            "bassins Niger Supérieur, Sénégal (Bafing/Bakoye), Gambie, Konkouré, "
            "mais à confronter avec les aménagements hydroélectriques majeurs "
            "post-2000 (Kaléta, Souapiti, Amaria) qui modifient localement la "
            "topologie réelle vs SRTM 2000. Cohérence à acter en passe d'ingestion "
            "phase 2+. "
            "Consulté le 2026-05-10."
        ),
    },
    {
        "code": "iec_60041_1991",
        "titre": (
            "IEC 60041:1991 - Field acceptance tests to determine the hydraulic "
            "performance of hydraulic turbines, storage pumps and pump-turbines "
            "(Edition 3.0, avec Corrigendum 1 de mars 1996 inclus)"
        ),
        "auteurs": None,
        "organisation": "International Electrotechnical Commission (IEC)",
        "type_source": "norme_technique",
        "annee_publication": 1991,
        "date_consultation": _DATE_CONSULTATION_1_1E,
        "url": "https://webstore.iec.ch/en/publication/154",
        "doi": None,
        "isbn": "283182222X",
        "metadonnees": {
            "editeur": "International Electrotechnical Commission (IEC)",
            "comite_technique": "TC 4 - Hydraulic turbines",
            "edition_millesimee": (
                "3.0 (1991-11-30) avec Corrigendum 1 (mars 1996) ; Stability "
                "date 2025 - date de revue planifiée par l'IEC, pas date de "
                "remplacement ; norme courante en vigueur à mai 2026 "
                "[À reverifier en passe 2 phase 2+ si une nouvelle édition a "
                "été publiée]"
            ),
        },
        "fiabilite": "haute",
        "langue": "en",
        "notes": (
            _MENTION_BETA2_NORMEE + " "
            "Norme de référence internationale pour les essais de réception sur "
            "site des machines hydrauliques (turbines, pompes d'accumulation, "
            "pompes-turbines), tous types et toutes tailles - impulse, réaction, "
            "Pelton, Francis, Kaplan, etc. Couche C des 3 couches Kuma "
            "(post-traitement éditorial : convention IEC appliquée aux calculs de "
            "productible et performance hydroélectrique). Source hydro "
            "structurelle 3/4 du périmètre β2 phase 1 (les 3 autres : `wmo_grdc`, "
            "`wwf_hydrosheds`, `wmo_168_2008`). "
            "Spécifie les méthodes d'essai applicables, la rédaction des règles "
            "de tests, les méthodes de calcul des résultats, et le contenu du "
            "rapport final. Détermine si les garanties contractuelles ont été "
            "satisfaites. ICS code : 27.140 (Hydraulic energy engineering) - "
            "distinct du 27.160 (Solar energy engineering) de `iec_61724_1_2021`. "
            "Lignée historique : 1ère édition IEC 41:1963 (« International code "
            "for the field acceptance tests of hydraulic turbines », périmètre "
            "limité aux turbines hydrauliques, status « Cancelled ») → 2ème "
            "édition (datation à confirmer en passe 2) → 3ème édition "
            "1991-11-30 avec élargissement du périmètre aux storage pumps et "
            "pump-turbines (titre actuel reflète cet élargissement) ; "
            "Corrigendum 1 de mars 1996 intégré dans les copies actuelles. Cette "
            "3ème édition a remplacé deux normes antérieures consolidées : IEC "
            "60198 (1966) et IEC 60607 (1978). "
            "Stabilité de la norme : Stability date 2025 selon la fiche IEC "
            "officielle. Cette date est une date de revue planifiée (« date à "
            "laquelle l'IEC examinera si la norme doit être révisée, reconduite "
            "ou retirée »), pas une date de remplacement automatique. À mai 2026, "
            "la norme reste pleinement en vigueur, et aucune édition postérieure "
            "n'a été publiée à la date de consultation. La revue 2025 peut "
            "prendre plusieurs années avant aboutissement à une 4ème édition. À "
            "surveiller en passe d'activation phase 2+. "
            "Pattern de stabilité prolongée documenté : intertekinform recense "
            "une stability date 2017 antérieure à l'actuelle 2025, signe que la "
            "norme a déjà été reconduite au moins une fois sans rupture "
            "éditoriale (au moins 2017 → 2025 attesté). Confirme la stabilité "
            "éditoriale maintenue par revues successives depuis 1991. "
            "Convention de code DT-1 : `iec_60041_1991` retient l'organisme "
            "producteur (IEC, tutelle internationale), la référence (60041 = "
            "série « Field acceptance tests for hydraulic machines »), l'édition "
            "millésimée (1991). Cohérent strict avec `iec_61724_1_2021`. "
            "Convention transverse normes éditées confirmée par 3ème occurrence "
            "(NASA POWER sans année, IEC 61724-1:2021 avec année, "
            "WMO-No.8:2024 avec année, IEC 60041:1991 avec année). Pattern "
            "stable : code avec année si rupture éditoriale identifiée par "
            "millésime, sans année si versionnage continu. "
            "Pas de DOI canonique (cohérent IEC). Identifiant canonique = code "
            "IEC + édition. ISBN natif IEC `283182222X` (format ISBN-10 "
            "pré-2007 ; visible champ « ISBN number » page "
            "webstore.iec.ch/en/publication/154 ; dérivées nationales "
            "BSI/AFNOR/etc. peuvent avoir leurs propres ISBN distincts, hors "
            "périmètre source IEC cf. DT-9 du CdC v2.2). "
            "Famille de normes hydro adjacentes (hors scope direct 1-1E, à "
            "mentionner pour traçabilité) : IEC 60193:2019 (Hydraulic turbines, "
            "storage pumps and pump-turbines - Model acceptance tests) - essais "
            "sur modèles laboratoire, distincte de IEC 60041 qui couvre les "
            "essais sur site (field acceptance tests) ; IEC 62097-2 (Hydraulic "
            "Machines, Radial and Axial - Methodology for Performance "
            "Transposition from Model to Prototype, Edition 2) - norme de "
            "transposition modèle-prototype. Si Kuma phase 2+ étend les calculs "
            "hydro à plusieurs niveaux (modèles + prototypes + transposition), "
            "ces normes pourraient mériter des fiches dédiées (DT-X potentielle). "
            "Pertinence Kuma - convention applicative phase 2+ : norme "
            "directement opérationnelle pour les calculs de productible et "
            "performance des centrales hydroélectriques guinéennes : Kaléta "
            "(240 MW, opérationnelle 2015), Souapiti (450 MW, opérationnelle "
            "2020+), Amaria (300 MW, en construction mai 2026). Si Kuma calcule "
            "le productible de ces centrales (couche C - post-traitement "
            "éditorial), l'application de IEC 60041 (méthodes officielles "
            "d'essais de performance) sera attendue. Convention applicative à "
            "acter en spec préparatoire phase 2+. "
            "Accès : paywall IEC Webstore (CHF 450, 478 USD au taux mai 2026). "
            "Pages : 419 pages bilingues EN+FR (selon VDE-Verlag et "
            "MyStandards) ou 210 pages EN seul (selon IEC Webstore - "
            "discordance probable due aux deux versions linguistiques). GF-1 "
            "fortement applicable : texte intégral payant ; métadonnées "
            "canoniques publiques via page produit IEC. "
            "Note licence : la version IEC 60041:1991 est sous copyright IEC "
            "(paywall officiel webstore.iec.ch). Une dérivée nationale existe "
            "sur Internet Archive (IS/IEC 41:1991, Bureau of Indian Standards) "
            "- à NE PAS exploiter dans Kuma tant que la licence n'est pas "
            "clarifiée, l'IEC défendant historiquement ses droits d'auteur. "
            "Citation académique et utilisation effective : référence IEC "
            "officielle uniquement (achat sur webstore.iec.ch). "
            "Citation canonique : « IEC 60041:1991, Field acceptance tests to "
            "determine the hydraulic performance of hydraulic turbines, storage "
            "pumps and pump-turbines, International Electrotechnical Commission, "
            "Edition 3.0, November 1991, with Corrigendum 1 of March 1996 ». "
            "Consulté le 2026-05-10."
        ),
    },
    {
        "code": "wmo_168_2008",
        "titre": (
            "WMO-No.168 - Guide to Hydrological Practices, Volume I - "
            "Hydrology: From Measurement to Hydrological Information (6ème "
            "édition, 2008)"
        ),
        "auteurs": None,
        "organisation": "World Meteorological Organization (WMO)",
        "type_source": "norme_technique",
        "annee_publication": 2008,
        "date_consultation": _DATE_CONSULTATION_1_1E,
        "url": "https://library.wmo.int/idurl/4/35804",
        "doi": None,
        "isbn": "9789263101686",
        "metadonnees": {
            "editeur": "World Meteorological Organization (WMO)",
            "comite_technique": (
                "Standing Committee on Hydrological Services (SC-HYD) sous "
                "Services Commission (SERCOM) ; coordination avec INFCOM et "
                "Hydrology, Climate and Water Department (HCP) ; anciennement "
                "Commission for Hydrology (CHy) avant la réforme WMO 2019"
            ),
            "edition_millesimee": (
                "6ème édition (Vol I 2008, Vol II 2009) ; scope fiche = "
                "Vol I 2008 ; 7ème édition en cours de développement (Review "
                "Committee établi 2024, group of contributors établi début "
                "2025), non encore publiée à mai 2026"
            ),
        },
        "fiabilite": "haute",
        "langue": "en",
        "notes": (
            _MENTION_BETA2_NORMEE + " "
            "Méta-norme métrologique hydrologique pour la phase 1 β2. Couche C "
            "des 3 couches Kuma (post-traitement éditorial : conventions WMO "
            "hydrométriques appliquées aux mesures pour produire les grandeurs "
            "métier hydro). Source hydro structurelle 4/4 et dernière du "
            "périmètre β2 phase 1. "
            "Scope de la présente fiche : Volume I - Hydrology: From Measurement "
            "to Hydrological Information (édition 2008), le plus pertinent pour "
            "Kuma phase 1 (mesures hydrométriques : débit, niveaux d'eau, "
            "précipitations, évapotranspiration, neige, sédiment, qualité de "
            "l'eau, traitement et analyse hydrologiques). Le Volume II - "
            "Management of Water Resources and Application of Hydrological "
            "Practices (édition 2009) couvre la gestion des ressources en eau et "
            "l'application des pratiques hydrologiques - hors scope principal "
            "mais mentionné pour traçabilité ; fiche dédiée future possible si "
            "extension Kuma vers gestion ressources en eau (DT-X potentielle). "
            "Lignée historique : 1ère publication 1965, mises à jour régulières "
            "au fil des éditions. 4ème édition (1981/1983) publiée en 2 volumes "
            "(Vol I 1981 « data acquisition and processing », Vol II 1983 "
            "« analysis, forecasting and other applications ») - approuvée à la "
            "5ème session de la Commission for Hydrology, Ottawa 1976. 5ème "
            "édition (1994) publiée comme volume consolidé monolithique + "
            "CD-ROM (élargissement de l'audience au-delà des NMHS traditionnels). "
            "6ème édition (2008-2009) réintroduit le découpage en 2 volumes "
            "(Vol I 2008 / Vol II 2009) - pattern de découpage non-linéaire dans "
            "le temps. 7ème édition en cours de développement par SC-HYD : "
            "Review Committee établi en 2024, group of contributors établi début "
            "2025, contenu en cours de revue et mise à jour. Selon SC-HYD "
            "officiel : « The revision of the Guide to Hydrological Practices "
            "(WMO-No. 168), last published in 2008, has now become a priority. "
            "SERCOM will focus mainly on Volume II […], while INFCOM will take "
            "the lead in the revision of Volume I ». Publication 7ème édition "
            "non datée à mai 2026. "
            "Multilingue officiel : English (texte de référence, édition 2008), "
            "French (Guide des pratiques hydrologiques, 6ème édition), Spanish "
            "(Guía de prácticas hidrológicas), Russian (Руководство по "
            "гидрологической практике - édition 2008 mise à jour en 2020 ; cas "
            "de versioning linguistique asymétrique, le contenu anglophone "
            "restant l'édition 2008 originale). Versions traduites disponibles "
            "via la WMO Library. Pas de version Arabe ni Chinoise (contraste "
            "avec `wmo_8_2024` qui est dans 6 langues - différence éditoriale "
            "entre les guides WMO). "
            "Permalinks library.wmo.int : Vol I = "
            "`https://library.wmo.int/idurl/4/35804` ; Vol II = "
            "`https://library.wmo.int/idurl/4/36066`. Accès libre, PDF "
            "téléchargeable directement (pattern WMO cohérent avec "
            "`wmo_8_2024`). "
            "Pas de DOI canonique : édition de 2008 antérieure à la pratique "
            "WMO de DOI'isation (pattern post-2018 observé sur `wmo_8_2024` "
            "Volume I). Confirmation transverse de l'observation faite en "
            "compilation `wmo_grdc` : le pattern « DOI WMO post-2018 » "
            "s'applique aux publications-guides récentes (CIMO Guide 2024) "
            "mais pas aux éditions antérieures. La 7ème édition de WMO-No.168 "
            "(publication future) sera vraisemblablement DOI'ée. "
            "Convention de code DT-1 : `wmo_168_2008` retient l'organisme "
            "(WMO, tutelle internationale), la référence (168 = numéro de "
            "publication officielle WMO), l'édition millésimée (2008 pour "
            "Vol I, scope effectif fiche). Convention transverse normes "
            "éditées confirmée par 4ème et dernière occurrence "
            "(`iec_61724_1_2021`, `wmo_8_2024`, `iec_60041_1991`, "
            "`wmo_168_2008`). Pattern parfaitement stable sur toute la passe : "
            "code avec année si rupture éditoriale identifiée par millésime, "
            "sans année si versionnage continu (NASA POWER, ECMWF ERA5, "
            "WMO/GRDC, WWF/HydroSHEDS, ANM Guinée stations). "
            "Citation canonique : « WMO, 2008: Guide to Hydrological Practices. "
            "Volume I - Hydrology: From Measurement to Hydrological Information. "
            "WMO-No. 168, sixth edition, World Meteorological Organization, "
            "Geneva. ISBN 978-92-63-10168-6. » "
            "Pertinence Kuma - convention applicative phase 2+ : norme "
            "méthodologique de référence pour les conventions hydrométriques "
            "applicables aux bassins guinéens (Niger Supérieur, Sénégal, "
            "Gambie, Konkouré). Si Kuma calcule des grandeurs métier hydro "
            "phase 2+ (débit moyen, débit caractéristique, courbe de tarage, "
            "productible hydroélectrique théorique amont, etc.), application "
            "des conventions de WMO-No.168 attendue. Convention applicative à "
            "acter en spec préparatoire phase 2+. "
            "GF-1 non applicable (accès libre direct via library.wmo.int). "
            "GF-4 fortement applicable au moment d'activation phase 2+ : "
            "surveiller la publication de la 7ème édition (drift CdC futur "
            "potentiel similaire à `wmo_8_2024`). "
            "Famille adjacente WMO en hydrologie (hors scope direct 1-1E) : "
            "Technical Regulations Volume III: Hydrology (WMO-No. 49) - texte "
            "régulateur (status « regulation » plus contraignant que le "
            "Guide) ; Manuals on Hydrology and Water Resources (série "
            "WMO-Nos. 519, 686, etc.) - manuels opérationnels spécialisés "
            "(par exemple : Manual on Stream Gauging WMO-No. 519, Operational "
            "Methods for the Measurement of Sediment Transport WMO-No. 686). "
            "Si Kuma phase 2+ étend les pratiques hydrométriques "
            "opérationnelles, ces manuels pourraient mériter des fiches "
            "dédiées (DT-X potentielle). "
            "Consulté le 2026-05-10."
        ),
    },
]


assert len(SOURCES_SEED) == 9, f"Expected 9 sources, got {len(SOURCES_SEED)}"

_codes_seen: set[str] = set()
for _entry in SOURCES_SEED:
    _code = _entry["code"]
    assert _code not in _codes_seen, f"Code dupliqué dans SOURCES_SEED : {_code!r}"
    _codes_seen.add(_code)
del _codes_seen, _entry, _code
