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
