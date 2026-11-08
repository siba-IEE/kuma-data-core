"""Productible PV à la volée corrigé de la température du module (NOCT, Ross 1980 [1]).

    T_cell = T_amb + (NOCT - 20) * G / 800
    P_AC = P_STC * (G / 1000) * [1 + gamma_Pmax / 100 * (T_cell - 25)]

G : irradiance reçue (GHI ou POA) ; T_amb : T2M NASA POWER ; gamma_Pmax en
%/°C (négatif, -0.4 typique en c-Si). En journalier, T_cell est calculée sur
``G_jour * 1000 / 24`` (W/m² moyen sur 24 h) : le pic de midi est lissé.

Limites : pas de vent. Faiman 2008 [2] en tiendrait compte, mais ses
coefficients par défaut sont calibrés en climat désertique ; sans calibration
locale ils donneraient une fausse confiance B (code archivé sur la branche
``wip/faiman-terrain``). SAPM [3] et PVsyst exigent une calibration de site.
T2M MERRA-2 peut être sous-estimée en altitude (Labé, Mamou).

[1] Ross R.G. Jr. 1980. "Flat-plate photovoltaic array design
    optimization." 14th IEEE PVSC, San Diego, p. 1126-1132.
[2] Faiman D. 2008. "Assessing the outdoor operating temperature of
    photovoltaic modules." Progress in Photovoltaics 16(4), 307-315.
    DOI : 10.1002/pip.813.
[3] King D.L., Boyson W.E., Kratochvil J.A. 2004. "Photovoltaic Array
    Performance Model." Sandia SAND2004-3535.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date, datetime
from typing import Literal, TypedDict

from kuma_data_core.api.v1.schemas.grandeurs import (
    ParametresProductibleCorrectionThermique,
    ResultatJournalier,
)
from kuma_data_core.editorial.niveaux_confiance import NiveauConfiance

PLAFOND_CONFIANCE: NiveauConfiance = "B"
"""Plafond ``B`` : modèle et paramètres déclarés par l'appelant, invérifiables."""

# === Constantes module ====================================================

UNITE_PRODUCTIBLE: str = "kWh"
"""Énergie journalière en kWh."""

NIVEAU_CONFIANCE_DERIVE_F2_V1: Literal["B"] = "B"
"""Niveau provisoire du calcul pur, remplacé par la route (règle de propagation P)."""

TEMPERATURE_STC_DEGC: float = 25.0
"""Température STC de référence (°C)."""

TEMPERATURE_NOCT_REFERENCE_DEGC: float = 20.0
"""Température ambiante de référence du test NOCT (°C, Ross 1980)."""

IRRADIANCE_NOCT_REFERENCE_W_PAR_M2: float = 800.0
"""Irradiance de référence du test NOCT (W/m², Ross 1980)."""


# === TypedDict d'entree ===================================================


class MesureJourThermique(TypedDict):
    """Mesure journalière : T2M (°C) et irradiance G (GHI ou POA, kWh/m²/jour)."""

    instant_mesure: date
    t_amb_degc: float
    irradiance_kwh_par_m2_jour: float


class MesureHeureThermique(TypedDict):
    """Mesure horaire : T2M (°C) et GHI en W/m² (≈ Wh/m² sur l'heure)."""

    instant_mesure: datetime
    t_amb_degc: float
    irradiance_w_par_m2: float


# === Fonctions privees pures ==============================================


def _temperature_cellule_noct(
    t_amb_degc: float,
    irradiance_w_par_m2: float,
    noct_degc: float,
) -> float:
    """Température cellule par le modèle NOCT simple (formule en tête de module)."""
    return t_amb_degc + (noct_degc - TEMPERATURE_NOCT_REFERENCE_DEGC) * (
        irradiance_w_par_m2 / IRRADIANCE_NOCT_REFERENCE_W_PAR_M2
    )


def _productible_jour(
    mesure: MesureJourThermique,
    parametres: ParametresProductibleCorrectionThermique,
) -> float:
    """Productible journalier (kWh), T_cell calculée sur l'irradiance moyenne sur 24 h."""
    # kWh/m²/jour -> W/m² moyen sur 24 h.
    irradiance_w_par_m2 = mesure["irradiance_kwh_par_m2_jour"] * 1000.0 / 24.0

    t_cell = _temperature_cellule_noct(
        t_amb_degc=mesure["t_amb_degc"],
        irradiance_w_par_m2=irradiance_w_par_m2,
        noct_degc=parametres.noct_degc,
    )

    facteur_thermique = 1.0 + parametres.coeff_temp_pourcent_par_degc / 100.0 * (
        t_cell - TEMPERATURE_STC_DEGC
    )

    # kWh = P_STC (kWc) x irradiance (kWh/m²/jour) / G_STC (1 kW/m²) x facteur
    productible_kwh = (
        parametres.puissance_stc_wc
        / 1000.0
        * mesure["irradiance_kwh_par_m2_jour"]
        * facteur_thermique
    )

    return max(0.0, productible_kwh)


# === Fonction publique ====================================================


def calculer_productible_correction_thermique(
    mesures: Sequence[MesureJourThermique],
    parametres: ParametresProductibleCorrectionThermique,
) -> list[ResultatJournalier]:
    """Productible journalier corrigé NOCT, ordonné par date.

    Confiance provisoire ``'B'``, remplacée par la route (règle P).
    """
    resultats: list[ResultatJournalier] = []
    for mesure in mesures:
        productible = _productible_jour(mesure=mesure, parametres=parametres)
        resultats.append(
            ResultatJournalier(
                instant=mesure["instant_mesure"],
                valeur=productible,
                unite=UNITE_PRODUCTIBLE,
                niveau_confiance=NIVEAU_CONFIANCE_DERIVE_F2_V1,
            )
        )
    return resultats


def calculer_productible_correction_thermique_horaire(
    mesures: Sequence[MesureHeureThermique],
    parametres: ParametresProductibleCorrectionThermique,
) -> list[ResultatJournalier]:
    """Productible NOCT calculé heure par heure, sommé par jour UTC (kWh).

    La moyenne sur 24 h sous-estime T_cell à midi et donc surestime le
    productible ; l'intégration horaire lève ce biais.
    """
    energie_par_jour: dict[date, float] = {}
    for mesure in mesures:
        irradiance_w = mesure["irradiance_w_par_m2"]
        t_cell = _temperature_cellule_noct(
            t_amb_degc=mesure["t_amb_degc"],
            irradiance_w_par_m2=irradiance_w,
            noct_degc=parametres.noct_degc,
        )
        facteur_thermique = 1.0 + parametres.coeff_temp_pourcent_par_degc / 100.0 * (
            t_cell - TEMPERATURE_STC_DEGC
        )
        # kWh = P_STC (kWc) x G (W/m² sur 1 h, /1000 -> kWh/m²) / G_STC (1 kW/m²) x facteur
        energie_heure_kwh = (
            parametres.puissance_stc_wc / 1000.0 * (irradiance_w / 1000.0) * facteur_thermique
        )
        jour = mesure["instant_mesure"].date()
        energie_par_jour[jour] = energie_par_jour.get(jour, 0.0) + energie_heure_kwh

    return [
        ResultatJournalier(
            instant=jour,
            valeur=max(0.0, energie),
            unite=UNITE_PRODUCTIBLE,
            niveau_confiance=NIVEAU_CONFIANCE_DERIVE_F2_V1,
        )
        for jour, energie in energie_par_jour.items()
    ]
