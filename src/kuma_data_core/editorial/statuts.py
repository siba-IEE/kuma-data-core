"""Machine d'état du statut éditorial (``mesures_ressource``, ``grandeurs_metier``).

| État courant       | Transitions sortantes autorisées                 |
|--------------------|--------------------------------------------------|
| ``brut``           | ``valide_auto``, ``valide_humain``, ``deprecie`` |
| ``valide_auto``    | ``valide_humain``, ``deprecie``                  |
| ``valide_humain``  | ``publie``, ``deprecie``                         |
| ``publie``         | ``deprecie``                                     |
| ``deprecie``       | aucune (état terminal)                           |

Pas de retour en arrière ; une donnée dépréciée revient par une nouvelle
version de ligne, pas par transition. Les référentiels stables se retirent
par soft delete (``actif``), pas par statut. Module sans SQLAlchemy : la mise
à jour de la ligne revient à l'appelant.

Une mesure est utilisable (lue pour sa valeur par l'API ou un calcul) si elle
est courante (``valide_au IS NULL``) et :

- journalière ou mensuelle : non dépréciée ; une mesure ``brut`` reste
  utilisable, ces tables n'ont pas de contrôle qualité automatique ;
- horaire : passée par le contrôle qualité (``valide_auto``, ``valide_humain``
  ou ``publie``) ; ``brut`` y signale un rejet du contrôle.

Les grandeurs calculées suivent la vue ``v_grandeurs_metier_courantes``
(courante, non dépréciée, version de formule actuelle).
"""

from __future__ import annotations

from kuma_data_core.exceptions import TransitionEditorialeRefusee

STATUTS_EDITORIAUX_AUTORISES: frozenset[str] = frozenset(
    {
        "brut",
        "valide_auto",
        "valide_humain",
        "publie",
        "deprecie",
    }
)
"""Miroir de la CHECK ``ck_<table>_statut_valide``, identique sur les deux tables."""


TRANSITIONS_AUTORISEES: frozenset[tuple[str, str]] = frozenset(
    {
        ("brut", "valide_auto"),
        ("brut", "valide_humain"),
        ("brut", "deprecie"),
        ("valide_auto", "valide_humain"),
        ("valide_auto", "deprecie"),
        ("valide_humain", "publie"),
        ("valide_humain", "deprecie"),
        ("publie", "deprecie"),
    }
)
"""Matrice exhaustive : toute paire absente est refusée."""


STATUTS_HORAIRES_UTILISABLES: tuple[str, ...] = ("valide_auto", "valide_humain", "publie")
"""Statuts d'une mesure horaire qui a passé le contrôle qualité."""


def filtre_mesure_utilisable(alias: str | None = None) -> str:
    """Prédicat SQL d'une mesure journalière ou mensuelle utilisable."""
    p = f"{alias}." if alias else ""
    return f"{p}valide_au IS NULL AND {p}statut <> 'deprecie'"


def filtre_mesure_horaire_utilisable(alias: str | None = None) -> str:
    """Prédicat SQL d'une mesure horaire utilisable."""
    p = f"{alias}." if alias else ""
    statuts = ", ".join(f"'{s}'" for s in STATUTS_HORAIRES_UTILISABLES)
    return f"{p}valide_au IS NULL AND {p}statut IN ({statuts})"


def transition_autorisee(statut_courant: str, nouveau_statut: str) -> bool:
    """Indique, sans lever, si la transition est autorisée."""
    return (statut_courant, nouveau_statut) in TRANSITIONS_AUTORISEES


def transition_statut(statut_courant: str, nouveau_statut: str) -> None:
    """Lève ``TransitionEditorialeRefusee`` si la transition n'est pas dans la matrice.

    Une transition vers le même statut ou depuis/vers un statut inconnu est
    refusée elle aussi (pas de no-op silencieux).
    """
    if not transition_autorisee(statut_courant, nouveau_statut):
        raise TransitionEditorialeRefusee(
            statut_courant=statut_courant, nouveau_statut=nouveau_statut
        )
