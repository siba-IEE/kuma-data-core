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

import calendar
import math
from collections import defaultdict
from collections.abc import Sequence
from datetime import date
from typing import Any, TypedDict

from sqlalchemy import text
from sqlalchemy.orm import Session

from kuma_data_core.editorial.niveaux_confiance import (
    NiveauConfiance,
    NiveauxEntrees,
    calculer_niveau_confiance_derive,
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


class _LigneAgregeeHumidex(TypedDict):
    periode_type: str
    annee_debut: int
    annee_fin: int
    mois: int | None
    valeur: float


class _AgregationResultat(TypedDict):
    lignes_annuelles: list[_LigneAgregeeHumidex]
    lignes_mensuelles: list[_LigneAgregeeHumidex]
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

    lignes_annuelles: list[_LigneAgregeeHumidex] = []
    lignes_mensuelles: list[_LigneAgregeeHumidex] = []
    annees_skip: list[int] = []
    mois_skip: list[tuple[int, int]] = []
    nb_jours_inconfort_par_annee: dict[int, int] = {}

    for (annee, mois), valeurs in sorted(par_mois.items()):
        n_attendu = calendar.monthrange(annee, mois)[1]
        if len(valeurs) != n_attendu:
            mois_skip.append((annee, mois))
            continue
        lignes_mensuelles.append(
            {
                "periode_type": "mensuel",
                "annee_debut": annee,
                "annee_fin": annee,
                "mois": mois,
                "valeur": float(sum(valeurs) / len(valeurs)),
            }
        )

    for annee, valeurs in sorted(par_annee.items()):
        n_attendu = 366 if calendar.isleap(annee) else 365
        if len(valeurs) != n_attendu:
            annees_skip.append(annee)
            continue
        lignes_annuelles.append(
            {
                "periode_type": "annuel",
                "annee_debut": annee,
                "annee_fin": annee,
                "mois": None,
                "valeur": float(sum(valeurs) / len(valeurs)),
            }
        )
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
    version_actuelle = session.execute(
        text("SELECT version_formule_actuelle FROM grandeurs_referentiel WHERE code = :code"),
        {"code": GRANDEUR_CODE_HUMIDEX},
    ).scalar()
    if version_actuelle is None:
        raise RuntimeError(
            f"Grandeur {GRANDEUR_CODE_HUMIDEX!r} introuvable dans grandeurs_referentiel."
        )
    if version_formule != int(version_actuelle):
        raise RuntimeError(
            f"Desalignement version_formule : argument={version_formule}, "
            f"version_formule_actuelle pour {GRANDEUR_CODE_HUMIDEX!r}={int(version_actuelle)}."
        )

    serie_cible = session.execute(
        text(
            """
            SELECT
                sm.id AS serie_id,
                sm.localite_id,
                sm.grandeur_code,
                sm.methode_collecte,
                s.fiabilite AS fiabilite_source
            FROM series_metadonnees sm
            JOIN sources s ON s.id = sm.source_id
            WHERE sm.code = :code
            """
        ),
        {"code": code_serie_humidex},
    ).first()
    if serie_cible is None:
        raise RuntimeError(
            f"Serie humidex cible {code_serie_humidex!r} introuvable dans series_metadonnees."
        )
    if serie_cible.grandeur_code != GRANDEUR_CODE_HUMIDEX:
        raise RuntimeError(
            f"Serie cible {code_serie_humidex!r} : grandeur_code="
            f"{serie_cible.grandeur_code!r}, attendu {GRANDEUR_CODE_HUMIDEX!r}."
        )
    if serie_cible.methode_collecte != METHODE_COLLECTE_HUMIDEX:
        raise RuntimeError(
            f"Serie cible {code_serie_humidex!r} : methode_collecte="
            f"{serie_cible.methode_collecte!r}, attendu {METHODE_COLLECTE_HUMIDEX!r}."
        )

    serie_t2m = session.execute(
        text(
            "SELECT id AS serie_id, localite_id, grandeur_code "
            "FROM series_metadonnees WHERE code = :code"
        ),
        {"code": code_serie_t2m_amont},
    ).first()
    if serie_t2m is None:
        raise RuntimeError(f"Serie T2M amont {code_serie_t2m_amont!r} introuvable.")
    if serie_t2m.grandeur_code != GRANDEUR_CODE_T2M:
        raise RuntimeError(
            f"Serie {code_serie_t2m_amont!r} : grandeur_code="
            f"{serie_t2m.grandeur_code!r}, attendu {GRANDEUR_CODE_T2M!r}."
        )

    serie_rh2m = session.execute(
        text(
            "SELECT id AS serie_id, localite_id, grandeur_code "
            "FROM series_metadonnees WHERE code = :code"
        ),
        {"code": code_serie_rh2m_amont},
    ).first()
    if serie_rh2m is None:
        raise RuntimeError(f"Serie RH2M amont {code_serie_rh2m_amont!r} introuvable.")
    if serie_rh2m.grandeur_code != GRANDEUR_CODE_RH2M:
        raise RuntimeError(
            f"Serie {code_serie_rh2m_amont!r} : grandeur_code="
            f"{serie_rh2m.grandeur_code!r}, attendu {GRANDEUR_CODE_RH2M!r}."
        )

    localite_cible = int(serie_cible.localite_id)
    if int(serie_t2m.localite_id) != localite_cible:
        raise RuntimeError(
            f"Incoherence localite : serie cible {code_serie_humidex!r} "
            f"localite_id={localite_cible} vs serie T2M amont "
            f"{code_serie_t2m_amont!r} localite_id={int(serie_t2m.localite_id)}."
        )
    if int(serie_rh2m.localite_id) != localite_cible:
        raise RuntimeError(
            f"Incoherence localite : serie cible {code_serie_humidex!r} "
            f"localite_id={localite_cible} vs serie RH2M amont "
            f"{code_serie_rh2m_amont!r} localite_id={int(serie_rh2m.localite_id)}."
        )

    rows_t2m = session.execute(
        text(
            """
            SELECT instant_mesure, valeur,
                   coalesce(niveau_confiance_override, niveau_confiance_derive) AS niveau
            FROM mesures_ressource
            WHERE serie_id = :serie_id AND valide_au IS NULL AND statut <> 'deprecie'
            ORDER BY instant_mesure
            """
        ),
        {"serie_id": int(serie_t2m.serie_id)},
    ).all()
    rows_rh2m = session.execute(
        text(
            """
            SELECT instant_mesure, valeur,
                   coalesce(niveau_confiance_override, niveau_confiance_derive) AS niveau
            FROM mesures_ressource
            WHERE serie_id = :serie_id AND valide_au IS NULL AND statut <> 'deprecie'
            ORDER BY instant_mesure
            """
        ),
        {"serie_id": int(serie_rh2m.serie_id)},
    ).all()
    mesures_t2m: list[tuple[date, float]] = [(r.instant_mesure, float(r.valeur)) for r in rows_t2m]
    mesures_rh2m: list[tuple[date, float]] = [
        (r.instant_mesure, float(r.valeur)) for r in rows_rh2m
    ]

    niveaux = NiveauxEntrees()
    for r in (*rows_t2m, *rows_rh2m):
        niveaux.ajouter(r.instant_mesure, r.niveau)

    agregation = _agreger_humidex(
        mesures_t2m, mesures_rh2m, seuil_inconfort_modere=seuil_inconfort_modere
    )

    toutes_lignes: list[_LigneAgregeeHumidex] = list(agregation["lignes_annuelles"]) + list(
        agregation["lignes_mensuelles"]
    )
    if toutes_lignes:
        params: list[dict[str, Any]] = [
            {
                "grandeur_code": GRANDEUR_CODE_HUMIDEX,
                "localite_id": localite_cible,
                "series_metadonnees_id": int(serie_cible.serie_id),
                "periode_type": ligne["periode_type"],
                "annee_debut": ligne["annee_debut"],
                "annee_fin": ligne["annee_fin"],
                "mois": ligne["mois"],
                "version_formule": version_formule,
                "valeur": ligne["valeur"],
                "niveau_confiance_derive": calculer_niveau_confiance_derive(
                    methode_collecte=serie_cible.methode_collecte,
                    fiabilite_source=serie_cible.fiabilite_source,
                    plafond=PLAFOND_CONFIANCE,
                    niveaux_entrees=niveaux.de_periode(
                        ligne["annee_debut"], ligne["annee_fin"], ligne["mois"]
                    ),
                ),
            }
            for ligne in toutes_lignes
        ]
        session.execute(
            text(
                """
                INSERT INTO grandeurs_metier
                    (grandeur_code, localite_id, series_metadonnees_id,
                     periode_type, annee_debut, annee_fin, mois,
                     version_formule, valeur, niveau_confiance_derive)
                VALUES
                    (:grandeur_code, :localite_id, :series_metadonnees_id,
                     :periode_type, :annee_debut, :annee_fin, :mois,
                     :version_formule, :valeur, :niveau_confiance_derive)
                """
            ),
            params,
        )
        session.flush()

    return {
        "code_serie_humidex": code_serie_humidex,
        "nb_annuel_insere": len(agregation["lignes_annuelles"]),
        "nb_mensuel_insere": len(agregation["lignes_mensuelles"]),
        "annees_traitees": agregation["annees_traitees"],
        "annees_skip_completude": agregation["annees_skip_completude"],
        "mois_skip_completude": agregation["mois_skip_completude"],
        "nb_jours_inconfort_modere_par_annee": agregation["nb_jours_inconfort_modere_par_annee"],
    }
