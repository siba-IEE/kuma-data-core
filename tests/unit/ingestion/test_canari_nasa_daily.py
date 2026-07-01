"""Tests unitaires du canari NASA POWER daily - exit + maturation-aware.

Vérifie les verdicts de :func:`executer_canari` en remplaçant le fetch live par un
double (pas de réseau), sur le seed réel committé :

- fetch == seed -> écart nul -> exit 0 ;
- fetch indisponible (blip) -> exit 0 (nightly verte) ;
- dérive dans la fenêtre STABLE -> exit 1 (re-seed) ;
- dérive UNIQUEMENT dans la queue maturante (> DERNIERE_DATE_STABLE) -> exit 0
  (maturation normale, pas une alarme) : le coeur maturation-aware.
"""

from __future__ import annotations

import copy
from typing import Any

import pytest

from kuma_data_core.db.seeds.nasa_power_daily_seed_data import NASA_DAILY_PAYLOADS
from kuma_data_core.exceptions import NasaPowerTimeoutError
from kuma_data_core.ingestion import canari_nasa_daily
from kuma_data_core.ingestion.canari_nasa_daily import DERNIERE_DATE_STABLE, executer_canari
from kuma_data_core.ingestion.nasa_power_daily import _cle_ville_offline

pytestmark = pytest.mark.unit


@pytest.fixture(autouse=True)
def _mode_live(monkeypatch: pytest.MonkeyPatch) -> None:
    """Le canari exige le mode live (sinon il lève)."""
    monkeypatch.setenv("KUMA_INGESTION_MODE", "live")


def _seed_de(latitude: float, longitude: float) -> dict[str, Any]:
    return NASA_DAILY_PAYLOADS[_cle_ville_offline(latitude, longitude)]


def _perturber(seed: dict[str, Any], *, prefixe_date: str, facteur: float) -> dict[str, Any]:
    """Copie le seed et multiplie par facteur les valeurs aux clés-dates préfixées."""
    live = copy.deepcopy(seed)
    for vals in live["properties"]["parameter"].values():
        for cle in list(vals):
            if cle.startswith(prefixe_date) and vals[cle] != -999.0:
                vals[cle] = vals[cle] * facteur
    return live


def test_canari_ok_exit_0(monkeypatch: pytest.MonkeyPatch) -> None:
    """Fetch identique au seed -> écart nul -> exit 0."""

    def _fetch_seed(**kwargs: Any) -> dict[str, Any]:
        return _seed_de(kwargs["latitude"], kwargs["longitude"])

    monkeypatch.setattr(canari_nasa_daily, "fetch_daily_raw", _fetch_seed)
    assert executer_canari() == 0


def test_canari_reseau_indispo_exit_0(monkeypatch: pytest.MonkeyPatch) -> None:
    """Blip réseau (fetch lève) -> exit 0, la nightly ne rougit pas."""

    def _fetch_indispo(**kwargs: Any) -> dict[str, Any]:
        raise NasaPowerTimeoutError(url="https://power.larc.nasa.gov", timeout_seconds=30.0)

    monkeypatch.setattr(canari_nasa_daily, "fetch_daily_raw", _fetch_indispo)
    assert executer_canari() == 0


def test_canari_derive_fenetre_stable_exit_1(monkeypatch: pytest.MonkeyPatch) -> None:
    """Dérive +5 % sur une date de la fenêtre STABLE (2021) -> exit 1 (re-seed)."""

    def _fetch_perturbe(**kwargs: Any) -> dict[str, Any]:
        return _perturber(
            _seed_de(kwargs["latitude"], kwargs["longitude"]), prefixe_date="2021", facteur=1.05
        )

    monkeypatch.setattr(canari_nasa_daily, "fetch_daily_raw", _fetch_perturbe)
    assert executer_canari() == 1


def test_canari_derive_queue_maturante_exit_0(monkeypatch: pytest.MonkeyPatch) -> None:
    """Dérive +5 % UNIQUEMENT dans la queue maturante (2025-12) -> exit 0 (pas une alarme)."""
    # Coherence : la queue 2025-12 est posterieure a DERNIERE_DATE_STABLE (2025-06).
    assert DERNIERE_DATE_STABLE.year == 2025
    assert DERNIERE_DATE_STABLE.month < 12

    def _fetch_perturbe(**kwargs: Any) -> dict[str, Any]:
        return _perturber(
            _seed_de(kwargs["latitude"], kwargs["longitude"]), prefixe_date="202512", facteur=1.05
        )

    monkeypatch.setattr(canari_nasa_daily, "fetch_daily_raw", _fetch_perturbe)
    assert executer_canari() == 0
