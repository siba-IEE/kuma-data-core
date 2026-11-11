"""Modèle SQLAlchemy de la table ``series_metadonnees`` : métadonnées des séries de mesures.

Une série est identifiée par sa localité, sa grandeur, sa source, sa période et
sa granularité ; les tables de mesures la citent par ``serie_id``.
``granularite`` indique dans quelle table vivent ses mesures (journalière,
mensuelle ou horaire).

Pas de versionnement ni de statut éditorial à ce niveau : une série se désactive
par ``actif`` / ``desactive_le``, et le niveau de confiance est porté par chaque
mesure. ``grandeur_code`` référence ``grandeurs_referentiel.code``, colonne
unique qui n'est pas la clé primaire.
"""

from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
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


class SerieMetadonnees(Base):
    """Métadonnées éditoriales d'une série de mesures Kuma."""

    __tablename__ = "series_metadonnees"

    id: Mapped[int] = mapped_column(BigInteger, Identity(start=1, increment=1), primary_key=True)
    code: Mapped[str] = mapped_column(
        String(80),
        nullable=False,
        unique=True,
        comment=(
            "Clé naturelle métier (ASCII pur, snake_case). Convention : "
            "<localite>_<grandeur>_<source>[_<granularite>]_<periode>, ex. "
            "gin_conakry_hep_kuma_calculs_2021_2025. Voir "
            "https://github.com/siba-IEE/kuma-data-core/blob/main/docs/conventions/01-naming.md"
        ),
    )
    libelle: Mapped[str] = mapped_column(Text, nullable=False)

    localite_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey(
            "localites.id",
            name="fk_series_metadonnees_localite_id__localites",
            ondelete="RESTRICT",
        ),
        nullable=False,
    )
    grandeur_code: Mapped[str] = mapped_column(
        String(80),
        ForeignKey(
            "grandeurs_referentiel.code",
            name="fk_series_metadonnees_grandeur_code__grandeurs_referentiel",
            ondelete="RESTRICT",
        ),
        nullable=False,
        comment=(
            "FK vers grandeurs_referentiel.code (colonne UNIQUE non-PK). "
            "Lisibilite metier prioritaire sur convention SQL classique."
        ),
    )
    source_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey(
            "sources.id",
            name="fk_series_metadonnees_source_id__sources",
            ondelete="RESTRICT",
        ),
        nullable=False,
    )

    periode_debut: Mapped[date] = mapped_column(Date, nullable=False)
    periode_fin: Mapped[date | None] = mapped_column(
        Date,
        nullable=True,
        comment=(
            "NULL si la serie est en cours (pas de fin annoncee). "
            "Sinon date de la derniere mesure attendue, >= periode_debut."
        ),
    )

    granularite: Mapped[str | None] = mapped_column(
        String(16),
        nullable=True,
        comment=(
            "Discriminant de granularité temporelle, qui désigne la table des mesures de la "
            "série : journalier (mesures_ressource), mensuel (mesures_ressource_mensuelles) ou "
            "horaire (mesures_ressource_horaires). NULL pour les séries de la source "
            "kuma_calculs, dont les valeurs sont dans grandeurs_metier et la temporalité dans "
            "grandeurs_metier.periode_type."
        ),
    )

    methode_collecte: Mapped[str | None] = mapped_column(
        String(40),
        nullable=True,
        comment=(
            "Méthode dominante de collecte de la série : mesure_directe, modele_satellitaire, "
            "interpolation_geographique, extrapolation_temporelle, calcul_derive ou "
            "expertise_humaine (contrainte CHECK, NULL admis). Elle entre dans le niveau de "
            "confiance dérivé : voir "
            "https://github.com/siba-IEE/kuma-data-core/blob/main/docs/contribution/confiance-et-statuts.md"
        ),
    )
    methode_collecte_doc: Mapped[str | None] = mapped_column(Text, nullable=True)
    commentaire_editorial: Mapped[str | None] = mapped_column(Text, nullable=True)
    note_publique: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment=(
            "Passeport public de la série (servi par l'API sous l'alias "
            "notes_fr, affiché sur les fiches du site). Auto-portant : "
            "aucune référence de chantier interne. Toute nouvelle série "
            "doit le renseigner à l'insertion ; commentaire_editorial "
            "reste le journal interne, assaini à l'export d'édition."
        ),
    )
    url_documentation: Mapped[str | None] = mapped_column(Text, nullable=True)

    actif: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("TRUE"))
    desactive_le: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    cree_le: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    cree_par: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey(
            "contributeurs.id",
            name="fk_series_metadonnees_cree_par__contributeurs",
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
            name="fk_series_metadonnees_modifie_par__contributeurs",
            ondelete="SET NULL",
        ),
        nullable=True,
    )

    __table_args__ = (
        CheckConstraint(
            "periode_fin IS NULL OR periode_fin >= periode_debut",
            name="ck_series_metadonnees_periode_coherente",
        ),
        CheckConstraint(
            "granularite IS NULL OR granularite IN ('journalier', 'mensuel', 'horaire')",
            name="ck_series_metadonnees_granularite_valide",
        ),
        CheckConstraint(
            "(actif = TRUE AND desactive_le IS NULL) "
            "OR (actif = FALSE AND desactive_le IS NOT NULL)",
            name="ck_series_metadonnees_actif_desactive_coherent",
        ),
        CheckConstraint(
            "methode_collecte IS NULL OR methode_collecte IN ("
            "'mesure_directe', 'modele_satellitaire', 'interpolation_geographique', "
            "'extrapolation_temporelle', 'calcul_derive', 'expertise_humaine')",
            name="ck_series_metadonnees_methode_collecte_valide",
        ),
        Index("idx_series_metadonnees_actif", "actif"),
        Index("idx_series_metadonnees_localite_id", "localite_id"),
        Index("idx_series_metadonnees_grandeur_code", "grandeur_code"),
        Index("idx_series_metadonnees_source_id", "source_id"),
        # Nom explicite : la convention de nommage (``db/base.py``) ne
        # reprendrait que la première colonne.
        UniqueConstraint(
            "localite_id",
            "grandeur_code",
            "source_id",
            "periode_debut",
            "periode_fin",
            "granularite",
            name="uq_series_metadonnees_identite_metier_plage_granularite",
        ),
        # ``alembic check`` compare ce commentaire de table à la base. Le dict
        # doit rester le dernier élément de ``__table_args__``.
        {
            "comment": (
                "Référentiel éditorial des séries de mesures Kuma. Une série est identifiée par"
                " sa localité, sa grandeur, sa source, sa période et sa granularité ; elle "
                "porte les métadonnées éditoriales communes à ses mesures."
            ),
        },
    )

    def __repr__(self) -> str:
        return f"<SerieMetadonnees(code={self.code!r}, grandeur={self.grandeur_code!r})>"
