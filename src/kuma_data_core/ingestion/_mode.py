"""Mode d'ingestion (``live`` / ``offline``).

Mode unique cohérent remplaçant progressivement
les ``KUMA_SKIP_*`` : sous ``KUMA_INGESTION_MODE=offline``, un module d'ingestion
**converti** renvoie la donnée d'un seed committé au lieu du réseau.

**Gating fail-safe** : défaut ``live`` (réseau réel) ; le mode
``offline`` ne sert **jamais** en production. Si l'environnement est ``prod`` et
le mode ``offline``, :func:`est_mode_offline` **lève** plutôt que de servir de la
donnée figée (un flag qui « fuit » échoue franchement).
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
    """True si le mode offline (seed) est actif - fail-safe : interdit en prod.

    Returns:
        ``True`` si ``KUMA_INGESTION_MODE=offline`` **et** environnement non-prod.
        ``False`` si mode ``live`` (défaut).

    Raises:
        RuntimeError : si mode ``offline`` **et** ``API_ENVIRONNEMENT=prod``
            (le mode offline ne doit jamais servir de la donnée figée en prod).
    """
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
