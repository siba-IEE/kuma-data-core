"""Productible PV à la volée avec un Performance Ratio fourni par l'appelant.

- ``correction='aucune'``, PR brut [1] :
    E_AC = P_STC * G / G_STC * PR_fourni
- ``correction='temperature'``, PR_T [2], T_cell par le modèle NOCT [3] :
    T_cell = T_amb + (NOCT - 20) * G / 800
    ratio_T = 1 + gamma_Pmax / 100 * (T_cell - 25)
    E_AC = P_STC * G / G_STC * PR_fourni * ratio_T

PR_W et PR_C (Dierauf 2013) ne sont pas exposés : pas de TMY Guinée public.

[1] Marion B. et al. 2005. "Performance parameters for grid-connected PV
    systems." NREL/CP-520-37358, 31st IEEE PVSC.
[2] Dierauf T. et al. 2013. "Weather-Corrected Performance Ratio."
    NREL/TP-5200-57991. DOI : 10.2172/1078057.
[3] Ross R.G. Jr. 1980. "Flat-plate photovoltaic array design
    optimization." 14th IEEE PVSC, p. 1126-1132.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date, datetime
from typing import Literal, TypedDict

from kuma_data_core.api.v1.schemas.grandeurs import (
    ParametresProductiblePRFourni,
    ResultatJournalier,
    ResultatMensuel,
)
from kuma_data_core.editorial.niveaux_confiance import NiveauConfiance

# Import d'une fonction privée : le modèle NOCT a une seule source, le module thermique.
from kuma_data_core.services.grandeurs.productible_correction_thermique import (
    _temperature_cellule_noct,
)

PLAFOND_CONFIANCE: NiveauConfiance = "B"
"""Plafond ``B`` : modèle et paramètres déclarés par l'appelant, invérifiables."""

# === Constantes module ====================================================

UNITE_PRODUCTIBLE: str = "kWh"
"""Énergie journalière en kWh."""

NIVEAU_CONFIANCE_DERIVE_F2_V1: Literal["B"] = "B"
"""Niveau provisoire du calcul pur, remplacé par la route (règle de propagation P)."""

TEMPERATURE_STC_DEGC: float = 25.0
"""Température STC de référence (°C)."""


# === TypedDict d'entree ===================================================


class MesureJourPRFourni(TypedDict):
    """Mesure journalière ; ``t_amb_degc`` n'est lu qu'en ``correction='temperature'``."""

    instant_mesure: date
    irradiance_kwh_par_m2_jour: float
    t_amb_degc: float | None


class MesureMoisPRFourni(TypedDict):
    """Moyenne quotidienne du mois (kWh/m²/jour), sans température.

    Seul ``correction='aucune'`` est permis au mois : le facteur thermique n'est
    pas linéaire en G et ne s'applique pas à une moyenne.
    """

    annee: int
    mois: int
    irradiance_kwh_par_m2_jour: float


class MesureHeurePRFourni(TypedDict):
    """Mesure horaire : GHI en W/m² (≈ Wh/m² sur l'heure), température si ``'temperature'``."""

    instant_mesure: datetime
    irradiance_w_par_m2: float
    t_amb_degc: float | None


# === Fonctions privees pures ==============================================


def _productible_brut_jour(
    irradiance_kwh_par_m2_jour: float,
    puissance_stc_wc: float,
    pr_fourni: float,
) -> float:
    """PR brut journalier (Marion 2005)."""
    return puissance_stc_wc / 1000.0 * irradiance_kwh_par_m2_jour * pr_fourni


def _productible_pr_t_jour(
    mesure: MesureJourPRFourni,
    parametres: ParametresProductiblePRFourni,
) -> float:
    """PR_T journalier (Dierauf 2013), T_cell NOCT (Ross 1980) ; entrées validées en amont."""
    assert parametres.noct_degc is not None
    assert parametres.coeff_temp_pourcent_par_degc is not None
    assert mesure["t_amb_degc"] is not None

    # kWh/m²/jour -> W/m² moyen sur 24 h, comme le module thermique.
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


# === Fonction publique ====================================================


def calculer_productible_pr_fourni(
    mesures: Sequence[MesureJourPRFourni],
    parametres: ParametresProductiblePRFourni,
) -> list[ResultatJournalier]:
    """Productible journalier, PR brut ou PR_T selon ``parametres.correction``.

    Confiance provisoire ``'B'``, remplacée par la route (règle P).
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
    parametres: ParametresProductiblePRFourni,
) -> list[ResultatMensuel]:
    """Productible quotidien moyen du mois (kWh), mode ``'aucune'`` seulement.

    L'entrée étant une moyenne quotidienne, on ne multiplie pas par le nombre de
    jours. ``AssertionError`` en mode ``'temperature'`` : la route renvoie déjà
    HTTP 400, l'assertion n'est qu'un filet.
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
    parametres: ParametresProductiblePRFourni,
) -> list[ResultatJournalier]:
    """Productible calculé heure par heure puis sommé par jour UTC (kWh).

    En PR brut, linéaire en G, le résultat égale le journalier. Le gain est en
    PR_T : T_cell sur l'irradiance horaire réelle lève le biais de Jensen.
    """
    energie_par_jour: dict[date, float] = {}
    for mesure in mesures:
        irradiance_w = mesure["irradiance_w_par_m2"]
        # kWh = P_STC (kWc) x G (W/m² sur 1 h, /1000 -> kWh/m²) x PR
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
