"""Conversion des réponses horaires de NASA POWER vers le format de l'API.

Clés ``YYYYMMDDHH`` en ``datetime`` UTC naïf, sentinelle ``-999.0`` en
``None``, code de grandeur Kuma vers code de paramètre amont et unité cible.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field

from kuma_data_core.editorial.selection import StatutValide
from kuma_data_core.external.nasa_power import SENTINELLE_VALEUR_MANQUANTE


class ResultatHoraire(BaseModel):
    """Un point horaire (24 par jour, fuseau UTC).

    ``statut_editorial`` dit d'où vient la valeur :

    - ``valide_auto``, ``valide_humain`` ou ``publie`` : valeur stockée, avec
      le statut de sa ligne (validée par le contrôle qualité automatique,
      validée par un éditeur, ou publiée) ;
    - ``passe_plat_non_valide`` : valeur relayée à la volée (passe-plat), non
      validée, servie en repli là où aucune série stockée ne couvre la plage
      demandée.
    """

    instant: datetime
    valeur: float | None = Field(
        default=None,
        description=(
            "Valeur numerique ou null si donnee manquante (sentinelle "
            "amont ou indice physique non defini selon la grandeur)."
        ),
    )
    unite: str
    statut_editorial: StatutValide | Literal["passe_plat_non_valide"] = "passe_plat_non_valide"


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
"""Grandeur Kuma -> (code amont, unité cible).

Les codes amont ne sont pas exposés au consommateur. Les irradiances
horaires sont en Wh/m², contre kWh/m²/jour pour le journalier.
"""


def code_parametre_amont(grandeur: str) -> str:
    """Code de paramètre amont d'une grandeur Kuma ; ``KeyError`` si elle est inconnue."""
    return _MAPPING_GRANDEUR[grandeur][0]


def unite_cible(grandeur: str) -> str:
    """Unité cible d'une grandeur horaire."""
    return _MAPPING_GRANDEUR[grandeur][1]


def parser_cle_horaire(cle: str) -> datetime:
    """Convertit une clé ``YYYYMMDDHH`` en ``datetime`` naïf, à lire en UTC.

    ``"2024060112"`` donne 2024-06-01 12:00. Lève ``ValueError`` hors format.
    """
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
    """Convertit ``{YYYYMMDDHH: valeur}`` en résultats triés par instant.

    La sentinelle ``-999.0`` devient ``None``, quelle qu'en soit la cause
    (nuit, donnée pas encore disponible).
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
    """Garde les résultats du jour ``periode_debut`` au jour ``periode_fin``, bornes incluses."""
    return [r for r in resultats if periode_debut <= r.instant.date() <= periode_fin]
