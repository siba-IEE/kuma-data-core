"""Grandeur F2 : productible PV avec correction thermique.

La température de fonctionnement du module dégrade sa puissance par rapport
aux conditions STC (1000 W/m², 25 °C, AM1.5). Modèle NOCT simple (Ross 1980)
[1], à partir de la seule constante NOCT de la fiche produit :

    T_cell = T_amb + (NOCT - 20) * G / 800
    P_AC = P_STC * (G / 1000) * [1 + gamma_Pmax / 100 * (T_cell - 25)]

- G : irradiance reçue par le module (GHI ou POA), W/m² ;
- T_amb : température ambiante (T2M NASA POWER), °C ;
- gamma_Pmax : coefficient de température en %/°C (négatif, typiquement -0,4
  pour le silicium cristallin).

En méthode journalière, T_cell est calculée avec l'irradiance moyenne sur
24 h, ``G_24h = G_jour * 1000 / 24`` : le pic de midi est lissé, donc T_cell
sous-estimée et le productible surestimé. L'intégration horaire lève ce biais.

Limites :

- le modèle ignore le vent. Le modèle de Faiman 2008 [2] le prend en compte,
  mais ses coefficients par défaut sont calibrés en climat désertique : sans
  calibration locale, ils donneraient une fausse assurance en climat tropical ;
- les modèles Sandia SAPM [3] et PVsyst, plus précis, demandent davantage de
  paramètres ou une calibration par site ;
- T_amb = T2M MERRA-2, biais possible en altitude (Labé, Mamou).

Niveau de confiance : le plus bas des entrées, au plus ``PLAFOND_CONFIANCE``,
par la règle de propagation que la route applique (ADR-0008).

Références :

[1] Ross R.G. Jr. 1980. "Flat-plate photovoltaic array design
    optimization." Conference Record of the 14th IEEE Photovoltaic
    Specialists Conference, San Diego, CA, p. 1126-1132.
[2] Faiman D. 2008. "Assessing the outdoor operating temperature of
    photovoltaic modules." Progress in Photovoltaics 16(4), 307-315.
    DOI : 10.1002/pip.813.
[3] King D.L., Boyson W.E., Kratochvil J.A. 2004. "Photovoltaic Array
    Performance Model." Sandia National Laboratories Report
    SAND2004-3535 (OSTI 919131).
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
"""Plafond de confiance : modèle de calcul et paramètres déclarés, invérifiables."""


UNITE_PRODUCTIBLE: str = "kWh"
"""Unité de sortie : énergie cumulée journalière en kWh."""

NIVEAU_CONFIANCE_DERIVE_F2_V1: Literal["B"] = "B"
"""Niveau provisoire du calcul pur, remplacé par la route (règle de propagation P)."""

IRRADIANCE_STC_W_PAR_M2: float = 1000.0
"""Irradiance STC de référence (W/m²)."""

TEMPERATURE_STC_DEGC: float = 25.0
"""Température STC de référence (°C)."""

TEMPERATURE_NOCT_REFERENCE_DEGC: float = 20.0
"""Température ambiante de référence du test NOCT (°C, Ross 1980)."""

IRRADIANCE_NOCT_REFERENCE_W_PAR_M2: float = 800.0
"""Irradiance de référence du test NOCT (W/m², Ross 1980)."""


class MesureJourThermique(TypedDict):
    """Mesure journalière consommée par le calcul productible thermique.

    Température ambiante T2M et irradiance G (GHI ou POA pré-calculé) en
    kWh/m²/jour.
    """

    instant_mesure: date
    t_amb_degc: float
    irradiance_kwh_par_m2_jour: float


class MesureHeureThermique(TypedDict):
    """Mesure horaire consommée par le productible thermique en intégration horaire.

    ``irradiance_w_par_m2`` est l'irradiance horaire (GHI, W/m² ≈ Wh/m² par
    heure) ; ``t_amb_degc`` la température ambiante horaire.
    """

    instant_mesure: datetime
    t_amb_degc: float
    irradiance_w_par_m2: float


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
    """Productible journalier (kWh) avec correction thermique, borné à 0.

    T_cell est calculée avec l'irradiance moyenne sur 24 h (voir l'en-tête du
    module).
    """
    irradiance_w_par_m2 = mesure["irradiance_kwh_par_m2_jour"] * 1000.0 / 24.0

    t_cell = _temperature_cellule_noct(
        t_amb_degc=mesure["t_amb_degc"],
        irradiance_w_par_m2=irradiance_w_par_m2,
        noct_degc=parametres.noct_degc,
    )

    facteur_thermique = 1.0 + parametres.coeff_temp_pourcent_par_degc / 100.0 * (
        t_cell - TEMPERATURE_STC_DEGC
    )

    # P_STC (kWc) x irradiance (kWh/m²/jour) / G_STC (1 kW/m²) x facteur_thermique
    productible_kwh = (
        parametres.puissance_stc_wc
        / 1000.0
        * mesure["irradiance_kwh_par_m2_jour"]
        * facteur_thermique
    )

    return max(0.0, productible_kwh)


def calculer_productible_correction_thermique(
    mesures: Sequence[MesureJourThermique],
    parametres: ParametresProductibleCorrectionThermique,
) -> list[ResultatJournalier]:
    """Productible PV journalier (kWh) avec correction thermique NOCT (Ross 1980).

    Le niveau de confiance ``'B'`` des résultats est provisoire : la route le
    remplace.
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
    """Productible journalier (kWh) corrigé en température, par intégration horaire.

    T_cell et le facteur thermique sont calculés heure par heure sur
    l'irradiance horaire, puis l'énergie est sommée par jour (date de
    ``instant_mesure``) et bornée à 0. L'appelant fournit GHI et T2M horaires
    alignés.
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
        # W/m² pendant 1 h = Wh/m² ; G_STC = 1 kW/m² est implicite.
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
