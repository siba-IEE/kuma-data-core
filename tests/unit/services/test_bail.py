"""Tests unitaires du bail SolClim-3 (signature Ed25519, sans base).

Couvrent :

1. Aller-retour : un bail signé se vérifie avec la clé publique et rend
   la charge à l'identique.
2. Intégrité : une charge ou une signature altérée ne se vérifie plus, ni
   avec une autre clé publique.
3. Terme : la fin du bail est la durée nominale, plafonnée par la fin de
   la licence quand elle est plus proche.
4. Clés : graine et clé publique se rechargent depuis leur base64, une
   longueur fausse est refusée.
"""

from __future__ import annotations

import base64
import json
from datetime import UTC, datetime, timedelta

import pytest

from kuma_data_core.services.bail import (
    PRODUIT,
    VERSION_BAIL,
    Bail,
    BailInvalideError,
    charger_cle_privee,
    charger_cle_publique,
    construire_charge,
    generer_paire,
    signer,
    verifier,
)

pytestmark = pytest.mark.unit

MAINTENANT = datetime(2026, 10, 1, 12, 30, 45, 123456, tzinfo=UTC)


def _charge(fin_licence: datetime | None = None) -> dict[str, object]:
    return construire_charge(
        prefixe_cle="kuma_AbCdEfGh",
        titulaire="Aïssatou Camara",
        organisation="Bureau d'études de Kankan",
        fin_licence=fin_licence,
        maintenant=MAINTENANT,
        duree=timedelta(days=30),
        version_minimale="1.1.0",
    )


def test_aller_retour_signature() -> None:
    graine, publique = generer_paire()
    bail = signer(_charge(), charger_cle_privee(graine))
    assert verifier(bail, charger_cle_publique(publique)) == _charge()


def test_charge_porte_le_contrat() -> None:
    charge = _charge()
    assert charge["version"] == VERSION_BAIL
    assert charge["produit"] == PRODUIT
    assert charge["prefixe_cle"] == "kuma_AbCdEfGh"
    assert charge["titulaire"] == "Aïssatou Camara"
    assert charge["emis_le"] == "2026-10-01T12:30:45Z"
    assert charge["expire_le"] == "2026-10-31T12:30:45Z"
    assert charge["version_minimale"] == "1.1.0"


def test_charge_transportee_en_json_canonique() -> None:
    graine, _ = generer_paire()
    bail = signer(_charge(), charger_cle_privee(graine))
    octets = base64.urlsafe_b64decode(bail.charge + "=" * (-len(bail.charge) % 4))
    assert octets == json.dumps(
        _charge(), ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    assert "=" not in bail.charge and "=" not in bail.signature


def test_charge_alteree_refusee() -> None:
    graine, publique = generer_paire()
    bail = signer(_charge(), charger_cle_privee(graine))
    falsifiee = dict(_charge(), expire_le="2099-12-31T00:00:00Z")
    autre = signer(falsifiee, charger_cle_privee(generer_paire()[0]))
    with pytest.raises(BailInvalideError):
        verifier(
            Bail(charge=autre.charge, signature=bail.signature), charger_cle_publique(publique)
        )


def test_signature_alteree_refusee() -> None:
    graine, publique = generer_paire()
    bail = signer(_charge(), charger_cle_privee(graine))
    signature = bytearray(base64.urlsafe_b64decode(bail.signature + "=="))
    signature[0] ^= 0x01
    alteree = base64.urlsafe_b64encode(bytes(signature)).rstrip(b"=").decode("ascii")
    with pytest.raises(BailInvalideError):
        verifier(Bail(charge=bail.charge, signature=alteree), charger_cle_publique(publique))


def test_autre_cle_publique_refusee() -> None:
    graine, _ = generer_paire()
    _, autre_publique = generer_paire()
    bail = signer(_charge(), charger_cle_privee(graine))
    with pytest.raises(BailInvalideError):
        verifier(bail, charger_cle_publique(autre_publique))


def test_terme_plafonne_par_la_licence() -> None:
    fin_proche = MAINTENANT + timedelta(days=10)
    assert _charge(fin_proche)["expire_le"] == "2026-10-11T12:30:45Z"


def test_licence_lointaine_ne_prolonge_pas_le_bail() -> None:
    fin_lointaine = MAINTENANT + timedelta(days=400)
    assert _charge(fin_lointaine)["expire_le"] == "2026-10-31T12:30:45Z"


def test_graine_de_mauvaise_longueur_refusee() -> None:
    with pytest.raises(ValueError, match="32 octets"):
        charger_cle_privee(base64.b64encode(b"trop court").decode("ascii"))


def test_graine_non_base64_refusee() -> None:
    with pytest.raises(ValueError, match="base64"):
        charger_cle_privee("pas du base64 !")


def test_encodage_casse_refuse() -> None:
    graine, publique = generer_paire()
    bail = signer(_charge(), charger_cle_privee(graine))
    with pytest.raises(BailInvalideError):
        verifier(Bail(charge="@@@", signature=bail.signature), charger_cle_publique(publique))
