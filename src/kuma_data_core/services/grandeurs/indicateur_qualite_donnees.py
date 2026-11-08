"""Score qualité 1-5 d'une série brute, inséré dans ``grandeurs_metier``.

```
score = 0.5 * C1 + 0.3 * C2 + 0.2 * C3
C1 = min(nb_mesures_courantes / nb_jours_attendus, 1)   # complétude
C2 = moyenne des niveaux (A=1, B=0.7, C=0.4)
C3 = sources.fiabilite (haute=1, moyenne=0.7, faible=0.4)
```

Classes ``[0, 0.2) → 1`` ... ``[0.8, 1] → 5``. Pour NASA POWER (B, haute),
score = 0.5·C1 + 0.41, donc 3 à 5. La ligne pointe vers la série évaluée,
pas vers une série calculée : son ``grandeur_code`` diffère de celui de la
série.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import TypedDict

from sqlalchemy import text
from sqlalchemy.orm import Session

from kuma_data_core.editorial.niveaux_confiance import (
    NiveauConfiance,
    propager_niveau_confiance,
)
from kuma_data_core.editorial.statuts import filtre_mesure_utilisable
from kuma_data_core.services.grandeurs._commun import (
    inserer_lignes_grandeurs_metier,
    resoudre_serie_cible,
    verifier_version_formule,
)

PLAFOND_CONFIANCE: NiveauConfiance = "B"
"""Méta-indicateur sur une série : au plus B."""

GRANDEUR_CODE_INDICATEUR: str = "indicateur_qualite_donnees"

POIDS_COMPLETUDE: float = 0.5
POIDS_CONFIANCE_MOYENNE: float = 0.3
POIDS_FIABILITE_SOURCE: float = 0.2

NIVEAU_VALEUR: dict[str, float] = {"A": 1.0, "B": 0.7, "C": 0.4}
"""Mapping niveau_confiance_derive -> valeur numerique pour la composante C2."""

FIABILITE_VALEUR: dict[str, float] = {"haute": 1.0, "moyenne": 0.7, "faible": 0.4}
"""Mapping sources.fiabilite -> valeur numerique pour la composante C3."""

BORNES_BINNING: tuple[float, ...] = (0.2, 0.4, 0.6, 0.8)
"""Bornes hautes exclusives des classes 1 à 4 ; la classe 5 inclut 1.0."""


class _CalculScoreResultat(TypedDict):
    c1_completude: float
    c2_confiance_moyenne: float
    c3_fiabilite_source: float
    score_continu: float
    score_discret: int


class CalculIndicateurResultat(TypedDict):
    """Resultat d'un appel a :func:`calculer_et_inserer_indicateur_qualite_donnees`."""

    code_serie_evaluee: str
    nb_lignes_inseres: int  # toujours 0 ou 1
    score_continu: float
    score_discret: int
    c1_completude: float
    c2_confiance_moyenne: float
    c3_fiabilite_source: float
    nb_mesures_courantes: int
    nb_jours_attendus: int


def _binning_score(score_continu: float) -> int:
    """Score continu [0, 1] -> classe 1-5."""
    for bin_idx, borne_sup in enumerate(BORNES_BINNING, start=1):
        if score_continu < borne_sup:
            return bin_idx
    return 5


def _calculer_score(
    *,
    nb_mesures_courantes: int,
    nb_jours_attendus: int,
    niveaux_confiance: Sequence[str],
    fiabilite_source: str | None,
) -> _CalculScoreResultat:
    """Composantes C1-C3, score continu et classe (pur)."""
    c1 = min(nb_mesures_courantes / nb_jours_attendus, 1.0) if nb_jours_attendus > 0 else 0.0

    if niveaux_confiance:
        somme_ponderee = sum(NIVEAU_VALEUR.get(n, 0.0) for n in niveaux_confiance)
        c2 = somme_ponderee / len(niveaux_confiance)
    else:
        c2 = 0.0

    c3 = 0.0 if fiabilite_source is None else FIABILITE_VALEUR.get(fiabilite_source, 0.0)

    score_continu = (
        POIDS_COMPLETUDE * c1 + POIDS_CONFIANCE_MOYENNE * c2 + POIDS_FIABILITE_SOURCE * c3
    )
    score_discret = _binning_score(score_continu)

    return {
        "c1_completude": c1,
        "c2_confiance_moyenne": c2,
        "c3_fiabilite_source": c3,
        "score_continu": score_continu,
        "score_discret": score_discret,
    }


def _nb_jours_civils_plage(annee_debut: int, annee_fin: int) -> int:
    """Compte le nombre de jours civils sur [annee_debut, annee_fin] inclusifs."""
    from datetime import date

    debut = date(annee_debut, 1, 1)
    fin = date(annee_fin, 12, 31)
    return (fin - debut).days + 1


def calculer_et_inserer_indicateur_qualite_donnees(
    *,
    session: Session,
    code_serie_evaluee: str,
    annee_debut: int = 2021,
    annee_fin: int = 2025,
    version_formule: int = 1,
) -> CalculIndicateurResultat:
    """Évalue la série et insère une ligne ``periode_type='statique'`` pointant vers elle.

    ``RuntimeError`` si ``version_formule`` diffère de la version du
    référentiel, ou si la série ou sa source est introuvable.
    """
    verifier_version_formule(session, GRANDEUR_CODE_INDICATEUR, version_formule)
    # Pas de contrôle de grandeur ni de méthode : la série évaluée est une série brute.
    serie = resoudre_serie_cible(
        session,
        code_serie_evaluee,
        message_introuvable=(
            f"Serie evaluee {code_serie_evaluee!r} introuvable dans series_metadonnees."
        ),
    )

    rows = session.execute(
        text(
            f"""
            SELECT niveau_confiance_derive,
                   coalesce(niveau_confiance_override, niveau_confiance_derive) AS niveau
            FROM mesures_ressource
            WHERE serie_id = :serie_id
              AND {filtre_mesure_utilisable()}
            """
        ),
        {"serie_id": serie.serie_id},
    ).all()
    niveaux_confiance: list[str] = [r.niveau_confiance_derive for r in rows]
    # Règle P : l'indicateur ne peut pas être plus sûr que les mesures qu'il évalue
    niveau_indicateur = (
        propager_niveau_confiance((r.niveau for r in rows), plafond=PLAFOND_CONFIANCE)
        if rows
        else "B"
    )
    nb_mesures_courantes = len(niveaux_confiance)
    nb_jours_attendus = _nb_jours_civils_plage(annee_debut, annee_fin)

    score = _calculer_score(
        nb_mesures_courantes=nb_mesures_courantes,
        nb_jours_attendus=nb_jours_attendus,
        niveaux_confiance=niveaux_confiance,
        fiabilite_source=serie.confiance.fiabilite_source,
    )

    inserer_lignes_grandeurs_metier(
        session,
        [
            {
                "grandeur_code": GRANDEUR_CODE_INDICATEUR,
                "localite_id": serie.localite_id,
                "series_metadonnees_id": serie.serie_id,
                "periode_type": "statique",
                "annee_debut": annee_debut,
                "annee_fin": annee_fin,
                "mois": None,
                "version_formule": version_formule,
                "valeur": score["score_discret"],
                "niveau_confiance_derive": niveau_indicateur,
            }
        ],
    )
    session.flush()

    return {
        "code_serie_evaluee": code_serie_evaluee,
        "nb_lignes_inseres": 1,
        "score_continu": score["score_continu"],
        "score_discret": score["score_discret"],
        "c1_completude": score["c1_completude"],
        "c2_confiance_moyenne": score["c2_confiance_moyenne"],
        "c3_fiabilite_source": score["c3_fiabilite_source"],
        "nb_mesures_courantes": nb_mesures_courantes,
        "nb_jours_attendus": nb_jours_attendus,
    }
