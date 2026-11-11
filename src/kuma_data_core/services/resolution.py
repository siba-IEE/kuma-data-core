"""Résolution d'un point : quelle candidate porte la climatologie qui le représente.

La climatologie est donnée sur une grille de 1° x 1°, frontières aux degrés
entiers : tous les points d'une cellule ont la même valeur. Un point est donc
représenté par une candidate de sa cellule ; à défaut, par une candidate de
l'une des huit cellules voisines (par un côté ou par un coin), dont la
climatologie est alors transportée d'une cellule ; au-delà, il n'est pas résolu.

La limite se compte en cellules, pas en kilomètres : l'erreur vient du nombre
de cellules franchies, pas de la position de la candidate dans la sienne. La
mesure qui fonde cette limite est dans l'ADR-0010.
"""

from __future__ import annotations

import math
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from typing import Protocol

RAYON_TERRE_KM = 6371.0

MESSAGE_POINT_HORS_ZONE = (
    "Point hors de la zone couverte : aucun point d'ingestion de climatologie "
    "dans sa cellule de grille ni dans une cellule voisine."
)


class Geolocalisee(Protocol):
    """Position WGS84 d'une candidate, en degrés décimaux."""

    @property
    def latitude(self) -> float: ...

    @property
    def longitude(self) -> float: ...


@dataclass(frozen=True)
class Resolution[C: Geolocalisee]:
    """Candidate retenue pour un point.

    ``meme_cellule`` est faux quand la candidate vient d'une cellule voisine.
    """

    candidate: C
    distance_km: float
    meme_cellule: bool


def distance_grand_cercle_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Distance du grand cercle entre deux points WGS84, en km (formule de haversine)."""
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return 2 * RAYON_TERRE_KM * math.asin(math.sqrt(a))


def cellule(latitude: float, longitude: float) -> tuple[int, int]:
    """Coin sud-ouest, en degrés entiers, de la cellule de grille qui contient le point."""
    return math.floor(latitude), math.floor(longitude)


def _ecart_de_cellules(a: tuple[int, int], b: tuple[int, int]) -> int:
    """Nombre de cellules franchies de l'une à l'autre, un pas en diagonale comptant pour un.

    La longitude est circulaire (180 et -180 sont la même) ; la latitude ne boucle pas.
    """
    ecart_longitude = abs(a[1] - b[1]) % 360
    return max(abs(a[0] - b[0]), min(ecart_longitude, 360 - ecart_longitude))


def plus_proche[C: Geolocalisee](
    latitude: float, longitude: float, candidates: Iterable[C]
) -> tuple[C, float]:
    """``(candidate, distance en km)`` la plus proche du point, toutes cellules confondues.

    À distance égale, la première rencontrée. Lève ``ValueError`` s'il n'y a aucune candidate.
    """
    return min(
        (
            (c, distance_grand_cercle_km(latitude, longitude, c.latitude, c.longitude))
            for c in candidates
        ),
        key=lambda paire: paire[1],
    )


def resoudre[C: Geolocalisee](
    latitude: float, longitude: float, candidates: Sequence[C]
) -> Resolution[C] | None:
    """Candidate qui représente le point, ou ``None`` s'il est hors de la zone couverte.

    La plus proche de celles de sa cellule ; à défaut, la plus proche de celles des
    huit cellules voisines. À distance égale, la première de la liste.
    """
    ici = cellule(latitude, longitude)
    ecarts = [_ecart_de_cellules(ici, cellule(c.latitude, c.longitude)) for c in candidates]
    for ecart_admis in (0, 1):
        retenues = [c for c, ecart in zip(candidates, ecarts, strict=True) if ecart == ecart_admis]
        if retenues:
            candidate, distance_km = plus_proche(latitude, longitude, retenues)
            return Resolution(candidate, distance_km, meme_cellule=ecart_admis == 0)
    return None
