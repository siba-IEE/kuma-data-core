"""Schémas Pydantic de ``POST /v1/licence/bail`` (licences SolClim-3)."""

from __future__ import annotations

from pydantic import BaseModel, Field


class ReponseBail(BaseModel):
    """Le bail signé, et de quoi l'afficher sans le décoder."""

    charge: str = Field(
        description=(
            "Charge du bail : JSON canonique (titulaire, organisation, "
            "préfixe de clé, émis le, expire le, version minimale) encodé "
            "en base64url sans remplissage."
        )
    )
    signature: str = Field(
        description="Signature Ed25519 des octets de la charge, en base64url sans remplissage."
    )
    titulaire: str = Field(description="Titulaire de la licence, en clair.")
    expire_le: str = Field(description="Fin du bail, ISO 8601 UTC (suffixe Z).")
