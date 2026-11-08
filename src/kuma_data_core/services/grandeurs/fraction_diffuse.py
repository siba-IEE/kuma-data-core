"""Fraction diffuse stockée : ratio des sommes DHI / GHI, annuel et mensuel.

```
fraction_diffuse(periode) := sum DHI(t) / sum GHI(t), t ∈ jours(periode)
```

Complétude stricte sur les jours où DHI et GHI existent tous deux.
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
"""Plafond de confiance : ratio exact DHI / GHI, sans modèle ni hypothèse."""

GRANDEUR_CODE_FRACTION_DIFFUSE: str = "fraction_diffuse"
"""Code naturel de la grandeur dans `grandeurs_referentiel`."""

METHODE_COLLECTE_FRACTION_DIFFUSE: str = "calcul_derive"
"""Méthode attendue sur la série cible (calcul_derive → grandeurs_metier)."""

GRANDEUR_CODE_DHI: str = "dhi"
GRANDEUR_CODE_GHI: str = "ghi"


class CalculFractionDiffuseResultat(TypedDict):
    """Résultat d'un appel à :func:`calculer_et_inserer_fraction_diffuse`."""

    code_serie_fraction_diffuse: str
    nb_annuel_insere: int
    nb_mensuel_insere: int
    annees_traitees: tuple[int, ...]
    annees_skip_completude: tuple[int, ...]
    mois_skip_completude: tuple[tuple[int, int], ...]


class _AgregationResultat(TypedDict):
    lignes_annuelles: list[LignePeriode]
    lignes_mensuelles: list[LignePeriode]
    annees_traitees: tuple[int, ...]
    annees_skip_completude: tuple[int, ...]
    mois_skip_completude: tuple[tuple[int, int], ...]


def _agreger_fraction_diffuse(
    mesures_dhi: Sequence[tuple[date, float]],
    mesures_ghi: Sequence[tuple[date, float]],
) -> _AgregationResultat:
    """Fractions annuelles et mensuelles complètes ; une période où sum(GHI) = 0 est écartée."""
    dhi_par_date: dict[date, float] = dict(mesures_dhi)
    ghi_par_date: dict[date, float] = dict(mesures_ghi)
    dates_communes = sorted(set(dhi_par_date) & set(ghi_par_date))

    par_mois: dict[tuple[int, int], list[tuple[float, float]]] = defaultdict(list)
    par_annee: dict[int, list[tuple[float, float]]] = defaultdict(list)
    for d in dates_communes:
        couple = (dhi_par_date[d], ghi_par_date[d])
        par_mois[(d.year, d.month)].append(couple)
        par_annee[d.year].append(couple)

    lignes_annuelles: list[LignePeriode] = []
    lignes_mensuelles: list[LignePeriode] = []
    annees_skip: list[int] = []
    mois_skip: list[tuple[int, int]] = []

    for (annee, mois), couples in sorted(par_mois.items()):
        if len(couples) != jours_attendus_mois(annee, mois):
            mois_skip.append((annee, mois))
            continue
        somme_dhi = sum(c[0] for c in couples)
        somme_ghi = sum(c[1] for c in couples)
        if somme_ghi <= 0:
            mois_skip.append((annee, mois))
            continue
        lignes_mensuelles.append(ligne_mensuelle(annee, mois, float(somme_dhi / somme_ghi)))

    for annee, couples in sorted(par_annee.items()):
        if len(couples) != jours_attendus_annee(annee):
            annees_skip.append(annee)
            continue
        somme_dhi = sum(c[0] for c in couples)
        somme_ghi = sum(c[1] for c in couples)
        if somme_ghi <= 0:
            annees_skip.append(annee)
            continue
        lignes_annuelles.append(ligne_annuelle(annee, float(somme_dhi / somme_ghi)))

    return {
        "lignes_annuelles": lignes_annuelles,
        "lignes_mensuelles": lignes_mensuelles,
        "annees_traitees": tuple(sorted(par_annee.keys())),
        "annees_skip_completude": tuple(annees_skip),
        "mois_skip_completude": tuple(mois_skip),
    }


def calculer_et_inserer_fraction_diffuse(
    *,
    session: Session,
    code_serie_fraction_diffuse: str,
    code_serie_dhi_amont: str,
    code_serie_ghi_amont: str,
    version_formule: int = 1,
) -> CalculFractionDiffuseResultat:
    """Calcule et insère la fraction diffuse annuelle et mensuelle (flush, sans commit).

    ``RuntimeError`` si une série est introuvable ou non conforme, si les
    localités diffèrent, ou si ``version_formule`` diffère du référentiel.
    """
    verifier_version_formule(session, GRANDEUR_CODE_FRACTION_DIFFUSE, version_formule)
    cible = resoudre_serie_cible(
        session,
        code_serie_fraction_diffuse,
        message_introuvable=(
            f"Serie fraction_diffuse cible {code_serie_fraction_diffuse!r} "
            "introuvable dans series_metadonnees."
        ),
        grandeur_attendue=GRANDEUR_CODE_FRACTION_DIFFUSE,
        methode_attendue=METHODE_COLLECTE_FRACTION_DIFFUSE,
    )
    serie_dhi = resoudre_serie_amont(
        session, code_serie_dhi_amont, libelle="DHI", grandeur_attendue=GRANDEUR_CODE_DHI
    )
    serie_ghi = resoudre_serie_amont(
        session, code_serie_ghi_amont, libelle="GHI", grandeur_attendue=GRANDEUR_CODE_GHI
    )
    verifier_localite_amont(
        code_cible=code_serie_fraction_diffuse,
        cible=cible,
        code_amont=code_serie_dhi_amont,
        libelle="DHI",
        amont=serie_dhi,
    )
    verifier_localite_amont(
        code_cible=code_serie_fraction_diffuse,
        cible=cible,
        code_amont=code_serie_ghi_amont,
        libelle="GHI",
        amont=serie_ghi,
    )

    niveaux = NiveauxEntrees()
    mesures_dhi = lire_mesures_journalieres(session, serie_dhi.serie_id, niveaux)
    mesures_ghi = lire_mesures_journalieres(session, serie_ghi.serie_id, niveaux)
    agregation = _agreger_fraction_diffuse(mesures_dhi, mesures_ghi)
    inserer_periodes(
        session,
        grandeur_code=GRANDEUR_CODE_FRACTION_DIFFUSE,
        cible=cible,
        version_formule=version_formule,
        lignes=[*agregation["lignes_annuelles"], *agregation["lignes_mensuelles"]],
        plafond=PLAFOND_CONFIANCE,
        niveaux=niveaux,
    )

    return {
        "code_serie_fraction_diffuse": code_serie_fraction_diffuse,
        "nb_annuel_insere": len(agregation["lignes_annuelles"]),
        "nb_mensuel_insere": len(agregation["lignes_mensuelles"]),
        "annees_traitees": agregation["annees_traitees"],
        "annees_skip_completude": agregation["annees_skip_completude"],
        "mois_skip_completude": agregation["mois_skip_completude"],
    }
