"""Exceedance inter-annuelle P50/P90 de l'irradiation annuelle (GHI NASA POWER 1991-2020).

    total_annuel(y) = Σ_mois GHI(y, m) [kWh/m²/jour] x nb_jours(m, y)

puis ``numpy.percentile`` (interpolation linéaire) sur les 30 totaux :
P50 = médiane, P90 = **10ᵉ** percentile (valeur dépassée 90 % des années),
donc P90 < P50.

Limites, reprises dans le champ ``limite`` de la réponse : variabilité
inter-annuelle seule, sans incertitude du modèle satellitaire (pas un P90
bancable complet) ; 3 valeurs en queue sur 30 ; Kindia et Mamou partagent un
pixel CERES SYN1deg (110 km à 10° N) et ont donc les mêmes P50/P90.

Référence : IEA PVPS Task 16, "Best Practices for Solar Resource Assessment".
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

# === Constantes module ====================================================

UNITE_GHI_EXCEEDANCE: str = "kWh/m²/an"
"""Unité de sortie : irradiation annuelle (énergie cumulée sur l'année)."""

PERCENTILE_P50: float = 50.0
"""Médiane : irradiation annuelle typique."""

PERCENTILE_P90: float = 10.0
"""P90 (exceedance) = 10ᵉ percentile : valeur dépassée 90 % des années."""

METHODE_PERCENTILE: Literal["linear"] = "linear"
"""Interpolation par défaut de ``numpy.percentile`` ; ``Literal`` pour les overloads mypy."""

ANNEE_DEBUT_CLIMATOLOGIE: int = 1991
ANNEE_FIN_CLIMATOLOGIE: int = 2020
"""Bornes de la fenêtre climatologique OMM 1991-2020."""

NOMBRE_ANNEES_BASE: int = ANNEE_FIN_CLIMATOLOGIE - ANNEE_DEBUT_CLIMATOLOGIE + 1
"""30 années : base d'échantillonnage des percentiles."""


# === Constantes co-localisation ===========================================

PAIRES_COLOCALISEES_D29: dict[str, str] = {
    "gin_kindia": "gin_mamou",
    "gin_mamou": "gin_kindia",
}
"""Villes dans le même pixel CERES SYN1deg (110 km à 10° N) : P50/P90 identiques."""


# === Modele de resultat ===================================================


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


# === Fonction publique pure ===============================================


def calculer_ghi_exceedance(
    totaux_annuels: Sequence[float],
) -> ResultatGhiExceedance:
    """P50 et P90 sur des totaux annuels (kWh/m²/an) ; ``ValueError`` sous 2 valeurs."""
    if len(totaux_annuels) < 2:
        raise ValueError(
            f"calculer_ghi_exceedance requiert au moins 2 totaux annuels, "
            f"recu : {len(totaux_annuels)}."
        )
    valeurs = np.asarray(totaux_annuels, dtype=float)
    p50 = float(np.percentile(valeurs, PERCENTILE_P50, method=METHODE_PERCENTILE))
    p90 = float(np.percentile(valeurs, PERCENTILE_P90, method=METHODE_PERCENTILE))
    return ResultatGhiExceedance(p50=p50, p90=p90)


# === Utilitaires de l'orchestrateur (pures, sans I/O) =====================


def calculer_totaux_annuels(
    mesures_mensuelles: Sequence[tuple[int, int, float]],
) -> dict[int, float]:
    """``{annee: total kWh/m²}`` depuis des ``(annee, mois, kWh/m²/jour)``.

    Pondère par le nombre réel de jours (bissextiles comprises). Une année
    incomplète est renvoyée telle quelle : à l'appelant de la filtrer.
    """
    totaux: dict[int, float] = {}
    for annee, mois, valeur in mesures_mensuelles:
        nb_jours = calendar.monthrange(annee, mois)[1]
        totaux[annee] = totaux.get(annee, 0.0) + valeur * nb_jours
    return totaux
