"""Logging structuré (structlog) : console lisible en ``texte``, une ligne JSON en ``json``.

Horodatage ISO 8601 UTC ; les ``contextvars`` sont fusionnées dans chaque
événement. Événements et attributs en snake_case français
(``requete_traitee``, ``duree_ms``).
"""

from __future__ import annotations

import logging
import sys
from typing import cast

import structlog
from structlog.types import Processor

from kuma_data_core.core.config import get_settings


def configurer_logging() -> None:
    """Configure structlog selon ``log_format`` ; idempotent."""
    settings = get_settings()

    processeurs_partages: list[Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
    ]

    rendu_final: Processor
    if settings.log_format == "json":
        rendu_final = structlog.processors.JSONRenderer()
    else:
        rendu_final = structlog.dev.ConsoleRenderer(colors=True)

    structlog.configure(
        processors=[*processeurs_partages, rendu_final],
        wrapper_class=structlog.make_filtering_bound_logger(
            logging.getLevelName(settings.log_niveau)
        ),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(file=sys.stdout),
        cache_logger_on_first_use=True,
    )


def obtenir_logger(nom: str) -> structlog.stdlib.BoundLogger:
    """Logger nommé, ex. ``obtenir_logger("kuma.api.requete").info("requete_traitee")``."""
    return cast(structlog.stdlib.BoundLogger, structlog.get_logger(nom))
