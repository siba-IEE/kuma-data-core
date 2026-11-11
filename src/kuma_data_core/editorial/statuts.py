"""Machine d'état du statut éditorial des tables de mesures et de ``grandeurs_metier``.

Statuts : ``brut`` (importé, non validé), ``valide_auto`` (contrôle qualité
automatique passé), ``valide_humain`` (validation éditoriale), ``publie``,
``deprecie`` (retiré, état terminal). Les transitions admises sont dans
``TRANSITIONS_AUTORISEES`` : jamais de retour en arrière, sauts permis dans
le sens du circuit. Une donnée dépréciée ne revient que par rotation
versionnée d'une nouvelle ligne.

Les référentiels (unités, localités, sources…) ne suivent pas ce circuit :
leur retrait passe par ``actif`` / ``desactive_le``.
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
"""Miroir des contraintes SQL ``ck_<table>_statut_valide`` de ces tables."""


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
        # Aucune transition depuis ``deprecie``.
    }
)
"""Paires ``(statut_courant, nouveau_statut)`` admises ; toute autre est refusée."""


def transition_autorisee(statut_courant: str, nouveau_statut: str) -> bool:
    """Indique si la transition est autorisée, sans lever d'exception."""
    return (statut_courant, nouveau_statut) in TRANSITIONS_AUTORISEES


def transition_statut(statut_courant: str, nouveau_statut: str) -> None:
    """Lève ``TransitionEditorialeRefusee`` si la transition n'est pas autorisée.

    Un statut inconnu ou une transition vers le même statut sont refusés
    de la même façon. Ne modifie rien : l'appelant met à jour la ligne
    (``statut``, ``modifie_le``, ``modifie_par``) dans sa transaction.
    """
    if not transition_autorisee(statut_courant, nouveau_statut):
        raise TransitionEditorialeRefusee(
            statut_courant=statut_courant, nouveau_statut=nouveau_statut
        )
