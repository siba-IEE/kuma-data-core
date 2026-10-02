"""Tests d'intégration de ``/v1/contributions`` et de l'outil de bilan.

Régime serveur (base de service = base de test). Couvrent :

- une clé sans licence ne dépose pas de fiche (403 ``LICENCE_ABSENTE``) ;
- une clé porteuse d'une licence dépose (201), puis remplace (200) la fiche
  d'une étude : une seule ligne par étude et par clé ;
- deux clés peuvent porter le même identifiant d'étude sans se remplacer ;
- ce qui est rangé en base est la fiche validée : point arrondi, nom
  d'appareil coupé, rien d'autre ;
- le retrait supprime la fiche (204), une seconde fois répond 404, et une
  clé ne retire jamais la fiche d'une autre ;
- la licence retirée, le dépôt est refusé mais le retrait reste possible ;
- sans base de service, les deux routes répondent 404
  ``CONTRIBUTIONS_NON_ACTIVEES`` ;
- l'outil compte les fiches et les exporte sans les clés.
"""

from __future__ import annotations

import json
import uuid
from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from kuma_data_core.api.codes_erreur import CodeErreur
from kuma_data_core.core.config import get_settings
from kuma_data_core.db.meta import BaseMeta, ContributionEtude
from kuma_data_core.db.session import get_engine, get_engine_meta
from kuma_data_core.services import contributions, licences
from tests.unit.api.test_schemas_contributions import (
    fiche_exemple,
    fiche_minireseau_exemple,
    fiche_pv_champ_exemple,
)

pytestmark = pytest.mark.integration


@pytest.fixture
def serveur_contributions(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Régime serveur : base de service = base de test."""
    settings = get_settings()
    monkeypatch.setattr(settings, "meta_db", settings.postgres_db)
    BaseMeta.metadata.create_all(get_engine_meta())
    yield
    with get_engine().begin() as connexion:
        connexion.execute(text("DROP TABLE IF EXISTS contributions_etudes"))
        connexion.execute(text("DROP TABLE IF EXISTS licences_solclim"))
        connexion.execute(text("DROP TABLE IF EXISTS cles_api"))


def _cle_licenciee(client: TestClient, email: str = "ingenieure@exemple.org") -> tuple[str, str]:
    r = client.post("/v1/cles", json={"email": email})
    assert r.status_code == 201, r.text
    cle, prefixe = str(r.json()["cle"]), str(r.json()["prefixe"])
    with Session(get_engine_meta()) as session:
        licences.accorder(session, prefixe, "Aïssatou Camara", "Bureau d'études", None)
    return cle, prefixe


def _deposer(
    client: TestClient, cle: str, uid: str, corps: dict[str, Any] | None = None
) -> tuple[int, dict[str, Any]]:
    r = client.post(
        f"/v1/contributions/{uid}",
        json=corps if corps is not None else fiche_exemple(),
        headers={"Authorization": f"Bearer {cle}"},
    )
    return r.status_code, r.json()


def _retirer(client: TestClient, cle: str, uid: str) -> int:
    r = client.post(f"/v1/contributions/{uid}/retrait", headers={"Authorization": f"Bearer {cle}"})
    return r.status_code


def _fiches() -> list[ContributionEtude]:
    with Session(get_engine_meta()) as session:
        return list(session.execute(select(ContributionEtude)).scalars())


def test_cle_sans_licence_ne_depose_pas(client: TestClient, serveur_contributions: None) -> None:
    r = client.post("/v1/cles", json={"email": "sans-licence@exemple.org"})
    statut, corps = _deposer(client, str(r.json()["cle"]), str(uuid.uuid4()))
    assert statut == 403
    assert corps["erreur"]["code"] == CodeErreur.LICENCE_ABSENTE.value
    assert _fiches() == []


def test_depot_puis_remplacement(client: TestClient, serveur_contributions: None) -> None:
    cle, _ = _cle_licenciee(client)
    uid = str(uuid.uuid4())
    statut, corps = _deposer(client, cle, uid)
    assert statut == 201, corps
    assert corps["nombre_envois"] == 1

    modifiee = fiche_exemple()
    modifiee["fiche"]["systeme"]["jours_autonomie"] = 3
    statut, corps = _deposer(client, cle, uid, modifiee)
    assert statut == 200, corps
    assert corps["nombre_envois"] == 2
    assert corps["recue_le"] < corps["mise_a_jour_le"]

    fiches = _fiches()
    assert len(fiches) == 1
    assert fiches[0].fiche["systeme"]["jours_autonomie"] == 3
    assert fiches[0].version_logiciel == "1.1.0"
    assert fiches[0].format_fiche == "pv-autonome@1"


def test_meme_etude_deux_cles_deux_fiches(client: TestClient, serveur_contributions: None) -> None:
    cle_a, _ = _cle_licenciee(client, "a@exemple.org")
    cle_b, _ = _cle_licenciee(client, "b@exemple.org")
    uid = str(uuid.uuid4())
    assert _deposer(client, cle_a, uid)[0] == 201
    assert _deposer(client, cle_b, uid)[0] == 201
    assert len(_fiches()) == 2


def test_la_base_ne_garde_que_la_fiche_validee(
    client: TestClient, serveur_contributions: None
) -> None:
    cle, _ = _cle_licenciee(client)
    corps = fiche_exemple()
    corps["fiche"]["lieu"] = {"point": {"latitude_deg": 7.77691, "longitude_deg": -9.18612}}
    corps["fiche"]["appareils"][0]["nom"] = "Réfrigérateur de la boutique " * 3
    assert _deposer(client, cle, str(uuid.uuid4()), corps)[0] == 201
    fiche = _fiches()[0].fiche
    assert fiche["lieu"]["point"] == {"latitude_deg": 7.8, "longitude_deg": -9.2}
    assert fiche["lieu"]["sous_prefecture"] is None
    assert len(fiche["appareils"][0]["nom"]) <= 40


def test_champ_hors_contrat_refuse_et_rien_n_est_range(
    client: TestClient, serveur_contributions: None
) -> None:
    cle, _ = _cle_licenciee(client)
    corps = fiche_exemple()
    corps["fiche"]["nom_etude"] = "Habitation Camara"
    statut, _ = _deposer(client, cle, str(uuid.uuid4()), corps)
    assert statut == 422
    assert _fiches() == []


def test_identifiant_d_etude_controle(client: TestClient, serveur_contributions: None) -> None:
    cle, _ = _cle_licenciee(client)
    assert _deposer(client, cle, "habitation-camara")[0] == 422


def test_retrait(client: TestClient, serveur_contributions: None) -> None:
    cle, _ = _cle_licenciee(client)
    uid = str(uuid.uuid4())
    _deposer(client, cle, uid)
    assert _retirer(client, cle, uid) == 204
    assert _fiches() == []
    assert _retirer(client, cle, uid) == 404


def test_une_cle_ne_retire_pas_la_fiche_d_une_autre(
    client: TestClient, serveur_contributions: None
) -> None:
    cle_a, _ = _cle_licenciee(client, "a@exemple.org")
    cle_b, _ = _cle_licenciee(client, "b@exemple.org")
    uid = str(uuid.uuid4())
    _deposer(client, cle_a, uid)
    assert _retirer(client, cle_b, uid) == 404
    assert len(_fiches()) == 1


def test_licence_retiree_le_retrait_reste_possible(
    client: TestClient, serveur_contributions: None
) -> None:
    cle, prefixe = _cle_licenciee(client)
    uid = str(uuid.uuid4())
    _deposer(client, cle, uid)
    with Session(get_engine_meta()) as session:
        licences.retirer(session, prefixe)
    statut, corps = _deposer(client, cle, uid)
    assert statut == 403
    assert corps["erreur"]["code"] == CodeErreur.LICENCE_ABSENTE.value
    assert _retirer(client, cle, uid) == 204


def test_sans_base_de_service(client: TestClient) -> None:
    uid = str(uuid.uuid4())
    entetes = {"Authorization": "Bearer test_cle_admin_yyyyyyyy"}
    r = client.post(f"/v1/contributions/{uid}", json=fiche_exemple(), headers=entetes)
    assert r.status_code == 404
    assert r.json()["erreur"]["code"] == CodeErreur.CONTRIBUTIONS_NON_ACTIVEES.value
    r = client.post(f"/v1/contributions/{uid}/retrait", headers=entetes)
    assert r.status_code == 404
    assert r.json()["erreur"]["code"] == CodeErreur.CONTRIBUTIONS_NON_ACTIVEES.value


def test_outil_bilan_et_export(
    client: TestClient,
    serveur_contributions: None,
    capsys: pytest.CaptureFixture[str],
) -> None:
    cle, prefixe = _cle_licenciee(client)
    _deposer(client, cle, str(uuid.uuid4()))
    _deposer(client, cle, str(uuid.uuid4()))

    assert contributions.principal(["bilan"]) == 0
    assert "pv-autonome  2 fiche(s)  1 contributeur(s)" in capsys.readouterr().out

    assert contributions.principal(["exporter", "--module", "pv-autonome"]) == 0
    lignes = capsys.readouterr().out.strip().splitlines()
    assert len(lignes) == 2
    premiere = json.loads(lignes[0])
    assert premiere["fiche"]["logiciel"]["version"] == "1.1.0"
    assert prefixe not in lignes[0]
    assert cle not in lignes[0]


def test_les_trois_modules_cote_a_cote(
    client: TestClient,
    serveur_contributions: None,
    capsys: pytest.CaptureFixture[str],
) -> None:
    cle, _ = _cle_licenciee(client)
    assert _deposer(client, cle, str(uuid.uuid4()))[0] == 201
    assert _deposer(client, cle, str(uuid.uuid4()), fiche_minireseau_exemple())[0] == 201
    assert _deposer(client, cle, str(uuid.uuid4()), fiche_pv_champ_exemple())[0] == 201

    par_module = {f.module: f for f in _fiches()}
    assert sorted(par_module) == ["minireseau", "pv-autonome", "pv-champ"]
    assert par_module["pv-champ"].fiche["module"]["puissance_crete_w"] == 550
    mini = par_module["minireseau"]
    assert mini.format_fiche == "minireseau@1"
    assert mini.fiche["lieu"]["point"] == {"latitude_deg": 7.8, "longitude_deg": -9.2}
    assert len(mini.fiche["charge"]["postes"][0]["profil_24"]) == 24

    assert contributions.principal(["bilan"]) == 0
    sortie = capsys.readouterr().out
    assert "minireseau  1 fiche(s)" in sortie
    assert "pv-autonome  1 fiche(s)" in sortie
    assert "pv-champ  1 fiche(s)" in sortie
