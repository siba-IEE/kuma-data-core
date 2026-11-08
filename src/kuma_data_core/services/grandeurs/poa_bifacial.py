"""POA bifacial à la volée d'un champ de rangées, modèle infinite-sheds [1] (pvlib).

Contrairement au POA mono-plan, modélise la géométrie des rangées (gcr,
hauteur, pas) et la face arrière éclairée par l'albédo du sol.
``poa_global`` inclut le gain arrière, bifacialité appliquée par pvlib
(``bifaciality=0`` donne ``poa_front``). Diffus du ciel isotrope. En
journalier, géométrie du midi solaire sur les totaux du jour (biais de
moyennage), levé par la méthode horaire.

[1] Mikofski M. et al. 2019. "Bifacial Performance Modeling in Large
    Arrays." 46th IEEE PVSC.
[2] Marion B. et al. 2017. "A Practical Irradiance Model for Bifacial PV
    Modules." 44th IEEE PVSC. DOI : 10.1109/PVSC.2017.8366263.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date, datetime
from typing import Literal, TypedDict

import pandas as pd  # type: ignore[import-untyped]
import pvlib  # type: ignore[import-untyped]
from pvlib.bifacial import infinite_sheds  # type: ignore[import-untyped]

from kuma_data_core.api.v1.schemas.grandeurs import (
    ParametresBifacial,
    ResultatJournalier,
)
from kuma_data_core.editorial.niveaux_confiance import NiveauConfiance

# Import privé : même approche du midi solaire que le POA mono-plan.
from kuma_data_core.services.grandeurs.poa_parametrable import _midi_solaire_utc

PLAFOND_CONFIANCE: NiveauConfiance = "B"
"""Plafond ``B`` : modèle et paramètres déclarés par l'appelant, invérifiables."""

# === Constantes module ====================================================

UNITE_POA_BIFACIAL: str = "kWh/m²/jour"
"""Unité de sortie (POA global bifacial journalier)."""

NIVEAU_CONFIANCE_DERIVE_F2_V1: Literal["B"] = "B"
"""Niveau provisoire du calcul pur, remplacé par la route (règle de propagation P)."""


# === TypedDict d'entree ===================================================


class MesureJourBifacial(TypedDict):
    """Mesure journaliere consommee par le POA bifacial (GHI/DNI/DHI + albedo)."""

    instant_mesure: date
    ghi: float
    dni: float
    dhi: float
    albedo: float


class MesureHeureBifacial(TypedDict):
    """Irradiances horaires (W/m²) ; l'albédo, seulement journalier, est celui du jour."""

    instant_mesure: datetime
    ghi: float
    dni: float
    dhi: float
    albedo: float


# === Repli albedo (pur, testable) =========================================


def albedo_du_jour(albedo_par_jour: dict[date, float], jour: date, albedo_repli: float) -> float:
    """Albédo du jour de la série ``albedo_surface``, sinon ``albedo_repli``."""
    return albedo_par_jour.get(jour, albedo_repli)


# === Fonction privee pure (cœur infinite-sheds) ===========================


def _poa_global_infinite_sheds(
    index: pd.DatetimeIndex,
    ghi: pd.Series,
    dni: pd.Series,
    dhi: pd.Series,
    albedo: pd.Series,
    latitude_deg: float,
    longitude_deg: float,
    parametres: ParametresBifacial,
) -> pd.Series:
    """``poa_global`` dans l'unité des irradiances d'entrée (modèle linéaire)."""
    solpos = pvlib.solarposition.get_solarposition(index, latitude_deg, longitude_deg)
    resultat = infinite_sheds.get_irradiance(
        surface_tilt=parametres.inclinaison_deg,
        surface_azimuth=parametres.orientation_deg,
        solar_zenith=solpos["apparent_zenith"],
        solar_azimuth=solpos["azimuth"],
        gcr=parametres.gcr,
        height=parametres.hauteur_m,
        pitch=parametres.pitch_m,
        ghi=ghi,
        dhi=dhi,
        dni=dni,
        albedo=albedo,
        bifaciality=parametres.bifacialite,
    )
    return resultat["poa_global"]


# === Fonctions publiques ==================================================


def calculer_poa_bifacial(
    mesures: Sequence[MesureJourBifacial],
    latitude_deg: float,
    longitude_deg: float,
    parametres: ParametresBifacial,
) -> list[ResultatJournalier]:
    """POA bifacial journalier (kWh/m²/jour), géométrie du midi solaire.

    Confiance provisoire ``'B'``, remplacée par la route (règle P).
    """
    if not mesures:
        return []
    jours = [m["instant_mesure"] for m in mesures]
    index = pd.DatetimeIndex([_midi_solaire_utc(j, longitude_deg) for j in jours])
    ghi = pd.Series([m["ghi"] for m in mesures], index=index, dtype=float)
    dni = pd.Series([m["dni"] for m in mesures], index=index, dtype=float)
    dhi = pd.Series([m["dhi"] for m in mesures], index=index, dtype=float)
    albedo = pd.Series([m["albedo"] for m in mesures], index=index, dtype=float)

    poa = _poa_global_infinite_sheds(
        index, ghi, dni, dhi, albedo, latitude_deg, longitude_deg, parametres
    )
    valeurs = poa.clip(lower=0).fillna(0.0).to_numpy()
    return [
        ResultatJournalier(
            instant=jours[i],
            valeur=float(valeurs[i]),
            unite=UNITE_POA_BIFACIAL,
            niveau_confiance=NIVEAU_CONFIANCE_DERIVE_F2_V1,
        )
        for i in range(len(jours))
    ]


def calculer_poa_bifacial_horaire(
    mesures: Sequence[MesureHeureBifacial],
    latitude_deg: float,
    longitude_deg: float,
    parametres: ParametresBifacial,
) -> list[ResultatJournalier]:
    """POA bifacial heure par heure, sommé par jour UTC (kWh/m²/jour).

    Confiance provisoire ``'B'``, remplacée par la route (règle P).
    """
    if not mesures:
        return []
    index = pd.DatetimeIndex([m["instant_mesure"] for m in mesures])
    ghi = pd.Series([m["ghi"] for m in mesures], index=index, dtype=float)
    dni = pd.Series([m["dni"] for m in mesures], index=index, dtype=float)
    dhi = pd.Series([m["dhi"] for m in mesures], index=index, dtype=float)
    albedo = pd.Series([m["albedo"] for m in mesures], index=index, dtype=float)

    poa = _poa_global_infinite_sheds(
        index, ghi, dni, dhi, albedo, latitude_deg, longitude_deg, parametres
    )
    # W/m² horaire ≈ Wh/m² ; nuit -> 0 ; somme par jour /1000 -> kWh/m²/jour.
    poa_horaire = poa.clip(lower=0).fillna(0.0)
    poa_par_jour = poa_horaire.groupby(poa_horaire.index.date).sum() / 1000.0

    return [
        ResultatJournalier(
            instant=jour,
            valeur=float(valeur),
            unite=UNITE_POA_BIFACIAL,
            niveau_confiance=NIVEAU_CONFIANCE_DERIVE_F2_V1,
        )
        for jour, valeur in poa_par_jour.items()
    ]
