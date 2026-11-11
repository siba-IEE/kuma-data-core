"""Modèle SQLAlchemy de la table ``calage_couverture`` : localités couvertes par un calage.

Une ligne par localité qualifiée pour le transport d'un référentiel de calage
(ADR-0004). Cette liste détermine où une étude calée est permise : étendre la
couverture revient à ajouter des lignes et à publier une édition.

Le lien vers ``referentiels_calage`` passe par ``referentiel_code``, sans clé
étrangère : ce code y est partagé par les lignes de saisons et n'y est donc pas
unique.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Identity,
    Index,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from kuma_data_core.db.base import Base


class CalageCouverture(Base):
    """Une localité qualifiée pour le transport d'un référentiel de calage."""

    __tablename__ = "calage_couverture"

    id: Mapped[int] = mapped_column(BigInteger, Identity(start=1, increment=1), primary_key=True)
    referentiel_code: Mapped[str] = mapped_column(String(120), nullable=False)
    localite_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("localites.id", name="fk_calage_couverture_localite__localites"),
        nullable=False,
    )

    justification: Mapped[str] = mapped_column(Text, nullable=False)
    version: Mapped[str] = mapped_column(String(20), nullable=False, server_default=text("'v1'"))

    actif: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("TRUE"))

    cree_le: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    modifie_le: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (
        UniqueConstraint(
            "referentiel_code",
            "localite_id",
            "version",
            name="uq_calage_couverture_referentiel_localite_version",
        ),
        Index("idx_calage_couverture_referentiel", "referentiel_code"),
        Index("idx_calage_couverture_actif", "actif"),
        {
            "comment": (
                "Domaine de couverture des referentiels de calage : "
                "localites qualifiees pour le transport, avec justification. "
                "Pilote la couverture geographique des consommateurs "
                "(ADR-0004, couverture progressive)."
            ),
        },
    )

    def __repr__(self) -> str:
        return (
            f"<CalageCouverture(referentiel={self.referentiel_code!r}, "
            f"localite_id={self.localite_id!r})>"
        )
