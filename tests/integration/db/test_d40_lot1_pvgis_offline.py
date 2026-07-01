"""Tests d'integration : chemin offline PVGIS-SARAH3.

Verifie que ``KUMA_INGESTION_MODE=offline`` :

- renvoie le payload committe **sans aucun appel reseau** (client httpx garde
  qui leve s'il est sollicite) ;
- reproduit **exactement** les 216 lignes SARAH-3 deja en base (fidelite, pas
  de recalage des TI) ;
- est deterministe ;
- et que le canari de derive (``ecart_relatif_max_sarah3``) detecte un ecart.
"""

from __future__ import annotations

import httpx
import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

from kuma_data_core.db.seeds.localites_seed_data import LOCALITES_SEED
from kuma_data_core.ingestion.sarah3_monthly import (
    _extraire_valeurs_mensuelles,
    _fetch_sarah3_monthly_raw,
    ecart_relatif_max_sarah3,
)

pytestmark = pytest.mark.integration

_VILLES: tuple[tuple[str, str], ...] = (
    ("gin_conakry_kaloum", "gin_conakry_ghi_sarah3_2021_2023"),
    ("gin_kankan", "gin_kankan_ghi_sarah3_2021_2023"),
    ("gin_kindia", "gin_kindia_ghi_sarah3_2021_2023"),
    ("gin_labe", "gin_labe_ghi_sarah3_2021_2023"),
    ("gin_mamou", "gin_mamou_ghi_sarah3_2021_2023"),
    ("gin_nzerekore", "gin_nzerekore_ghi_sarah3_2021_2023"),
)
_IDX = {e["code"]: e for e in LOCALITES_SEED}


def _coords(code: str) -> tuple[float, float]:
    e = _IDX[code]
    return float(e["latitude"]), float(e["longitude"])


def _client_garde() -> httpx.Client:
    """Client httpx qui lève si on tente un appel réseau (preuve 0-réseau)."""

    def _interdit(request: httpx.Request) -> httpx.Response:
        raise AssertionError(f"Appel reseau interdit en mode offline : {request.url}")

    return httpx.Client(transport=httpx.MockTransport(_interdit))


def _payload_offline(code: str, garde: httpx.Client) -> dict[str, object]:
    lat, lon = _coords(code)
    return _fetch_sarah3_monthly_raw(
        latitude=lat,
        longitude=lon,
        annee_debut=2021,
        annee_fin=2023,
        timeout=1.0,
        httpx_client=garde,
    )


def test_offline_renvoie_seed_sans_reseau(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("KUMA_INGESTION_MODE", "offline")
    monkeypatch.setenv("API_ENVIRONNEMENT", "dev")
    with _client_garde() as garde:
        payload = _payload_offline("gin_conakry_kaloum", garde)
    monthly = payload["outputs"]["monthly"]  # type: ignore[index]
    assert len(monthly) == 36  # 3 ans x 12 mois, aucun appel reseau


def test_offline_deterministe(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("KUMA_INGESTION_MODE", "offline")
    monkeypatch.setenv("API_ENVIRONNEMENT", "dev")
    with _client_garde() as garde:
        p1 = _extraire_valeurs_mensuelles(_payload_offline("gin_labe", garde))
        p2 = _extraire_valeurs_mensuelles(_payload_offline("gin_labe", garde))
    assert p1 == p2


def test_fidelite_seed_vs_db(db_session: Session, monkeypatch: pytest.MonkeyPatch) -> None:
    """Le seed offline reproduit exactement les 216 lignes SARAH-3 en base."""
    monkeypatch.setenv("KUMA_INGESTION_MODE", "offline")
    monkeypatch.setenv("API_ENVIRONNEMENT", "dev")
    total = 0
    with _client_garde() as garde:
        for code, serie in _VILLES:
            seed_vals = {
                (a, m): v for a, m, v in _extraire_valeurs_mensuelles(_payload_offline(code, garde))
            }
            db_vals = {
                (int(r.annee), int(r.mois)): float(r.valeur)
                for r in db_session.execute(
                    text(
                        "SELECT m.annee, m.mois, m.valeur FROM mesures_ressource_mensuelles m "
                        "JOIN series_metadonnees sm ON sm.id = m.serie_id WHERE sm.code = :s"
                    ),
                    {"s": serie},
                ).all()
            }
            assert seed_vals.keys() == db_vals.keys(), f"{code}: mois divergents"
            for cle in db_vals:
                assert abs(seed_vals[cle] - db_vals[cle]) < 1e-9, f"{code} {cle}: valeur divergente"
            total += len(db_vals)
    assert total == 216


def _payload_synthetique(facteur: float) -> dict[str, object]:
    monthly = [{"year": 2021, "month": m, "H(h)_m": (150.0 + m) * facteur} for m in range(1, 13)]
    return {"outputs": {"monthly": monthly}}


def test_canari_detecte_derive() -> None:
    """Canari : écart nul sur payload identique, > seuil sur perturbation (re-seed)."""
    base = _payload_synthetique(1.0)
    assert ecart_relatif_max_sarah3(base, base) == 0.0
    assert ecart_relatif_max_sarah3(_payload_synthetique(1.05), base) > 1e-3  # +5 %
