"""Humidex stocké (moyennes annuelles et mensuelles) depuis T2M et RH2M journaliers.

Masterton & Richardson 1979, constantes de Magnus :

```
e = (RH/100) * 6.112 * exp((17.67 * T) / (T + 243.5))
H = T + (5/9) * (e - 10)
```

T en °C, RH en %, e en hPa, H en °C apparents ; T = 30 °C, RH = 70 % donne
H ≈ 40.96. Complétude stricte sur les jours où T2M et RH2M existent tous
deux. Le nombre de jours d'inconfort est renvoyé mais pas stocké (pas
d'entrée de référentiel pour lui).
"""

from __future__ import annotations

import math
from collections import defaultdict
from collections.abc import Sequence
from datetime import date
from typing import TypedDict

from sqlalchemy.orm import Session

from kuma_data_core.editorial.niveaux_confiance import NiveauConfiance, NiveauxEntrees
from kuma_data_core.services.grandeurs._commun import (
    LignePeriode,
    inserer_periodes,
    jours_attendus_annee,
    jours_attendus_mois,
    ligne_annuelle,
    ligne_mensuelle,
    lire_mesures_journalieres,
    resoudre_serie_amont,
    resoudre_serie_cible,
    verifier_localite_amont,
    verifier_version_formule,
)

PLAFOND_CONFIANCE: NiveauConfiance = "A"
"""Plafond de confiance : formule fermée sur T2M et RH2M, sans modèle ni hypothèse."""

GRANDEUR_CODE_HUMIDEX: str = "humidex"
METHODE_COLLECTE_HUMIDEX: str = "calcul_derive"
GRANDEUR_CODE_T2M: str = "t2m"
GRANDEUR_CODE_RH2M: str = "rh2m"

SEUIL_INCONFORT_MODERE_DEFAUT: float = 40.0
"""Seuil d'inconfort modéré (°C apparents, Environnement Canada)."""


class CalculHumidexResultat(TypedDict):
    """Résultat d'un appel à :func:`calculer_et_inserer_humidex`."""

    code_serie_humidex: str
    nb_annuel_insere: int
    nb_mensuel_insere: int
    annees_traitees: tuple[int, ...]
    annees_skip_completude: tuple[int, ...]
    mois_skip_completude: tuple[tuple[int, int], ...]
    nb_jours_inconfort_modere_par_annee: dict[int, int]


class _AgregationResultat(TypedDict):
    lignes_annuelles: list[LignePeriode]
    lignes_mensuelles: list[LignePeriode]
    annees_traitees: tuple[int, ...]
    annees_skip_completude: tuple[int, ...]
    mois_skip_completude: tuple[tuple[int, int], ...]
    nb_jours_inconfort_modere_par_annee: dict[int, int]


def _calculer_humidex_journalier(t_celsius: float, rh_pourcent: float) -> float:
    """Humidex (°C apparents) d'une T moyenne (°C) et d'une RH moyenne (%)."""
    e_hpa = (rh_pourcent / 100.0) * 6.112 * math.exp((17.67 * t_celsius) / (t_celsius + 243.5))
    return t_celsius + (5.0 / 9.0) * (e_hpa - 10.0)


def _agreger_humidex(
    mesures_t2m: Sequence[tuple[date, float]],
    mesures_rh2m: Sequence[tuple[date, float]],
    seuil_inconfort_modere: float = SEUIL_INCONFORT_MODERE_DEFAUT,
) -> _AgregationResultat:
    """Humidex moyens annuels et mensuels complets, et jours d'inconfort par année."""
    t2m_par_date: dict[date, float] = dict(mesures_t2m)
    rh2m_par_date: dict[date, float] = dict(mesures_rh2m)
    dates_communes = sorted(set(t2m_par_date) & set(rh2m_par_date))

    humidex_par_date: dict[date, float] = {
        d: _calculer_humidex_journalier(t2m_par_date[d], rh2m_par_date[d]) for d in dates_communes
    }

    par_mois: dict[tuple[int, int], list[float]] = defaultdict(list)
    par_annee: dict[int, list[float]] = defaultdict(list)
    for d, h in humidex_par_date.items():
        par_mois[(d.year, d.month)].append(h)
        par_annee[d.year].append(h)

    lignes_annuelles: list[LignePeriode] = []
    lignes_mensuelles: list[LignePeriode] = []
    annees_skip: list[int] = []
    mois_skip: list[tuple[int, int]] = []
    nb_jours_inconfort_par_annee: dict[int, int] = {}

    for (annee, mois), valeurs in sorted(par_mois.items()):
        if len(valeurs) != jours_attendus_mois(annee, mois):
            mois_skip.append((annee, mois))
            continue
        lignes_mensuelles.append(ligne_mensuelle(annee, mois, float(sum(valeurs) / len(valeurs))))

    for annee, valeurs in sorted(par_annee.items()):
        if len(valeurs) != jours_attendus_annee(annee):
            annees_skip.append(annee)
            continue
        lignes_annuelles.append(ligne_annuelle(annee, float(sum(valeurs) / len(valeurs))))
        nb_jours_inconfort_par_annee[annee] = sum(1 for h in valeurs if h >= seuil_inconfort_modere)

    return {
        "lignes_annuelles": lignes_annuelles,
        "lignes_mensuelles": lignes_mensuelles,
        "annees_traitees": tuple(sorted(par_annee.keys())),
        "annees_skip_completude": tuple(annees_skip),
        "mois_skip_completude": tuple(mois_skip),
        "nb_jours_inconfort_modere_par_annee": nb_jours_inconfort_par_annee,
    }


def calculer_et_inserer_humidex(
    *,
    session: Session,
    code_serie_humidex: str,
    code_serie_t2m_amont: str,
    code_serie_rh2m_amont: str,
    version_formule: int = 1,
    seuil_inconfort_modere: float = SEUIL_INCONFORT_MODERE_DEFAUT,
) -> CalculHumidexResultat:
    """Calcule et insère l'humidex moyen annuel et mensuel d'une localité.

    ``RuntimeError`` si une série est introuvable ou non conforme, si les
    localités diffèrent, ou si ``version_formule`` diffère du référentiel.
    """
    verifier_version_formule(session, GRANDEUR_CODE_HUMIDEX, version_formule)
    cible = resoudre_serie_cible(
        session,
        code_serie_humidex,
        message_introuvable=(
            f"Serie humidex cible {code_serie_humidex!r} introuvable dans series_metadonnees."
        ),
        grandeur_attendue=GRANDEUR_CODE_HUMIDEX,
        methode_attendue=METHODE_COLLECTE_HUMIDEX,
    )
    serie_t2m = resoudre_serie_amont(
        session, code_serie_t2m_amont, libelle="T2M", grandeur_attendue=GRANDEUR_CODE_T2M
    )
    serie_rh2m = resoudre_serie_amont(
        session, code_serie_rh2m_amont, libelle="RH2M", grandeur_attendue=GRANDEUR_CODE_RH2M
    )
    verifier_localite_amont(
        code_cible=code_serie_humidex,
        cible=cible,
        code_amont=code_serie_t2m_amont,
        libelle="T2M",
        amont=serie_t2m,
    )
    verifier_localite_amont(
        code_cible=code_serie_humidex,
        cible=cible,
        code_amont=code_serie_rh2m_amont,
        libelle="RH2M",
        amont=serie_rh2m,
    )

    niveaux = NiveauxEntrees()
    mesures_t2m = lire_mesures_journalieres(session, serie_t2m.serie_id, niveaux)
    mesures_rh2m = lire_mesures_journalieres(session, serie_rh2m.serie_id, niveaux)
    agregation = _agreger_humidex(
        mesures_t2m, mesures_rh2m, seuil_inconfort_modere=seuil_inconfort_modere
    )
    inserer_periodes(
        session,
        grandeur_code=GRANDEUR_CODE_HUMIDEX,
        cible=cible,
        version_formule=version_formule,
        lignes=[*agregation["lignes_annuelles"], *agregation["lignes_mensuelles"]],
        plafond=PLAFOND_CONFIANCE,
        niveaux=niveaux,
    )

    return {
        "code_serie_humidex": code_serie_humidex,
        "nb_annuel_insere": len(agregation["lignes_annuelles"]),
        "nb_mensuel_insere": len(agregation["lignes_mensuelles"]),
        "annees_traitees": agregation["annees_traitees"],
        "annees_skip_completude": agregation["annees_skip_completude"],
        "mois_skip_completude": agregation["mois_skip_completude"],
        "nb_jours_inconfort_modere_par_annee": agregation["nb_jours_inconfort_modere_par_annee"],
    }
