"""Productible spécifique théorique stocké : ``hep(periode) * pr_theorique`` (kWh/kWc).

Lit les agrégats ``hep`` de ``grandeurs_metier``, pas les mesures GHI : la
complétude est donc celle de ``hep``.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import TypedDict

from sqlalchemy import text
from sqlalchemy.orm import Session

from kuma_data_core.editorial.niveaux_confiance import NiveauConfiance
from kuma_data_core.services.grandeurs._commun import (
    LignePeriode,
    inserer_lignes_grandeurs_metier,
    ligne_grandeur_metier,
    resoudre_serie_amont,
    resoudre_serie_cible,
    verifier_localite_amont,
    verifier_version_formule,
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
    verifier_version_formule(session, GRANDEUR_CODE_PRODUCTIBLE, version_formule)
    cible = resoudre_serie_cible(
        session,
        code_serie_productible,
        message_introuvable=f"Serie productible cible {code_serie_productible!r} introuvable.",
        grandeur_attendue=GRANDEUR_CODE_PRODUCTIBLE,
        methode_attendue=METHODE_COLLECTE_PRODUCTIBLE,
    )
    serie_hep = resoudre_serie_amont(
        session, code_serie_hep_amont, libelle="HEP", grandeur_attendue=GRANDEUR_CODE_HEP
    )
    verifier_localite_amont(
        code_cible=code_serie_productible,
        cible=cible,
        code_amont=code_serie_hep_amont,
        libelle="HEP",
        amont=serie_hep,
    )

    rows_hep = session.execute(
        text(
            """
            SELECT
                gm.periode_type, gm.annee_debut, gm.annee_fin, gm.mois, gm.valeur,
                coalesce(gm.niveau_confiance_override, gm.niveau_confiance_derive) AS niveau
            FROM v_grandeurs_metier_courantes gm
            WHERE gm.series_metadonnees_id = :serie_id
              AND gm.grandeur_code = :grandeur_code
            ORDER BY gm.annee_debut, gm.mois NULLS FIRST
            """
        ),
        {
            "serie_id": serie_hep.serie_id,
            "grandeur_code": GRANDEUR_CODE_HEP,
        },
    ).all()

    if not rows_hep:
        raise RuntimeError(
            f"Aucune ligne HEP courante trouvee pour la serie {code_serie_hep_amont!r}. "
            "Verifier que 1-5D-iii (migration 027) a bien ete applique."
        )

    lignes_a_inserer: list[LignePeriode] = [
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

    inserer_lignes_grandeurs_metier(
        session,
        [
            ligne_grandeur_metier(
                grandeur_code=GRANDEUR_CODE_PRODUCTIBLE,
                cible=cible,
                version_formule=version_formule,
                ligne=ligne,
                plafond=PLAFOND_CONFIANCE,
                # Règle P : chaque ligne prend le niveau de la ligne HEP dont elle est tirée
                niveaux_entrees={r.niveau},
            )
            for ligne, r in zip(lignes_a_inserer, rows_hep, strict=True)
        ],
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
