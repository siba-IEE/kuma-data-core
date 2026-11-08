"""Productible spécifique théorique stocké : ``hep(periode) * pr_theorique`` (kWh/kWc).

Lit les agrégats ``hep`` de ``grandeurs_metier``, pas les mesures GHI : la
complétude est donc celle de ``hep``.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any, TypedDict

from sqlalchemy import text
from sqlalchemy.orm import Session

from kuma_data_core.editorial.niveaux_confiance import (
    NiveauConfiance,
    calculer_niveau_confiance_derive,
)

PLAFOND_CONFIANCE: NiveauConfiance = "B"
"""Plafond de confiance : le PR théorique est une hypothèse conventionnelle, pas une mesure."""

GRANDEUR_CODE_PRODUCTIBLE: str = "productible_specifique_theorique"
METHODE_COLLECTE_PRODUCTIBLE: str = "calcul_derive"
GRANDEUR_CODE_HEP: str = "hep"

PR_THEORIQUE_DEFAUT: float = 0.8
"""PR conservateur usuel (IEC 61724-1 ; PVWatts retient 0.84)."""


class CalculProductibleResultat(TypedDict):
    """Résultat d'un appel à :func:`calculer_et_inserer_productible_specifique_theorique`."""

    code_serie_productible: str
    nb_annuel_insere: int
    nb_mensuel_insere: int
    pr_theorique_applique: float


class _LigneAgregeeProductible(TypedDict):
    periode_type: str
    annee_debut: int
    annee_fin: int
    mois: int | None
    valeur: float


def _appliquer_pr_theorique(valeur_hep: float, pr_theorique: float) -> float:
    """HEP (h_eq) x PR ; à 1 kW/m² STC, h_eq et kWh/kWc coïncident."""
    return float(valeur_hep) * float(pr_theorique)


def calculer_et_inserer_productible_specifique_theorique(
    *,
    session: Session,
    code_serie_productible: str,
    code_serie_hep_amont: str,
    pr_theorique: float = PR_THEORIQUE_DEFAUT,
    version_formule: int = 1,
) -> CalculProductibleResultat:
    """Insère le productible annuel et mensuel tiré des lignes ``hep`` courantes.

    ``RuntimeError`` si une série est introuvable ou non conforme, si les
    localités diffèrent, ou si ``version_formule`` diffère du référentiel.
    """
    version_actuelle = session.execute(
        text("SELECT version_formule_actuelle FROM grandeurs_referentiel WHERE code = :code"),
        {"code": GRANDEUR_CODE_PRODUCTIBLE},
    ).scalar()
    if version_actuelle is None:
        raise RuntimeError(
            f"Grandeur {GRANDEUR_CODE_PRODUCTIBLE!r} introuvable dans grandeurs_referentiel."
        )
    if version_formule != int(version_actuelle):
        raise RuntimeError(
            f"Desalignement version_formule : argument={version_formule}, "
            f"version_formule_actuelle pour {GRANDEUR_CODE_PRODUCTIBLE!r}={int(version_actuelle)}."
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
        {"code": code_serie_productible},
    ).first()
    if serie_cible is None:
        raise RuntimeError(f"Serie productible cible {code_serie_productible!r} introuvable.")
    if serie_cible.grandeur_code != GRANDEUR_CODE_PRODUCTIBLE:
        raise RuntimeError(
            f"Serie cible {code_serie_productible!r} : grandeur_code="
            f"{serie_cible.grandeur_code!r}, attendu {GRANDEUR_CODE_PRODUCTIBLE!r}."
        )
    if serie_cible.methode_collecte != METHODE_COLLECTE_PRODUCTIBLE:
        raise RuntimeError(
            f"Serie cible {code_serie_productible!r} : methode_collecte="
            f"{serie_cible.methode_collecte!r}, attendu {METHODE_COLLECTE_PRODUCTIBLE!r}."
        )

    serie_hep = session.execute(
        text(
            "SELECT id AS serie_id, localite_id, grandeur_code "
            "FROM series_metadonnees WHERE code = :code"
        ),
        {"code": code_serie_hep_amont},
    ).first()
    if serie_hep is None:
        raise RuntimeError(f"Serie HEP amont {code_serie_hep_amont!r} introuvable.")
    if serie_hep.grandeur_code != GRANDEUR_CODE_HEP:
        raise RuntimeError(
            f"Serie {code_serie_hep_amont!r} : grandeur_code="
            f"{serie_hep.grandeur_code!r}, attendu {GRANDEUR_CODE_HEP!r}."
        )

    localite_cible = int(serie_cible.localite_id)
    if int(serie_hep.localite_id) != localite_cible:
        raise RuntimeError(
            f"Incoherence localite : serie cible {code_serie_productible!r} "
            f"localite_id={localite_cible} vs serie HEP amont "
            f"{code_serie_hep_amont!r} localite_id={int(serie_hep.localite_id)}."
        )

    # Même filtre de version courante que v_grandeurs_metier_courantes.
    rows_hep = session.execute(
        text(
            """
            SELECT
                gm.periode_type, gm.annee_debut, gm.annee_fin, gm.mois, gm.valeur,
                coalesce(gm.niveau_confiance_override, gm.niveau_confiance_derive) AS niveau
            FROM grandeurs_metier gm
            JOIN grandeurs_referentiel gr ON gr.code = gm.grandeur_code
            WHERE gm.series_metadonnees_id = :serie_id
              AND gm.grandeur_code = :grandeur_code
              AND gm.valide_au IS NULL
              AND gm.statut <> 'deprecie'
              AND gm.version_formule = gr.version_formule_actuelle
            ORDER BY gm.annee_debut, gm.mois NULLS FIRST
            """
        ),
        {
            "serie_id": int(serie_hep.serie_id),
            "grandeur_code": GRANDEUR_CODE_HEP,
        },
    ).all()

    if not rows_hep:
        raise RuntimeError(
            f"Aucune ligne HEP courante trouvee pour la serie {code_serie_hep_amont!r}. "
            "Verifier que 1-5D-iii (migration 027) a bien ete applique."
        )

    lignes_a_inserer: list[_LigneAgregeeProductible] = [
        {
            "periode_type": r.periode_type,
            "annee_debut": int(r.annee_debut),
            "annee_fin": int(r.annee_fin),
            "mois": int(r.mois) if r.mois is not None else None,
            "valeur": _appliquer_pr_theorique(float(r.valeur), pr_theorique),
        }
        for r in rows_hep
    ]

    nb_annuel = sum(1 for ligne in lignes_a_inserer if ligne["periode_type"] == "annuel")
    nb_mensuel = sum(1 for ligne in lignes_a_inserer if ligne["periode_type"] == "mensuel")

    params: list[dict[str, Any]] = [
        {
            "grandeur_code": GRANDEUR_CODE_PRODUCTIBLE,
            "localite_id": localite_cible,
            "series_metadonnees_id": int(serie_cible.serie_id),
            "periode_type": ligne["periode_type"],
            "annee_debut": ligne["annee_debut"],
            "annee_fin": ligne["annee_fin"],
            "mois": ligne["mois"],
            "version_formule": version_formule,
            "valeur": ligne["valeur"],
            # Règle P : chaque ligne prend le niveau de la ligne HEP dont elle est tirée
            "niveau_confiance_derive": calculer_niveau_confiance_derive(
                methode_collecte=serie_cible.methode_collecte,
                fiabilite_source=serie_cible.fiabilite_source,
                plafond=PLAFOND_CONFIANCE,
                niveaux_entrees={r.niveau},
            ),
        }
        for ligne, r in zip(lignes_a_inserer, rows_hep, strict=True)
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
        "code_serie_productible": code_serie_productible,
        "nb_annuel_insere": nb_annuel,
        "nb_mensuel_insere": nb_mensuel,
        "pr_theorique_applique": float(pr_theorique),
    }


# Re-export pour cohérence avec les autres modules services/grandeurs/
__all__: Sequence[str] = (
    "GRANDEUR_CODE_PRODUCTIBLE",
    "METHODE_COLLECTE_PRODUCTIBLE",
    "PR_THEORIQUE_DEFAUT",
    "CalculProductibleResultat",
    "_appliquer_pr_theorique",
    "calculer_et_inserer_productible_specifique_theorique",
)
