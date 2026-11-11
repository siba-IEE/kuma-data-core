"""Calcul à la volée du proxy de salissure.

Perte de transmission par salissure des modules PV, en % = ``(1 - ratio_hsu) x 100``,
estimée par le modèle HSU (``pvlib.soiling.hsu``, Coello & Boyle 2019) à partir des
PM2.5 et PM10 (EAC4) et de la pluie (NASA POWER). La route applique ensuite la règle
de propagation P pour le niveau de confiance (ADR-0008).

Unités (signature de pvlib 0.15.1) : ``pvlib.soiling.hsu`` attend les PM en g/m³, la
pluie en mm, l'inclinaison en degrés, et renvoie un ratio de salissure (1 = propre).
Les PM stockées sont en µg/m³ : elles sont converties en g/m³ (x 1e-6) avant l'appel.
Sans cette conversion, la perte calculée est fausse d'un facteur d'échelle (34 % au
lieu de 2 % sur un essai).

``rain_accum_period = 1 jour`` : la pluie est déjà cumulée à la journée ; un jour de
pluie au-delà du seuil ``cleaning_threshold`` nettoie le module ce jour-là.

Référence : Coello M. & Boyle L. 2019, "Simple Model For Predicting Time Series
Soiling of Photovoltaic Panels", IEEE Journal of Photovoltaics, DOI :
10.1109/JPHOTOV.2019.2919628.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date
from typing import Literal, TypedDict

import pandas as pd  # type: ignore[import-untyped]
from pvlib import soiling  # type: ignore[import-untyped]
from pydantic import BaseModel

from kuma_data_core.editorial.niveaux_confiance import NiveauConfiance
from kuma_data_core.services.grandeurs.types import MesureSoilingJour

PLAFOND_CONFIANCE: NiveauConfiance = "B"
"""Plafond de confiance : modèle HSU, proxy de la salissure (pas une mesure)."""

SURFACE_TILT_DEFAUT: float = 10.0
"""Inclinaison fixe par défaut (degrés), proche de la latitude de la Guinée
(9-10° N). Un parc incliné autrement se salit différemment."""

CLEANING_THRESHOLD_DEFAUT_MM: float = 1.0
"""Hauteur de pluie (mm) sur une période d'accumulation qui suffit à nettoyer le
module (valeur par défaut usuelle du modèle HSU)."""

NIVEAU_CONFIANCE: Literal["B"] = "B"
"""Niveau provisoire du calcul pur, remplacé par la route (règle de propagation P)."""

RAIN_ACCUM_PERIOD = pd.Timedelta("1D")
"""Période d'accumulation de la pluie : 1 jour, la pluie étant déjà cumulée à la
journée (pvlib recommande entre 1 h et 24 h)."""

GRAMMES_PAR_MICROGRAMME: float = 1e-6
"""Conversion µg/m³ (donnée stockée) -> g/m³ (entrée attendue par pvlib.soiling.hsu)."""

CAVEAT_SPIN_UP: str = (
    "Le modèle HSU démarre avec des modules propres (salissure nulle) : les premiers "
    "jours de la fenêtre sous-estiment la salissure réelle (amorçage du modèle). "
    "Estimation par modèle, pas une mesure de salissure : elle n'est pas calée sur des "
    "mesures au sol. Les particules (PM) EAC4 sont sur une grille grossière de 0,75° : "
    "des localités proches peuvent partager la même cellule."
)


class MesureEntreeSoiling(TypedDict):
    """Mesure journalière alignée, entrée du proxy de salissure.

    ``pm2_5`` et ``pm10`` en µg/m³ (EAC4), ``rainfall_mm`` en mm.
    """

    instant_mesure: date
    rainfall_mm: float
    pm2_5: float
    pm10: float


class ResultatSoiling(BaseModel):
    """Résultat du proxy de salissure : pertes journalières et mise en garde."""

    mesures: list[MesureSoilingJour]
    limite: str


def calculer_taux_salissure_proxy(
    mesures: Sequence[MesureEntreeSoiling],
    surface_tilt_deg: float = SURFACE_TILT_DEFAUT,
    cleaning_threshold_mm: float = CLEANING_THRESHOLD_DEFAUT_MM,
) -> ResultatSoiling:
    """Perte de salissure journalière (% = (1 - ratio_hsu) x 100, bornée à [0, 100]).

    Applique ``pvlib.soiling.hsu`` sur la fenêtre journalière alignée, PM en µg/m³
    en entrée.
    """
    if not mesures:
        return ResultatSoiling(mesures=[], limite=CAVEAT_SPIN_UP)

    mesures_tri = sorted(mesures, key=lambda m: m["instant_mesure"])
    index = pd.DatetimeIndex([m["instant_mesure"] for m in mesures_tri])
    rainfall = pd.Series([m["rainfall_mm"] for m in mesures_tri], index=index, dtype=float)
    # pvlib attend des g/m³.
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
