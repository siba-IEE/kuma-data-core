"""Tests d'intégration de ``POST /v1/licence/bail`` et de l'outil de licences.

Régime serveur (base de service = base de test, ``cles_api`` et
``licences_solclim`` créées par ``BaseMeta``) et graine de signature de
test. Couvrent :

- une clé sans licence n'obtient pas de bail (403 ``LICENCE_ABSENTE``) ;
- une licence accordée ouvre un bail qui se vérifie avec la clé publique,
  porte le titulaire et dure 30 jours ;
- le terme de la licence plafonne le bail ; une licence échue ne l'ouvre
  plus ;
- retirer la licence tarit le bail, la clé continue d'ouvrir l'API ;
- révoquer la clé coupe tout (401) ;
- la clé d'environnement partagée n'a pas de bail ;
- sans base de service ou sans graine, l'émission répond 404
  ``LICENCE_NON_ACTIVEE`` ;
- l'outil en ligne de commande accorde, liste et retire.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy import text
from sqlalchemy.orm import Session

from kuma_data_core.api.codes_erreur import CodeErreur
from kuma_data_core.core.config import get_settings
from kuma_data_core.db.meta import BaseMeta
from kuma_data_core.db.session import get_engine, get_engine_meta
from kuma_data_core.services import licences
from kuma_data_core.services.bail import (
    Bail,
    charger_cle_publique,
    generer_paire,
    verifier,
)

pytestmark = pytest.mark.integration

GRAINE, PUBLIQUE = generer_paire()
ADMIN = {"Authorization": "Bearer test_cle_admin_yyyyyyyy"}


@pytest.fixture
def serveur_licences(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Régime serveur avec base de service et graine de signature de test."""
    settings = get_settings()
    monkeypatch.setattr(settings, "meta_db", settings.postgres_db)
    monkeypatch.setattr(settings, "licence_cle_signature", SecretStr(GRAINE))
    BaseMeta.metadata.create_all(get_engine_meta())
    yield
    with get_engine().begin() as connexion:
        connexion.execute(text("DROP TABLE IF EXISTS contributions_etudes"))
        connexion.execute(text("DROP TABLE IF EXISTS licences_solclim"))
        connexion.execute(text("DROP TABLE IF EXISTS cles_api"))


def _emettre_cle(client: TestClient) -> tuple[str, str]:
    r = client.post("/v1/cles", json={"email": "ingenieure@exemple.org"})
    assert r.status_code == 201, r.text
    corps = r.json()
    return str(corps["cle"]), str(corps["prefixe"])


def _bail(client: TestClient, cle: str) -> tuple[int, dict[str, object]]:
    r = client.post("/v1/licence/bail", headers={"Authorization": f"Bearer {cle}"})
    return r.status_code, r.json()


def _accorder(prefixe: str, expire_le: datetime | None = None) -> None:
    with Session(get_engine_meta()) as session:
        licences.accorder(
            session, prefixe, "Aïssatou Camara", "Bureau d'études de Kankan", expire_le
        )


def test_cle_sans_licence_sans_bail(client: TestClient, serveur_licences: None) -> None:
    cle, _ = _emettre_cle(client)
    statut, corps = _bail(client, cle)
    assert statut == 403
    assert corps["erreur"]["code"] == CodeErreur.LICENCE_ABSENTE.value  # type: ignore[index]


def test_licence_ouvre_un_bail_verifiable(client: TestClient, serveur_licences: None) -> None:
    cle, prefixe = _emettre_cle(client)
    _accorder(prefixe)
    statut, corps = _bail(client, cle)
    assert statut == 200, corps
    charge = verifier(
        Bail(charge=str(corps["charge"]), signature=str(corps["signature"])),
        charger_cle_publique(PUBLIQUE),
    )
    assert charge["titulaire"] == "Aïssatou Camara"
    assert charge["organisation"] == "Bureau d'études de Kankan"
    assert charge["prefixe_cle"] == prefixe
    assert corps["expire_le"] == charge["expire_le"]
    emis = datetime.fromisoformat(str(charge["emis_le"]))
    fin = datetime.fromisoformat(str(charge["expire_le"]))
    assert fin - emis == timedelta(days=30)


def test_dernier_bail_est_note(client: TestClient, serveur_licences: None) -> None:
    cle, prefixe = _emettre_cle(client)
    _accorder(prefixe)
    _bail(client, cle)
    with Session(get_engine_meta()) as session:
        ((licence, _),) = licences.lister(session)
        assert licence.dernier_bail_le is not None


def test_terme_de_licence_plafonne_le_bail(client: TestClient, serveur_licences: None) -> None:
    cle, prefixe = _emettre_cle(client)
    fin = datetime.now(tz=UTC).replace(microsecond=0) + timedelta(days=5)
    _accorder(prefixe, fin)
    _, corps = _bail(client, cle)
    assert datetime.fromisoformat(str(corps["expire_le"])) == fin


def test_licence_echue_sans_bail(client: TestClient, serveur_licences: None) -> None:
    cle, prefixe = _emettre_cle(client)
    _accorder(prefixe, datetime.now(tz=UTC) - timedelta(days=1))
    statut, _ = _bail(client, cle)
    assert statut == 403


def test_retrait_tarit_le_bail_sans_couper_la_cle(
    client: TestClient, serveur_licences: None
) -> None:
    cle, prefixe = _emettre_cle(client)
    _accorder(prefixe)
    with Session(get_engine_meta()) as session:
        assert licences.retirer(session, prefixe) == 1
    statut, _ = _bail(client, cle)
    assert statut == 403
    r = client.get("/v1/localites", headers={"Authorization": f"Bearer {cle}"})
    assert r.status_code == 200


def test_revocation_de_la_cle_coupe_tout(client: TestClient, serveur_licences: None) -> None:
    cle, prefixe = _emettre_cle(client)
    _accorder(prefixe)
    r = client.delete(f"/v1/cles/{prefixe}", headers=ADMIN)
    assert r.status_code == 200
    statut, _ = _bail(client, cle)
    assert statut == 401


def test_cle_partagee_sans_bail(client: TestClient, serveur_licences: None) -> None:
    statut, corps = _bail(client, "test_cle_solar_xxxxxxxx")
    assert statut == 403
    assert corps["erreur"]["code"] == CodeErreur.LICENCE_ABSENTE.value  # type: ignore[index]


def test_une_seule_licence_active_par_cle(client: TestClient, serveur_licences: None) -> None:
    _, prefixe = _emettre_cle(client)
    _accorder(prefixe)
    with pytest.raises(licences.LicenceError, match="déjà une licence active"):
        _accorder(prefixe)


def test_sans_graine_pas_de_bail(
    client: TestClient, serveur_licences: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    cle, prefixe = _emettre_cle(client)
    _accorder(prefixe)
    monkeypatch.setattr(get_settings(), "licence_cle_signature", None)
    statut, corps = _bail(client, cle)
    assert statut == 404
    assert corps["erreur"]["code"] == CodeErreur.LICENCE_NON_ACTIVEE.value  # type: ignore[index]


def test_graine_vide_vaut_absence(
    client: TestClient, serveur_licences: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """``LICENCE_CLE_SIGNATURE=`` (présente mais vide) : 404, jamais 500."""
    cle, prefixe = _emettre_cle(client)
    _accorder(prefixe)
    monkeypatch.setattr(get_settings(), "licence_cle_signature", SecretStr(""))
    statut, _ = _bail(client, cle)
    assert statut == 404


def test_sans_base_de_service_pas_de_bail(client: TestClient) -> None:
    statut, corps = _bail(client, "test_cle_solar_xxxxxxxx")
    assert statut == 404
    assert corps["erreur"]["code"] == CodeErreur.LICENCE_NON_ACTIVEE.value  # type: ignore[index]


def test_outil_accorde_liste_retire(
    client: TestClient, serveur_licences: None, capsys: pytest.CaptureFixture[str]
) -> None:
    _, prefixe = _emettre_cle(client)
    code = licences.principal(
        ["accorder", prefixe, "--titulaire", "Mamadou Bah", "--expire", "2027-12-31"]
    )
    assert code == 0
    assert licences.principal(["lister"]) == 0
    sortie = capsys.readouterr().out
    assert "Mamadou Bah" in sortie and "2027-12-31" in sortie
    assert licences.principal(["retirer", prefixe]) == 0
    assert licences.principal(["retirer", prefixe]) == 1
