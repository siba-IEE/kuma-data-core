"""Énergie utile à la volée d'un capteur solaire ECS, au bord du capteur.

Hottel-Whillier-Bliss [1, 2], rendement instantané du second ordre :

    eta = eta0 - a1 * dT / G - a2 * dT² / G      (borné à 0)
    Q_utile = eta * G * Delta_t

eta0 sans unité, a1 en W/(m²·K), a2 en W/(m²·K²) (fiche Solar Keymark,
fournie par l'appelant), dT = T_fluide - T_amb (K), G en W/m² dans le plan
du capteur. T_fluide est approchée par la température d'entrée (débit non
modélisé).

Limites : pas de système complet (stockage, fraction solaire : f-chart [3]),
pas d'IAM, T2M MERRA-2 possiblement sous-estimée en altitude (Labé, Mamou).

[1] Hottel H.C., Whillier A. 1958. "Evaluation of flat-plate solar
    collector performance." Trans. Conference on the Use of Solar Energy,
    vol. 2, part 1, p. 74. University of Arizona Press.
[2] Duffie J.A., Beckman W.A., Blair N. 2020. "Solar Engineering of
    Thermal Processes, Photovoltaics and Wind", 5e éd. Wiley.
    ISBN 978-1-119-54028-1.
[3] Klein S.A., Beckman W.A., Duffie J.A. 1976. "A design procedure for
    solar heating systems." Solar Energy 18(2), 113-127.
    DOI : 10.1016/0038-092X(76)90044-X.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date, datetime
from typing import Literal, TypedDict

from kuma_data_core.api.v1.schemas.grandeurs import (
    ParametresEnergieUtileECS,
    ResultatJournalier,
)
from kuma_data_core.editorial.niveaux_confiance import NiveauConfiance

PLAFOND_CONFIANCE: NiveauConfiance = "B"
"""Plafond ``B`` : modèle et paramètres déclarés par l'appelant, invérifiables."""

# === Constantes module ====================================================

UNITE_ENERGIE_UTILE: str = "kWh/m²"
"""Énergie journalière par m² de capteur."""

NIVEAU_CONFIANCE_DERIVE_F2_V1: Literal["B"] = "B"
"""Niveau provisoire du calcul pur, remplacé par la route (règle de propagation P)."""


# === TypedDict d'entree ===================================================


class MesureJourECS(TypedDict):
    """Mesure journalière : T2M (°C) et irradiance G (GHI ou POA, kWh/m²/jour)."""

    instant_mesure: date
    t_amb_degc: float
    irradiance_kwh_par_m2_jour: float


class MesureHeureECS(TypedDict):
    """Mesure horaire : T2M (°C) et GHI en W/m² (≈ Wh/m² sur l'heure)."""

    instant_mesure: datetime
    t_amb_degc: float
    irradiance_w_par_m2: float


# === Fonctions privees pures ==============================================


def _rendement_instantane_hwb(
    eta0: float,
    a1: float,
    a2: float,
    dt_kelvin: float,
    irradiance_w_par_m2: float,
) -> float:
    """Rendement HWB ; 0 sans irradiance ou en stagnation (rendement négatif)."""
    if irradiance_w_par_m2 <= 0:
        return 0.0
    eta = eta0 - a1 * dt_kelvin / irradiance_w_par_m2 - a2 * (dt_kelvin**2) / irradiance_w_par_m2
    return max(0.0, eta)


def _energie_utile_jour(
    mesure: MesureJourECS,
    parametres: ParametresEnergieUtileECS,
) -> float:
    """Énergie utile journalière (kWh/m²), rendement calculé sur G moyen sur 24 h."""
    # kWh/m²/jour -> W/m² moyen sur 24 h : le rendement dépend de G en W/m².
    irradiance_w_par_m2 = mesure["irradiance_kwh_par_m2_jour"] * 1000.0 / 24.0

    dt_kelvin = parametres.temperature_fluide_entree_degc - mesure["t_amb_degc"]

    eta = _rendement_instantane_hwb(
        eta0=parametres.rendement_optique_eta0,
        a1=parametres.pertes_lineaires_a1,
        a2=parametres.pertes_quadratiques_a2,
        dt_kelvin=dt_kelvin,
        irradiance_w_par_m2=irradiance_w_par_m2,
    )

    return eta * mesure["irradiance_kwh_par_m2_jour"]


# === Fonction publique ====================================================


def calculer_energie_utile_ecs(
    mesures: Sequence[MesureJourECS],
    parametres: ParametresEnergieUtileECS,
) -> list[ResultatJournalier]:
    """Énergie utile journalière (kWh/m² de capteur), ordonnée par date.

    Confiance provisoire ``'B'``, remplacée par la route (règle P).
    """
    resultats: list[ResultatJournalier] = []
    for mesure in mesures:
        energie = _energie_utile_jour(mesure=mesure, parametres=parametres)
        resultats.append(
            ResultatJournalier(
                instant=mesure["instant_mesure"],
                valeur=energie,
                unite=UNITE_ENERGIE_UTILE,
                niveau_confiance=NIVEAU_CONFIANCE_DERIVE_F2_V1,
            )
        )
    return resultats


def calculer_energie_utile_ecs_horaire(
    mesures: Sequence[MesureHeureECS],
    parametres: ParametresEnergieUtileECS,
) -> list[ResultatJournalier]:
    """Énergie utile calculée heure par heure, sommée par jour UTC (kWh/m²).

    Le rendement HWB n'est pas linéaire en G : le rendement de la moyenne sur
    24 h ne reproduit pas la somme horaire (biais de Jensen).
    """
    energie_par_jour: dict[date, float] = {}
    for mesure in mesures:
        irradiance_w = mesure["irradiance_w_par_m2"]
        dt_kelvin = parametres.temperature_fluide_entree_degc - mesure["t_amb_degc"]
        eta = _rendement_instantane_hwb(
            eta0=parametres.rendement_optique_eta0,
            a1=parametres.pertes_lineaires_a1,
            a2=parametres.pertes_quadratiques_a2,
            dt_kelvin=dt_kelvin,
            irradiance_w_par_m2=irradiance_w,
        )
        # kWh/m² = eta x G (W/m² sur 1 h, /1000)
        energie_heure = eta * (irradiance_w / 1000.0)
        jour = mesure["instant_mesure"].date()
        energie_par_jour[jour] = energie_par_jour.get(jour, 0.0) + energie_heure

    return [
        ResultatJournalier(
            instant=jour,
            valeur=energie,
            unite=UNITE_ENERGIE_UTILE,
            niveau_confiance=NIVEAU_CONFIANCE_DERIVE_F2_V1,
        )
        for jour, energie in energie_par_jour.items()
    ]
