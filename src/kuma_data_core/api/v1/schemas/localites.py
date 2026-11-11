"""Schémas Pydantic des routes ``/v1/localites``.

Mêmes conventions que les séries (ADR-0001, ADR-0002) : identifiants entiers,
dates ISO 8601 UTC, ``cree_le`` et ``modifie_le`` publiés sous les noms
``created_at`` et ``updated_at``, latitude et longitude en ``float``.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class LocaliteListee(BaseModel):
    """Localité, telle que rendue par la liste ``GET /v1/localites`` et par le détail.

    Identité, hiérarchie, géolocalisation, démographie, fuseau horaire et
    dates de création et de modification. ``parent_code`` est le code de la
    localité parente, fourni pour éviter un second appel.
    """

    id: int
    code: str = Field(min_length=1, max_length=100)
    nom: str

    type_localite: str  # continent, region_supranationale, pays,
    #                     region_administrative, commune, site
    parent_id: int | None
    parent_code: str | None

    pays_iso3: str | None = Field(default=None, pattern=r"^[A-Z]{3}$")
    latitude: float | None  # Numeric(11,8) en base
    longitude: float | None  # Numeric(12,8) en base
    altitude_metres: int | None

    population_estimee: int | None
    annee_population: int | None

    fuseau_horaire: str | None  # nom IANA (ex. "Africa/Conakry")

    created_at: datetime  # <- cree_le
    updated_at: datetime  # <- modifie_le

    actif: bool


class LocaliteListeePaginee(BaseModel):
    """Enveloppe paginée de la liste ``GET /v1/localites``.

    ``total`` est le nombre de localités correspondant aux filtres, toutes
    pages confondues.
    """

    items: list[LocaliteListee]
    total: int = Field(ge=0)
    limit: int = Field(ge=1)
    offset: int = Field(ge=0)


# Le détail a les mêmes champs que la liste.
LocaliteDetail = LocaliteListee


class PointGeographique(BaseModel):
    """Point WGS84 en degres decimaux."""

    latitude_deg: float
    longitude_deg: float


class CelluleResolution(BaseModel):
    """Cellule de la grille de climatologie qui contient le point.

    Grille de la source de climatologie mensuelle : 1° x 1°, frontières aux
    degrés entiers.
    """

    lat_min: float
    lat_max: float
    lon_min: float
    lon_max: float


class LocaliteResolue(BaseModel):
    """Localite du referentiel retenue par la resolution."""

    code: str
    nom: str
    latitude_deg: float
    longitude_deg: float


class ReponseResolution(BaseModel):
    """Réponse de ``GET /v1/localites/resolution``.

    ``meme_cellule`` est vrai si la localité retenue est dans la cellule du
    point : sa climatologie est alors celle du point. Il est faux si aucune
    localité ne partage la cellule ; la plus proche est alors renvoyée avec
    sa distance, et l'appelant doit signaler que la climatologie est
    transportée depuis une autre cellule.
    """

    point: PointGeographique
    grandeur: str
    cellule: CelluleResolution
    localite: LocaliteResolue
    distance_km: float
    meme_cellule: bool
    serie_climatologie: str = Field(
        description=(
            "Code de la série de climatologie mensuelle de la localité "
            "retenue : la série qui représente la cellule du point. À lire "
            "dans cette réponse plutôt qu'à reconstruire par convention de "
            "nommage."
        )
    )
