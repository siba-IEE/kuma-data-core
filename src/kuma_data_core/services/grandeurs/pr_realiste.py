"""Calcul à la volée du PR réaliste saisonnier.

``pr_realiste = PR_fourni x ratio_T x (1 - perte_salissure / 100)``, ratio sans
dimension. Sa moyenne mensuelle donne la courbe saisonnière du PR : creux
d'Harmattan (particules élevées de décembre à février), remontée à la mousson
(lessivage).

Le facteur thermique ``ratio_T`` vient du modèle NOCT (Ross 1980,
``productible_correction_thermique``), le facteur de salissure du modèle HSU
(``soiling_hsu``). Ils sont calculés indépendamment : le couplage de second ordre
G -> T_cell -> rendement est ignoré.

Le PR fourni est supposé hors salissure et hors température. Un PR « plaque » qui
inclut déjà ces pertes serait corrigé deux fois : l'appelant qui en dispose choisit
``correction='aucune'``.

Modes (``correction``) : ``aucune`` (renvoie le PR fourni), ``temperature``
(compagne T2M), ``salissure`` (compagnes PM2.5, PM10 et pluie),
``temperature_salissure`` (défaut).

Références : Dierauf et al. 2013 (PR corrigé de la température,
NREL/TP-5200-57991), Ross 1980 (NOCT), Coello & Boyle 2019 (HSU).
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Sequence
from datetime import date
from typing import Literal, TypedDict

from pydantic import BaseModel

from kuma_data_core.editorial.niveaux_confiance import NiveauConfiance, propager_niveau_confiance
from kuma_data_core.services.grandeurs.productible_correction_thermique import (
    TEMPERATURE_STC_DEGC,
    _temperature_cellule_noct,
)
from kuma_data_core.services.grandeurs.soiling_hsu import (
    MesureEntreeSoiling,
    calculer_taux_salissure_proxy,
)
from kuma_data_core.services.grandeurs.types import MesureJourPR, MesureMoisPR, ModeCorrectionPR

PLAFOND_CONFIANCE: NiveauConfiance = "B"
"""Plafond de confiance : modèle thermique, proxy de salissure et PR fourni par l'utilisateur."""

_BESOIN_THERMIQUE: frozenset[str] = frozenset({"temperature", "temperature_salissure"})
_BESOIN_SALISSURE: frozenset[str] = frozenset({"salissure", "temperature_salissure"})

NIVEAU_CONFIANCE: Literal["B"] = "B"
"""Niveau provisoire du calcul pur, remplacé par la route (règle de propagation P)."""

_HEURES_PAR_JOUR: float = 24.0
_WATT_PAR_KILOWATT: float = 1000.0

_CAVEAT_PR_REFERENCE: str = (
    "Le PR fourni est supposé hors salissure et hors température : les corrections "
    "s'appliquent en facteurs multiplicatifs séparés, et un PR « plaque » qui inclut "
    "déjà ces pertes les compterait deux fois. Résultat issu de modèles (confiance au "
    "plus B), pas un PR mesuré sur site. Les facteurs thermique et salissure sont "
    "calculés indépendamment l'un de l'autre."
)
_CAVEAT_SPIN_UP: str = (
    " Salissure : le modèle HSU démarre avec des modules propres, les premiers jours "
    "de la fenêtre sont donc sous-estimés (amorçage du modèle) ; la fenêtre est bornée "
    "au recouvrement avec les séries de particules (PM) EAC4."
)
_CAVEAT_L_TR_6: str = (
    " Thermique : le calcul est journalier, or la moyenne sur 24 h sous-estime le pic "
    "d'irradiance de midi, donc la température de cellule ; le PR obtenu est "
    "légèrement optimiste par temps chaud (biais de moyennage)."
)


class MesureJourPRRealiste(TypedDict):
    """Mesure journalière alignée, entrée du PR réaliste.

    Champs requis selon le mode (``None`` sinon) : ``ghi_kwh_par_m2_jour`` et
    ``t_amb_degc`` pour la température ; ``rainfall_mm``, ``pm2_5`` et ``pm10``
    (µg/m³) pour la salissure.
    """

    instant_mesure: date
    ghi_kwh_par_m2_jour: float | None
    t_amb_degc: float | None
    rainfall_mm: float | None
    pm2_5: float | None
    pm10: float | None


class ResultatPRRealiste(BaseModel):
    """Résultat du PR réaliste : PR effectif journalier et mise en garde."""

    mesures: list[MesureJourPR]
    limite: str


def _exiger_present(valeur: float | None, nom: str, mode: str) -> float:
    if valeur is None:
        raise ValueError(f"Champ {nom!r} requis pour la correction {mode!r}, recu None.")
    return valeur


def _ratio_thermique_jour(
    ghi_kwh_par_m2_jour: float, t_amb_degc: float, noct_degc: float, gamma_pmax_pct: float
) -> float:
    """Facteur de correction thermique ``ratio_T`` (NOCT, Ross 1980)."""
    irradiance_w_par_m2 = ghi_kwh_par_m2_jour * _WATT_PAR_KILOWATT / _HEURES_PAR_JOUR
    t_cell = _temperature_cellule_noct(
        t_amb_degc=t_amb_degc, irradiance_w_par_m2=irradiance_w_par_m2, noct_degc=noct_degc
    )
    return 1.0 + gamma_pmax_pct / 100.0 * (t_cell - TEMPERATURE_STC_DEGC)


def _limite(correction: ModeCorrectionPR) -> str:
    suite = ""
    if correction in _BESOIN_SALISSURE:
        suite += _CAVEAT_SPIN_UP
    if correction in _BESOIN_THERMIQUE:
        suite += _CAVEAT_L_TR_6
    return _CAVEAT_PR_REFERENCE + suite


def calculer_pr_realiste(
    mesures: Sequence[MesureJourPRRealiste],
    pr_fourni: float,
    correction: ModeCorrectionPR = "temperature_salissure",
    noct_degc: float | None = None,
    gamma_pmax_pct: float | None = None,
) -> ResultatPRRealiste:
    """PR effectif journalier = ``PR_fourni x ratio_T x (1 - perte/100)`` selon le mode.

    Un PR négatif est ramené à 0. Lève ``ValueError`` si un champ requis par le mode
    (ou ``noct_degc`` / ``gamma_pmax_pct`` en mode thermique) est absent.
    """
    if not mesures:
        return ResultatPRRealiste(mesures=[], limite=_limite(correction))

    mesures_tri = sorted(mesures, key=lambda m: m["instant_mesure"])

    if correction in _BESOIN_THERMIQUE and (noct_degc is None or gamma_pmax_pct is None):
        raise ValueError(f"noct_degc et gamma_pmax_pct requis pour la correction {correction!r}.")

    facteur_salissure: dict[date, float] = {}
    if correction in _BESOIN_SALISSURE:
        entrees_soiling: list[MesureEntreeSoiling] = [
            {
                "instant_mesure": m["instant_mesure"],
                "rainfall_mm": _exiger_present(m["rainfall_mm"], "rainfall_mm", correction),
                "pm2_5": _exiger_present(m["pm2_5"], "pm2_5", correction),
                "pm10": _exiger_present(m["pm10"], "pm10", correction),
            }
            for m in mesures_tri
        ]
        resultat_soiling = calculer_taux_salissure_proxy(entrees_soiling)
        facteur_salissure = {
            ms.instant: 1.0 - ms.perte_pct / 100.0 for ms in resultat_soiling.mesures
        }

    sorties: list[MesureJourPR] = []
    for m in mesures_tri:
        jour = m["instant_mesure"]
        ratio_t = 1.0
        if correction in _BESOIN_THERMIQUE:
            assert noct_degc is not None and gamma_pmax_pct is not None
            ratio_t = _ratio_thermique_jour(
                _exiger_present(m["ghi_kwh_par_m2_jour"], "ghi_kwh_par_m2_jour", correction),
                _exiger_present(m["t_amb_degc"], "t_amb_degc", correction),
                noct_degc,
                gamma_pmax_pct,
            )
        sf = facteur_salissure.get(jour, 1.0) if correction in _BESOIN_SALISSURE else 1.0
        pr = max(0.0, pr_fourni * ratio_t * sf)
        sorties.append(
            MesureJourPR(instant=jour, pr_realiste=pr, niveau_confiance=NIVEAU_CONFIANCE)
        )

    return ResultatPRRealiste(mesures=sorties, limite=_limite(correction))


def agreger_pr_mensuel(mesures_jour: Sequence[MesureJourPR]) -> list[MesureMoisPR]:
    """Moyenne mensuelle du PR réaliste journalier, triée par mois (``YYYY-MM``).

    Chaque mois prend le niveau de confiance le plus bas de ses jours (règle de
    propagation P).
    """
    par_mois: dict[str, list[MesureJourPR]] = defaultdict(list)
    for m in mesures_jour:
        par_mois[f"{m.instant.year:04d}-{m.instant.month:02d}"].append(m)
    return [
        MesureMoisPR(
            instant=mois,
            pr_realiste=sum(j.pr_realiste for j in jours) / len(jours),
            niveau_confiance=propager_niveau_confiance(
                (j.niveau_confiance for j in jours), plafond=PLAFOND_CONFIANCE
            ),
        )
        for mois, jours in sorted(par_mois.items())
    ]
