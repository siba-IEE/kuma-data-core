"""Tests unitaires du canari PVGIS-SARAH3 - logique d'exit.

Vérifie les 3 verdicts de :func:`executer_canari` en remplaçant le fetch live
par un double (pas de réseau) :

- fetch == seed -> écart nul -> **exit 0** ;
- fetch indisponible (blip réseau) -> **exit 0** (warning, nightly verte) ;
- fetch réussi + perturbation > seuil (dérive réelle) -> **exit 1** (re-seed).
"""

from __future__ import annotations

from typing import Any

import pytest

from kuma_data_core.db.seeds.sarah3_monthly_seed_data import SARAH3_PAYLOADS
from kuma_data_core.exceptions import PvgisTimeoutError
from kuma_data_core.ingestion import canari_sarah3
from kuma_data_core.ingestion.canari_sarah3 import executer_canari
from kuma_data_core.ingestion.sarah3_monthly import _cle_payload_offline

pytestmark = pytest.mark.unit


@pytest.fixture(autouse=True)
def _mode_live(monkeypatch: pytest.MonkeyPatch) -> None:
    """Le canari exige le mode live (sinon il lève)."""
    monkeypatch.setenv("KUMA_INGESTION_MODE", "live")


def _seed_de(latitude: float, longitude: float, annee_debut: int, annee_fin: int) -> dict[str, Any]:
    return SARAH3_PAYLOADS[_cle_payload_offline(latitude, longitude, annee_debut, annee_fin)]


def test_canari_ok_exit_0(monkeypatch: pytest.MonkeyPatch) -> None:
    """Fetch identique au seed -> écart nul -> exit 0."""

    def _fetch_seed(**kwargs: Any) -> dict[str, Any]:
        return _seed_de(
            kwargs["latitude"], kwargs["longitude"], kwargs["annee_debut"], kwargs["annee_fin"]
        )

    monkeypatch.setattr(canari_sarah3, "_fetch_sarah3_monthly_raw", _fetch_seed)
    assert executer_canari() == 0


def test_canari_reseau_indispo_exit_0(monkeypatch: pytest.MonkeyPatch) -> None:
    """Blip réseau (fetch lève) -> exit 0, la nightly ne rougit pas."""

    def _fetch_indispo(**kwargs: Any) -> dict[str, Any]:
        raise PvgisTimeoutError(
            url="https://re.jrc.ec.europa.eu/api/v5_3/MRcalc", timeout_seconds=60.0
        )

    monkeypatch.setattr(canari_sarah3, "_fetch_sarah3_monthly_raw", _fetch_indispo)
    assert executer_canari() == 0


def test_canari_derive_exit_1(monkeypatch: pytest.MonkeyPatch) -> None:
    """Fetch réussi mais valeurs +5 % (dérive réelle) -> exit 1 (re-seed)."""

    def _fetch_perturbe(**kwargs: Any) -> dict[str, Any]:
        seed = _seed_de(
            kwargs["latitude"], kwargs["longitude"], kwargs["annee_debut"], kwargs["annee_fin"]
        )
        monthly = [
            {"year": e["year"], "month": e["month"], "H(h)_m": float(e["H(h)_m"]) * 1.05}
            for e in seed["outputs"]["monthly"]
        ]
        return {"inputs": {}, "outputs": {"monthly": monthly}, "meta": {}}

    monkeypatch.setattr(canari_sarah3, "_fetch_sarah3_monthly_raw", _fetch_perturbe)
    assert executer_canari() == 1
