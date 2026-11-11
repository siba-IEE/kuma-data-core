"""Types de résultat et de mesure que construisent les calculs de grandeurs.

L'API les reprend tels quels comme éléments de ses réponses : noms de classe,
champs et docstrings sont des textes servis. Le module ne dépend d'aucun module
de calcul, pour rester importable sans cycle.
"""

from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import BaseModel, Field


class ResultatJournalier(BaseModel):
    """Élément de réponse F2 à granularité journalière."""

    granularite: Literal["journalier"] = "journalier"
    instant: date
    valeur: float
    unite: str
    niveau_confiance: Literal["A", "B", "C"]


class ResultatMensuel(BaseModel):
    """Élément de réponse F2 à granularité mensuelle (instant format YYYY-MM)."""

    granularite: Literal["mensuel"] = "mensuel"
    instant: str = Field(
        pattern=r"^\d{4}-(0[1-9]|1[0-2])$",
        description="Mois calendaire au format YYYY-MM.",
    )
    valeur: float
    unite: str
    niveau_confiance: Literal["A", "B", "C"]


class MesureSoilingJour(BaseModel):
    """Perte de salissure d'un jour (proxy HSU, % de transmission perdue)."""

    instant: date
    perte_pct: float = Field(
        ...,
        ge=0.0,
        le=100.0,
        description="Perte de transmission = (1 - ratio HSU) x 100, bornee [0, 100].",
    )
    niveau_confiance: Literal["A", "B", "C"] = "B"


ModeCorrectionPR = Literal["aucune", "temperature", "salissure", "temperature_salissure"]
"""Modes de correction du PR réaliste (superposition thermique et/ou salissure)."""


class MesureJourPR(BaseModel):
    """PR réaliste d'un jour (ratio sans dimension)."""

    instant: date
    pr_realiste: float
    niveau_confiance: Literal["A", "B", "C"] = "B"


class MesureMoisPR(BaseModel):
    """PR réaliste moyen d'un mois (la courbe mensuelle = la 'PR saisonnière')."""

    instant: str = Field(pattern=r"^\d{4}-(0[1-9]|1[0-2])$", description="Mois (YYYY-MM).")
    pr_realiste: float
    niveau_confiance: Literal["A", "B", "C"] = "B"
