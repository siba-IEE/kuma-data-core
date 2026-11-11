"""Modèle SQLAlchemy de la table ``referentiels_calage`` : biais saisonniers satellite/sol.

Une ligne par (station, grandeur, saison) (ADR-0004). Les biais sont des
résultats d'analyse, publiés avec leur provenance (notes
``docs/methodologie/calage-*-terrain-lite.md``) : ils sont stockés et non
recalculés par le serveur, car les lignes satellite des appariements horaires
dont ils sont tirés ne sont plus en base.

Le facteur de calage ``k = 1 / (1 + biais)`` s'applique à la climatologie du
site étudié.
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
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column

from kuma_data_core.db.base import Base


class ReferentielCalage(Base):
    """Biais saisonnier satellite/sol d'une station de référence."""

    __tablename__ = "referentiels_calage"

    id: Mapped[int] = mapped_column(BigInteger, Identity(start=1, increment=1), primary_key=True)
    code: Mapped[str] = mapped_column(String(120), nullable=False)

    localite_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("localites.id", name="fk_referentiels_calage_localite__localites"),
        nullable=False,
    )
    grandeur_code: Mapped[str] = mapped_column(String(50), nullable=False)
    saison: Mapped[str] = mapped_column(String(40), nullable=False)
    mois: Mapped[list[int]] = mapped_column(ARRAY(BigInteger), nullable=False)
    # Biais relatif moyen, satellite moins sol (0.044 pour +4,4 %). Le facteur
    # k = 1 / (1 + biais) en est dérivé et n'est pas stocké.
    biais: Mapped[Decimal] = mapped_column(Numeric(8, 6), nullable=False)

    # Code de la série sol sur laquelle le référentiel est fondé : la séquence
    # horaire de référence à utiliser avec ce calage. Les consommateurs la lisent
    # ici plutôt que de la coder en dur.
    serie_sol: Mapped[str] = mapped_column(String(120), nullable=False)

    provenance: Mapped[str] = mapped_column(Text, nullable=False)
    portee: Mapped[str] = mapped_column(Text, nullable=False)
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
            "localite_id",
            "grandeur_code",
            "saison",
            "version",
            name="uq_referentiels_calage_station_grandeur_saison_version",
        ),
        CheckConstraint("biais > -1", name="ck_referentiels_calage_biais_definissable"),
        Index("idx_referentiels_calage_localite_grandeur", "localite_id", "grandeur_code"),
        Index("idx_referentiels_calage_actif", "actif"),
        {
            "comment": (
                "Référentiel de calage satellite/sol : biais saisonniers mesurés aux stations "
                "de référence, publiés avec leur provenance et la portée de leur transport. "
                "Voir "
                "https://github.com/siba-IEE/kuma-data-core/blob/main/docs/decisions/0004-exposition-etudes-au-point.md"
            ),
        },
    )

    def __repr__(self) -> str:
        return f"<ReferentielCalage(code={self.code!r}, saison={self.saison!r})>"
