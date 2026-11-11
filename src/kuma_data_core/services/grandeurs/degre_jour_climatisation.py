"""Grandeur F2 : degrés-jours de climatisation (DJC) mensuels.

Besoin de refroidissement d'un bâtiment par rapport à une température de base
T_b (°C) fournie par l'appelant. Deux méthodes :

- moyenne journalière [1, 2] :
    DJC_mois = Σ_jours max(0, T_moy_jour - T_b) ;
- intégration horaire :
    DJC_mois = Σ_heures max(0, T_heure - T_b) / 24.

Les résultats sont des :class:`ResultatMensuel` (``instant="YYYY-MM"``).

Limites :

- la moyenne journalière sous-estime le DJC quand le cycle diurne est marqué
  (-5 à -15 % en climat tropical humide) ; l'intégration horaire lève ce
  biais ;
- pas de base T_b normalisée pour la Guinée : 18,3 °C (ASHRAE), 24-26 °C
  (CEDEAO) et 24 °C (RTAA DOM) sont des références régionales partiellement
  transposables ;
- T_amb = T2M MERRA-2, biais possible en altitude (Labé, Mamou) ;
- la méthode du point d'équilibre (ASHRAE) n'est pas traitée.

Niveau de confiance : le plus bas des entrées, au plus ``PLAFOND_CONFIANCE``,
par la règle de propagation que la route applique (ADR-0008).

Références :

[1] Erbs D.G., Klein S.A., Beckman W.A. 1983. "Estimation of degree-days
    and ambient temperature bin data from monthly-average temperatures."
    ASHRAE Journal 25(6), 60-65.
[2] Schoenau G.J., Kehrig R.A. 1990. "Method for calculating degree-days
    to any base temperature." Energy and Buildings 14(4), 299-302.
    DOI : 10.1016/0378-7788(90)90092-W.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date, datetime
from typing import Literal, Protocol, TypedDict

from kuma_data_core.editorial.niveaux_confiance import NiveauConfiance
from kuma_data_core.services.grandeurs.types import ResultatMensuel

PLAFOND_CONFIANCE: NiveauConfiance = "B"
"""Plafond de confiance : modèle de calcul et paramètres déclarés, invérifiables."""


UNITE_DJC: str = "°C·j"
"""Unité de sortie : degrés-jours cumulés sur le mois."""

HEURES_PAR_JOUR: float = 24.0
"""Diviseur de l'intégration horaire : convertit la somme d'écarts horaires
(°C) en degrés-jours (°C·j). Méthode Erbs 1983."""

NIVEAU_CONFIANCE_DERIVE_F2_V1: Literal["B"] = "B"
"""Niveau provisoire du calcul pur, remplacé par la route (règle de propagation P)."""


class ParametresCalculDJC(Protocol):
    """Grandeur physique que lit le calcul des degrés-jours : la température de base T_b."""

    @property
    def base_temperature_degc(self) -> float: ...


class MesureJourTemperature(TypedDict):
    """Mesure journalière de température moyenne consommée par le calcul DJC."""

    instant_mesure: date
    t_moy_degc: float


class MesureHeureTemperature(TypedDict):
    """Mesure horaire de température consommée par l'intégration horaire."""

    instant_mesure: datetime
    t_degc: float


def _ecart_jour(t_moy_degc: float, base_temperature_degc: float) -> float:
    """Écart positif à la base pour un jour : ``max(0, T_moy_jour - T_b)``."""
    return max(0.0, t_moy_degc - base_temperature_degc)


def _cle_mois(jour: date) -> str:
    """Formate un mois calendaire au format ``YYYY-MM`` (ResultatMensuel)."""
    return f"{jour.year:04d}-{jour.month:02d}"


def _agreger_djc_par_mois(
    mesures: Sequence[MesureJourTemperature],
    base_temperature_degc: float,
) -> dict[str, float]:
    """Somme les écarts journaliers par mois ``YYYY-MM``, dans l'ordre des mesures."""
    djc_par_mois: dict[str, float] = {}
    for mesure in mesures:
        ecart = _ecart_jour(
            t_moy_degc=mesure["t_moy_degc"],
            base_temperature_degc=base_temperature_degc,
        )
        cle = _cle_mois(mesure["instant_mesure"])
        djc_par_mois[cle] = djc_par_mois.get(cle, 0.0) + ecart
    return djc_par_mois


def calculer_degre_jour_climatisation(
    mesures: Sequence[MesureJourTemperature],
    parametres: ParametresCalculDJC,
) -> list[ResultatMensuel]:
    """DJC mensuels par la méthode de la moyenne journalière, en °C·j.

    Le niveau de confiance ``'B'`` des résultats est provisoire : la route le
    remplace.
    """
    djc_par_mois = _agreger_djc_par_mois(
        mesures=mesures,
        base_temperature_degc=parametres.base_temperature_degc,
    )
    return [
        ResultatMensuel(
            instant=cle_mois,
            valeur=djc_cumule,
            unite=UNITE_DJC,
            niveau_confiance=NIVEAU_CONFIANCE_DERIVE_F2_V1,
        )
        for cle_mois, djc_cumule in djc_par_mois.items()
    ]


def _agreger_djc_horaire_par_mois(
    mesures: Sequence[MesureHeureTemperature],
    base_temperature_degc: float,
) -> dict[str, float]:
    """Somme par mois ``YYYY-MM`` les écarts horaires positifs, divisés par 24.

    Une heure chaude compte même si la moyenne du jour reste sous T_b.
    """
    djc_par_mois: dict[str, float] = {}
    for mesure in mesures:
        ecart = max(0.0, mesure["t_degc"] - base_temperature_degc)
        cle = _cle_mois(mesure["instant_mesure"])
        djc_par_mois[cle] = djc_par_mois.get(cle, 0.0) + ecart / HEURES_PAR_JOUR
    return djc_par_mois


def calculer_degre_jour_climatisation_horaire(
    mesures: Sequence[MesureHeureTemperature],
    parametres: ParametresCalculDJC,
) -> list[ResultatMensuel]:
    """DJC mensuels par intégration horaire, en °C·j.

    La méthode n'est pas un paramètre du calcul : l'appelant choisit la fonction
    et fournit les heures à retenir. Le niveau de confiance ``'B'`` des résultats
    est provisoire : la route le remplace.
    """
    djc_par_mois = _agreger_djc_horaire_par_mois(
        mesures=mesures,
        base_temperature_degc=parametres.base_temperature_degc,
    )
    return [
        ResultatMensuel(
            instant=cle_mois,
            valeur=djc_cumule,
            unite=UNITE_DJC,
            niveau_confiance=NIVEAU_CONFIANCE_DERIVE_F2_V1,
        )
        for cle_mois, djc_cumule in djc_par_mois.items()
    ]
