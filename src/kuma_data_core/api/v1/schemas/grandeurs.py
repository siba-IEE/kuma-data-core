"""Schémas Pydantic des routes ``/v1/grandeurs/<code>``.

Paramètres des grandeurs paramétrables (``Parametres*``), résultats journaliers
ou mensuels distingués par le champ ``granularite``, et réponses des grandeurs
calculées à la volée (P50/P90 du GHI, salissure, PR réaliste, incertitude
inter-source).
"""

from __future__ import annotations

from datetime import date
from typing import Annotated, Literal

from pydantic import BaseModel, Field, model_validator

from kuma_data_core.services.grandeurs.types import (
    MesureJourPR,
    MesureMoisPR,
    MesureSoilingJour,
    ModeCorrectionPR,
    ResultatJournalier,
    ResultatMensuel,
)


class ParametresCommunsF2(BaseModel):
    """Paramètres communs aux grandeurs F2 paramétrables.

    ``format_sortie`` se passe dans l'URL sous le nom ``format``.
    """

    code_serie_source: str = Field(
        ...,
        min_length=1,
        max_length=80,
        description="Code de la série F1 source, tel que listé par /v1/series.",
    )
    periode_debut: date = Field(..., description="Date de debut (inclusive).")
    periode_fin: date = Field(..., description="Date de fin (inclusive).")
    format_sortie: Literal["json", "csv"] = Field(
        "json",
        alias="format",
        description="Format de reponse : 'json' (defaut) ou 'csv'.",
    )

    @model_validator(mode="after")
    def _valider_plage_temporelle(self) -> ParametresCommunsF2:
        if self.periode_fin < self.periode_debut:
            raise ValueError("periode_fin doit etre superieure ou egale a periode_debut")
        return self


class ParametresPOA(ParametresCommunsF2):
    """Paramètres du POA paramétrable (modèle de Perez 1990, repli Liu-Jordan)."""

    inclinaison_deg: float = Field(
        ...,
        ge=0,
        le=90,
        description="Inclinaison beta du plan (degres, 0=horizontal, 90=vertical).",
    )
    orientation_deg: float = Field(
        ...,
        ge=0,
        lt=360,
        description=(
            "Orientation gamma du plan (azimut en degres, 0=nord, 90=est, 180=sud, 270=ouest)."
        ),
    )
    albedo_sol: float = Field(
        0.2,
        ge=0,
        le=1,
        description="Albedo du sol (defaut 0.2, typique sol vegetalise).",
    )
    methode: Literal["moyenne_journaliere", "integration_horaire"] = Field(
        "moyenne_journaliere",
        description=(
            "Méthode de calcul. 'moyenne_journaliere' (valeur par défaut) : modèle de "
            "Perez appliqué au midi solaire sur les totaux journaliers, série source "
            "journalière. 'integration_horaire' : modèle de Perez appliqué heure par "
            "heure puis sommé sur la journée, série source horaire (GHI, avec les séries "
            "DNI et DHI horaires de la même localité et de la même source) ; évite le "
            "biais de moyennage du calcul journalier, qui surestime le gain d'un plan "
            "incliné."
        ),
    )


class ParametresBifacial(ParametresCommunsF2):
    """Paramètres du POA bifacial (modèle infinite-sheds de pvlib, champ de rangées).

    Ajoute à ceux du POA mono-plan la géométrie des rangées (gcr, hauteur, pas
    entre rangées) et la bifacialité du module. L'albédo vient de la série
    ``albedo_surface`` de la localité ; ``albedo_sol`` ne sert que les jours où
    cette série n'a pas de valeur.
    """

    inclinaison_deg: float = Field(
        ..., ge=0, le=90, description="Inclinaison beta du plan (degres, 0=horizontal)."
    )
    orientation_deg: float = Field(
        ...,
        ge=0,
        lt=360,
        description="Orientation gamma (azimut degres, 0=nord, 90=est, 180=sud, 270=ouest).",
    )
    gcr: float = Field(
        ..., gt=0, le=1, description="Ground coverage ratio (largeur capteur / pitch), dans ]0, 1]."
    )
    hauteur_m: float = Field(
        ...,
        gt=0,
        description="Hauteur du centre de rangee au-dessus du sol (m, meme unite que pitch).",
    )
    pitch_m: float = Field(
        ..., gt=0, description="Espacement rangee a rangee (m, meme unite que hauteur)."
    )
    bifacialite: float = Field(
        0.8,
        ge=0,
        le=1,
        description="Bifacialite du module (rendement face arriere / avant, defaut 0.8).",
    )
    albedo_sol: float = Field(
        0.2,
        ge=0,
        le=1,
        description="Albedo de repli si la serie albedo_surface est absente (defaut 0.2).",
    )
    methode: Literal["moyenne_journaliere", "integration_horaire"] = Field(
        "moyenne_journaliere",
        description=(
            "Méthode de calcul. 'moyenne_journaliere' (valeur par défaut) : modèle "
            "infinite-sheds appliqué au midi solaire sur les totaux journaliers (série "
            "source journalière). 'integration_horaire' : modèle appliqué heure par "
            "heure puis sommé sur la journée (série source horaire, avec les séries DNI "
            "et DHI horaires ; l'albédo du jour vaut pour chacune de ses heures) ; évite "
            "le biais de moyennage du calcul journalier."
        ),
    )


class ParametresProductibleCorrectionThermique(ParametresCommunsF2):
    """Paramètres du productible avec correction thermique (NOCT simple, Ross 1980).

    Seul ce modèle thermique est proposé : celui de Faiman (2008), qui dépend du
    vent, demande des coefficients calés localement sur des mesures au sol.
    """

    noct_degc: float = Field(
        ...,
        ge=40,
        le=50,
        description="NOCT (°C), fiche produit module (typique 45).",
    )
    coeff_temp_pourcent_par_degc: float = Field(
        ...,
        ge=-0.6,
        le=-0.1,
        description="Coefficient temperature gamma_Pmax (%/°C), valeur negative.",
    )
    puissance_stc_wc: float = Field(
        ...,
        gt=0,
        description="Puissance nominale STC du systeme (Wc).",
    )
    methode: Literal["moyenne_journaliere", "integration_horaire"] = Field(
        "moyenne_journaliere",
        description=(
            "Méthode de calcul. 'moyenne_journaliere' (valeur par défaut) : température "
            "de cellule calculée sur l'irradiance moyenne des 24 h (série source "
            "journalière). 'integration_horaire' : température de cellule et correction "
            "calculées heure par heure sur le GHI horaire (série source horaire, avec la "
            "série T2M horaire), puis sommées sur la journée ; évite le biais de "
            "moyennage du calcul journalier (la moyenne sur 24 h sous-estime le pic de "
            "midi, donc la température de cellule, et surestime le productible)."
        ),
    )


class ParametresProductiblePRFourni(ParametresCommunsF2):
    """Paramètres du productible avec PR fourni (Marion 2005, Dierauf 2013).

    Avec ``correction='temperature'``, ``noct_degc`` et
    ``coeff_temp_pourcent_par_degc`` sont obligatoires.
    """

    pr_fourni: float = Field(
        ...,
        ge=0,
        le=1,
        description="Performance Ratio fourni par l'appelant (sans unite).",
    )
    correction: Literal["aucune", "temperature"] = Field(
        "aucune",
        description="Type de correction : 'aucune' (PR brut) ou 'temperature' (PR_T).",
    )
    puissance_stc_wc: float = Field(
        ...,
        gt=0,
        description="Puissance nominale STC du systeme (Wc).",
    )
    noct_degc: float | None = Field(
        None,
        ge=40,
        le=50,
        description="NOCT (°C) - obligatoire si correction='temperature'.",
    )
    coeff_temp_pourcent_par_degc: float | None = Field(
        None,
        ge=-0.6,
        le=-0.1,
        description=(
            "Coefficient temperature gamma_Pmax (%/°C) - obligatoire si correction='temperature'."
        ),
    )
    methode: Literal["moyenne_journaliere", "integration_horaire"] = Field(
        "moyenne_journaliere",
        description=(
            "Méthode de calcul. 'moyenne_journaliere' (valeur par défaut) : PR appliqué "
            "à l'irradiation du jour, série source journalière ou mensuelle. "
            "'integration_horaire' : PR appliqué heure par heure (série source horaire, "
            "avec la série T2M horaire si correction='temperature'), puis sommé sur la "
            "journée. Avec correction='aucune', le calcul est linéaire et le résultat "
            "horaire est identique au résultat journalier ; l'intégration horaire ne "
            "change le résultat qu'avec correction='temperature', où elle évite le biais "
            "de moyennage sur la température de cellule."
        ),
    )

    @model_validator(mode="after")
    def _valider_parametres_temperature(self) -> ParametresProductiblePRFourni:
        if self.correction == "temperature":
            manquants: list[str] = []
            if self.noct_degc is None:
                manquants.append("noct_degc")
            if self.coeff_temp_pourcent_par_degc is None:
                manquants.append("coeff_temp_pourcent_par_degc")
            if manquants:
                raise ValueError(f"correction='temperature' requiert : {', '.join(manquants)}")
        return self


class ParametresEnergieUtileECS(ParametresCommunsF2):
    """Paramètres de l'énergie utile ECS en sortie de capteur (Hottel-Whillier-Bliss 1958)."""

    rendement_optique_eta0: float = Field(
        ...,
        ge=0.5,
        le=0.9,
        description=("Rendement optique eta0 (sans unite), fiche capteur Solar Keymark."),
    )
    pertes_lineaires_a1: float = Field(
        ...,
        ge=1,
        le=8,
        description="Coefficient pertes lineaires a1 (W/(m²·K)).",
    )
    pertes_quadratiques_a2: float = Field(
        ...,
        ge=0,
        le=0.05,
        description="Coefficient pertes quadratiques a2 (W/(m²·K²)).",
    )
    temperature_fluide_entree_degc: float = Field(
        ...,
        ge=10,
        le=90,
        description="Temperature fluide caloporteur a l'entree T_in (°C).",
    )
    methode: Literal["moyenne_journaliere", "integration_horaire"] = Field(
        "moyenne_journaliere",
        description=(
            "Méthode de calcul. 'moyenne_journaliere' (valeur par défaut) : rendement du "
            "capteur calculé sur l'irradiance moyenne des 24 h (série source "
            "journalière). 'integration_horaire' : rendement calculé heure par heure sur "
            "le GHI horaire (série source horaire, avec la série T2M horaire), puis "
            "sommé sur la journée ; évite le biais de moyennage du calcul journalier (le "
            "rendement n'est pas linéaire en irradiance)."
        ),
    )


class ParametresDegreJourClimatisation(ParametresCommunsF2):
    """Paramètres des degrés-jours de climatisation (Erbs 1983, Schoenau & Kehrig 1990)."""

    base_temperature_degc: float = Field(
        ...,
        ge=10,
        le=35,
        description="Base de reference T_b (°C, plage couvrant 18.3 ASHRAE a 26 CEDEAO).",
    )
    methode: Literal["moyenne_journaliere", "integration_horaire"] = Field(
        "moyenne_journaliere",
        description=(
            "Méthode de calcul. 'moyenne_journaliere' (valeur par défaut) : écart de la "
            "température moyenne du jour à T_b, série source journalière. "
            "'integration_horaire' (Erbs 1983) : somme des écarts horaires positifs à "
            "T_b ; évite le biais de moyennage du calcul journalier, qui sous-estime "
            "les degrés-jours en climat tropical (-5 à -15 %) ; exige une série source "
            "horaire."
        ),
    )


class ReponseGhiExceedance(BaseModel):
    """Réponse de ``/v1/grandeurs/ghi_exceedance/{code_localite}``.

    Irradiation annuelle dépassée une année sur deux (P50) et neuf années sur dix
    (P90) pour une localité, d'après sa série GHI mensuelle 1991-2020 NASA POWER.
    Calculée à chaque appel, jamais stockée.
    """

    code_grandeur: Literal["ghi_exceedance"] = "ghi_exceedance"
    code_localite: str = Field(
        ...,
        description="Code de la localite cible (ex. gin_kankan, gin_conakry_kaloum).",
    )
    code_serie_source: str = Field(
        ...,
        description=(
            "Code de la série GHI mensuelle 1991-2020 utilisée pour le calcul "
            "(ex. gin_kankan_ghi_power_1991_2020)."
        ),
    )
    periode: str = Field(
        ...,
        pattern=r"^\d{4}-\d{4}$",
        description="Fenetre climatologique source au format YYYY-YYYY (ex. 1991-2020).",
    )
    base_annees: int = Field(
        ...,
        ge=2,
        description="Nombre d'annees utilisees pour le calcul des percentiles.",
    )
    p50: float = Field(
        ...,
        gt=0,
        description="Mediane de l'irradiation annuelle (kWh/m²/an). Annee typique.",
    )
    p90: float = Field(
        ...,
        gt=0,
        description=(
            "Exceedance P90 = irradiation annuelle depassee 90 % des annees "
            "(percentile 10 cote distribution). Scenario conservateur. "
            "Strictement < p50 par construction."
        ),
    )
    unite: str = Field(
        "kWh/m²/an",
        description="Unite des valeurs p50 et p90.",
    )
    methode_percentile: str = Field(
        ...,
        description="Methode d'interpolation des percentiles (ex. 'linear' numpy).",
    )
    niveau_confiance: Literal["A", "B", "C"] = Field(
        ...,
        description=(
            "Niveau de confiance du calcul : le plus bas des mesures lues (regle de propagation P)."
        ),
    )
    limite: str = Field(
        ...,
        description=(
            "Mise en garde sur la portée du résultat : variabilité d'une année à "
            "l'autre uniquement, pas un P90 bancable complet. Quand deux localités "
            "tombent dans la même cellule de la source et reçoivent donc des valeurs "
            "identiques, le texte nomme la localité jumelle."
        ),
    )


ResultatGrandeurF2 = Annotated[
    ResultatJournalier | ResultatMensuel,
    Field(discriminator="granularite"),
]
"""Résultat journalier ou mensuel, distingué par le champ ``granularite``."""


class ReponseTauxSalissureProxy(BaseModel):
    """Réponse de ``/v1/grandeurs/taux_salissure_proxy/{code_serie_source}``.

    Proxy de salissure (modèle HSU, Coello & Boyle 2019) sur les jours où les
    séries de particules (PM2.5 et PM10 EAC4) et de pluie (NASA POWER) ont toutes
    une valeur. Calculée à chaque appel, jamais stockée.
    """

    code_grandeur: Literal["taux_salissure_proxy"] = "taux_salissure_proxy"
    code_serie_source: str = Field(..., description="Code de la série PM2.5 source (EAC4).")
    code_localite: str = Field(..., description="Code de la localite (derive de la serie source).")
    periode: str = Field(
        ...,
        description="Fenetre effective (intersection PM ∩ pluie), YYYY-MM-DD/YYYY-MM-DD.",
    )
    unite: str = Field(default="%", description="Unite des pertes (pourcent).")
    surface_tilt_deg: float = Field(
        ..., description="Inclinaison fixe utilisée (valeur par défaut, degrés)."
    )
    cleaning_threshold_mm: float = Field(
        ..., description="Seuil de pluie nettoyante utilisé (valeur par défaut, mm)."
    )
    mesures: list[MesureSoilingJour] = Field(..., description="Perte de salissure par jour.")
    limite: str = Field(
        ...,
        description=(
            "Mise en garde : estimation par modèle et non mesure de salissure, non "
            "calée sur des mesures au sol ; premiers jours de la fenêtre sous-estimés "
            "(amorçage du modèle) ; grille EAC4 grossière."
        ),
    )


class ParametresPRRealiste(BaseModel):
    """Paramètres de la route ``pr_realiste`` ; la série GHI source est dans le chemin.

    ``pr_fourni`` est supposé hors salissure et hors température : les corrections
    s'y appliquent en facteurs multiplicatifs séparés.
    """

    pr_fourni: float = Field(
        ...,
        ge=0,
        le=1,
        description="PR de reference (ratio sans unite), hors salissure et hors temperature.",
    )
    correction: ModeCorrectionPR = Field(
        "temperature_salissure",
        description="Mode de correction superpose (defaut : thermique + salissure).",
    )
    noct_degc: float | None = Field(
        None,
        ge=40,
        le=50,
        description="NOCT (°C) - obligatoire si la correction inclut la temperature.",
    )
    coeff_temp_pourcent_par_degc: float | None = Field(
        None,
        ge=-0.6,
        le=-0.1,
        description=(
            "Coefficient de température gamma_Pmax (%/°C, négatif), obligatoire si la "
            "correction inclut la température (422 sinon)."
        ),
    )


class ReponsePRRealiste(BaseModel):
    """Réponse de ``/v1/grandeurs/pr_realiste/{code_serie_source}`` (calculée à la volée)."""

    code_grandeur: Literal["pr_realiste"] = "pr_realiste"
    code_serie_source: str = Field(..., description="Code de la série GHI source.")
    code_localite: str = Field(..., description="Code de la localite (derive de la serie GHI).")
    periode: str = Field(
        ..., description="Fenetre effective (intersection selon le mode), YYYY-MM-DD/YYYY-MM-DD."
    )
    unite: str = Field(default="ratio", description="PR adimensionnel (ratio [0, 1]).")
    correction: ModeCorrectionPR = Field(..., description="Mode de correction applique.")
    pr_fourni: float = Field(..., description="PR de reference fourni (echo).")
    mesures_journalier: list[MesureJourPR] = Field(..., description="PR realiste par jour.")
    mesures_mensuel: list[MesureMoisPR] = Field(
        ..., description="PR realiste moyen par mois (courbe saisonniere, creux Harmattan)."
    )
    limite: str = Field(
        ...,
        description=(
            "Mises en garde : hypothèse sur le PR fourni, amorçage du modèle de "
            "salissure, biais de moyennage du calcul thermique."
        ),
    )


class ReponseGrandeurF2(BaseModel):
    """Réponse complète d'une grandeur F2 paramétrable."""

    code_grandeur: str = Field(
        ...,
        description="Code de la grandeur F2 calculée.",
    )
    code_serie_source: str = Field(
        ...,
        description="Code de la serie F1 source utilisee pour le calcul.",
    )
    parametres_appliques: dict[str, object] = Field(
        ...,
        description="Echo des parametres techniques utilisateur reçus.",
    )
    resultats: list[ResultatGrandeurF2] = Field(
        default_factory=list,
        description="Liste ordonnee des resultats F2 calcules sur la fenetre demandee.",
    )


class EcartPaireInterSource(BaseModel):
    """Écart entre deux sources pour une grandeur, agrégé sur 2021-2023.

    La comparaison se fait par paire (GHI : NASA POWER et SARAH-3 ; DNI : NASA POWER
    et CAMS), pas entre les trois sources à la fois. ``ecart_abs_pct`` (médiane des
    écarts absolus) est l'indicateur d'incertitude à retenir ; le signe n'indique
    qu'un sens et ne doit pas servir à corriger un biais.
    """

    grandeur: Literal["ghi", "dni"]
    paire: str = Field(
        ..., description="Couple de sources compare (ex. 'NASA POWER vs PVGIS-SARAH3')."
    )
    ecart_abs_pct: float = Field(
        ...,
        ge=0.0,
        description=(
            "Médiane des écarts mensuels absolus (%), 2021-2023. Indicateur "
            "d'incertitude principal."
        ),
    )
    ecart_signe_pct: float = Field(
        ...,
        description=(
            "Moyenne signée des écarts mensuels (%). N'indique qu'un sens (négatif : "
            "NASA POWER inférieur à la référence) et ne doit pas servir à corriger un "
            "biais : l'écart compare deux sources entre elles, pas une source à des "
            "mesures au sol."
        ),
    )
    n_mois: int = Field(
        ..., ge=1, description="Nombre de mois compares (36 attendu sur 2021-2023)."
    )


class DegenerescenceFiche(BaseModel):
    """Dégénérescence de pixel d'une localité dans la grille de la source.

    Une seule valeur par localité : le GHI et le DNI de NASA POWER partagent la
    grille CERES. ``note`` reprend tel quel le commentaire éditorial enregistré
    (groupe de jumeaux et nature de l'indicateur).
    """

    n_jumeaux: int = Field(
        ...,
        ge=0,
        description="Nombre d'autres points partageant la cellule NASA CERES (0 = point resolu).",
    )
    grille: str = Field(
        ...,
        description="Grille source de la degenerescence (ex. 'CERES SYN1deg 1 deg / 110 km').",
    )
    note: str = Field(
        ...,
        description=(
            "Commentaire éditorial tel qu'enregistré (groupe de jumeaux et nature de l'indicateur)."
        ),
    )


class ReponseIncertitudeInterSource(BaseModel):
    """Fiche d'incertitude inter-source d'une localité.

    Présente séparément deux informations : l'écart entre sources (par paire et
    par grandeur) et la dégénérescence de pixel. Confiance B : la fiche compare
    des sources entre elles et ne quantifie pas l'incertitude absolue par rapport
    à des mesures au sol.
    """

    code_grandeur: Literal["incertitude_inter_source"] = "incertitude_inter_source"
    code_localite: str = Field(..., description="Code de la localite (ex. gin_boffa).")
    fenetre: str = Field(
        ..., description="Fenêtre commune aux sources comparées (fixe, ex. '2021-2023')."
    )
    ecarts: list[EcartPaireInterSource] = Field(
        ..., description="Écart entre sources, par paire et par grandeur."
    )
    degenerescence: DegenerescenceFiche = Field(
        ...,
        description="Dégénérescence de pixel de la localité.",
    )
    niveau_confiance: Literal["A", "B", "C"] = Field(
        ...,
        description=(
            "Niveau de confiance lu dans les données (B attendu : comparaison entre "
            "sources, sans mesure au sol)."
        ),
    )
    limite: str = Field(
        ...,
        description=(
            "Mise en garde : incertitude relative entre sources, confiance B ; ne "
            "quantifie pas l'incertitude absolue par rapport à des mesures au sol."
        ),
    )


class FichePointIncertitude(ReponseIncertitudeInterSource):
    """Fiche d'incertitude inter-source d'un point, avec ses coordonnées.

    Mêmes champs que la fiche par localité, plus la latitude et la longitude, pour
    placer le point sur une carte sans second appel.
    """

    latitude_deg: float = Field(..., description="Latitude du point (degres).")
    longitude_deg: float = Field(..., description="Longitude du point (degres).")


class ReponseIncertitudeInterSourceCollection(BaseModel):
    """Collection paginée des fiches d'incertitude inter-source des points de l'atlas.

    Même enveloppe que /v1/series (``items``, ``total``, ``limit``, ``offset``).
    """

    items: list[FichePointIncertitude] = Field(
        ..., description="Fiches par point de l'atlas (fiche de la localité et coordonnées)."
    )
    total: int = Field(..., ge=0, description="Nombre total de points de l'atlas.")
    limit: int = Field(..., ge=1, description="Taille de page demandee.")
    offset: int = Field(..., ge=0, description="Decalage de pagination.")
