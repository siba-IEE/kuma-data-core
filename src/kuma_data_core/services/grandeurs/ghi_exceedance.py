"""Grandeur F1 ``ghi_exceedance`` : P50 et P90 de l'irradiation annuelle.

Exceedance inter-annuelle dérivée de la série GHI mensuelle 1991-2020 NASA
POWER (fenêtre climatologique OMM).

Méthode :

1. Totaux annuels : total_annuel(y) = Σ_mois [GHI(y, m) x nb_jours(m, y)],
   GHI mensuel en kWh/m²/jour, nb_jours réel du mois (années bissextiles
   incluses).
2. Percentiles ``numpy.percentile`` (interpolation linéaire) sur les totaux
   annuels : P50 = médiane ; P90 = 10ᵉ percentile, valeur dépassée 90 % des
   années (et non le 90ᵉ percentile), donc P90 ≤ P50.

Niveau de confiance : le plus bas des mesures mensuelles lues, plafonné à A
(percentiles exacts), par la règle de propagation que la route applique
(ADR-0008).

Limites (reprises dans le champ ``limite`` de la réponse API) :

- exceedance inter-annuelle uniquement : l'incertitude du modèle satellitaire
  n'est pas propagée. Ce n'est pas un P90 bancable complet, qui demanderait
  un modèle d'erreur explicite et idéalement une calibration au sol ;
- Kindia et Mamou tombent dans le même pixel CERES SYN1deg de NASA POWER :
  leurs séries mensuelles, donc leurs P50/P90, sont identiques ;
- sur 30 ans, le 10ᵉ percentile repose sur 3 valeurs en queue de
  distribution : incertitude d'échantillonnage sur P90.

Référence : exceedance probabiliste P50/P90, pratique courante en évaluation
de ressource solaire (IEA PVPS Task 16, « Best Practices for Solar Resource
Assessment »).
"""

from __future__ import annotations

import calendar
from collections.abc import Sequence
from typing import Literal

import numpy as np
from pydantic import BaseModel, Field

from kuma_data_core.editorial.niveaux_confiance import NiveauConfiance

PLAFOND_CONFIANCE: NiveauConfiance = "A"
"""Plafond de confiance : percentiles exacts des totaux annuels, sans modèle ni hypothèse."""


UNITE_GHI_EXCEEDANCE: str = "kWh/m²/an"
"""Unité de sortie : irradiation annuelle (énergie cumulée sur l'année)."""

PERCENTILE_P50: float = 50.0
"""Médiane : irradiation annuelle typique."""

PERCENTILE_P90: float = 10.0
"""P90 (exceedance) = 10ᵉ percentile : valeur dépassée 90 % des années."""

METHODE_PERCENTILE: Literal["linear"] = "linear"
"""Interpolation de ``numpy.percentile`` (défaut).

``Literal`` et non ``str`` : exigé par les surcharges de ``numpy.percentile``
sous mypy strict.
"""

ANNEE_DEBUT_CLIMATOLOGIE: int = 1991
ANNEE_FIN_CLIMATOLOGIE: int = 2020
"""Bornes de la fenêtre climatologique OMM 1991-2020."""

NOMBRE_ANNEES_BASE: int = ANNEE_FIN_CLIMATOLOGIE - ANNEE_DEBUT_CLIMATOLOGIE + 1
"""30 années : base d'échantillonnage des percentiles."""


PAIRES_COLOCALISEES_D29: dict[str, str] = {
    "gin_kindia": "gin_mamou",
    "gin_mamou": "gin_kindia",
}
"""Villes partageant le même pixel CERES SYN1deg de NASA POWER : leurs P50/P90
sont identiques à ceux de la ville jumelle."""


class ResultatGhiExceedance(BaseModel):
    """Résultat structuré du calcul P50/P90 d'une ville."""

    p50: float = Field(
        ...,
        description="Mediane (percentile 50) de l'irradiation annuelle, kWh/m²/an.",
    )
    p90: float = Field(
        ...,
        description=(
            "Exceedance P90 = percentile 10 (valeur depassee 90 % des annees), "
            "kWh/m²/an. Toujours < P50 par construction."
        ),
    )


def calculer_ghi_exceedance(
    totaux_annuels: Sequence[float],
) -> ResultatGhiExceedance:
    """Calcule P50 et P90 (10ᵉ percentile) de totaux annuels en kWh/m²/an.

    Lève ``ValueError`` s'il y a moins de 2 valeurs.
    """
    if len(totaux_annuels) < 2:
        raise ValueError(
            f"calculer_ghi_exceedance requiert au moins 2 totaux annuels, "
            f"recu : {len(totaux_annuels)}."
        )
    valeurs = np.asarray(totaux_annuels, dtype=float)
    p50 = float(np.percentile(valeurs, PERCENTILE_P50, method=METHODE_PERCENTILE))
    p90 = float(np.percentile(valeurs, PERCENTILE_P90, method=METHODE_PERCENTILE))
    return ResultatGhiExceedance(p50=p50, p90=p90)


def calculer_totaux_annuels(
    mesures_mensuelles: Sequence[tuple[int, int, float]],
) -> dict[int, float]:
    """Somme par année les valeurs mensuelles pondérées par les jours du mois.

    ``mesures_mensuelles`` : tuples ``(annee, mois, valeur)``, valeur en
    kWh/m²/jour. Une année figure dans le résultat dès qu'elle a une mesure :
    l'appelant écarte les années incomplètes.
    """
    totaux: dict[int, float] = {}
    for annee, mois, valeur in mesures_mensuelles:
        nb_jours = calendar.monthrange(annee, mois)[1]
        totaux[annee] = totaux.get(annee, 0.0) + valeur * nb_jours
    return totaux
