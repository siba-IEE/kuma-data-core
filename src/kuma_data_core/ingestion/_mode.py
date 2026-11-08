"""Mode d'ingestion ``live`` (défaut) ou ``offline`` (seed committé au lieu du réseau).

``offline`` est interdit en prod : :func:`est_mode_offline` lève plutôt que
de servir une donnée figée.
"""

from __future__ import annotations

import os

VARIABLE_ENV_MODE: str = "KUMA_INGESTION_MODE"
VARIABLE_ENV_ENVIRONNEMENT: str = "API_ENVIRONNEMENT"

MODE_LIVE: str = "live"
MODE_OFFLINE: str = "offline"
_MODES_VALIDES: tuple[str, ...] = (MODE_LIVE, MODE_OFFLINE)


def mode_ingestion() -> str:
    """Mode d'ingestion courant. Défaut : ``live`` (réseau réel)."""
    valeur = os.environ.get(VARIABLE_ENV_MODE, MODE_LIVE).strip().lower() or MODE_LIVE
    if valeur not in _MODES_VALIDES:
        raise RuntimeError(
            f"{VARIABLE_ENV_MODE}={valeur!r} invalide (attendu {MODE_LIVE!r} ou {MODE_OFFLINE!r})."
        )
    return valeur


def est_mode_offline() -> bool:
    """Vrai si ``KUMA_INGESTION_MODE=offline`` hors prod ; ``RuntimeError`` en prod."""
    if mode_ingestion() != MODE_OFFLINE:
        return False
    environnement = os.environ.get(VARIABLE_ENV_ENVIRONNEMENT, "dev").strip().lower()
    if environnement == "prod":
        raise RuntimeError(
            f"{VARIABLE_ENV_MODE}={MODE_OFFLINE} interdit en production "
            f"({VARIABLE_ENV_ENVIRONNEMENT}=prod) : le mode offline ne doit jamais "
            f"servir de la donnée figée en prod (gating fail-safe D-40 lot 1)."
        )
    return True
