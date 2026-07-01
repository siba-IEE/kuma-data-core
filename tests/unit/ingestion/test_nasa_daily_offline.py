"""Tests unitaires du seam offline-seed NASA daily.

Couvre le tranchage du payload ville (sélection paramètres + fenêtre, sentinelles
conservées, source non mutée), et l'aiguillage ``_fetch_nasa_daily_raw`` (live vs
offline, gating fail-safe prod). Aucun de ces tests ne requiert le seed committé :
le tranchage est exercé sur un payload synthétique, et l'aiguillage est testé en
monkeypatchant le chargement / le fetch live.
"""

from __future__ import annotations

import json
from datetime import date
from typing import Any

import pytest

from kuma_data_core.ingestion import nasa_power_daily
from kuma_data_core.ingestion.nasa_power_daily import (
    _cle_ville_offline,
    _fetch_nasa_daily_raw,
    _trancher_payload_offline,
)

pytestmark = pytest.mark.unit


def _payload_ville() -> dict[str, Any]:
    """Payload NASA ville synthétique : 2 paramètres sur quelques dates."""
    return {
        "type": "Feature",
        "geometry": {"type": "Point", "coordinates": [-13.7, 9.5, 6.0]},
        "properties": {
            "parameter": {
                "ALLSKY_SFC_SW_DWN": {
                    "20210101": 5.4,
                    "20210102": 5.1,
                    "20221231": 4.8,
                    "20230101": 6.0,
                },
                "T2M": {"20210101": 27.0, "20230101": 28.0},
            }
        },
    }


# --- Clé de ville ----------------------------------------------------------


def test_cle_ville_arrondit_4_decimales() -> None:
    assert _cle_ville_offline(9.509170, -13.712220) == "9.5092_-13.7122"


# --- Tranchage du payload --------------------------------------------------


def test_trancher_selectionne_parametre_et_fenetre() -> None:
    res = _trancher_payload_offline(
        _payload_ville(),
        parameters=["ALLSKY_SFC_SW_DWN"],
        periode_debut=date(2021, 1, 1),
        periode_fin=date(2022, 12, 31),
    )
    param = res["properties"]["parameter"]
    assert set(param) == {"ALLSKY_SFC_SW_DWN"}
    # 20230101 hors fenêtre -> exclu ; les 3 autres conservés.
    assert set(param["ALLSKY_SFC_SW_DWN"]) == {"20210101", "20210102", "20221231"}


def test_trancher_parametre_absent_leve() -> None:
    with pytest.raises(RuntimeError, match="absent du seed"):
        _trancher_payload_offline(
            _payload_ville(),
            parameters=["INEXISTANT"],
            periode_debut=date(2021, 1, 1),
            periode_fin=date(2025, 12, 31),
        )


def test_trancher_conserve_les_sentinelles() -> None:
    payload = _payload_ville()
    payload["properties"]["parameter"]["ALLSKY_SFC_SW_DWN"]["20210103"] = -999.0
    res = _trancher_payload_offline(
        payload,
        parameters=["ALLSKY_SFC_SW_DWN"],
        periode_debut=date(2021, 1, 1),
        periode_fin=date(2021, 12, 31),
    )
    # La sentinelle est conservée ici (filtrée en aval, comme en live).
    assert res["properties"]["parameter"]["ALLSKY_SFC_SW_DWN"]["20210103"] == -999.0


def test_trancher_deterministe() -> None:
    payload = _payload_ville()
    a = _trancher_payload_offline(
        payload,
        parameters=["ALLSKY_SFC_SW_DWN", "T2M"],
        periode_debut=date(2021, 1, 1),
        periode_fin=date(2025, 12, 31),
    )
    b = _trancher_payload_offline(
        payload,
        parameters=["ALLSKY_SFC_SW_DWN", "T2M"],
        periode_debut=date(2021, 1, 1),
        periode_fin=date(2025, 12, 31),
    )
    assert a == b


def test_trancher_ne_mute_pas_la_source_et_preserve_les_autres_champs() -> None:
    payload = _payload_ville()
    copie = json.loads(json.dumps(payload))
    res = _trancher_payload_offline(
        payload,
        parameters=["T2M"],
        periode_debut=date(2021, 1, 1),
        periode_fin=date(2021, 12, 31),
    )
    assert payload == copie  # le seed source (caché en module) n'est jamais muté
    assert res["type"] == "Feature"  # geometry / type préservés pour le parse
    assert res["geometry"] == payload["geometry"]


# --- Aiguillage live / offline --------------------------------------------


def test_aiguillage_live_appelle_fetch_daily_raw(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("KUMA_INGESTION_MODE", raising=False)
    captures: dict[str, Any] = {}

    def faux_fetch_daily_raw(**kwargs: Any) -> dict[str, Any]:
        captures.update(kwargs)
        return {"src": "live"}

    monkeypatch.setattr(nasa_power_daily, "fetch_daily_raw", faux_fetch_daily_raw)
    res = _fetch_nasa_daily_raw(
        latitude=9.5,
        longitude=-13.7,
        parameters=["ALLSKY_SFC_SW_DWN"],
        periode_debut=date(2021, 1, 1),
        periode_fin=date(2021, 1, 2),
        httpx_client=None,
    )
    assert res == {"src": "live"}
    assert captures["parameters"] == ["ALLSKY_SFC_SW_DWN"]
    assert captures["start"] == date(2021, 1, 1)
    assert captures["end"] == date(2021, 1, 2)


def test_aiguillage_offline_charge_le_seed_sans_reseau(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("KUMA_INGESTION_MODE", "offline")
    monkeypatch.setenv("API_ENVIRONNEMENT", "dev")
    monkeypatch.setattr(
        nasa_power_daily, "_charger_payload_offline", lambda **_: {"src": "offline"}
    )

    def reseau_interdit(**_: Any) -> dict[str, Any]:
        raise AssertionError("appel réseau interdit en mode offline")

    monkeypatch.setattr(nasa_power_daily, "fetch_daily_raw", reseau_interdit)
    res = _fetch_nasa_daily_raw(
        latitude=9.5,
        longitude=-13.7,
        parameters=["ALLSKY_SFC_SW_DWN"],
        periode_debut=date(2021, 1, 1),
        periode_fin=date(2021, 1, 2),
        httpx_client=None,
    )
    assert res == {"src": "offline"}


def test_aiguillage_offline_en_prod_leve(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("KUMA_INGESTION_MODE", "offline")
    monkeypatch.setenv("API_ENVIRONNEMENT", "prod")
    with pytest.raises(RuntimeError, match="prod"):
        _fetch_nasa_daily_raw(
            latitude=9.5,
            longitude=-13.7,
            parameters=["ALLSKY_SFC_SW_DWN"],
            periode_debut=date(2021, 1, 1),
            periode_fin=date(2021, 1, 2),
            httpx_client=None,
        )
