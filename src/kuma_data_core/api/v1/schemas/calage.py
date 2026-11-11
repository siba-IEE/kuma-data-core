"""Schémas Pydantic des routes ``/v1/calage``.

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
    """Référentiel de calage d'un couple (station, grandeur).

    ``localites_couvertes`` liste, triés, les codes des localités où ce
    calage peut être transporté : une étude calée n'est possible que si la
    localité du site en fait partie. ``justification_couverture`` en donne
    la provenance.
    """

    localite: str
    grandeur: str
    code: str
    version: str
    saisons: list[SaisonCalage]
    provenance: str
    portee: str
    localites_couvertes: list[str] = Field(default_factory=list)
    justification_couverture: str | None = None
    serie_sol: str = Field(
        description=(
            "Code de la série sol sur laquelle le référentiel est fondé : la "
            "séquence horaire de référence à utiliser avec ce calage. À lire "
            "dans cette réponse plutôt qu'à coder en dur."
        )
    )


class ReferentielListe(BaseModel):
    """Un référentiel de calage dans la liste (une entrée par code)."""

    code: str
    localite: str
    grandeur: str
    version: str
    serie_sol: str
    localites_couvertes: list[str] = Field(default_factory=list)


class ReponseCalageListe(BaseModel):
    """Réponse de ``GET /v1/calage`` : les référentiels publiés."""

    items: list[ReferentielListe]
    total: int
