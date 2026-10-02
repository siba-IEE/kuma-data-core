"""Bail d'usage de SolClim-3 : charge, signature Ed25519, vérification.

Le bail est ce que le logiciel garde sur le poste pour travailler hors
ligne : il dit à qui il est accordé et jusqu'à quand. Il est **signé** par
le serveur avec une clé privée Ed25519 que seul le serveur détient ; le
logiciel et le service de calage le vérifient avec la clé publique, sans
appeler le serveur. Un bail modifié sur le poste ne se vérifie plus.

Forme transportée (JSON) :

- ``charge`` : la charge utile, JSON canonique (clés triées, séparateurs
  compacts) encodé en base64url sans remplissage ;
- ``signature`` : la signature Ed25519 des **octets** de la charge, en
  base64url sans remplissage.

On signe les octets transportés, pas un objet re-sérialisé : le
vérificateur n'a pas à reproduire une sérialisation, il décode, vérifie,
puis lit le JSON.
"""

from __future__ import annotations

import base64
import binascii
import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)

from kuma_data_core.exceptions import KumaError

VERSION_BAIL = 1
PRODUIT = "solclim3"


class BailInvalideError(KumaError):
    """Bail mal formé ou dont la signature ne se vérifie pas."""


@dataclass(frozen=True)
class Bail:
    """Un bail signé, prêt à transporter."""

    charge: str
    signature: str


def _b64url(octets: bytes) -> str:
    return base64.urlsafe_b64encode(octets).rstrip(b"=").decode("ascii")


def _de_b64url(texte: str) -> bytes:
    remplissage = "=" * (-len(texte) % 4)
    try:
        return base64.urlsafe_b64decode(texte + remplissage)
    except (binascii.Error, ValueError) as erreur:
        raise BailInvalideError("encodage base64url invalide") from erreur


def charger_cle_privee(graine_b64: str) -> Ed25519PrivateKey:
    """Clé privée depuis sa graine de 32 octets en base64 (variable d'environnement)."""
    try:
        graine = base64.b64decode(graine_b64, validate=True)
    except (binascii.Error, ValueError) as erreur:
        raise ValueError("LICENCE_CLE_SIGNATURE : base64 invalide") from erreur
    if len(graine) != 32:
        raise ValueError("LICENCE_CLE_SIGNATURE : la graine Ed25519 fait 32 octets")
    return Ed25519PrivateKey.from_private_bytes(graine)


def charger_cle_publique(publique_b64: str) -> Ed25519PublicKey:
    """Clé publique depuis ses 32 octets en base64 (celle qu'on embarque)."""
    try:
        octets = base64.b64decode(publique_b64, validate=True)
    except (binascii.Error, ValueError) as erreur:
        raise ValueError("clé publique : base64 invalide") from erreur
    if len(octets) != 32:
        raise ValueError("clé publique : une clé Ed25519 fait 32 octets")
    return Ed25519PublicKey.from_public_bytes(octets)


def cle_publique_b64(privee: Ed25519PrivateKey) -> str:
    """Les 32 octets bruts de la clé publique, en base64 : à embarquer."""
    octets = privee.public_key().public_bytes(
        encoding=serialization.Encoding.Raw, format=serialization.PublicFormat.Raw
    )
    return base64.b64encode(octets).decode("ascii")


def generer_paire() -> tuple[str, str]:
    """Nouvelle paire : ``(graine privée base64, clé publique base64)``."""
    privee = Ed25519PrivateKey.generate()
    graine = privee.private_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PrivateFormat.Raw,
        encryption_algorithm=serialization.NoEncryption(),
    )
    return base64.b64encode(graine).decode("ascii"), cle_publique_b64(privee)


def _horodatage(instant: datetime) -> str:
    """ISO 8601 en UTC à la seconde, suffixe ``Z`` : lisible partout, sans fuseau ambigu."""
    return instant.astimezone(UTC).replace(microsecond=0).strftime("%Y-%m-%dT%H:%M:%SZ")


def construire_charge(
    *,
    prefixe_cle: str,
    titulaire: str,
    organisation: str | None,
    fin_licence: datetime | None,
    maintenant: datetime,
    duree: timedelta,
    version_minimale: str,
) -> dict[str, Any]:
    """La charge du bail : à qui, depuis quand, jusqu'à quand.

    La fin du bail est la durée nominale, sans jamais dépasser la fin de la
    licence quand elle en a une.
    """
    fin = maintenant + duree
    if fin_licence is not None and fin_licence < fin:
        fin = fin_licence
    return {
        "version": VERSION_BAIL,
        "produit": PRODUIT,
        "prefixe_cle": prefixe_cle,
        "titulaire": titulaire,
        "organisation": organisation,
        "emis_le": _horodatage(maintenant),
        "expire_le": _horodatage(fin),
        "version_minimale": version_minimale,
    }


def signer(charge: dict[str, Any], privee: Ed25519PrivateKey) -> Bail:
    """Signe la charge sérialisée en JSON canonique."""
    octets = json.dumps(charge, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode(
        "utf-8"
    )
    return Bail(charge=_b64url(octets), signature=_b64url(privee.sign(octets)))


def verifier(bail: Bail, publique: Ed25519PublicKey) -> dict[str, Any]:
    """Vérifie la signature et rend la charge ; lève ``BailInvalideError`` sinon.

    Ne juge pas l'expiration : c'est au lecteur de comparer ``expire_le`` à
    son horloge, selon sa propre politique (le logiciel, le calage).
    """
    octets = _de_b64url(bail.charge)
    try:
        publique.verify(_de_b64url(bail.signature), octets)
    except InvalidSignature as erreur:
        raise BailInvalideError("signature invalide") from erreur
    try:
        charge = json.loads(octets.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as erreur:
        raise BailInvalideError("charge illisible") from erreur
    if not isinstance(charge, dict):
        raise BailInvalideError("charge illisible")
    return charge
