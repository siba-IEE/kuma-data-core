"""Calcul à la volée du productible avec PR fourni.

Productible PV obtenu en appliquant un Performance Ratio (PR) fourni par
l'appelant à la production théorique « plaque » du système. Le PR
quantifie l'ensemble des pertes par rapport au cas idéal STC.

- PR brut [1] : ratio E_AC / (P_STC * H_POA / 1000), sans correction.
- PR_T corrigé de la température [2] : ajoute un facteur thermique (modèle
  NOCT de Ross 1980 [3]).

Les variantes PR_W (corrigé de la météo) et PR_C (corrigé du climat) de [2]
ne sont pas calculées.

- ``correction='aucune'`` :
    E_AC = P_STC * G / G_STC * PR_fourni
- ``correction='temperature'`` :
    T_cell = T_amb + (NOCT - 20) * G / 800
    ratio_T = 1 + gamma_Pmax / 100 * (T_cell - 25)
    E_AC = P_STC * G / G_STC * PR_fourni * ratio_T

Niveau de confiance : le plus bas des entrées, au plus ``PLAFOND_CONFIANCE``
(B), par la règle de propagation P que la route applique (ADR-0008).

Références bibliographiques :

[1] Marion B., Adelstein J., Boyle K., Hayden H., Hammond B.,
    Fletcher T., Canada B., Narang D., Shugar D., Wenger H., Kimber A.,
    Mitchell L., Rich G., Townsend T. 2005. "Performance parameters for
    grid-connected PV systems." NREL Conference Paper NREL/CP-520-37358,
    31st IEEE PVSC. Open NREL : docs.nrel.gov/docs/fy05osti/37358.pdf.

[2] Dierauf T., Growitz A., Kurtz S., Cruz J.L.B., Riley E., Hansen C.
    2013. "Weather-Corrected Performance Ratio." NREL Technical Report
    NREL/TP-5200-57991. DOI : 10.2172/1078057. Open NREL.

[3] Ross R.G. Jr. 1980. "Flat-plate photovoltaic array design
    optimization." 14th IEEE PVSC, p. 1126-1132. JPL/NASA open access.
    (Modèle NOCT pour T_cell, réutilisé depuis
    ``productible_correction_thermique``.)
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date, datetime
from typing import Literal, Protocol, TypedDict

from kuma_data_core.editorial.niveaux_confiance import NiveauConfiance

# Import d'une fonction privée d'un autre module : le PR_T (Dierauf 2013)
# reprend le modèle NOCT de Ross 1980, dont ``productible_correction_thermique``
# porte la formule. L'importer évite de la dupliquer.
from kuma_data_core.services.grandeurs.productible_correction_thermique import (
    _temperature_cellule_noct,
)
from kuma_data_core.services.grandeurs.types import ResultatJournalier, ResultatMensuel

PLAFOND_CONFIANCE: NiveauConfiance = "B"
"""Plafond de confiance : modèle de calcul et paramètres déclarés par l'appelant,
invérifiables."""

UNITE_PRODUCTIBLE: str = "kWh"
"""Unité de sortie : énergie cumulée journalière en kWh."""

NIVEAU_CONFIANCE_DERIVE_F2_V1: Literal["B"] = "B"
"""Niveau provisoire du calcul pur, remplacé par la route (règle de propagation P)."""

TEMPERATURE_STC_DEGC: float = 25.0
"""Température STC de référence (°C)."""


class ParametresCalculPRFourni(Protocol):
    """Grandeurs physiques et mode de correction que lit le calcul avec PR fourni."""

    @property
    def pr_fourni(self) -> float: ...  # sans dimension

    @property
    def correction(self) -> Literal["aucune", "temperature"]: ...

    @property
    def puissance_stc_wc(self) -> float: ...

    # Les deux suivants ne sont lus qu'avec correction='temperature'.
    @property
    def noct_degc(self) -> float | None: ...

    @property
    def coeff_temp_pourcent_par_degc(self) -> float | None: ...  # gamma_Pmax, négatif


class MesureJourPRFourni(TypedDict):
    """Mesure journalière, entrée du productible avec PR fourni.

    ``t_amb_degc`` n'est requis que si ``correction='temperature'`` ; il est
    ignoré sinon.
    """

    instant_mesure: date
    irradiance_kwh_par_m2_jour: float
    t_amb_degc: float | None


class MesureMoisPRFourni(TypedDict):
    """Mesure mensuelle d'une série climatologique, entrée du productible avec PR fourni.

    ``irradiance_kwh_par_m2_jour`` est ici une moyenne quotidienne sur le mois.
    Pas de champ ``t_amb_degc`` : le calcul mensuel n'admet que
    ``correction='aucune'``, la correction thermique étant non linéaire en G et
    donc incompatible avec une moyenne.
    """

    annee: int
    mois: int
    irradiance_kwh_par_m2_jour: float


class MesureHeurePRFourni(TypedDict):
    """Mesure horaire, entrée du productible avec PR fourni en intégration horaire.

    ``irradiance_w_par_m2`` est le GHI horaire (W/m², soit Wh/m² sur l'heure) ;
    ``t_amb_degc`` n'est requis que si ``correction='temperature'``.
    """

    instant_mesure: datetime
    irradiance_w_par_m2: float
    t_amb_degc: float | None


def _productible_brut_jour(
    irradiance_kwh_par_m2_jour: float,
    puissance_stc_wc: float,
    pr_fourni: float,
) -> float:
    """Productible journalier (kWh) avec PR brut (Marion 2005)."""
    return puissance_stc_wc / 1000.0 * irradiance_kwh_par_m2_jour * pr_fourni


def _productible_pr_t_jour(
    mesure: MesureJourPRFourni,
    parametres: ParametresCalculPRFourni,
) -> float:
    """Productible journalier (kWh) avec PR_T corrigé de la température (Dierauf 2013).

    ``noct_degc``, ``coeff_temp_pourcent_par_degc`` et ``mesure['t_amb_degc']``
    doivent être renseignés : le schéma des paramètres le garantit en amont.
    """
    assert parametres.noct_degc is not None
    assert parametres.coeff_temp_pourcent_par_degc is not None
    assert mesure["t_amb_degc"] is not None

    # Irradiance moyenne sur 24 h (W/m²), comme productible_correction_thermique.
    irradiance_w_par_m2 = mesure["irradiance_kwh_par_m2_jour"] * 1000.0 / 24.0

    t_cell = _temperature_cellule_noct(
        t_amb_degc=mesure["t_amb_degc"],
        irradiance_w_par_m2=irradiance_w_par_m2,
        noct_degc=parametres.noct_degc,
    )

    ratio_temperature = 1.0 + parametres.coeff_temp_pourcent_par_degc / 100.0 * (
        t_cell - TEMPERATURE_STC_DEGC
    )

    productible_brut = _productible_brut_jour(
        irradiance_kwh_par_m2_jour=mesure["irradiance_kwh_par_m2_jour"],
        puissance_stc_wc=parametres.puissance_stc_wc,
        pr_fourni=parametres.pr_fourni,
    )

    return productible_brut * ratio_temperature


def calculer_productible_pr_fourni(
    mesures: Sequence[MesureJourPRFourni],
    parametres: ParametresCalculPRFourni,
) -> list[ResultatJournalier]:
    """Productible journalier (kWh) avec PR fourni, brut ou corrigé de la température.

    ``correction='aucune'`` applique le PR brut (Marion 2005), ``'temperature'``
    le PR_T (Dierauf 2013). Un productible négatif est ramené à 0. Le niveau de
    confiance ``'B'`` est provisoire : la route le remplace (règle P).
    """
    resultats: list[ResultatJournalier] = []
    for mesure in mesures:
        if parametres.correction == "aucune":
            productible = _productible_brut_jour(
                irradiance_kwh_par_m2_jour=mesure["irradiance_kwh_par_m2_jour"],
                puissance_stc_wc=parametres.puissance_stc_wc,
                pr_fourni=parametres.pr_fourni,
            )
        else:
            productible = _productible_pr_t_jour(mesure=mesure, parametres=parametres)

        resultats.append(
            ResultatJournalier(
                instant=mesure["instant_mesure"],
                valeur=max(0.0, productible),
                unite=UNITE_PRODUCTIBLE,
                niveau_confiance=NIVEAU_CONFIANCE_DERIVE_F2_V1,
            )
        )
    return resultats


def calculer_productible_pr_fourni_mensuel(
    mesures: Sequence[MesureMoisPRFourni],
    parametres: ParametresCalculPRFourni,
) -> list[ResultatMensuel]:
    """Productible quotidien moyen du mois (kWh par jour) sur une série climatologique.

    L'entrée est une moyenne quotidienne sur le mois : la sortie l'est aussi, elle
    n'est pas multipliée par le nombre de jours. Résultats au format
    ``instant='YYYY-MM'``, niveau de confiance ``'B'`` provisoire (la route le
    remplace, règle P).

    Seul ``correction='aucune'`` est admis : la correction thermique est non
    linéaire en G, donc incompatible avec une moyenne mensuelle. La route rejette
    l'autre mode en 400 avant d'appeler ; l'assertion ne fait que le rappeler.
    """
    assert parametres.correction == "aucune", (
        "calculer_productible_pr_fourni_mensuel : seul le mode "
        "correction='aucune' est supporte en lot 2 (mode 'temperature' "
        "non-lineaire incompatible avec moyenne climato mensuelle)."
    )
    resultats: list[ResultatMensuel] = []
    for mesure in mesures:
        productible = _productible_brut_jour(
            irradiance_kwh_par_m2_jour=mesure["irradiance_kwh_par_m2_jour"],
            puissance_stc_wc=parametres.puissance_stc_wc,
            pr_fourni=parametres.pr_fourni,
        )
        resultats.append(
            ResultatMensuel(
                instant=f"{mesure['annee']:04d}-{mesure['mois']:02d}",
                valeur=max(0.0, productible),
                unite=UNITE_PRODUCTIBLE,
                niveau_confiance=NIVEAU_CONFIANCE_DERIVE_F2_V1,
            )
        )
    return resultats


def calculer_productible_pr_fourni_horaire(
    mesures: Sequence[MesureHeurePRFourni],
    parametres: ParametresCalculPRFourni,
) -> list[ResultatJournalier]:
    """Productible journalier (kWh) avec PR fourni, par intégration horaire.

    Le calcul est fait heure par heure (``T_cell`` sur l'irradiance horaire pour
    le PR_T), puis l'énergie est sommée par jour (date de ``instant_mesure``).

    Avec ``correction='aucune'`` le calcul est linéaire en G : la somme horaire
    égale le résultat journalier. L'intégration horaire ne change le résultat
    qu'avec ``correction='temperature'``, où ``T_cell`` n'est pas linéaire en G
    (biais de moyennage, inégalité de Jensen).
    """
    energie_par_jour: dict[date, float] = {}
    for mesure in mesures:
        irradiance_w = mesure["irradiance_w_par_m2"]
        # Énergie de l'heure (kWh) = P_STC (kWc) x irradiation de l'heure (kWh/m²) x PR.
        productible = (
            parametres.puissance_stc_wc / 1000.0 * (irradiance_w / 1000.0) * parametres.pr_fourni
        )
        if parametres.correction == "temperature":
            assert parametres.noct_degc is not None
            assert parametres.coeff_temp_pourcent_par_degc is not None
            assert mesure["t_amb_degc"] is not None
            t_cell = _temperature_cellule_noct(
                t_amb_degc=mesure["t_amb_degc"],
                irradiance_w_par_m2=irradiance_w,
                noct_degc=parametres.noct_degc,
            )
            ratio_temperature = 1.0 + parametres.coeff_temp_pourcent_par_degc / 100.0 * (
                t_cell - TEMPERATURE_STC_DEGC
            )
            productible *= ratio_temperature
        jour = mesure["instant_mesure"].date()
        energie_par_jour[jour] = energie_par_jour.get(jour, 0.0) + productible

    return [
        ResultatJournalier(
            instant=jour,
            valeur=max(0.0, energie),
            unite=UNITE_PRODUCTIBLE,
            niveau_confiance=NIVEAU_CONFIANCE_DERIVE_F2_V1,
        )
        for jour, energie in energie_par_jour.items()
    ]
