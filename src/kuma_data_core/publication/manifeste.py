"""Manifeste du filtre de publication d'une édition publique (ADR-0003).

Toute table de ``Base.metadata`` est exactement dans une des trois
catégories (publiée, assainie, exclue) : une table non classée casse les
tests, rien ne fuit en silence. L'assainissement s'exécute en local sur la
base d'édition intermédiaire avant ``pg_dump`` ; le VPS ne reçoit rien à
nettoyer. Aucun filtrage par statut : l'historique versionné fait partie de
la donnée, l'API ne sert que ``statut <> 'deprecie'``.
"""

from __future__ import annotations

# Tables dumpées telles quelles.
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

# Tables dumpées après assainissement (règles ci-dessous).
TABLES_ASSAINIES: frozenset[str] = frozenset({"contributeurs", "series_metadonnees"})

# Tables jamais dumpées.
TABLES_EXCLUES: frozenset[str] = frozenset({"audit_log"})

# table -> {colonne: membre droit de ``UPDATE ... SET colonne = ...``}.
# ``email_principal`` est NOT NULL UNIQUE : valeur dérivée de ``id``.
ASSAINISSEMENTS: dict[str, dict[str, str]] = {
    "contributeurs": {
        "email_principal": "'contributeur-' || id::text || '@retire.invalid'",
        "biographie": "NULL",
        "notes_internes": "NULL",
    },
    # Le journal interne d'une série ne sort pas ; le texte public est
    # note_publique, servi par l'API sous l'alias notes_fr.
    "series_metadonnees": {
        "commentaire_editorial": "NULL",
    },
}

# Supprimés de la base d'édition avant dump : pas d'écriture sur le VPS.
FONCTION_AUDIT: str = "kuma_log_audit"
PREFIXE_TRIGGERS_AUDIT: str = "trg_audit_"


def tables_classees() -> frozenset[str]:
    """Union des trois catégories : le périmètre couvert par le manifeste."""
    return TABLES_PUBLIEES | TABLES_ASSAINIES | TABLES_EXCLUES


def tables_dumpees() -> frozenset[str]:
    """Tables ORM effectivement présentes dans le dump d'une édition."""
    return TABLES_PUBLIEES | TABLES_ASSAINIES
