"""Grandeur F2 : POA bifacial d'un champ de rangées.

Modèle infinite-sheds (``pvlib.bifacial.infinite_sheds``) [1, 2] : à la
différence du ``poa_parametrable`` mono-plan, il tient compte de la géométrie
des rangées (gcr, hauteur, pitch) et de la face arrière, qui capte le
rayonnement réfléchi par le sol (albedo). La grandeur expose ``poa_global``,
face avant plus gain arrière ; pvlib applique la bifacialité
(``bifaciality=0`` donne ``poa_global == poa_front``).

Diffus du ciel isotrope (défaut d'infinite-sheds), moins anisotrope que le
Perez du POA mono-plan. Niveau de confiance au plus B, par la règle de
propagation que la route applique (ADR-0008).

La méthode journalière applique la géométrie du midi solaire aux totaux du
jour, ce qui biaise le résultat ; la méthode horaire lève ce biais.

Références :

[1] Mikofski M., Darawali R., Hamer M., Neubert A., Newmiller J. 2019.
    "Bifacial Performance Modeling in Large Arrays." 46th IEEE PVSC.
[2] Marion B. et al. 2017. "A Practical Irradiance Model for Bifacial PV
    Modules." 44th IEEE PVSC. DOI : 10.1109/PVSC.2017.8366263.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date, datetime
from typing import Literal, Protocol, TypedDict

import pandas as pd  # type: ignore[import-untyped]
import pvlib  # type: ignore[import-untyped]
from pvlib.bifacial import infinite_sheds  # type: ignore[import-untyped]

from kuma_data_core.editorial.niveaux_confiance import NiveauConfiance

# Même approche journalière que le POA mono-plan : géométrie du midi solaire
# appliquée aux totaux du jour.
from kuma_data_core.services.grandeurs.poa_parametrable import _midi_solaire_utc
from kuma_data_core.services.grandeurs.types import ResultatJournalier

PLAFOND_CONFIANCE: NiveauConfiance = "B"
"""Plafond de confiance : modèle de calcul et paramètres déclarés, invérifiables."""


UNITE_POA_BIFACIAL: str = "kWh/m²/jour"
"""Unité de sortie (POA global bifacial journalier)."""

NIVEAU_CONFIANCE_DERIVE_F2_V1: Literal["B"] = "B"
"""Niveau provisoire du calcul pur, remplacé par la route (règle de propagation P)."""


class ParametresCalculBifacial(Protocol):
    """Grandeurs physiques que lit le calcul bifacial : plan, rangées et bifacialité."""

    @property
    def inclinaison_deg(self) -> float: ...  # 0 = horizontal, 90 = vertical

    @property
    def orientation_deg(self) -> float: ...  # azimut : 0 = nord, 90 = est, 180 = sud

    @property
    def gcr(self) -> float: ...  # largeur du capteur / pas entre rangées

    @property
    def hauteur_m(self) -> float: ...  # centre de la rangée au-dessus du sol

    @property
    def pitch_m(self) -> float: ...  # pas entre rangées, même unité que la hauteur

    @property
    def bifacialite(self) -> float: ...  # rendement face arrière / face avant


class MesureJourBifacial(TypedDict):
    """Mesure journaliere consommee par le POA bifacial (GHI/DNI/DHI + albedo)."""

    instant_mesure: date
    ghi: float
    dni: float
    dhi: float
    albedo: float


class MesureHeureBifacial(TypedDict):
    """Mesure horaire consommée par le POA bifacial en intégration horaire.

    GHI, DNI et DHI horaires en W/m² ; ``albedo`` est celui du jour, répété
    sur chaque heure (l'albedo n'existe qu'en journalier).
    """

    instant_mesure: datetime
    ghi: float
    dni: float
    dhi: float
    albedo: float


def albedo_du_jour(albedo_par_jour: dict[date, float], jour: date, albedo_repli: float) -> float:
    """Albedo du jour dans la série ``albedo_surface``, sinon ``albedo_repli``.

    Quand la série ne couvre pas le jour, le calcul bifacial utilise l'albedo
    fourni par l'utilisateur plutôt que d'échouer.
    """
    return albedo_par_jour.get(jour, albedo_repli)


def _poa_global_infinite_sheds(
    index: pd.DatetimeIndex,
    ghi: pd.Series,
    dni: pd.Series,
    dhi: pd.Series,
    albedo: pd.Series,
    latitude_deg: float,
    longitude_deg: float,
    parametres: ParametresCalculBifacial,
) -> pd.Series:
    """Applique infinite-sheds et renvoie la série ``poa_global``.

    Le modèle étant linéaire en irradiance, la sortie a l'unité des entrées :
    kWh/m²/jour pour des totaux journaliers au midi solaire, W/m² pour des
    entrées horaires.
    """
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


def calculer_poa_bifacial(
    mesures: Sequence[MesureJourBifacial],
    latitude_deg: float,
    longitude_deg: float,
    parametres: ParametresCalculBifacial,
) -> list[ResultatJournalier]:
    """POA bifacial journalier (kWh/m²/jour), infinite-sheds au midi solaire.

    Le niveau de confiance ``'B'`` des résultats est provisoire : la route le
    remplace.
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
    parametres: ParametresCalculBifacial,
) -> list[ResultatJournalier]:
    """POA bifacial journalier (kWh/m²/jour) par intégration horaire.

    Infinite-sheds est appliqué heure par heure, puis sommé par jour (date de
    ``instant_mesure``). Le niveau de confiance ``'B'`` des résultats est
    provisoire : la route le remplace.
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
    # W/m² pendant 1 h = Wh/m² ; nuit et horizon ramenés à 0 ; somme par jour
    # puis /1000 -> kWh/m²/jour.
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
