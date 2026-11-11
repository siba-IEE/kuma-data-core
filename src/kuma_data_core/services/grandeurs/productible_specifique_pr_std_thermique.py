"""Grandeur F2 dérivée : productible spécifique climatologique mensuel
(kWh/kWc), PR standard hors thermique et correction thermique journalière.

Pour une unité géographique, 12 valeurs représentant la production attendue
d'un mois moyen de la période fournie, avec :

- le PR standard hors thermique de la méthode v1.1 (0,78975 =
  ``rend_onduleur × rend_mppt × (1 − pertes_diverses_pct / 100)``) ;
- la correction thermique de Dierauf 2013, appliquée jour par jour puis
  agrégée par mois.

Alimente la clé ``pspNormalesKwhParKwc[12]`` du pack v1.1. Ne sert pas au
dimensionnement crête, qui reste calé sur le mois défavorable via
``ghiNormales``.

Le calcul est journalier parce que le facteur NOCT dépend non linéairement de
l'irradiance : appliquer la correction à une moyenne mensuelle biaiserait le
résultat (c'est pourquoi le service mensuel de ``productible_pr_fourni``
l'interdit).

Références :
[1] Marion et al. 2005, NREL/CP-520-37358 (PR brut).
[2] Dierauf et al. 2013, NREL/TP-5200-57991 (PR corrigé en température).
[3] Ross R.G. Jr. 1980, Flat-plate PV array design optimization (modèle NOCT,
    repris de ``productible_correction_thermique``).
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Final, TypedDict

from kuma_data_core.services.grandeurs.productible_correction_thermique import (
    _temperature_cellule_noct,
)

UNITE_SORTIE: Final[str] = "kWh/kWc"
"""Unité de sortie : énergie mensuelle par kWc de crête installée."""

TEMPERATURE_STC_DEGC: Final[float] = 25.0
"""Température STC de référence (°C), identique à ``productible_pr_fourni``."""

NB_MOIS: Final[int] = 12


class MesureJourGhiTamb(TypedDict):
    """Mesure journalière GHI + T_amb pour un point donné.

    ``ghi_kwh_par_m2_jour`` : irradiation globale horizontale intégrée sur la
    journée. ``t_amb_degc`` : température ambiante moyenne 24 h.
    """

    annee: int
    mois: int  # 1..12
    ghi_kwh_par_m2_jour: float
    t_amb_degc: float


def calculer_productible_specifique_pr_std_thermique_mensuel(
    mesures: Sequence[MesureJourGhiTamb],
    pr_std: float,
    noct_degc: float,
    coeff_temp_pct_par_degc: float,
) -> list[float]:
    """Retourne 12 valeurs mensuelles en kWh/kWc (janvier à l'index 0).

    Chaque valeur est la moyenne, sur les années présentes dans ``mesures``,
    des sommes journalières du mois. ``pr_std`` est le PR standard hors
    thermique (méthode v1.1 : 0,78975), ``noct_degc`` le NOCT du module
    (méthode : 45,0) et ``coeff_temp_pct_par_degc`` le coefficient de
    température de P_max (méthode : −0,4 %/°C). Un mois sans mesure donne 0,0 :
    l'appelant garantit la couverture de la période climatologique.
    """
    sommes: dict[tuple[int, int], float] = {}
    compteurs: dict[int, set[int]] = {m: set() for m in range(1, NB_MOIS + 1)}

    for m in mesures:
        annee = m["annee"]
        mois = m["mois"]
        ghi = m["ghi_kwh_par_m2_jour"]
        t_amb = m["t_amb_degc"]

        # Irradiance moyenne sur 24 h (W/m²), comme dans
        # productible_pr_fourni._productible_pr_t_jour.
        irradiance_w_par_m2 = ghi * 1000.0 / 24.0
        t_cell = _temperature_cellule_noct(
            t_amb_degc=t_amb,
            irradiance_w_par_m2=irradiance_w_par_m2,
            noct_degc=noct_degc,
        )
        ratio_thermique = 1.0 + coeff_temp_pct_par_degc / 100.0 * (t_cell - TEMPERATURE_STC_DEGC)
        # Productible journalier pour 1 kWc, en kWh :
        #   P_STC (1 kWc) × GHI (kWh/m²/j) / G_STC (1 kW/m²) × PR × ratio
        productible_jour = ghi * pr_std * ratio_thermique
        productible_jour = max(0.0, productible_jour)

        cle = (annee, mois)
        sommes[cle] = sommes.get(cle, 0.0) + productible_jour
        compteurs[mois].add(annee)

    resultats: list[float] = [0.0] * NB_MOIS
    for mois in range(1, NB_MOIS + 1):
        annees = compteurs[mois]
        if not annees:
            resultats[mois - 1] = 0.0
            continue
        total = sum(sommes[(annee, mois)] for annee in annees)
        resultats[mois - 1] = total / len(annees)

    return resultats
