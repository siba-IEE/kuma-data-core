"""Fixtures des tests ``tests/unit/external/`` : pas d'attente réelle dans les retries."""

from __future__ import annotations

from collections.abc import Iterator

import pytest


@pytest.fixture(autouse=True)
def _neutraliser_time_sleep(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """``time.sleep`` neutralisé dans ``external._http_retry`` (sinon 21 s par épuisement)."""
    monkeypatch.setattr(
        "kuma_data_core.external._http_retry.time.sleep",
        lambda _seconds: None,
    )
    yield
