"""Schémas Pydantic des contributions d'études SolClim-3 (ADR-0006).

La fiche est le contrat de ce qui quitte le poste de l'utilisateur. Elle est
validée **strictement** : un champ que le contrat ne nomme pas est refusé
(422), si bien qu'une version du logiciel qui enverrait plus que convenu
(le nom de l'étude, un chemin, des coordonnées exactes) échoue au lieu de
fuir. Deux garanties sont reprises côté serveur, quoi qu'envoie le client :
le point saisi est arrondi à 0,1° (environ 11 km), et le nom d'un appareil
est coupé à 40 caractères.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

#: Longueur conservée du nom d'un appareil (texte libre saisi par l'utilisateur).
LONGUEUR_NOM_APPAREIL = 40

#: Pas de l'arrondi d'un point saisi, en degrés (environ 11 km).
DECIMALES_POINT = 1


class _Strict(BaseModel):
    """Refuse tout champ que le contrat ne nomme pas."""

    model_config = ConfigDict(extra="forbid")


class Logiciel(_Strict):
    version: str = Field(min_length=1, max_length=32, description="Version de SolClim-3.")
    enregistre_le: date = Field(description="Jour de l'enregistrement de l'étude.")


class Point(_Strict):
    """Un point saisi à la main, arrondi : il situe sans identifier."""

    latitude_deg: float = Field(ge=-90, le=90)
    longitude_deg: float = Field(ge=-180, le=180)

    @field_validator("latitude_deg", "longitude_deg")
    @classmethod
    def _arrondir(cls, valeur: float) -> float:
        return round(valeur, DECIMALES_POINT)


class Lieu(_Strict):
    """La sous-préfecture choisie dans la base, ou à défaut le point arrondi."""

    sous_prefecture: str | None = Field(
        default=None, pattern=r"^GN\d{8}$", description="Code de la sous-préfecture (pcode)."
    )
    point: Point | None = None

    @model_validator(mode="after")
    def _un_seul(self) -> Lieu:
        if (self.sous_prefecture is None) == (self.point is None):
            raise ValueError("le lieu est une sous-préfecture ou un point, l'un des deux")
        return self


class Panneaux(_Strict):
    inclinaison_deg: float = Field(ge=0, le=90)
    orientation_deg: float = Field(ge=-180, le=360)
    module_wc: float = Field(gt=0, le=2000, description="Puissance crête d'un module.")


class Ressource(_Strict):
    mode: Literal["brut", "cale"]
    version_base: str | None = Field(
        default=None, max_length=64, description="Version de la base de sous-préfectures."
    )


class Appareil(_Strict):
    nom: str = Field(max_length=200)
    puissance_w: float = Field(ge=0, le=1_000_000)
    heures_par_jour: float = Field(ge=0, le=24)
    quantite: float = Field(ge=0, le=10_000)
    moment: Literal["jour", "soir", "jour_nuit"]

    @field_validator("nom")
    @classmethod
    def _couper(cls, valeur: str) -> str:
        return valeur.strip()[:LONGUEUR_NOM_APPAREIL].strip()


class Systeme(_Strict):
    jours_autonomie: float = Field(ge=0, le=30)
    batterie: Literal["lithium", "plomb"]


class Prix(_Strict):
    """Les prix saisis par l'utilisateur, dans la monnaie de l'étude."""

    monnaie: Literal["GNF", "USD", "EUR", "XOF"]
    kwc_installe: float = Field(ge=0)
    kwh_batterie: float = Field(ge=0)
    onduleur_par_kw: float = Field(ge=0)
    kwh_evite: float = Field(ge=0)


class Resultats(_Strict):
    """Les valeurs de synthèse du calcul, jamais les séries horaires."""

    puissance_champ_kwc: float = Field(ge=0)
    nombre_modules: int = Field(ge=0)
    capacite_batterie_kwh: float = Field(ge=0)
    puissance_onduleur_kw: float = Field(ge=0)
    productible_annuel_kwh: float = Field(ge=0)
    taux_autonomie: float = Field(ge=0, le=1, description="Part de la consommation couverte.")
    mois_defavorable: int | None = Field(
        default=None, ge=1, le=12, description="1 pour janvier ; absent en base annuelle."
    )
    cout_installation: float | None = Field(default=None, ge=0)
    economies_annuelles: float | None = None
    temps_retour_ans: float | None = Field(default=None, ge=0)
    energie_non_servie: float | None = Field(
        default=None, ge=0, le=1, description="Part non servie à la simulation horaire."
    )


class FichePvAutonome(_Strict):
    """Fiche d'une étude Photovoltaïque autonome, format ``pv-autonome@1``."""

    logiciel: Logiciel
    lieu: Lieu | None = None
    panneaux: Panneaux
    ressource: Ressource | None = None
    appareils: list[Appareil] = Field(max_length=200)
    systeme: Systeme
    prix: Prix
    resultats: Resultats | None = None


class DemandeContribution(_Strict):
    """Corps de ``POST /v1/contributions/{etude_uid}``."""

    module: Literal["pv-autonome"]
    format: Literal["pv-autonome@1"]
    fiche: FichePvAutonome


class ReponseContribution(BaseModel):
    """Accusé de réception d'une fiche."""

    etude_uid: str
    recue_le: datetime = Field(description="Premier envoi de cette fiche.")
    mise_a_jour_le: datetime = Field(description="Dernier envoi.")
    nombre_envois: int
