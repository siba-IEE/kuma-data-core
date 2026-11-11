"""Plafond de débit par adresse, appliqué avant l'authentification."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from kuma_data_core.api.codes_erreur import CodeErreur
from kuma_data_core.api.dependencies import identite_reseau, limiter_debit_par_ip
from kuma_data_core.api.erreurs import ExceptionKuma
from kuma_data_core.core.config import get_settings
from kuma_data_core.services import quotas

pytestmark = pytest.mark.unit


class FauxRedis:
    def __init__(self) -> None:
        self.valeurs: dict[str, int] = {}

    def incr(self, cle: str) -> int:
        self.valeurs[cle] = self.valeurs.get(cle, 0) + 1
        return self.valeurs[cle]

    def expire(self, cle: str, secondes: int) -> None:
        pass


def _requete(ip: str) -> SimpleNamespace:
    return SimpleNamespace(client=SimpleNamespace(host=ip), headers={})


@pytest.fixture
def faux_redis(monkeypatch: pytest.MonkeyPatch) -> FauxRedis:
    faux = FauxRedis()
    monkeypatch.setattr(quotas, "obtenir_client", lambda: faux)
    monkeypatch.setattr(get_settings(), "rate_limiting_actif", True)
    monkeypatch.setattr(get_settings(), "debit_ip_par_minute", 2)
    monkeypatch.setattr(get_settings(), "derriere_proxy_confiance", False)
    return faux


@pytest.mark.parametrize(
    ("adresse", "attendu"),
    [
        ("203.0.113.7", "203.0.113.7"),
        ("2001:db8:1:2:aaaa:bbbb:cccc:dddd", "2001:db8:1:2::/64"),
        ("2001:db8:1:2::1", "2001:db8:1:2::/64"),
        ("::ffff:203.0.113.7", "203.0.113.7"),
        ("inconnue", "inconnue"),
    ],
)
def test_identite_reseau(adresse: str, attendu: str) -> None:
    assert identite_reseau(adresse) == attendu


def test_refus_au_dela_du_plafond(faux_redis: FauxRedis) -> None:
    requete = _requete("203.0.113.7")
    limiter_debit_par_ip(requete, authorization=None)  # type: ignore[arg-type]
    limiter_debit_par_ip(requete, authorization="Bearer inconnue")  # type: ignore[arg-type]
    with pytest.raises(ExceptionKuma) as info:
        limiter_debit_par_ip(requete, authorization=None)  # type: ignore[arg-type]
    assert info.value.code is CodeErreur.DEBIT_DEPASSE
    assert info.value.statut_http == 429


def test_adresses_ipv6_du_meme_reseau_partagent_le_compteur(faux_redis: FauxRedis) -> None:
    limiter_debit_par_ip(_requete("2001:db8:1:2::1"), authorization=None)  # type: ignore[arg-type]
    limiter_debit_par_ip(_requete("2001:db8:1:2::2"), authorization=None)  # type: ignore[arg-type]
    assert list(faux_redis.valeurs.values()) == [2]


def test_cle_d_environnement_exemptee(faux_redis: FauxRedis, cle_solar_valide: str) -> None:
    for _ in range(5):
        limiter_debit_par_ip(
            _requete("203.0.113.7"),  # type: ignore[arg-type]
            authorization=f"Bearer {cle_solar_valide}",
        )
    assert faux_redis.valeurs == {}


def test_inactif_hors_profil_serveur(
    faux_redis: FauxRedis, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(get_settings(), "rate_limiting_actif", False)
    for _ in range(5):
        limiter_debit_par_ip(_requete("203.0.113.7"), authorization=None)  # type: ignore[arg-type]
    assert faux_redis.valeurs == {}
