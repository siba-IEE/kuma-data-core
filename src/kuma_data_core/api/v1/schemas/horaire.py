"""Schémas Pydantic des routes ``/v1/horaire/{localite}/{grandeur}``.

Aucun champ ne nomme la source amont. ``statut_editorial`` distingue les
valeurs stockées et validées (``valide_auto``) des valeurs relayées sans
validation (``passe_plat_non_valide``).
"""

from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import BaseModel, Field, model_validator

from kuma_data_core.services.horaire import ResultatHoraire

GRANDEURS_AUTORISEES: tuple[str, ...] = (
    "ghi",
    "dni",
    "dhi",
    "t2m",
    "rh2m",
    "kt",
    "vent_2m",
    "vent_10m",
    "precipitation",
)
"""Grandeurs servies en horaire."""

PLAGE_MAX_JOURS: int = 366
"""Plage temporelle maximale par requête (année bissextile incluse)."""

DATE_DEBUT_DISPONIBILITE: date = date(2001, 1, 1)
"""Début de la disponibilité des données horaires."""


class ParametresHoraire(BaseModel):
    """Paramètres de la route de données horaires.

    ``format_sortie`` se passe dans l'URL sous le nom ``format``.
    """

    # Code complet d'une localité du référentiel (ex. gin_kankan) ; un code
    # court (kankan) reste accepté, la route le complète.
    localite: str = Field(..., min_length=1, max_length=100, pattern=r"^[a-z0-9_]+$")
    grandeur: Literal[
        "ghi", "dni", "dhi", "t2m", "rh2m", "kt", "vent_2m", "vent_10m", "precipitation"
    ]
    periode_debut: date = Field(..., ge=DATE_DEBUT_DISPONIBILITE)
    periode_fin: date
    format_sortie: Literal["json", "csv"] = Field(
        default="json",
        alias="format",
        description="Format de reponse : 'json' (defaut) ou 'csv'.",
    )

    @model_validator(mode="after")
    def _valider_plage_temporelle(self) -> ParametresHoraire:
        if self.periode_fin < self.periode_debut:
            raise ValueError("periode_fin doit etre superieure ou egale a periode_debut")
        if (self.periode_fin - self.periode_debut).days > PLAGE_MAX_JOURS:
            raise ValueError(f"plage maximale {PLAGE_MAX_JOURS} jours par requete")
        return self


class PlageTemporelle(BaseModel):
    """Plage temporelle inclusive [début, fin]."""

    debut: date
    fin: date


class ReponseHoraire(BaseModel):
    """Réponse de la route de données horaires."""

    localite: str
    grandeur: str
    periode_demandee: PlageTemporelle
    resultats: list[ResultatHoraire]


class ReponseDisponibilite(BaseModel):
    """Réponse de la route ``/disponibilite``."""

    localite: str
    grandeur: str
    plage_disponible: PlageTemporelle
    statut_editorial: Literal["passe_plat_non_valide"] = "passe_plat_non_valide"
