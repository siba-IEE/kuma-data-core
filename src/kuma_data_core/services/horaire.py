"""Conversion des réponses horaires amont en ``ResultatHoraire`` (passe-plat).

Le code du paramètre amont n'est pas exposé au consommateur.
"""

from __future__ import annotations

from datetime import date, datetime

from kuma_data_core.api.v1.schemas.horaire import ResultatHoraire
from kuma_data_core.external.nasa_power import SENTINELLE_VALEUR_MANQUANTE

# === Mapping grandeur Kuma -> (code amont, unité cible) ===================

_MAPPING_GRANDEUR: dict[str, tuple[str, str]] = {
    "ghi": ("ALLSKY_SFC_SW_DWN", "Wh/m²"),
    "dni": ("ALLSKY_SFC_SW_DNI", "Wh/m²"),
    "dhi": ("ALLSKY_SFC_SW_DIFF", "Wh/m²"),
    "t2m": ("T2M", "°C"),
    "rh2m": ("RH2M", "%"),
    "kt": ("ALLSKY_KT", "sans dimension"),
    "vent_2m": ("WS2M", "m/s"),
    "vent_10m": ("WS10M", "m/s"),
    "precipitation": ("PRECTOTCORR", "mm/h"),
}
"""Grandeur -> (code amont, unité cible) ; irradiances horaires en Wh/m²."""


# === Helpers publics ======================================================


def code_parametre_amont(grandeur: str) -> str:
    """Code du paramètre amont ; ``KeyError`` hors mapping (filtré en amont par Pydantic)."""
    return _MAPPING_GRANDEUR[grandeur][0]


def unite_cible(grandeur: str) -> str:
    """Renvoie l'unité cible Kuma pour une grandeur horaire."""
    return _MAPPING_GRANDEUR[grandeur][1]


def parser_cle_horaire(cle: str) -> datetime:
    """``YYYYMMDDHH`` -> ``datetime`` naïf en UTC ; ``ValueError`` si mal formée."""
    if len(cle) != 10 or not cle.isdigit():
        raise ValueError(f"cle horaire invalide : {cle!r} (attendu YYYYMMDDHH 10 chiffres)")
    return datetime(
        year=int(cle[0:4]),
        month=int(cle[4:6]),
        day=int(cle[6:8]),
        hour=int(cle[8:10]),
    )


def convertir_valeurs_amont_en_resultats(
    valeurs_par_cle: dict[str, float],
    grandeur: str,
) -> list[ResultatHoraire]:
    """``{YYYYMMDDHH: valeur}`` -> ``ResultatHoraire`` triés, statut ``passe_plat_non_valide``.

    La sentinelle ``-999.0`` devient ``None``, sans distinguer nuit, NRT
    indisponible ou autre cause.
    """
    unite = unite_cible(grandeur)
    resultats: list[ResultatHoraire] = []
    for cle in sorted(valeurs_par_cle):
        instant = parser_cle_horaire(cle)
        valeur_amont = valeurs_par_cle[cle]
        valeur: float | None = None if valeur_amont == SENTINELLE_VALEUR_MANQUANTE else valeur_amont
        resultats.append(
            ResultatHoraire(
                instant=instant,
                valeur=valeur,
                unite=unite,
            )
        )
    return resultats


def filtrer_resultats_par_plage(
    resultats: list[ResultatHoraire],
    periode_debut: date,
    periode_fin: date,
) -> list[ResultatHoraire]:
    """Garde ``[periode_debut, periode_fin]``, jour de fin inclus jusqu'à 23:59."""
    return [r for r in resultats if periode_debut <= r.instant.date() <= periode_fin]
