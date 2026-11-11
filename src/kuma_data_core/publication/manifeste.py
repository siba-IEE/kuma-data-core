"""Manifeste du filtre de publication (ADR-0003).

Chaque table du schéma de référence appartient à exactement une catégorie :
publiée telle quelle, assainie (colonnes sensibles neutralisées) ou exclue.
Les tests de ``tests/unit/publication/`` le vérifient : une table ajoutée
sans classement casse la CI, rien ne peut fuiter en silence.

L'assainissement s'applique en local, sur la base d'édition intermédiaire,
avant ``pg_dump`` : le serveur ne reçoit jamais rien à nettoyer.

Aucune ligne n'est filtrée par statut au dump : l'historique versionné fait
partie de la donnée publiée, et c'est l'API qui choisit les lignes qu'elle
sert, par les règles de ``editorial.selection``.
"""

from __future__ import annotations

TABLES_PUBLIEES: frozenset[str] = frozenset(
    {
        "unites",
        "localites",
        "sources",
        "grandeurs_referentiel",
        "grandeurs_metier",
        "mesures_ressource",
        "mesures_ressource_mensuelles",
        "mesures_ressource_horaires",
        "referentiels_calage",
        "calage_couverture",
    }
)

TABLES_ASSAINIES: frozenset[str] = frozenset({"contributeurs", "series_metadonnees"})

TABLES_EXCLUES: frozenset[str] = frozenset({"audit_log"})

# Règles d'assainissement : table -> {colonne: expression SQL}, membre droit
# d'un ``UPDATE ... SET colonne = expression``. Une colonne NOT NULL ne peut
# pas recevoir NULL et une colonne UNIQUE veut une valeur distincte par
# ligne : d'où ``email_principal`` dérivé de ``id``.
ASSAINISSEMENTS: dict[str, dict[str, str]] = {
    "contributeurs": {
        "email_principal": "'contributeur-' || id::text || '@retire.invalid'",
        "biographie": "NULL",
        "notes_internes": "NULL",
    },
    # Le commentaire éditorial d'une série est un journal de travail interne :
    # il ne sort pas de la base de référence. Le texte public vit dans
    # ``note_publique``, servi par l'API sous l'alias ``notes_fr``.
    "series_metadonnees": {
        "commentaire_editorial": "NULL",
    },
}

# Fonction et triggers d'audit, supprimés de la base d'édition avant dump :
# rien n'est écrit sur le serveur, et ``audit_log`` est exclue.
FONCTION_AUDIT: str = "kuma_log_audit"
PREFIXE_TRIGGERS_AUDIT: str = "trg_audit_"

# Tables absentes de ``Base.metadata``, publiées pour traçabilité.
TABLES_HORS_ORM_PUBLIEES: frozenset[str] = frozenset({"alembic_version"})


def tables_classees() -> frozenset[str]:
    """Union des trois catégories : le périmètre couvert par le manifeste."""
    return TABLES_PUBLIEES | TABLES_ASSAINIES | TABLES_EXCLUES


def tables_dumpees() -> frozenset[str]:
    """Tables ORM effectivement présentes dans le dump d'une édition."""
    return TABLES_PUBLIEES | TABLES_ASSAINIES
