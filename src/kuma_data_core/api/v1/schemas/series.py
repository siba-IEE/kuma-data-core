"""Schémas Pydantic des routes ``/v1/series``.

Une série listée (``SerieListee``), son détail avec mesures (``SerieDetail``)
et trois formes de mesure, une par table d'origine, distinguées par le champ
``type`` : ``MesureJournaliere`` (``mesures_ressource``), ``MesureMensuelle``
(``mesures_ressource_mensuelles``) et ``GrandeurMetierValeur``
(``grandeurs_metier``).
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Annotated, Literal

from pydantic import BaseModel, Field


class MesureJournaliere(BaseModel):
    """Mesure journalière d'une série."""

    type: Literal["journalier"] = "journalier"
    instant_mesure: date
    valeur: float
    niveau_confiance_derive: str = Field(min_length=1, max_length=1)
    niveau_confiance_override: str | None = Field(default=None, min_length=1, max_length=1)
    niveau_effectif: str = Field(min_length=1, max_length=1)
    statut: str


class MesureMensuelle(BaseModel):
    """Mesure mensuelle d'une série."""

    type: Literal["mensuel"] = "mensuel"
    annee: int = Field(ge=1991, le=2099)
    mois: int = Field(ge=1, le=12)
    valeur: float
    niveau_confiance_derive: str = Field(min_length=1, max_length=1)
    niveau_confiance_override: str | None = Field(default=None, min_length=1, max_length=1)
    niveau_effectif: str = Field(min_length=1, max_length=1)
    statut: str


class GrandeurMetierValeur(BaseModel):
    """Valeur d'une grandeur calculée par Kuma."""

    type: Literal["grandeur_metier"] = "grandeur_metier"
    periode_type: Literal["annuel", "mensuel", "statique"]
    annee_debut: int = Field(ge=1991, le=2099)
    annee_fin: int = Field(ge=1991, le=2099)
    mois: int | None = Field(default=None, ge=1, le=12)
    version_formule: int = Field(ge=1)
    valeur: float
    niveau_confiance_derive: str = Field(min_length=1, max_length=1)
    niveau_confiance_override: str | None = Field(default=None, min_length=1, max_length=1)
    niveau_effectif: str = Field(min_length=1, max_length=1)
    statut: str


MesureLue = Annotated[
    MesureJournaliere | MesureMensuelle | GrandeurMetierValeur,
    Field(discriminator="type"),
]
"""Mesure d'une série, sous l'une de ses trois formes, distinguée par le champ ``type``."""


class SerieListee(BaseModel):
    """Série du catalogue, telle que rendue par la liste ``GET /v1/series``.

    Identifiants, localité (code, nom, pays), grandeur (code, libellé, unité),
    source (identifiant, code, libellé, URL), période, méthode de collecte,
    note publique (``notes_fr``) et dates de création et de modification.

    Les identifiants (``id``, ``localite_id``, ``source_id``) sont des
    entiers, pas des UUID.
    """

    # Noms publics et colonnes d'origine (ADR-0001) : source_label <- sources.titre,
    # grandeur_label <- grandeurs_referentiel.libelle, grandeur_unit <- unites.symbole,
    # notes_fr <- series_metadonnees.note_publique, created_at <- cree_le,
    # updated_at <- modifie_le.
    id: int
    code: str = Field(min_length=1, max_length=80)
    libelle: str

    localite_id: int
    localite_code: str
    localite_nom: str
    localite_iso3: str | None = Field(default=None, pattern=r"^[A-Z]{3}$")

    grandeur_code: str
    grandeur_label: str
    grandeur_unit: str

    source_id: int
    source_code: str
    source_label: str
    source_url: str | None

    periode_debut: date
    periode_fin: date | None
    methode_collecte: str | None
    notes_fr: str | None

    created_at: datetime
    updated_at: datetime

    actif: bool


class SerieListeePaginee(BaseModel):
    """Enveloppe paginée de la liste ``GET /v1/series``.

    ``total`` est le nombre de séries correspondant aux filtres, toutes pages
    confondues.
    """

    items: list[SerieListee]
    total: int = Field(ge=0)
    limit: int = Field(ge=1)
    offset: int = Field(ge=0)


class SerieDetail(SerieListee):
    """Détail d'une série, ``GET /v1/series/{code_serie}``, avec ses mesures.

    Aux champs du catalogue s'ajoutent ``unite_code``, code stable de l'unité
    de la grandeur (en plus du symbole ``grandeur_unit``), et ``mesures``,
    dont la forme (journalière, mensuelle ou valeur de grandeur calculée)
    dépend de la série et se lit dans le champ ``type`` de chaque mesure.
    """

    unite_code: str
    mesures: list[MesureLue]
