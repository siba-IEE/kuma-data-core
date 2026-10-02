"""Schémas Pydantic des contributions d'études SolClim-3 (ADR-0006).

Trois formats de fiche : ``pv-autonome@1`` (Photovoltaïque autonome),
``minireseau@1`` (mini-réseau) et ``pv-champ@1`` (conception de champ PV).
La demande les distingue par ``module``.

La fiche est le contrat de ce qui quitte le poste de l'utilisateur. Elle est
validée **strictement** : un champ que le contrat ne nomme pas est refusé
(422), si bien qu'une version du logiciel qui enverrait plus que convenu
(le nom de l'étude, un chemin, des coordonnées exactes) échoue au lieu de
fuir. Deux garanties sont reprises côté serveur, quoi qu'envoie le client :
le point saisi est arrondi à 0,1° (environ 11 km), et le nom d'un appareil
ou d'un poste de charge est coupé à 40 caractères.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

#: Longueur conservée du nom d'un appareil ou d'un poste (texte libre saisi).
LONGUEUR_NOM_APPAREIL = 40

#: Pas de l'arrondi d'un point saisi, en degrés (environ 11 km).
DECIMALES_POINT = 1


def couper_nom(valeur: str) -> str:
    """Le nom saisi, sans espaces de bord, coupé à la longueur convenue."""
    return valeur.strip()[:LONGUEUR_NOM_APPAREIL].strip()


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
        return couper_nom(valeur)


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


# === Mini-réseau, format ``minireseau@1`` ===


class ChampMiniReseau(_Strict):
    pr: float = Field(gt=0, le=1, description="Ratio de performance.")
    convention_pr: Literal["tout_compris", "hors_corrections"]
    inclinaison_deg: float = Field(ge=0, le=90)
    degradation_annuelle: float = Field(ge=0, le=0.2)
    plan_actif: bool = Field(description="Production mise au plan des panneaux.")
    orientation_deg: float = Field(ge=-180, le=360)
    albedo: float = Field(ge=0, le=1)


class PosteCharge(_Strict):
    nom: str = Field(max_length=200)
    energie_jour_kwh: float = Field(ge=0, le=1_000_000)
    profil_24: list[float] = Field(
        min_length=24, max_length=24, description="Profil de la journée, heure par heure."
    )

    @field_validator("nom")
    @classmethod
    def _couper(cls, valeur: str) -> str:
        return couper_nom(valeur)

    @field_validator("profil_24")
    @classmethod
    def _positif(cls, valeurs: list[float]) -> list[float]:
        if any(v < 0 for v in valeurs):
            raise ValueError("un profil horaire ne porte pas de valeur négative")
        return valeurs


class Charge(_Strict):
    postes: list[PosteCharge] = Field(max_length=200)
    facteurs_mensuels: list[float] = Field(min_length=12, max_length=12)
    croissance_annuelle: list[float] = Field(
        max_length=60, description="Facteur de la charge, année par année."
    )


class Stockage(_Strict):
    eta_charge: float = Field(gt=0, le=1)
    eta_decharge: float = Field(gt=0, le=1)
    profondeur_decharge: float = Field(gt=0, le=1)
    vieillissement_annuel: float = Field(ge=0, le=1)
    puissance_charge_max_kw: float | None = Field(default=None, ge=0)
    puissance_decharge_max_kw: float | None = Field(default=None, ge=0)


class Groupe(_Strict):
    puissance_kw: float | None = Field(default=None, ge=0)
    charge_minimale: float = Field(ge=0, le=1)
    disponibilite: float = Field(ge=0, le=1)
    conso_demi_charge_lh: float | None = Field(default=None, ge=0)
    conso_pleine_charge_lh: float | None = Field(default=None, ge=0)
    prix_litre_carburant: float | None = Field(default=None, ge=0)
    facteur_emission_kg_par_l: float | None = Field(default=None, ge=0)


class Axe(_Strict):
    min: float | None = None
    max: float | None = None
    pas: float | None = None


class Dimensionnement(_Strict):
    horizon_annees: int = Field(ge=1, le=60)
    cible_lpsp: float = Field(ge=0, le=1)
    cible_lpsp_puissance: float | None = Field(default=None, ge=0, le=1)
    grille_champ: Axe
    grille_stockage: Axe
    grille_auto: bool | None = None


class PrixMiniReseau(_Strict):
    """Les prix et paramètres économiques saisis, dans la monnaie de l'étude."""

    monnaie: Literal["GNF", "USD", "EUR", "XOF"]
    cout_par_kwc: float = Field(ge=0)
    cout_par_kwh_utile: float = Field(ge=0)
    taux_actualisation: float | None = Field(default=None, ge=0, lt=1)
    opex_annuel: float | None = Field(default=None, ge=0)
    capex_complement: float | None = Field(default=None, ge=0)
    annee_remplacement_stockage: int | None = Field(default=None, ge=1, le=60)


class ResultatsMiniReseau(_Strict):
    """La configuration retenue et son exploitation, en valeurs de synthèse."""

    champ_kwc: float = Field(ge=0)
    stockage_kwh: float = Field(ge=0)
    lpsp_hors_groupe: float = Field(ge=0, le=1)
    lpsp_vecu: float = Field(ge=0, le=1)
    part_groupe: float = Field(ge=0, le=1)
    demande_kwh_an: float = Field(ge=0)
    non_servie_energie_kwh_an: float = Field(ge=0)
    non_servie_puissance_kwh_an: float = Field(ge=0)
    heures_groupe_an: float = Field(ge=0)
    demarrages_groupe_an: float = Field(ge=0)
    carburant_litres_an: float | None = Field(default=None, ge=0)
    cout_carburant_an: float | None = Field(default=None, ge=0)
    co2_kg_an: float | None = Field(default=None, ge=0)
    lcoe_par_kwh: float | None = Field(default=None, ge=0)
    part_capex: float | None = Field(default=None, ge=0, le=1)
    part_opex: float | None = Field(default=None, ge=0, le=1)
    part_carburant: float | None = Field(default=None, ge=0, le=1)
    part_remplacement: float | None = Field(default=None, ge=0, le=1)


class FicheMiniReseau(_Strict):
    """Fiche d'une étude mini-réseau, format ``minireseau@1``.

    Ni nom de site, ni textes du rapport, ni séries de la ressource, ni détail
    du calage : le Core retrouve la ressource par le lieu et la version.
    """

    logiciel: Logiciel
    lieu: Lieu | None = None
    ressource: Ressource | None = None
    champ: ChampMiniReseau
    charge: Charge
    stockage: Stockage
    groupe: Groupe | None = None
    dimensionnement: Dimensionnement
    prix: PrixMiniReseau
    resultats: ResultatsMiniReseau | None = None


# === Conception de champ PV, format ``pv-champ@1`` ===


class PlanChamp(_Strict):
    inclinaison_deg: float = Field(ge=0, le=90)
    orientation_deg: float = Field(ge=-180, le=360)


class ConditionsChamp(_Strict):
    kwc_cible: float = Field(gt=0, le=100_000, description="Puissance visée.")
    t_min_c: float = Field(ge=-60, le=60)
    t_max_c: float = Field(ge=-20, le=80)
    hse_moyenne: float | None = Field(
        default=None, ge=0, le=15, description="Ensoleillement saisi à la main, sans site posé."
    )


class ModuleChamp(_Strict):
    """Les caractéristiques d'un module, sans marque ni référence."""

    puissance_crete_w: float = Field(gt=0, le=2000)
    voc_v: float = Field(gt=0, le=300)
    isc_a: float = Field(gt=0, le=100)
    vmp_v: float = Field(gt=0, le=300)
    imp_a: float = Field(gt=0, le=100)
    beta_voc_pct_par_c: float = Field(ge=-5, le=5)
    beta_vmp_pct_par_c: float = Field(ge=-5, le=5)
    gamma_pmax_pct_par_c: float | None = Field(default=None, ge=-5, le=5)
    noct_c: float | None = Field(default=None, ge=0, le=100)
    fusible_max_a: float | None = Field(default=None, ge=0, le=200)


class OnduleurChamp(_Strict):
    """Les caractéristiques d'un onduleur, sans marque ni référence."""

    puissance_ac_nom_w: float = Field(gt=0, le=10_000_000)
    tension_dc_max_v: float = Field(gt=0, le=3000)
    mppt_min_v: float = Field(ge=0, le=3000)
    mppt_max_v: float = Field(gt=0, le=3000)
    courant_mppt_max_a: float = Field(gt=0, le=2000)
    nombre_mppt: int = Field(ge=1, le=100)
    puissance_dc_max_w: float = Field(gt=0, le=20_000_000)


class PostePerte(_Strict):
    cle: str = Field(min_length=1, max_length=60, description="Code du poste de perte.")
    fraction: float = Field(ge=0, le=1)


class Cablage(_Strict):
    longueur_string_m: float = Field(ge=0, le=10_000)
    longueur_principal_dc_m: float = Field(ge=0, le=10_000)
    longueur_ac_m: float = Field(ge=0, le=10_000)
    chute_max_dc_pct: float = Field(ge=0, le=20)
    chute_max_ac_pct: float = Field(ge=0, le=20)
    materiau: Literal["cuivre", "aluminium"]
    tension_ac_v: float = Field(gt=0, le=2000)
    triphase: bool
    facteur_deratage: float = Field(gt=0, le=2)
    longueur_module_m: float = Field(gt=0, le=5)
    largeur_module_m: float = Field(gt=0, le=5)


class VerificationChamp(_Strict):
    cle: str = Field(min_length=1, max_length=60)
    valeur: float
    limite: float
    respecte: bool
    marge: float


class CableChamp(_Strict):
    cle: str = Field(min_length=1, max_length=60)
    courant_conception_a: float = Field(ge=0)
    longueur_m: float = Field(ge=0)
    section_mm2: float = Field(gt=0)
    chute_reelle_pct: float = Field(ge=0)
    contrainte: Literal["ampacite", "chute"]


class ProtectionChamp(_Strict):
    cle: str = Field(min_length=1, max_length=60)
    quantite: float = Field(ge=0)
    calibre: str = Field(max_length=60)
    conforme: bool | None = None


class ResultatsChamp(_Strict):
    """La configuration du champ, ses vérifications et ce qu'elle produit."""

    modules_par_string: int = Field(ge=0)
    modules_par_string_min: int = Field(ge=0)
    modules_par_string_max: int = Field(ge=0)
    fenetre_valide: bool
    nombre_strings: int = Field(ge=0)
    strings_par_mppt: int = Field(ge=0)
    nombre_onduleurs: int = Field(ge=0)
    nombre_modules: int = Field(ge=0)
    puissance_dc_kwc: float = Field(ge=0)
    ratio_dc_ac: float = Field(ge=0)
    t_cellule_max_c: float
    verifications: list[VerificationChamp] = Field(max_length=50)
    pr_reel: float | None = Field(default=None, ge=0, le=1)
    productible_annuel_kwh: float | None = Field(default=None, ge=0)
    productible_specifique_kwh_kwc: float | None = Field(default=None, ge=0)
    cables: list[CableChamp] = Field(max_length=20)
    protections: list[ProtectionChamp] = Field(max_length=50)


class FichePvChamp(_Strict):
    """Fiche d'une conception de champ PV, format ``pv-champ@1``.

    Le module et l'onduleur partent par leurs caractéristiques, sans marque ni
    référence. Ni nom d'étude, ni coordonnées exactes, ni nomenclature
    chiffrée (elle se recalcule de la saisie).
    """

    logiciel: Logiciel
    lieu: Lieu | None = None
    ressource: Ressource | None = None
    plan: PlanChamp
    conditions: ConditionsChamp
    module: ModuleChamp
    onduleur: OnduleurChamp
    pertes: list[PostePerte] = Field(max_length=30)
    cablage: Cablage
    resultats: ResultatsChamp | None = None


# === La demande ===


class DemandePvAutonome(_Strict):
    module: Literal["pv-autonome"]
    format: Literal["pv-autonome@1"]
    fiche: FichePvAutonome


class DemandeMiniReseau(_Strict):
    module: Literal["minireseau"]
    format: Literal["minireseau@1"]
    fiche: FicheMiniReseau


class DemandePvChamp(_Strict):
    module: Literal["pv-champ"]
    format: Literal["pv-champ@1"]
    fiche: FichePvChamp


#: Une demande, l'une des trois.
TypeDemande = DemandePvAutonome | DemandeMiniReseau | DemandePvChamp

#: Corps de ``POST /v1/contributions/{etude_uid}`` : le module choisit le format.
DemandeContribution = Annotated[TypeDemande, Field(discriminator="module")]


class ReponseContribution(BaseModel):
    """Accusé de réception d'une fiche."""

    etude_uid: str
    recue_le: datetime = Field(description="Premier envoi de cette fiche.")
    mise_a_jour_le: datetime = Field(description="Dernier envoi.")
    nombre_envois: int
