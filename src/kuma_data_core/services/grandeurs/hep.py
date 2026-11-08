"""HEP (heures équivalentes pleines), annuelles et mensuelles, depuis une série GHI journalière.

HEP_jour = GHI_jour : 1 kWh/m²/j équivaut à 1 h à 1 kW/m² (STC) ; mois et
année sont des sommes. Complétude stricte : pas de ligne pour une période à
laquelle manque un seul jour civil, sans imputation. Confiance par la règle
P sur les mesures de la période, jusqu'à A (somme exacte, ADR-0008).
"""

from __future__ import annotations

import calendar
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
from kuma_data_core.editorial.statuts import filtre_mesure_utilisable

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


class _LigneAgregeeHEP(TypedDict):
    """Ligne HEP agrégée (intermédiaire), avant matérialisation INSERT."""

    periode_type: str
    annee_debut: int
    annee_fin: int
    mois: int | None
    valeur: float


class _AgregationResultat(TypedDict):
    """Sortie de :func:`_agreger_hep_journaliers`."""

    lignes_annuelles: list[_LigneAgregeeHEP]
    lignes_mensuelles: list[_LigneAgregeeHEP]
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

    lignes_annuelles: list[_LigneAgregeeHEP] = []
    lignes_mensuelles: list[_LigneAgregeeHEP] = []
    annees_skip: list[int] = []
    mois_skip: list[tuple[int, int]] = []

    for (annee, mois), valeurs in sorted(valeurs_mensuelles.items()):
        n_jours_attendus = calendar.monthrange(annee, mois)[1]
        if len(valeurs) == n_jours_attendus:
            lignes_mensuelles.append(
                {
                    "periode_type": "mensuel",
                    "annee_debut": annee,
                    "annee_fin": annee,
                    "mois": mois,
                    "valeur": float(sum(valeurs)),
                }
            )
        else:
            mois_skip.append((annee, mois))

    for annee, valeurs in sorted(valeurs_annuelles.items()):
        n_jours_attendus = 366 if calendar.isleap(annee) else 365
        if len(valeurs) == n_jours_attendus:
            lignes_annuelles.append(
                {
                    "periode_type": "annuel",
                    "annee_debut": annee,
                    "annee_fin": annee,
                    "mois": None,
                    "valeur": float(sum(valeurs)),
                }
            )
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
    version_actuelle = session.execute(
        text("SELECT version_formule_actuelle FROM grandeurs_referentiel WHERE code = :code"),
        {"code": GRANDEUR_CODE_HEP},
    ).scalar()
    if version_actuelle is None:
        raise RuntimeError(
            f"Grandeur {GRANDEUR_CODE_HEP!r} introuvable dans grandeurs_referentiel."
        )
    if version_formule != int(version_actuelle):
        raise RuntimeError(
            f"Desalignement version_formule : argument={version_formule}, "
            f"version_formule_actuelle pour {GRANDEUR_CODE_HEP!r}="
            f"{int(version_actuelle)}."
        )

    serie_hep = session.execute(
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
        {"code": code_serie_hep},
    ).first()
    if serie_hep is None:
        raise RuntimeError(
            f"Serie HEP cible {code_serie_hep!r} introuvable dans series_metadonnees."
        )
    if serie_hep.grandeur_code != GRANDEUR_CODE_HEP:
        raise RuntimeError(
            f"Serie cible {code_serie_hep!r} : grandeur_code="
            f"{serie_hep.grandeur_code!r}, attendu {GRANDEUR_CODE_HEP!r}."
        )
    if serie_hep.methode_collecte != METHODE_COLLECTE_HEP:
        raise RuntimeError(
            f"Serie cible {code_serie_hep!r} : methode_collecte="
            f"{serie_hep.methode_collecte!r}, attendu "
            f"{METHODE_COLLECTE_HEP!r}."
        )

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
    if int(serie_ghi.localite_id) != int(serie_hep.localite_id):
        raise RuntimeError(
            f"Incoherence localite entre serie HEP {code_serie_hep!r} "
            f"(localite_id={int(serie_hep.localite_id)}) et serie GHI amont "
            f"{code_serie_ghi_amont!r} (localite_id={int(serie_ghi.localite_id)})."
        )

    rows_ghi = session.execute(
        text(
            f"""
            SELECT instant_mesure, valeur,
                   coalesce(niveau_confiance_override, niveau_confiance_derive) AS niveau
            FROM mesures_ressource
            WHERE serie_id = :serie_id
              AND {filtre_mesure_utilisable()}
            ORDER BY instant_mesure
            """
        ),
        {"serie_id": int(serie_ghi.serie_id)},
    ).all()
    mesures_journalieres: list[tuple[date, float]] = [
        (row.instant_mesure, float(row.valeur)) for row in rows_ghi
    ]

    niveaux = NiveauxEntrees()
    for r in rows_ghi:
        niveaux.ajouter(r.instant_mesure, r.niveau)

    agregation = _agreger_hep_journaliers(mesures_journalieres)

    # statut, validité, override, commentaire et audit : server_defaults.
    toutes_lignes: list[_LigneAgregeeHEP] = list(agregation["lignes_annuelles"]) + list(
        agregation["lignes_mensuelles"]
    )
    if toutes_lignes:
        params: list[dict[str, Any]] = [
            {
                "grandeur_code": GRANDEUR_CODE_HEP,
                "localite_id": int(serie_hep.localite_id),
                "series_metadonnees_id": int(serie_hep.serie_id),
                "periode_type": ligne["periode_type"],
                "annee_debut": ligne["annee_debut"],
                "annee_fin": ligne["annee_fin"],
                "mois": ligne["mois"],
                "version_formule": version_formule,
                "valeur": ligne["valeur"],
                "niveau_confiance_derive": calculer_niveau_confiance_derive(
                    methode_collecte=serie_hep.methode_collecte,
                    fiabilite_source=serie_hep.fiabilite_source,
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
        "code_serie_hep": code_serie_hep,
        "nb_annuel_insere": len(agregation["lignes_annuelles"]),
        "nb_mensuel_insere": len(agregation["lignes_mensuelles"]),
        "annees_traitees": agregation["annees_traitees"],
        "annees_skip_completude": agregation["annees_skip_completude"],
        "mois_skip_completude": agregation["mois_skip_completude"],
    }
