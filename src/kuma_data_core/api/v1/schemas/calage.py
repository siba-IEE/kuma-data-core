"""Schémas Pydantic de l'endpoint ``/api/v1/calage``.

Le référentiel de calage satellite/sol (ADR-0004) : biais saisonniers
mesurés aux stations de référence, publiés avec provenance et portée.
Le facteur ``k = 1 / (1 + biais)`` est dérivé côté serveur pour
éviter toute divergence d'arrondi chez les consommateurs.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class SaisonCalage(BaseModel):
    """Une saison du référentiel : biais mesuré et facteur dérivé."""

    nom: str
    mois: list[int] = Field(description="Mois couverts (1-12).")
    biais: float = Field(description="Biais relatif moyen satellite moins sol (0.044 pour +4,4 %).")
    k: float = Field(description="Facteur de calage derive : k = 1 / (1 + biais).")


class ReponseCalage(BaseModel):
    """Référentiel de calage d'un couple (station, grandeur)."""

    localite: str
    grandeur: str
    code: str
    version: str
    saisons: list[SaisonCalage]
    provenance: str
    portee: str
