"""Tests unitaires du mode d'ingestion.

Couvre :func:`mode_ingestion` (défaut live, validation) et
:func:`est_mode_offline` (activation + garde-fou fail-safe interdisant l'offline
en production).
"""

from __future__ import annotations

import pytest

from kuma_data_core.ingestion._mode import est_mode_offline, mode_ingestion

pytestmark = pytest.mark.unit


def test_mode_defaut_live(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("KUMA_INGESTION_MODE", raising=False)
    assert mode_ingestion() == "live"
    assert est_mode_offline() is False


def test_mode_offline_actif_hors_prod(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("KUMA_INGESTION_MODE", "offline")
    monkeypatch.setenv("API_ENVIRONNEMENT", "dev")
    assert est_mode_offline() is True


def test_mode_invalide_leve(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("KUMA_INGESTION_MODE", "snapshot")
    with pytest.raises(RuntimeError, match="invalide"):
        mode_ingestion()


def test_gating_failsafe_offline_prod_leve(monkeypatch: pytest.MonkeyPatch) -> None:
    """Garde-fou 1 : offline + prod -> erreur (jamais de donnée figée en prod)."""
    monkeypatch.setenv("KUMA_INGESTION_MODE", "offline")
    monkeypatch.setenv("API_ENVIRONNEMENT", "prod")
    with pytest.raises(RuntimeError, match="prod"):
        est_mode_offline()
