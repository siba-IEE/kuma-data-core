"""Modèle SQLAlchemy de la table ``localites`` : référentiel géographique hiérarchique.

Sept niveaux : ``continent``, ``region_supranationale``, ``pays``,
``region_administrative``, ``prefecture``, ``commune``, ``site``. La matrice
parent-enfant est validée par le trigger PL/pgSQL
``valider_hierarchie_localites()``, défini en migration et absent de ce modèle ;
il ne détecte pas les cycles. Une commune peut avoir pour parent une
``region_administrative`` : c'est le cas à Conakry, qui n'a pas de préfecture.

Convention de ``code`` : slug ASCII pour un continent ou une région
supranationale (``afrique``, ``uemoa``), code ISO 3166-1 alpha-3 en minuscules
pour un pays (``gin``), ``<code_pays>_<slug>`` en dessous (``gin_conakry``). La
cohérence entre ``code`` et ``pays_iso3`` n'est pas contrainte en base.

Les coordonnées ont 8 décimales (environ 1 mm à l'équateur). ``fuseau_horaire``
suit la base IANA (``Africa/Conakry``), sans CHECK car la liste évolue.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Identity,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from kuma_data_core.db.base import Base


class Localite(Base):
    """Référentiel des localités géographiques de Kuma Data Core."""

    __tablename__ = "localites"

    id: Mapped[int] = mapped_column(BigInteger, Identity(start=1, increment=1), primary_key=True)
    code: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)

    nom: Mapped[str] = mapped_column(Text, nullable=False)
    type_localite: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        comment=(
            "7 valeurs : continent, region_supranationale, pays, region_administrative, "
            "prefecture, commune, site. En Guinée : pays, région administrative, préfecture, "
            "commune ; les communes de Conakry sont rattachées directement à leur région "
            "administrative."
        ),
    )
    parent_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("localites.id", name="fk_localites_parent_id__localites"),
        nullable=True,
    )
    # Code administratif national officiel (décret guinéen de 2025, 3 lettres, ex. CKY).
    code_administratif_national: Mapped[str | None] = mapped_column(
        String(8),
        nullable=True,
        comment=(
            "Code administratif officiel externe (decret guineen de codification 2025, "
            "3 lettres majuscules, ex. CKY). Nullable. Convention identifiant externe "
            "comme sources.doi / sources.isbn. Candidat cle de jointure INS / gouvernemental."
        ),
    )

    pays_iso3: Mapped[str | None] = mapped_column(String(3), nullable=True)
    latitude: Mapped[Decimal | None] = mapped_column(Numeric(11, 8), nullable=True)
    longitude: Mapped[Decimal | None] = mapped_column(Numeric(12, 8), nullable=True)
    altitude_metres: Mapped[int | None] = mapped_column(Integer, nullable=True)

    population_estimee: Mapped[int | None] = mapped_column(Integer, nullable=True)
    annee_population: Mapped[int | None] = mapped_column(Integer, nullable=True)

    fuseau_horaire: Mapped[str | None] = mapped_column(String(50), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    actif: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("TRUE"))
    desactive_le: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    cree_le: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    cree_par: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("contributeurs.id", name="fk_localites_cree_par__contributeurs"),
        nullable=True,
    )
    modifie_le: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    modifie_par: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("contributeurs.id", name="fk_localites_modifie_par__contributeurs"),
        nullable=True,
    )

    __table_args__ = (
        CheckConstraint(
            "type_localite IN ("
            "'continent', 'region_supranationale', 'pays', "
            "'region_administrative', 'prefecture', 'commune', 'site')",
            name="ck_localites_type_valide",
        ),
        CheckConstraint(
            "(type_localite = 'continent' AND parent_id IS NULL) OR (type_localite != 'continent')",
            name="ck_localites_continent_racine",
        ),
        CheckConstraint(
            "latitude IS NULL OR (latitude BETWEEN -90 AND 90)",
            name="ck_localites_latitude_bornes",
        ),
        CheckConstraint(
            "longitude IS NULL OR (longitude BETWEEN -180 AND 180)",
            name="ck_localites_longitude_bornes",
        ),
        CheckConstraint(
            "pays_iso3 IS NULL OR pays_iso3 ~ '^[A-Z]{3}$'",
            name="ck_localites_pays_iso3_format",
        ),
        CheckConstraint(
            "population_estimee IS NULL OR population_estimee >= 0",
            name="ck_localites_population_positive",
        ),
        CheckConstraint(
            "annee_population IS NULL OR (annee_population BETWEEN 1900 AND 2100)",
            name="ck_localites_annee_population_bornes",
        ),
        CheckConstraint(
            "(population_estimee IS NULL AND annee_population IS NULL) "
            "OR (population_estimee IS NOT NULL "
            "AND annee_population IS NOT NULL)",
            name="ck_localites_demographie_coherente",
        ),
        CheckConstraint(
            "code ~ '^[a-z][a-z0-9_]*$'",
            name="ck_localites_code_format",
        ),
        CheckConstraint(
            "code_administratif_national IS NULL OR code_administratif_national ~ '^[A-Z]{3}$'",
            name="ck_localites_code_administratif_format",
        ),
        CheckConstraint(
            "(actif = TRUE AND desactive_le IS NULL) "
            "OR (actif = FALSE AND desactive_le IS NOT NULL)",
            name="ck_localites_actif_desactive_le",
        ),
        Index("idx_localites_actif", "actif"),
        Index("idx_localites_type_localite", "type_localite"),
        Index("idx_localites_pays_iso3", "pays_iso3"),
        Index("idx_localites_parent_id", "parent_id"),
    )

    def __repr__(self) -> str:
        return f"<Localite(code={self.code!r}, type={self.type_localite!r}, nom={self.nom!r})>"
