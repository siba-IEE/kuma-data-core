"""Variabilité journalière stockée : coefficient de variation annuel du GHI.

```
CoV(annee) := sigma(GHI_jour) / μ(GHI_jour)
```

Annuel seulement : un CoV sur 28-31 jours n'est pas robuste. Ordre de
grandeur : 0.2 en climat équatorial stable, 0.5 en transition de saisons.
Complétude stricte.
"""

from __future__ import annotations

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
    ligne_annuelle,
    lire_mesures_journalieres,
    resoudre_serie_amont,
    resoudre_serie_cible,
    verifier_localite_amont,
    verifier_version_formule,
)

PLAFOND_CONFIANCE: NiveauConfiance = "A"
"""Plafond de confiance : statistique exacte des mesures GHI (coefficient de variation)."""

GRANDEUR_CODE_VARIABILITE: str = "variabilite_journaliere"
METHODE_COLLECTE_VARIABILITE: str = "calcul_derive"
GRANDEUR_CODE_GHI: str = "ghi"


class CalculVariabiliteResultat(TypedDict):
    """Résultat d'un appel à :func:`calculer_et_inserer_variabilite_journaliere`."""

    code_serie_variabilite: str
    nb_annuel_insere: int
    annees_traitees: tuple[int, ...]
    annees_skip_completude: tuple[int, ...]


class _AgregationResultat(TypedDict):
    lignes_annuelles: list[LignePeriode]
    annees_traitees: tuple[int, ...]
    annees_skip_completude: tuple[int, ...]


def _calculer_coefficient_variation(valeurs: Sequence[float]) -> float:
    """sigma / μ (ddof=0) ; ValueError si vide ou moyenne <= 0."""
    n = len(valeurs)
    if n == 0:
        raise ValueError("Sequence vide, CoV non defini.")
    moyenne = sum(valeurs) / n
    if moyenne <= 0:
        raise ValueError(
            f"Moyenne <= 0 ({moyenne}), CoV non defini (division par zero ou negatif)."
        )
    variance = sum((v - moyenne) ** 2 for v in valeurs) / n
    return float((variance**0.5) / moyenne)


def _agreger_variabilite_journaliere(
    mesures_ghi: Sequence[tuple[date, float]],
) -> _AgregationResultat:
    """Un CoV par année complète."""
    par_annee: dict[int, list[float]] = defaultdict(list)
    for d, v in mesures_ghi:
        par_annee[d.year].append(v)

    lignes_annuelles: list[LignePeriode] = []
    annees_skip: list[int] = []

    for annee, valeurs in sorted(par_annee.items()):
        if len(valeurs) != jours_attendus_annee(annee):
            annees_skip.append(annee)
            continue
        try:
            cov = _calculer_coefficient_variation(valeurs)
        except ValueError:
            annees_skip.append(annee)
            continue
        lignes_annuelles.append(ligne_annuelle(annee, cov))

    return {
        "lignes_annuelles": lignes_annuelles,
        "annees_traitees": tuple(sorted(par_annee.keys())),
        "annees_skip_completude": tuple(annees_skip),
    }


def calculer_et_inserer_variabilite_journaliere(
    *,
    session: Session,
    code_serie_variabilite: str,
    code_serie_ghi_amont: str,
    version_formule: int = 1,
) -> CalculVariabiliteResultat:
    """Calcule et insère un CoV par année complète.

    ``RuntimeError`` si une série est introuvable ou non conforme, si les
    localités diffèrent, ou si ``version_formule`` diffère du référentiel.
    """
    verifier_version_formule(session, GRANDEUR_CODE_VARIABILITE, version_formule)
    cible = resoudre_serie_cible(
        session,
        code_serie_variabilite,
        message_introuvable=(
            f"Serie variabilite_journaliere cible {code_serie_variabilite!r} introuvable."
        ),
        grandeur_attendue=GRANDEUR_CODE_VARIABILITE,
        methode_attendue=METHODE_COLLECTE_VARIABILITE,
    )
    serie_ghi = resoudre_serie_amont(
        session, code_serie_ghi_amont, libelle="GHI", grandeur_attendue=GRANDEUR_CODE_GHI
    )
    verifier_localite_amont(
        code_cible=code_serie_variabilite,
        cible=cible,
        code_amont=code_serie_ghi_amont,
        libelle="GHI",
        amont=serie_ghi,
    )

    niveaux = NiveauxEntrees()
    mesures_ghi = lire_mesures_journalieres(session, serie_ghi.serie_id, niveaux)
    agregation = _agreger_variabilite_journaliere(mesures_ghi)
    inserer_periodes(
        session,
        grandeur_code=GRANDEUR_CODE_VARIABILITE,
        cible=cible,
        version_formule=version_formule,
        lignes=agregation["lignes_annuelles"],
        plafond=PLAFOND_CONFIANCE,
        niveaux=niveaux,
    )

    return {
        "code_serie_variabilite": code_serie_variabilite,
        "nb_annuel_insere": len(agregation["lignes_annuelles"]),
        "annees_traitees": agregation["annees_traitees"],
        "annees_skip_completude": agregation["annees_skip_completude"],
    }
