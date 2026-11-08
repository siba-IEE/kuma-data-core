"""POA à la volée pour un plan d'inclinaison ``beta`` et d'azimut ``gamma`` (pvlib).

- Perez 1990 [1] quand DNI et DHI sont disponibles.
- Sinon Liu-Jordan isotrope [2], DNI et DHI estimés du GHI par Erbs 1982 [3].

En journalier, le modèle est appliqué au midi solaire (biais de moyennage
assumé). Limites : coefficients Perez non recalibrés pour l'Afrique de
l'Ouest, Liu-Jordan perd 10-15 % sous ciel partiellement couvert, pas
d'ombrage local.

[1] Perez R. et al. 1990. "Modeling daylight availability and irradiance
    components from direct and global irradiance." Solar Energy 44(5),
    271-289. DOI : 10.1016/0038-092X(90)90055-H.
[2] Liu B.Y.H., Jordan R.C. 1963. "The long-term average performance of
    flat-plate solar-energy collectors." Solar Energy 7, 53-74.
    DOI : 10.1016/0038-092X(63)90006-9.
[3] Erbs D.G., Klein S.A., Duffie J.A. 1982. "Estimation of the diffuse
    radiation fraction for hourly, daily and monthly-average global
    radiation." Solar Energy 28(4), 293-302. DOI : 10.1016/0038-092X(82)90302-4.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, date, datetime, timedelta
from typing import Literal, TypedDict

import pandas as pd  # type: ignore[import-untyped]
import pvlib  # type: ignore[import-untyped]

from kuma_data_core.api.v1.schemas.grandeurs import (
    ParametresPOA,
    ResultatJournalier,
)
from kuma_data_core.editorial.niveaux_confiance import NiveauConfiance

PLAFOND_CONFIANCE: NiveauConfiance = "B"
"""Plafond ``B`` : modèle et paramètres déclarés par l'appelant, invérifiables."""

# === Constantes module ====================================================

UNITE_POA: str = "kWh/m²/jour"
"""Unité de sortie POA en granularité journalière."""

NIVEAU_CONFIANCE_DERIVE_F2_V1: Literal["B"] = "B"
"""Niveau provisoire du calcul pur, remplacé par la route (règle de propagation P)."""

MODELE_PEREZ: Literal["perez"] = "perez"
"""Identifiant pvlib du modèle Perez 1990."""

MODELE_ISOTROPE: Literal["isotropic"] = "isotropic"
"""Identifiant pvlib du modèle isotrope Liu-Jordan 1963."""


# === TypedDict d'entree ===================================================


class MesureJourPOA(TypedDict):
    """Irradiance journalière ; sans DNI ou DHI, le jour passe en Liu-Jordan."""

    instant_mesure: date
    ghi: float
    dni: float | None
    dhi: float | None


class MesureHeurePOA(TypedDict):
    """Irradiance horaire complète (l'appelant n'aligne que les instants complets)."""

    instant_mesure: datetime
    ghi: float
    dni: float
    dhi: float


# === Fonctions privees pures ==============================================


def _midi_solaire_utc(jour: date, longitude_deg: float) -> datetime:
    """Midi solaire approché : 12:00 UTC - longitude/15, suffisant en journalier."""
    decalage_heures = -longitude_deg / 15.0
    return datetime(jour.year, jour.month, jour.day, 12, 0, 0, tzinfo=UTC) + timedelta(
        hours=decalage_heures
    )


def _calculer_poa_jour(
    mesure: MesureJourPOA,
    latitude_deg: float,
    longitude_deg: float,
    parametres: ParametresPOA,
) -> float:
    """POA d'un jour (unité du GHI) : Perez si DNI et DHI, sinon Liu-Jordan + Erbs."""
    instant_utc = _midi_solaire_utc(mesure["instant_mesure"], longitude_deg)
    times = pd.DatetimeIndex([instant_utc])
    solpos = pvlib.solarposition.get_solarposition(times, latitude_deg, longitude_deg)

    dni_a_utiliser: float
    dhi_a_utiliser: float
    modele: str
    if mesure["dni"] is not None and mesure["dhi"] is not None:
        dni_a_utiliser = mesure["dni"]
        dhi_a_utiliser = mesure["dhi"]
        modele = MODELE_PEREZ
    else:
        # Liu-Jordan : DNI et DHI estimés du GHI par Erbs 1982.
        decomposition = pvlib.irradiance.erbs(
            ghi=mesure["ghi"],
            zenith=solpos["zenith"].iloc[0],
            datetime_or_doy=instant_utc,
        )
        dni_a_utiliser = float(decomposition["dni"])
        dhi_a_utiliser = float(decomposition["dhi"])
        modele = MODELE_ISOTROPE

    # Perez exige l'irradiance extra-atmosphérique (ValueError pvlib sinon).
    dni_extra = float(pvlib.irradiance.get_extra_radiation(instant_utc))

    resultat_poa = pvlib.irradiance.get_total_irradiance(
        surface_tilt=parametres.inclinaison_deg,
        surface_azimuth=parametres.orientation_deg,
        solar_zenith=solpos["zenith"].iloc[0],
        solar_azimuth=solpos["azimuth"].iloc[0],
        dni=dni_a_utiliser,
        ghi=mesure["ghi"],
        dhi=dhi_a_utiliser,
        dni_extra=dni_extra,
        albedo=parametres.albedo_sol,
        model=modele,
    )

    poa_global = float(resultat_poa["poa_global"])
    # pvlib renvoie NaN si la position solaire est dégénérée (nuit, polaire).
    if pd.isna(poa_global) or poa_global < 0:
        return 0.0
    return poa_global


# === Fonction publique ====================================================


def calculer_poa_parametrable(
    mesures: Sequence[MesureJourPOA],
    latitude_deg: float,
    longitude_deg: float,
    parametres: ParametresPOA,
) -> list[ResultatJournalier]:
    """POA journalier par jour mesuré, ordonné par date.

    Confiance provisoire ``'B'``, remplacée par la route (règle P).
    """
    resultats: list[ResultatJournalier] = []
    for mesure in mesures:
        poa_valeur = _calculer_poa_jour(
            mesure=mesure,
            latitude_deg=latitude_deg,
            longitude_deg=longitude_deg,
            parametres=parametres,
        )
        resultats.append(
            ResultatJournalier(
                instant=mesure["instant_mesure"],
                valeur=poa_valeur,
                unite=UNITE_POA,
                niveau_confiance=NIVEAU_CONFIANCE_DERIVE_F2_V1,
            )
        )
    return resultats


def calculer_poa_parametrable_horaire(
    mesures: Sequence[MesureHeurePOA],
    latitude_deg: float,
    longitude_deg: float,
    parametres: ParametresPOA,
) -> list[ResultatJournalier]:
    """POA journalier par Perez heure par heure, sommé par jour UTC (kWh/m²/jour).

    Contrairement au calcul au midi solaire, ne surestime pas le gain d'un plan
    incliné (biais de moyennage mesuré à +16 %).
    """
    if not mesures:
        return []

    index = pd.DatetimeIndex([m["instant_mesure"] for m in mesures])
    ghi = pd.Series([m["ghi"] for m in mesures], index=index, dtype=float)
    dni = pd.Series([m["dni"] for m in mesures], index=index, dtype=float)
    dhi = pd.Series([m["dhi"] for m in mesures], index=index, dtype=float)

    solpos = pvlib.solarposition.get_solarposition(index, latitude_deg, longitude_deg)
    dni_extra = pvlib.irradiance.get_extra_radiation(index)
    poa_global = pvlib.irradiance.get_total_irradiance(
        surface_tilt=parametres.inclinaison_deg,
        surface_azimuth=parametres.orientation_deg,
        solar_zenith=solpos["zenith"],
        solar_azimuth=solpos["azimuth"],
        dni=dni,
        ghi=ghi,
        dhi=dhi,
        dni_extra=dni_extra,
        albedo=parametres.albedo_sol,
        model=MODELE_PEREZ,
    )["poa_global"]

    # W/m² horaire ≈ Wh/m² ; nuit (NaN, négatif) -> 0 ; somme par jour /1000 -> kWh/m²/jour.
    poa_horaire = poa_global.clip(lower=0).fillna(0.0)
    poa_par_jour = poa_horaire.groupby(poa_horaire.index.date).sum() / 1000.0

    return [
        ResultatJournalier(
            instant=jour,
            valeur=float(valeur),
            unite=UNITE_POA,
            niveau_confiance=NIVEAU_CONFIANCE_DERIVE_F2_V1,
        )
        for jour, valeur in poa_par_jour.items()
    ]
