"""Modèle SQLAlchemy de la table ``sources`` : références bibliographiques des données.

Une seule table pour tous les types de source : colonnes communes optionnelles,
plus ``metadonnees`` (objet JSON) pour ce qui est propre à un type. La cohérence
entre ``type_source`` et le contenu de ``metadonnees`` n'est pas contrôlée en base.

Le DOI est stocké sans préfixe URL et l'ISBN sans tirets. Une publication
récurrente a une ligne par édition, avec des codes distincts
(``irena_lcoe_2024``, ``irena_lcoe_2025``).

Niveaux de ``fiabilite`` :

- ``haute`` : organismes officiels, normes techniques, publications à comité de
  lecture ;
- ``moyenne`` : ONG reconnues, presse spécialisée, organisations
  professionnelles, thèses ;
- ``faible`` : presse généraliste, blogs, communiqués d'entreprise.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date, datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Identity,
    Index,
    Integer,
    String,
    Text,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from kuma_data_core.db.base import Base


class Source(Base):
    """Référentiel des références bibliographiques de Kuma Data Core."""

    __tablename__ = "sources"

    id: Mapped[int] = mapped_column(BigInteger, Identity(start=1, increment=1), primary_key=True)
    code: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        unique=True,
        comment=(
            "Identifiant court unique. Convention : <organisme>_<theme>[_<annee>]. "
            "Ex: irena_lcoe_2024, bcrg_rapport_annuel_2023, iso_50001_2018. "
            "Pour les publications recurrentes, inclure l'annee."
        ),
    )

    titre: Mapped[str] = mapped_column(Text, nullable=False)
    auteurs: Mapped[Sequence[str] | None] = mapped_column(ARRAY(Text()), nullable=True)
    organisation: Mapped[str | None] = mapped_column(String(255), nullable=True)
    type_source: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        comment=(
            "11 valeurs autorisees : rapport, article_scientifique, texte_legal, "
            "communique, page_web, base_donnees, livre, chapitre_livre, these, "
            "norme_technique (10 valeurs documentaires externes initiales, "
            "migration 004) + auteur_kuma (couche editoriale interne Kuma, "
            "introduite en 1-5D-i pour la source synthetique kuma_calculs)."
        ),
    )

    annee_publication: Mapped[int | None] = mapped_column(Integer, nullable=True)
    date_consultation: Mapped[date | None] = mapped_column(Date, nullable=True)

    url: Mapped[str | None] = mapped_column(Text, nullable=True)
    doi: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
        comment=(
            "Digital Object Identifier (ISO 26324). Stocke sans prefixe URL. "
            "Ex: 10.1038/nature12373 (pas https://doi.org/10.1038/nature12373)."
        ),
    )
    isbn: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
        comment=(
            "International Standard Book Number (ISO 2108). "
            "Stocke sans tirets ni espaces. "
            "Ex: 9782123456789 (pas 978-2-1234-5678-9). "
            "ISBN-10 ou ISBN-13 acceptes."
        ),
    )

    metadonnees: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)

    fiabilite: Mapped[str | None] = mapped_column(
        String(20),
        nullable=True,
        comment=(
            "Qualification editoriale Kuma (3 niveaux). "
            "Voir docs/architecture/04-api.md pour le mapping editorial complet."
        ),
    )
    langue: Mapped[str | None] = mapped_column(
        String(2),
        nullable=True,
        comment=("Code ISO 639-1 (2 lettres minuscules). Ex: fr, en, ar, pt, sw, yo, wo."),
    )
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    actif: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("TRUE"))
    desactive_le: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    cree_le: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    cree_par: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("contributeurs.id", name="fk_sources_cree_par__contributeurs"),
        nullable=True,
    )
    modifie_le: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    modifie_par: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("contributeurs.id", name="fk_sources_modifie_par__contributeurs"),
        nullable=True,
    )

    __table_args__ = (
        CheckConstraint(
            "type_source IN ("
            "'rapport', 'article_scientifique', 'texte_legal', "
            "'communique', 'page_web', 'base_donnees', "
            "'livre', 'chapitre_livre', 'these', 'norme_technique', "
            "'auteur_kuma')",
            name="ck_sources_type_source_valide",
        ),
        CheckConstraint(
            "metadonnees IS NULL OR jsonb_typeof(metadonnees) = 'object'",
            name="ck_sources_metadonnees_objet",
        ),
        CheckConstraint(
            r"url IS NULL OR url ~ '^https?://[^\s]+$'",
            name="ck_sources_url_format",
        ),
        CheckConstraint(
            r"doi IS NULL OR doi ~ '^10\.[0-9]{4,}(\.[0-9]+)*/[^\s]+$'",
            name="ck_sources_doi_format",
        ),
        CheckConstraint(
            "isbn IS NULL OR isbn ~ '^(97[89][0-9]{10}|[0-9]{9}[0-9X])$'",
            name="ck_sources_isbn_format",
        ),
        CheckConstraint(
            "fiabilite IS NULL OR fiabilite IN ('haute', 'moyenne', 'faible')",
            name="ck_sources_fiabilite_valide",
        ),
        CheckConstraint(
            "langue IS NULL OR langue ~ '^[a-z]{2}$'",
            name="ck_sources_langue_format_iso6391",
        ),
        CheckConstraint(
            "annee_publication IS NULL OR annee_publication BETWEEN 1900 AND 2100",
            name="ck_sources_annee_publication_valide",
        ),
        CheckConstraint(
            "(actif = TRUE AND desactive_le IS NULL) "
            "OR (actif = FALSE AND desactive_le IS NOT NULL)",
            name="ck_sources_actif_desactive_le",
        ),
        Index("idx_sources_actif", "actif"),
        Index("idx_sources_type_source", "type_source"),
        Index("idx_sources_organisation", "organisation"),
        Index("idx_sources_annee_publication", "annee_publication"),
        Index("idx_sources_langue", "langue"),
        Index(
            "idx_sources_metadonnees_gin",
            "metadonnees",
            postgresql_using="gin",
        ),
    )

    def __repr__(self) -> str:
        return f"<Source(code={self.code!r}, type={self.type_source!r}, titre={self.titre!r})>"
