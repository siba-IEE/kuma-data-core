"""HEP (heures équivalentes pleines), annuelles et mensuelles, depuis une série GHI journalière.

HEP_jour = GHI_jour : 1 kWh/m²/j équivaut à 1 h à 1 kW/m² (STC) ; mois et
année sont des sommes. Complétude stricte : pas de ligne pour une période à
laquelle manque un seul jour civil, sans imputation. Confiance par la règle
P sur les mesures de la période, jusqu'à A (somme exacte, ADR-0008).
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Sequence
from datetime import date
from typing import TypedDict

from sqlalchemy import text
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
    resoudre_serie_cible,
    verifier_version_formule,
)

PLAFOND_CONFIANCE: NiveauConfiance = "A"
"""Plafond de confiance : somme exacte des mesures GHI, sans modèle ni hypothèse."""

GRANDEUR_CODE_HEP: str = "hep"
"""Code de la grandeur dans ``grandeurs_referentiel``."""

METHODE_COLLECTE_HEP: str = "calcul_derive"
"""Méthode attendue sur la série HEP cible (stockage dans ``grandeurs_metier``)."""


class CalculHEPResultat(TypedDict):
    """Résultat d'un appel à :func:`calculer_et_inserer_hep`."""

    code_serie_hep: str
    nb_annuel_insere: int
    nb_mensuel_insere: int
    annees_traitees: tuple[int, ...]
    annees_skip_completude: tuple[int, ...]
    mois_skip_completude: tuple[tuple[int, int], ...]


class _AgregationResultat(TypedDict):
    """Sortie de :func:`_agreger_hep_journaliers`."""

    lignes_annuelles: list[LignePeriode]
    lignes_mensuelles: list[LignePeriode]
    annees_traitees: tuple[int, ...]
    annees_skip_completude: tuple[int, ...]
    mois_skip_completude: tuple[tuple[int, int], ...]


def _agreger_hep_journaliers(
    mesures_journalieres: Sequence[tuple[date, float]],
) -> _AgregationResultat:
    """Agrège des ``(date, GHI kWh/m²/j)`` en HEP annuelles et mensuelles complètes.

    Les périodes incomplètes sont listées à part.
    """
    valeurs_mensuelles: dict[tuple[int, int], list[float]] = defaultdict(list)
    valeurs_annuelles: dict[int, list[float]] = defaultdict(list)

    for instant, valeur in mesures_journalieres:
        valeurs_mensuelles[(instant.year, instant.month)].append(valeur)
        valeurs_annuelles[instant.year].append(valeur)

    lignes_annuelles: list[LignePeriode] = []
    lignes_mensuelles: list[LignePeriode] = []
    annees_skip: list[int] = []
    mois_skip: list[tuple[int, int]] = []

    for (annee, mois), valeurs in sorted(valeurs_mensuelles.items()):
        if len(valeurs) == jours_attendus_mois(annee, mois):
            lignes_mensuelles.append(ligne_mensuelle(annee, mois, float(sum(valeurs))))
        else:
            mois_skip.append((annee, mois))

    for annee, valeurs in sorted(valeurs_annuelles.items()):
        if len(valeurs) == jours_attendus_annee(annee):
            lignes_annuelles.append(ligne_annuelle(annee, float(sum(valeurs))))
        else:
            annees_skip.append(annee)

    return {
        "lignes_annuelles": lignes_annuelles,
        "lignes_mensuelles": lignes_mensuelles,
        "annees_traitees": tuple(sorted(valeurs_annuelles.keys())),
        "annees_skip_completude": tuple(annees_skip),
        "mois_skip_completude": tuple(mois_skip),
    }


def calculer_et_inserer_hep(
    *,
    session: Session,
    code_serie_hep: str,
    code_serie_ghi_amont: str,
    version_formule: int = 1,
) -> CalculHEPResultat:
    """Calcule et insère les HEP depuis les mesures GHI courantes (flush, sans commit).

    ``RuntimeError`` si une série est introuvable, si la cible n'est pas
    ``hep``/``calcul_derive``, si les localités diffèrent, ou si
    ``version_formule`` diffère de la version du référentiel.
    """
    verifier_version_formule(session, GRANDEUR_CODE_HEP, version_formule)
    cible = resoudre_serie_cible(
        session,
        code_serie_hep,
        message_introuvable=(
            f"Serie HEP cible {code_serie_hep!r} introuvable dans series_metadonnees."
        ),
        grandeur_attendue=GRANDEUR_CODE_HEP,
        methode_attendue=METHODE_COLLECTE_HEP,
    )

    # Message et contrôle propres à HEP : la grandeur de la série amont n'est pas vérifiée.
    serie_ghi = session.execute(
        text(
            """
            SELECT
                sm.id AS serie_id,
                sm.localite_id,
                sm.grandeur_code
            FROM series_metadonnees sm
            WHERE sm.code = :code
            """
        ),
        {"code": code_serie_ghi_amont},
    ).first()
    if serie_ghi is None:
        raise RuntimeError(
            f"Serie GHI amont {code_serie_ghi_amont!r} introuvable dans series_metadonnees."
        )
    if int(serie_ghi.localite_id) != cible.localite_id:
        raise RuntimeError(
            f"Incoherence localite entre serie HEP {code_serie_hep!r} "
            f"(localite_id={cible.localite_id}) et serie GHI amont "
            f"{code_serie_ghi_amont!r} (localite_id={int(serie_ghi.localite_id)})."
        )

    niveaux = NiveauxEntrees()
    mesures_journalieres = lire_mesures_journalieres(session, int(serie_ghi.serie_id), niveaux)
    agregation = _agreger_hep_journaliers(mesures_journalieres)
    inserer_periodes(
        session,
        grandeur_code=GRANDEUR_CODE_HEP,
        cible=cible,
        version_formule=version_formule,
        lignes=[*agregation["lignes_annuelles"], *agregation["lignes_mensuelles"]],
        plafond=PLAFOND_CONFIANCE,
        niveaux=niveaux,
    )

    return {
        "code_serie_hep": code_serie_hep,
        "nb_annuel_insere": len(agregation["lignes_annuelles"]),
        "nb_mensuel_insere": len(agregation["lignes_mensuelles"]),
        "annees_traitees": agregation["annees_traitees"],
        "annees_skip_completude": agregation["annees_skip_completude"],
        "mois_skip_completude": agregation["mois_skip_completude"],
    }
