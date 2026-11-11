"""Modèle SQLAlchemy de la table ``mesures_ressource_mensuelles`` : mesures mensuelles ingérées.

Identité métier : ``(serie_id, annee, mois)``. L'année et le mois sont deux
colonnes plutôt qu'une date au premier du mois, qui laisserait croire à une
mesure datée de ce jour. Même versionnement que ``mesures_ressource``.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Identity,
    Index,
    SmallInteger,
    String,
    Text,
    func,
    text,
)
from sqlalchemy.ext.hybrid import hybrid_property
from sqlalchemy.orm import Mapped, mapped_column, relationship

from kuma_data_core.db.base import Base
from kuma_data_core.db.models.series_metadonnees import SerieMetadonnees


class MesureRessourceMensuelle(Base):
    """Mesure mensuelle d'une grandeur brute ingérée depuis une source externe."""

    __tablename__ = "mesures_ressource_mensuelles"

    id: Mapped[int] = mapped_column(BigInteger, Identity(start=1, increment=1), primary_key=True)

    serie_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey(
            "series_metadonnees.id",
            name="fk_mesures_ressource_mensuelles_serie_id__series_metadonnees",
            ondelete="RESTRICT",
        ),
        nullable=False,
    )
    annee: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    mois: Mapped[int] = mapped_column(SmallInteger, nullable=False)

    valeur: Mapped[float] = mapped_column(Float(precision=53), nullable=False)

    valide_du: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    valide_au: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    statut: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        server_default=text("'brut'"),
    )

    niveau_confiance_derive: Mapped[str] = mapped_column(String(1), nullable=False)
    niveau_confiance_override: Mapped[str | None] = mapped_column(String(1), nullable=True)

    commentaire_editorial: Mapped[str | None] = mapped_column(Text, nullable=True)

    cree_le: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    cree_par: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey(
            "contributeurs.id",
            name="fk_mesures_ressource_mensuelles_cree_par__contributeurs",
            ondelete="SET NULL",
        ),
        nullable=True,
    )
    modifie_le: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    modifie_par: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey(
            "contributeurs.id",
            name="fk_mesures_ressource_mensuelles_modifie_par__contributeurs",
            ondelete="SET NULL",
        ),
        nullable=True,
    )

    serie: Mapped[SerieMetadonnees] = relationship(
        SerieMetadonnees,
        lazy="select",
        foreign_keys=[serie_id],
    )

    @hybrid_property
    def niveau_effectif(self) -> str:
        """Niveau de confiance à utiliser : l'override s'il existe, sinon le niveau dérivé."""
        return (
            self.niveau_confiance_override
            if self.niveau_confiance_override is not None
            else self.niveau_confiance_derive
        )

    __table_args__ = (
        CheckConstraint(
            "annee BETWEEN 1981 AND 2099",
            name="ck_mesures_ressource_mensuelles_annee_valide",
        ),
        CheckConstraint(
            "mois BETWEEN 1 AND 12",
            name="ck_mesures_ressource_mensuelles_mois_valide",
        ),
        CheckConstraint(
            "statut IN ('brut', 'valide_auto', 'valide_humain', 'publie', 'deprecie')",
            name="ck_mesures_ressource_mensuelles_statut_valide",
        ),
        CheckConstraint(
            "niveau_confiance_derive IN ('A', 'B', 'C')",
            name="ck_mesures_ressource_mensuelles_niveau_confiance_derive_valide",
        ),
        CheckConstraint(
            "niveau_confiance_override IS NULL OR niveau_confiance_override IN ('A', 'B', 'C')",
            name="ck_mesures_ressource_mensuelles_niveau_confiance_override_valide",
        ),
        CheckConstraint(
            "valide_au IS NULL OR valide_au > valide_du",
            name="ck_mesures_ressource_mensuelles_periode_coherente",
        ),
        # Index partiel sur les lignes courantes, les plus lues.
        Index(
            "idx_mesures_ressource_mensuelles_courantes",
            "serie_id",
            "annee",
            "mois",
            postgresql_where=text("valide_au IS NULL"),
        ),
        {
            "comment": (
                "Mesures mensuelles ingérées depuis les sources externes (NASA POWER, SARAH-3 "
                "via PVGIS, CAMS Radiation, ERA5-Land). Pendant mensuel de mesures_ressource "
                "(journalier). Versionnement temporel par (valide_du, valide_au) et contrainte "
                "EXCLUDE BTree-GiST sur l'identité métier (serie_id, annee, mois). Statut "
                "éditorial et niveau de confiance dérivé ou forcé par la couche de service "
                "éditoriale."
            ),
        },
    )

    def __repr__(self) -> str:
        return (
            f"<MesureRessourceMensuelle(id={self.id}, serie_id={self.serie_id}, "
            f"annee={self.annee}, mois={self.mois}, valeur={self.valeur})>"
        )
