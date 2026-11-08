"""Productible spécifique climatologique mensuel (kWh/kWc), PR standard et correction thermique.

Douze valeurs pour un mois moyen 1991-2020 : PR standard hors thermique
(``rend_onduleur × rend_mppt × (1 − pertes_diverses_pct / 100)``, 0.78975)
et correction thermique PR_T [2] appliquée **jour par jour**, puis moyenne
mensuelle. Le facteur NOCT [3] n'est pas linéaire en G : appliqué à une
moyenne mensuelle il biaiserait le résultat, d'où le calcul journalier.
Ne sert pas au dimensionnement crête, calé sur le mois défavorable.

[1] Marion et al. 2005, NREL/CP-520-37358 (PR brut).
[2] Dierauf et al. 2013, NREL/TP-5200-57991 (PR_T).
[3] Ross R.G. Jr. 1980. Flat-plate PV array design optimization (NOCT).
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Final, TypedDict

from kuma_data_core.services.grandeurs.productible_correction_thermique import (
    _temperature_cellule_noct,
)

# === Constantes module ====================================================

UNITE_SORTIE: Final[str] = "kWh/kWc"
"""Énergie mensuelle par kWc installé."""

TEMPERATURE_STC_DEGC: Final[float] = 25.0
"""Température STC de référence (°C), identique à ``productible_pr_fourni``."""

NB_MOIS: Final[int] = 12


# === TypedDict d'entrée ===================================================


class MesureJourGhiTamb(TypedDict):
    """GHI journalier (kWh/m²/jour) et température ambiante moyenne sur 24 h (°C)."""

    annee: int
    mois: int  # 1..12
    ghi_kwh_par_m2_jour: float
    t_amb_degc: float


# === Fonction publique pure ==============================================


def calculer_productible_specifique_pr_std_thermique_mensuel(
    mesures: Sequence[MesureJourGhiTamb],
    pr_std: float,
    noct_degc: float,
    coeff_temp_pct_par_degc: float,
) -> list[float]:
    """Douze valeurs en kWh/kWc (janvier à l'index 0), moyennes inter-annuelles par mois.

    Valeurs de méthode : ``pr_std`` 0.78975, ``noct_degc`` 45.0,
    ``coeff_temp_pct_par_degc`` −0.4. Un mois sans mesure vaut 0.0 : à
    l'appelant de garantir la couverture 1991-2020.
    """
    sommes: dict[tuple[int, int], float] = {}
    compteurs: dict[int, set[int]] = {m: set() for m in range(1, NB_MOIS + 1)}

    for m in mesures:
        annee = m["annee"]
        mois = m["mois"]
        ghi = m["ghi_kwh_par_m2_jour"]
        t_amb = m["t_amb_degc"]

        # kWh/m²/jour -> W/m² moyen sur 24 h, comme productible_pr_fourni.
        irradiance_w_par_m2 = ghi * 1000.0 / 24.0
        t_cell = _temperature_cellule_noct(
            t_amb_degc=t_amb,
            irradiance_w_par_m2=irradiance_w_par_m2,
            noct_degc=noct_degc,
        )
        ratio_thermique = 1.0 + coeff_temp_pct_par_degc / 100.0 * (t_cell - TEMPERATURE_STC_DEGC)
        # kWh = P_STC (1 kWc) × GHI (kWh/m²/j) / G_STC (1 kW/m²) × PR × ratio
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
