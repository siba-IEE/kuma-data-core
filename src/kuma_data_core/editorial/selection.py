"""Règles de sélection des lignes servies, définies ici et nulle part ailleurs.

Une valeur est versionnée (``valide_au`` nul : version en vigueur) et porte un
statut éditorial. Deux règles, selon que la table passe ou non par le contrôle
qualité automatique :

- ``lignes_en_vigueur`` : version en vigueur, non dépréciée. Pour les mesures
  journalières (``mesures_ressource``), mensuelles
  (``mesures_ressource_mensuelles``) et les valeurs de grandeur
  (``grandeurs_metier``) : aucun contrôle automatique ne les juge, ``brut`` y
  est le statut ordinaire d'une valeur servie.
- ``lignes_en_vigueur_validees`` : version en vigueur, de statut validé. Pour
  les mesures horaires (``mesures_ressource_horaires``) : elles passent par le
  contrôle qualité automatique, ``brut`` y désigne une ligne qui ne l'a pas
  passé.

Chaque fonction rend un fragment de clause ``WHERE``, à combiner par ``AND``.
"""

from __future__ import annotations

import re
from typing import Literal

from kuma_data_core.editorial.statuts import STATUTS_VALIDES

VUE_GRANDEURS_EN_VIGUEUR = "v_grandeurs_metier_courantes"
"""Vue de ``grandeurs_metier`` : ``lignes_en_vigueur``, plus la version de formule actuelle."""

StatutValide = Literal["valide_auto", "valide_humain", "publie"]
"""Statut d'une ligne que ``lignes_en_vigueur_validees`` retient : les ``STATUTS_VALIDES``."""

_ALIAS = re.compile(r"[a-z_][a-z0-9_]*")


def _prefixe(alias: str | None) -> str:
    """Préfixe ``alias.`` des colonnes, vide sans alias.

    L'alias est inséré tel quel dans le SQL : il vient du code, jamais d'une requête.
    Lève ``ValueError`` s'il n'a pas la forme d'un identifiant.
    """
    if alias is None:
        return ""
    if not _ALIAS.fullmatch(alias):
        raise ValueError(f"alias de table invalide : {alias!r}")
    return f"{alias}."


def lignes_en_vigueur(alias: str | None = None) -> str:
    """Fragment SQL : version en vigueur, non dépréciée."""
    p = _prefixe(alias)
    return f"{p}valide_au IS NULL AND {p}statut <> 'deprecie'"


def lignes_en_vigueur_validees(alias: str | None = None) -> str:
    """Fragment SQL : version en vigueur dont le statut est l'un de ``STATUTS_VALIDES``."""
    p = _prefixe(alias)
    statuts = ", ".join(f"'{statut}'" for statut in STATUTS_VALIDES)
    return f"{p}valide_au IS NULL AND {p}statut IN ({statuts})"
