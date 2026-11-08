"""Fraction diffuse stockée : ratio des sommes DHI / GHI, annuel et mensuel.

```
fraction_diffuse(periode) := sum DHI(t) / sum GHI(t), t ∈ jours(periode)
```

Complétude stricte sur les jours où DHI et GHI existent tous deux.
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


class _LigneAgregeeFractionDiffuse(TypedDict):
    periode_type: str
    annee_debut: int
    annee_fin: int
    mois: int | None
    valeur: float


class _AgregationResultat(TypedDict):
    lignes_annuelles: list[_LigneAgregeeFractionDiffuse]
    lignes_mensuelles: list[_LigneAgregeeFractionDiffuse]
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

    lignes_annuelles: list[_LigneAgregeeFractionDiffuse] = []
    lignes_mensuelles: list[_LigneAgregeeFractionDiffuse] = []
    annees_skip: list[int] = []
    mois_skip: list[tuple[int, int]] = []

    for (annee, mois), couples in sorted(par_mois.items()):
        n_attendu = calendar.monthrange(annee, mois)[1]
        if len(couples) != n_attendu:
            mois_skip.append((annee, mois))
            continue
        somme_dhi = sum(c[0] for c in couples)
        somme_ghi = sum(c[1] for c in couples)
        if somme_ghi <= 0:
            mois_skip.append((annee, mois))
            continue
        lignes_mensuelles.append(
            {
                "periode_type": "mensuel",
                "annee_debut": annee,
                "annee_fin": annee,
                "mois": mois,
                "valeur": float(somme_dhi / somme_ghi),
            }
        )

    for annee, couples in sorted(par_annee.items()):
        n_attendu = 366 if calendar.isleap(annee) else 365
        if len(couples) != n_attendu:
            annees_skip.append(annee)
            continue
        somme_dhi = sum(c[0] for c in couples)
        somme_ghi = sum(c[1] for c in couples)
        if somme_ghi <= 0:
            annees_skip.append(annee)
            continue
        lignes_annuelles.append(
            {
                "periode_type": "annuel",
                "annee_debut": annee,
                "annee_fin": annee,
                "mois": None,
                "valeur": float(somme_dhi / somme_ghi),
            }
        )

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
    version_actuelle = session.execute(
        text("SELECT version_formule_actuelle FROM grandeurs_referentiel WHERE code = :code"),
        {"code": GRANDEUR_CODE_FRACTION_DIFFUSE},
    ).scalar()
    if version_actuelle is None:
        raise RuntimeError(
            f"Grandeur {GRANDEUR_CODE_FRACTION_DIFFUSE!r} introuvable dans grandeurs_referentiel."
        )
    if version_formule != int(version_actuelle):
        raise RuntimeError(
            f"Desalignement version_formule : argument={version_formule}, "
            f"version_formule_actuelle pour {GRANDEUR_CODE_FRACTION_DIFFUSE!r}="
            f"{int(version_actuelle)}."
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
        {"code": code_serie_fraction_diffuse},
    ).first()
    if serie_cible is None:
        raise RuntimeError(
            f"Serie fraction_diffuse cible {code_serie_fraction_diffuse!r} "
            "introuvable dans series_metadonnees."
        )
    if serie_cible.grandeur_code != GRANDEUR_CODE_FRACTION_DIFFUSE:
        raise RuntimeError(
            f"Serie cible {code_serie_fraction_diffuse!r} : grandeur_code="
            f"{serie_cible.grandeur_code!r}, attendu "
            f"{GRANDEUR_CODE_FRACTION_DIFFUSE!r}."
        )
    if serie_cible.methode_collecte != METHODE_COLLECTE_FRACTION_DIFFUSE:
        raise RuntimeError(
            f"Serie cible {code_serie_fraction_diffuse!r} : methode_collecte="
            f"{serie_cible.methode_collecte!r}, attendu "
            f"{METHODE_COLLECTE_FRACTION_DIFFUSE!r}."
        )

    serie_dhi = session.execute(
        text(
            """
            SELECT id AS serie_id, localite_id, grandeur_code
            FROM series_metadonnees WHERE code = :code
            """
        ),
        {"code": code_serie_dhi_amont},
    ).first()
    if serie_dhi is None:
        raise RuntimeError(f"Serie DHI amont {code_serie_dhi_amont!r} introuvable.")
    if serie_dhi.grandeur_code != GRANDEUR_CODE_DHI:
        raise RuntimeError(
            f"Serie {code_serie_dhi_amont!r} : grandeur_code="
            f"{serie_dhi.grandeur_code!r}, attendu {GRANDEUR_CODE_DHI!r}."
        )

    serie_ghi = session.execute(
        text(
            """
            SELECT id AS serie_id, localite_id, grandeur_code
            FROM series_metadonnees WHERE code = :code
            """
        ),
        {"code": code_serie_ghi_amont},
    ).first()
    if serie_ghi is None:
        raise RuntimeError(f"Serie GHI amont {code_serie_ghi_amont!r} introuvable.")
    if serie_ghi.grandeur_code != GRANDEUR_CODE_GHI:
        raise RuntimeError(
            f"Serie {code_serie_ghi_amont!r} : grandeur_code="
            f"{serie_ghi.grandeur_code!r}, attendu {GRANDEUR_CODE_GHI!r}."
        )

    localite_cible = int(serie_cible.localite_id)
    if int(serie_dhi.localite_id) != localite_cible:
        raise RuntimeError(
            f"Incoherence localite : serie cible {code_serie_fraction_diffuse!r} "
            f"localite_id={localite_cible} vs serie DHI amont "
            f"{code_serie_dhi_amont!r} localite_id={int(serie_dhi.localite_id)}."
        )
    if int(serie_ghi.localite_id) != localite_cible:
        raise RuntimeError(
            f"Incoherence localite : serie cible {code_serie_fraction_diffuse!r} "
            f"localite_id={localite_cible} vs serie GHI amont "
            f"{code_serie_ghi_amont!r} localite_id={int(serie_ghi.localite_id)}."
        )

    rows_dhi = session.execute(
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
        {"serie_id": int(serie_dhi.serie_id)},
    ).all()
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
    mesures_dhi: list[tuple[date, float]] = [(r.instant_mesure, float(r.valeur)) for r in rows_dhi]
    mesures_ghi: list[tuple[date, float]] = [(r.instant_mesure, float(r.valeur)) for r in rows_ghi]

    niveaux = NiveauxEntrees()
    for r in (*rows_dhi, *rows_ghi):
        niveaux.ajouter(r.instant_mesure, r.niveau)

    agregation = _agreger_fraction_diffuse(mesures_dhi, mesures_ghi)

    toutes_lignes: list[_LigneAgregeeFractionDiffuse] = list(agregation["lignes_annuelles"]) + list(
        agregation["lignes_mensuelles"]
    )
    if toutes_lignes:
        params: list[dict[str, Any]] = [
            {
                "grandeur_code": GRANDEUR_CODE_FRACTION_DIFFUSE,
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
        "code_serie_fraction_diffuse": code_serie_fraction_diffuse,
        "nb_annuel_insere": len(agregation["lignes_annuelles"]),
        "nb_mensuel_insere": len(agregation["lignes_mensuelles"]),
        "annees_traitees": agregation["annees_traitees"],
        "annees_skip_completude": agregation["annees_skip_completude"],
        "mois_skip_completude": agregation["mois_skip_completude"],
    }
