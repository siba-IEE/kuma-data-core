"""Grandeur F2 : énergie utile d'un capteur solaire d'eau chaude sanitaire.

Énergie thermique utile au bord du capteur, d'après l'irradiance, la
température ambiante, la température d'entrée du fluide et les caractéristiques
du capteur fournies par l'appelant.

Modèle de Hottel-Whillier-Bliss [1, 2], rendement instantané en polynôme du
second ordre :

    eta = eta0 - a1 * dT / G - a2 * dT² / G
    Q_utile = max(0, eta) * G * Delta_t

- eta0 : rendement optique sans pertes (fiche Solar Keymark ou équivalent) ;
- a1 : pertes linéaires, W/(m²·K) ; a2 : pertes quadratiques, W/(m²·K²) ;
- dT = T_fluide_moyenne - T_amb (K), T_fluide_moyenne étant approchée par la
  température d'entrée du fluide (débit massique non modélisé) ;
- G : irradiance globale dans le plan du capteur (W/m²).

Limites :

- pas de calcul du système complet (stockage, charge, fraction solaire ; voir
  la méthode f-chart [3]) ;
- pas de modificateur d'angle d'incidence (IAM) ;
- T_amb = T2M MERRA-2, biais possible en altitude (Labé, Mamou).

Niveau de confiance : le plus bas des entrées, au plus ``PLAFOND_CONFIANCE``,
par la règle de propagation que la route applique (ADR-0008).

Références :

[1] Hottel H.C., Whillier A. 1958. "Evaluation of flat-plate solar
    collector performance." Transactions of the Conference on the Use
    of Solar Energy, vol. 2, part 1, p. 74. University of Arizona Press.
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
from typing import Literal, Protocol, TypedDict

from kuma_data_core.editorial.niveaux_confiance import NiveauConfiance
from kuma_data_core.services.grandeurs.types import ResultatJournalier

PLAFOND_CONFIANCE: NiveauConfiance = "B"
"""Plafond de confiance : modèle de calcul et paramètres déclarés, invérifiables."""


UNITE_ENERGIE_UTILE: str = "kWh/m²"
"""Unité de sortie : énergie cumulée journalière par m² de capteur."""

NIVEAU_CONFIANCE_DERIVE_F2_V1: Literal["B"] = "B"
"""Niveau provisoire du calcul pur, remplacé par la route (règle de propagation P)."""


class ParametresCalculECS(Protocol):
    """Grandeurs physiques que lit le calcul ECS : capteur et température d'entrée du fluide."""

    @property
    def rendement_optique_eta0(self) -> float: ...  # sans dimension

    @property
    def pertes_lineaires_a1(self) -> float: ...  # W/(m²·K)

    @property
    def pertes_quadratiques_a2(self) -> float: ...  # W/(m²·K²)

    @property
    def temperature_fluide_entree_degc(self) -> float: ...


class MesureJourECS(TypedDict):
    """Mesure journalière consommée par le calcul énergie utile ECS.

    Combine la température ambiante T2M (NASA POWER) et l'irradiance G
    (GHI ou POA pré-calculé). G est exprimée en kWh/m²/jour.
    """

    instant_mesure: date
    t_amb_degc: float
    irradiance_kwh_par_m2_jour: float


class MesureHeureECS(TypedDict):
    """Mesure horaire consommée par l'énergie utile ECS en intégration horaire.

    ``irradiance_w_par_m2`` est l'irradiance horaire (GHI, W/m² ≈ Wh/m² par
    heure) ; ``t_amb_degc`` la température ambiante horaire.
    """

    instant_mesure: datetime
    t_amb_degc: float
    irradiance_w_par_m2: float


def _rendement_instantane_hwb(
    eta0: float,
    a1: float,
    a2: float,
    dt_kelvin: float,
    irradiance_w_par_m2: float,
) -> float:
    """Rendement instantané HWB (formule en tête de module).

    Renvoie 0 si irradiance ≤ 0 (capteur inactif) ou si le rendement
    calculé est négatif (stagnation thermique, pas d'énergie utile).
    """
    if irradiance_w_par_m2 <= 0:
        return 0.0
    eta = eta0 - a1 * dt_kelvin / irradiance_w_par_m2 - a2 * (dt_kelvin**2) / irradiance_w_par_m2
    return max(0.0, eta)


def _energie_utile_jour(
    mesure: MesureJourECS,
    parametres: ParametresCalculECS,
) -> float:
    """Énergie utile journalière par m² de capteur (kWh/m²).

    Le rendement HWB est évalué avec l'irradiance moyenne sur 24 h et la
    température ambiante moyenne du jour : approximation que lève
    l'intégration horaire.
    """
    # kWh/m²/jour -> W/m² moyen sur 24 h.
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


def calculer_energie_utile_ecs(
    mesures: Sequence[MesureJourECS],
    parametres: ParametresCalculECS,
) -> list[ResultatJournalier]:
    """Énergie utile journalière au bord du capteur, en kWh/m² (Hottel-Whillier-Bliss).

    Le niveau de confiance ``'B'`` des résultats est provisoire : la route le
    remplace.
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
    parametres: ParametresCalculECS,
) -> list[ResultatJournalier]:
    """Énergie utile journalière par intégration horaire (Hottel-Whillier-Bliss).

    Le rendement est appliqué heure par heure, puis l'énergie est sommée par
    jour (date de ``instant_mesure``). Le rendement HWB étant non linéaire en
    G, le rendement de la moyenne sur 24 h ne reproduit pas la somme horaire
    (biais de Jensen) ; cette variante l'évite. L'appelant fournit GHI et T2M
    horaires alignés ; un résultat par jour, en kWh/m².
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
        # W/m² pendant 1 h = Wh/m², d'où la division par 1000 pour des kWh/m².
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
