"""Rotation versionnée : réviser une valeur sans perdre son historique.

Ferme la ligne courante et insère la remplaçante dans la même transaction,
au même instant ``now()`` : ``valide_au`` de l'ancienne égale ``valide_du``
de la nouvelle, sans trou ni chevauchement sur ``tstzrange [)``. Si
l'EXCLUDE refuse l'INSERT, le rollback laisse l'ancienne ligne courante.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from kuma_data_core.db.models.mesures_ressource import MesureRessource

COLONNES_IDENTITE_MESURES_RESSOURCE: tuple[str, ...] = ("serie_id", "instant_mesure")


def roter_ligne_versionnee(
    ligne_courante: MesureRessource,
    nouvelles_valeurs: dict[str, Any],
    auteur_id: int | None,
    session: Session,
) -> MesureRessource:
    """Ferme ``ligne_courante`` et insère (flush, sans commit) une remplaçante.

    La nouvelle ligne repart en ``statut='brut'`` et garde l'identité
    ``(serie_id, instant_mesure)`` ; ``ValueError`` si ``nouvelles_valeurs``
    tente de la modifier. ``auteur_id`` vaut ``None`` pour une rotation automatique.
    """
    intersection = set(nouvelles_valeurs) & set(COLONNES_IDENTITE_MESURES_RESSOURCE)
    if intersection:
        raise ValueError(
            f"Colonnes d'identité métier interdites dans nouvelles_valeurs : "
            f"{sorted(intersection)}. La rotation versionnée préserve l'identité."
        )

    # now() est l'instant de début de transaction : un seul appel pour les deux lignes.
    instant: datetime = session.execute(text("SELECT now()")).scalar_one()

    ligne_courante.valide_au = instant
    ligne_courante.modifie_le = instant
    ligne_courante.modifie_par = auteur_id

    payload: dict[str, Any] = {
        col: getattr(ligne_courante, col) for col in COLONNES_IDENTITE_MESURES_RESSOURCE
    }
    payload.update(nouvelles_valeurs)
    payload.setdefault("statut", "brut")
    # À défaut d'un niveau recalculé par l'appelant, on reprend celui de la ligne courante.
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
