"""Modèle SQLAlchemy de la table ``unites`` : référentiel des unités de mesure.

Les facteurs et décalages de conversion sont en ``Numeric(60, 30)`` :
l'électronvolt (1,602176634e-19 J) serait tronqué à 0 avec 15 décimales, et le
quad (1,05505585262e18 J) demande 19 chiffres avant la virgule. Un type décimal,
plutôt que ``DOUBLE PRECISION``, conserve les définitions exactes (1 atm =
101 325 Pa, 1 cal_IT = 4,1868 J, année grégorienne moyenne = 365,2425 j).

L'unité de référence d'une grandeur n'est pas toujours l'unité SI : gCO2/kWh
pour l'intensité carbone, MJ/m²/jour pour l'irradiation solaire. Le pouvoir
calorifique est exprimé en PCI et les devises ne sont pas converties entre elles.
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
    func,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column

from kuma_data_core.db.base import Base


class Unite(Base):
    """Référentiel des unités de mesure de Kuma Data Core."""

    __tablename__ = "unites"

    id: Mapped[int] = mapped_column(BigInteger, Identity(start=1, increment=1), primary_key=True)
    code: Mapped[str] = mapped_column(String(80), nullable=False, unique=True)

    libelle: Mapped[str] = mapped_column(Text, nullable=False)
    symbole: Mapped[str] = mapped_column(String(50), nullable=False)
    grandeur: Mapped[str] = mapped_column(String(100), nullable=False)
    systeme: Mapped[str] = mapped_column(String(20), nullable=False)
    est_unite_de_base: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("FALSE")
    )

    # valeur_ref = valeur × facteur + decalage
    facteur_conversion_si: Mapped[Decimal] = mapped_column(
        Numeric(60, 30), nullable=False, server_default=text("1")
    )
    decalage_conversion_si: Mapped[Decimal] = mapped_column(
        Numeric(60, 30), nullable=False, server_default=text("0")
    )
    code_unite_si: Mapped[str] = mapped_column(String(80), nullable=False)

    note_methodologique: Mapped[str | None] = mapped_column(Text, nullable=True)
    contexte_usage: Mapped[str | None] = mapped_column(Text, nullable=True)
    references_normatives: Mapped[list[str] | None] = mapped_column(ARRAY(Text()), nullable=True)

    actif: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("TRUE"))
    desactive_le: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    cree_le: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    cree_par: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("contributeurs.id", name="fk_unites_cree_par__contributeurs"),
        nullable=True,
    )
    modifie_le: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    modifie_par: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("contributeurs.id", name="fk_unites_modifie_par__contributeurs"),
        nullable=True,
    )

    __table_args__ = (
        CheckConstraint(
            "systeme IN ('SI', 'non_SI_acceptee', 'composee_mixte', 'imperial', 'autre')",
            name="ck_unites_systeme_valide",
        ),
        CheckConstraint(
            "(est_unite_de_base = TRUE AND systeme = 'SI') OR (est_unite_de_base = FALSE)",
            name="ck_unites_base_coherence_systeme",
        ),
        CheckConstraint(
            "(actif = TRUE AND desactive_le IS NULL) "
            "OR (actif = FALSE AND desactive_le IS NOT NULL)",
            name="ck_unites_actif_desactive_le",
        ),
        Index("idx_unites_actif", "actif"),
        Index("idx_unites_grandeur", "grandeur"),
        Index("idx_unites_systeme", "systeme"),
        Index(
            "idx_unites_est_unite_de_base",
            "est_unite_de_base",
            postgresql_where=text("est_unite_de_base = TRUE"),
        ),
        Index("idx_unites_code_unite_si", "code_unite_si"),
        # ``alembic check`` compare ce commentaire de table à la base. Le dict
        # doit rester le dernier élément de ``__table_args__``.
        {
            "comment": (
                "Référentiel des unités de mesure de Kuma Data Core, avec leur conversion vers "
                "le Système international et leurs références normatives (BIPM, AIE, ONU, NIST, "
                "IUPAC, IEC, DIN, ISO, IPCC, IRENA, UNECE, etc.)."
            ),
        },
    )

    def __repr__(self) -> str:
        return f"<Unite(code={self.code!r}, symbole={self.symbole!r})>"
