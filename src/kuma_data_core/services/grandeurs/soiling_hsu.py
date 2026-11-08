"""Proxy de salissure à la volée : perte de transmission ``(1 - ratio_hsu) x 100`` en %.

Modèle HSU (``pvlib.soiling.hsu``, Coello & Boyle 2019) sur PM2.5/PM10
(EAC4) et pluie (NASA POWER). pvlib attend des PM en **g/m³** : nos µg/m³
sont multipliés par 1e-6, faute de quoi la perte serait très surestimée
(34 % au lieu de 2 %). Pluie en mm, cumulée à la journée
(``rain_accum_period`` = 1 jour) ; tilt en degrés.

Référence : Coello M. & Boyle L. 2019, "Simple Model For Predicting Time
Series Soiling of Photovoltaic Panels", IEEE Journal of Photovoltaics,
DOI : 10.1109/JPHOTOV.2019.2919628.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date
from typing import Literal, TypedDict

import pandas as pd  # type: ignore[import-untyped]
from pvlib import soiling  # type: ignore[import-untyped]
from pydantic import BaseModel

from kuma_data_core.api.v1.schemas.grandeurs import MesureSoilingJour
from kuma_data_core.editorial.niveaux_confiance import NiveauConfiance

PLAFOND_CONFIANCE: NiveauConfiance = "B"
"""Plafond de confiance : modèle HSU, proxy de la salissure (pas une mesure)."""

# === Constantes (defauts F1 "soiling de site", documentes) =================

SURFACE_TILT_DEFAUT: float = 10.0
"""Tilt fixe (degrés) proche de la latitude guinéenne (9-10° N) ; un autre tilt salit autrement."""

CLEANING_THRESHOLD_DEFAUT_MM: float = 1.0
"""Pluie (mm) sur la période d'accumulation qui nettoie le module (défaut HSU usuel)."""

NIVEAU_CONFIANCE: Literal["B"] = "B"
"""Niveau provisoire du calcul pur, remplacé par la route (règle de propagation P)."""

RAIN_ACCUM_PERIOD = pd.Timedelta("1D")
"""Pas journalier ; pvlib recommande entre 1 h et 24 h."""

GRAMMES_PAR_MICROGRAMME: float = 1e-6
"""Conversion µg/m³ (donnée Kuma) -> g/m³ (entrée attendue par pvlib.soiling.hsu)."""

CAVEAT_SPIN_UP: str = (
    "Modele HSU initialise propre (salissure nulle) : les premiers jours de la "
    "fenetre sous-estiment la salissure reelle (spin-up). Proxy modele, "
    "pas une mesure de salissure au sol ; PM EAC4 grille grossiere 0,75 deg."
)


# === Entree / sortie =======================================================


class MesureEntreeSoiling(TypedDict):
    """Mesure journalière alignée : PM en µg/m³, pluie en mm."""

    instant_mesure: date
    rainfall_mm: float
    pm2_5: float
    pm10: float


class ResultatSoiling(BaseModel):
    """Résultat du proxy de salissure : pertes journalières + caveat."""

    mesures: list[MesureSoilingJour]
    limite: str


# === Fonction publique pure (cœur HSU) =====================================


def calculer_taux_salissure_proxy(
    mesures: Sequence[MesureEntreeSoiling],
    surface_tilt_deg: float = SURFACE_TILT_DEFAUT,
    cleaning_threshold_mm: float = CLEANING_THRESHOLD_DEFAUT_MM,
) -> ResultatSoiling:
    """Perte journalière en %, bornée à [0, 100], PM convertis en g/m³ pour pvlib."""
    if not mesures:
        return ResultatSoiling(mesures=[], limite=CAVEAT_SPIN_UP)

    mesures_tri = sorted(mesures, key=lambda m: m["instant_mesure"])
    index = pd.DatetimeIndex([m["instant_mesure"] for m in mesures_tri])
    rainfall = pd.Series([m["rainfall_mm"] for m in mesures_tri], index=index, dtype=float)
    # µg/m³ -> g/m³ : unité attendue par pvlib.
    pm2_5_g = (
        pd.Series([m["pm2_5"] for m in mesures_tri], index=index, dtype=float)
        * GRAMMES_PAR_MICROGRAMME
    )
    pm10_g = (
        pd.Series([m["pm10"] for m in mesures_tri], index=index, dtype=float)
        * GRAMMES_PAR_MICROGRAMME
    )

    ratio = soiling.hsu(
        rainfall=rainfall,
        cleaning_threshold=cleaning_threshold_mm,
        surface_tilt=surface_tilt_deg,
        pm2_5=pm2_5_g,
        pm10=pm10_g,
        rain_accum_period=RAIN_ACCUM_PERIOD,
    )
    perte = ((1.0 - ratio) * 100.0).clip(lower=0.0, upper=100.0)

    mesures_out = [
        MesureSoilingJour(
            instant=pd.Timestamp(instant).date(),
            perte_pct=float(valeur),
            niveau_confiance=NIVEAU_CONFIANCE,
        )
        for instant, valeur in perte.items()
    ]
    return ResultatSoiling(mesures=mesures_out, limite=CAVEAT_SPIN_UP)
