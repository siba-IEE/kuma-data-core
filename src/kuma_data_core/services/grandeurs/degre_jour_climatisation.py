"""Degrés-jours de climatisation mensuels à la volée, base T_b (°C) fournie par l'appelant.

Méthode de la moyenne journalière [1, 2] :

    DJC_mois = somme sur les jours du mois de max(0, T_moy_jour - T_b)

ou intégration horaire : somme sur les heures de max(0, T_heure - T_b) / 24.

Limites : la moyenne journalière sous-estime le DJC de 5 à 15 % en tropical
humide (cycle diurne), d'où l'option horaire. Pas de base T_b normalisée
pour la Guinée (18.3 °C ASHRAE, 24-26 °C CEDEAO, 24 °C RTAA DOM). T2M MERRA-2
possiblement sous-estimée en altitude (Labé, Mamou).

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
from typing import Literal, TypedDict

from kuma_data_core.api.v1.schemas.grandeurs import (
    ParametresDegreJourClimatisation,
    ResultatMensuel,
)
from kuma_data_core.editorial.niveaux_confiance import NiveauConfiance

PLAFOND_CONFIANCE: NiveauConfiance = "B"
"""Plafond ``B`` : modèle et paramètres déclarés par l'appelant, invérifiables."""

# === Constantes module ====================================================

UNITE_DJC: str = "°C·j"
"""Unité de sortie : degrés-jours cumulés sur le mois."""

HEURES_PAR_JOUR: float = 24.0
"""Convertit une somme d'écarts horaires (°C·h) en degrés-jours (Erbs 1983)."""

NIVEAU_CONFIANCE_DERIVE_F2_V1: Literal["B"] = "B"
"""Niveau provisoire du calcul pur, remplacé par la route (règle de propagation P)."""


# === TypedDict d'entree ===================================================


class MesureJourTemperature(TypedDict):
    """Mesure journalière de température moyenne consommée par le calcul DJC."""

    instant_mesure: date
    t_moy_degc: float


class MesureHeureTemperature(TypedDict):
    """Mesure horaire de température consommée par l'intégration horaire."""

    instant_mesure: datetime
    t_degc: float


# === Fonctions privees pures ==============================================


def _ecart_jour(t_moy_degc: float, base_temperature_degc: float) -> float:
    """``max(0, T_moy_jour - T_b)`` : un jour sous la base ne compte pas."""
    return max(0.0, t_moy_degc - base_temperature_degc)


def _cle_mois(jour: date) -> str:
    """Formate un mois calendaire au format ``YYYY-MM`` (ResultatMensuel)."""
    return f"{jour.year:04d}-{jour.month:02d}"


def _agreger_djc_par_mois(
    mesures: Sequence[MesureJourTemperature],
    base_temperature_degc: float,
) -> dict[str, float]:
    """``{"YYYY-MM": DJC}`` dans l'ordre des mesures."""
    djc_par_mois: dict[str, float] = {}
    for mesure in mesures:
        ecart = _ecart_jour(
            t_moy_degc=mesure["t_moy_degc"],
            base_temperature_degc=base_temperature_degc,
        )
        cle = _cle_mois(mesure["instant_mesure"])
        djc_par_mois[cle] = djc_par_mois.get(cle, 0.0) + ecart
    return djc_par_mois


# === Fonction publique ====================================================


def calculer_degre_jour_climatisation(
    mesures: Sequence[MesureJourTemperature],
    parametres: ParametresDegreJourClimatisation,
) -> list[ResultatMensuel]:
    """DJC mensuels par la moyenne journalière (``°C·j``, ``YYYY-MM``).

    Confiance provisoire ``'B'``, remplacée par la route (règle P).
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
    """``{"YYYY-MM": DJC}`` par intégration horaire.

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
    parametres: ParametresDegreJourClimatisation,
) -> list[ResultatMensuel]:
    """DJC mensuels par intégration horaire (Erbs 1983), sur des heures validées.

    ``parametres.methode`` n'est pas lu : l'appelant a déjà choisi la branche.
    Confiance provisoire ``'B'``, remplacée par la route (règle P).
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
