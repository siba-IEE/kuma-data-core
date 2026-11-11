"""Rotation versionnée d'une ligne de ``mesures_ressource``.

Réviser une valeur sans perdre l'historique : la ligne courante est fermée
(``valide_au``) et une remplaçante de même identité ``(serie_id,
instant_mesure)`` est insérée, dans la même transaction. Si la contrainte
EXCLUDE refuse l'insertion, la transaction est annulée et l'ancienne ligne
reste courante.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from kuma_data_core.db.models.mesures_ressource import MesureRessource

# Identité métier, reportée telle quelle sur la ligne remplaçante.
COLONNES_IDENTITE_MESURES_RESSOURCE: tuple[str, ...] = ("serie_id", "instant_mesure")


def roter_ligne_versionnee(
    ligne_courante: MesureRessource,
    nouvelles_valeurs: dict[str, Any],
    auteur_id: int | None,
    session: Session,
) -> MesureRessource:
    """Ferme la ligne courante et insère sa remplaçante ; flush sans commit.

    ``nouvelles_valeurs`` porte les colonnes révisées (``{'valeur': 5.42}``) ;
    une colonne d'identité y lève ``ValueError``. ``auteur_id`` vaut ``None``
    pour une rotation automatique. La remplaçante naît ``brut`` sauf statut
    fourni, et garde le niveau de confiance dérivé de l'ancienne ligne si
    l'appelant ne le recalcule pas.
    """
    intersection = set(nouvelles_valeurs) & set(COLONNES_IDENTITE_MESURES_RESSOURCE)
    if intersection:
        raise ValueError(
            f"Colonnes d'identité métier interdites dans nouvelles_valeurs : "
            f"{sorted(intersection)}. La rotation versionnée préserve l'identité."
        )

    # Un seul ``now()`` (début de transaction) pour les deux lignes : ``valide_au``
    # de l'ancienne égale ``valide_du`` de la nouvelle, sans trou ni recouvrement
    # dans l'intervalle ``[)``.
    instant: datetime = session.execute(text("SELECT now()")).scalar_one()

    ligne_courante.valide_au = instant
    ligne_courante.modifie_le = instant
    ligne_courante.modifie_par = auteur_id

    payload: dict[str, Any] = {
        col: getattr(ligne_courante, col) for col in COLONNES_IDENTITE_MESURES_RESSOURCE
    }
    payload.update(nouvelles_valeurs)
    payload.setdefault("statut", "brut")
    # Le niveau dérivé dépend de la série (méthode, fiabilité de la source) :
    # à l'appelant de le recalculer, sinon celui de l'ancienne ligne est repris.
    if "niveau_confiance_derive" not in payload:
        payload["niveau_confiance_derive"] = ligne_courante.niveau_confiance_derive

    nouvelle_ligne = MesureRessource(
        **payload,
        valide_du=instant,
        valide_au=None,
        cree_le=instant,
        cree_par=auteur_id,
        modifie_le=instant,
        modifie_par=auteur_id,
    )
    session.add(nouvelle_ligne)
    session.flush()
    return nouvelle_ligne
