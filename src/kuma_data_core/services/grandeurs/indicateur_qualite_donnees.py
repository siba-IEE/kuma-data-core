"""Grandeur ``indicateur_qualite_donnees`` : score de qualité (1 à 5) d'une série.

    score_continu = 0.5 * C1 + 0.3 * C2 + 0.2 * C3

- C1, complétude : min(nb_mesures_courantes / nb_jours_attendus, 1) ;
- C2 : moyenne des ``niveau_confiance_derive`` (A = 1, B = 0,7, C = 0,4) ;
- C3 : ``sources.fiabilite`` (haute = 1, moyenne = 0,7, faible = 0,4).

Le score continu est ramené à un entier : [0, 0,2) → 1, [0,2, 0,4) → 2,
[0,4, 0,6) → 3, [0,6, 0,8) → 4, [0,8, 1] → 5. Pour une série de niveau B et de
source de fiabilité haute, le score vaut 0,5·C1 + 0,41, soit 3, 4 ou 5.

La ligne ``grandeurs_metier`` produite pointe vers la série évaluée
(``series_metadonnees_id``), pas vers une série propre à l'indicateur : son
``grandeur_code`` diffère donc de celui de la série pointée.
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

PLAFOND_CONFIANCE: NiveauConfiance = "B"
"""Plafond de confiance : méta-indicateur sur une série, au plus B."""

GRANDEUR_CODE_INDICATEUR: str = "indicateur_qualite_donnees"
METHODE_COLLECTE_INDICATEUR: str = "calcul_derive"
SOURCE_CODE_INDICATEUR: str = "kuma_calculs"

POIDS_COMPLETUDE: float = 0.5
POIDS_CONFIANCE_MOYENNE: float = 0.3
POIDS_FIABILITE_SOURCE: float = 0.2

NIVEAU_VALEUR: dict[str, float] = {"A": 1.0, "B": 0.7, "C": 0.4}
"""Valeur numérique de chaque ``niveau_confiance_derive`` (composante C2)."""

FIABILITE_VALEUR: dict[str, float] = {"haute": 1.0, "moyenne": 0.7, "faible": 0.4}
"""Valeur numérique de chaque ``sources.fiabilite`` (composante C3)."""

BORNES_BINNING: tuple[float, ...] = (0.2, 0.4, 0.6, 0.8)
"""Bornes supérieures exclusives des classes 1 à 4 ; au-delà, classe 5."""


class _CalculScoreResultat(TypedDict):
    c1_completude: float
    c2_confiance_moyenne: float
    c3_fiabilite_source: float
    score_continu: float
    score_discret: int


class CalculIndicateurResultat(TypedDict):
    """Résultat d'un appel à :func:`calculer_et_inserer_indicateur_qualite_donnees`."""

    code_serie_evaluee: str
    nb_lignes_inseres: int  # toujours 1
    score_continu: float
    score_discret: int
    c1_completude: float
    c2_confiance_moyenne: float
    c3_fiabilite_source: float
    nb_mesures_courantes: int
    nb_jours_attendus: int


def _binning_score(score_continu: float) -> int:
    """Ramène le score continu [0, 1] à un entier de 1 à 5 (voir ``BORNES_BINNING``)."""
    for bin_idx, borne_sup in enumerate(BORNES_BINNING, start=1):
        if score_continu < borne_sup:
            return bin_idx
    return 5


def _calculer_score(
    *,
    nb_mesures_courantes: int,
    nb_jours_attendus: int,
    niveaux_confiance: Sequence[str],
    fiabilite_source: str,
) -> _CalculScoreResultat:
    """Calcule les trois composantes, le score continu et le score entier.

    ``niveaux_confiance`` : niveaux dérivés des mesures courantes de la série ;
    un niveau ou une fiabilité inconnus comptent pour 0. C1 vaut 0 si
    ``nb_jours_attendus`` est nul, C2 vaut 0 sans mesure.
    """
    c1 = min(nb_mesures_courantes / nb_jours_attendus, 1.0) if nb_jours_attendus > 0 else 0.0

    if niveaux_confiance:
        somme_ponderee = sum(NIVEAU_VALEUR.get(n, 0.0) for n in niveaux_confiance)
        c2 = somme_ponderee / len(niveaux_confiance)
    else:
        c2 = 0.0

    c3 = FIABILITE_VALEUR.get(fiabilite_source, 0.0)

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
    """Nombre de jours civils du 1er janvier ``annee_debut`` au 31 décembre ``annee_fin``."""
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
    """Évalue la série désignée et insère une ligne dans ``grandeurs_metier``.

    La ligne porte ``periode_type='statique'`` et pointe vers la série évaluée.
    Son niveau de confiance est le plus bas des mesures courantes, plafonné à
    B. Fait un ``flush`` sans ``commit``.

    Lève ``RuntimeError`` si la série est introuvable ou si ``version_formule``
    diffère de ``grandeurs_referentiel.version_formule_actuelle``.
    """
    version_actuelle = session.execute(
        text("SELECT version_formule_actuelle FROM grandeurs_referentiel WHERE code = :code"),
        {"code": GRANDEUR_CODE_INDICATEUR},
    ).scalar()
    if version_actuelle is None:
        raise RuntimeError(
            f"Grandeur {GRANDEUR_CODE_INDICATEUR!r} introuvable dans grandeurs_referentiel."
        )
    if version_formule != int(version_actuelle):
        raise RuntimeError(
            f"Desalignement version_formule : argument={version_formule}, "
            f"version_formule_actuelle pour {GRANDEUR_CODE_INDICATEUR!r}={int(version_actuelle)}."
        )

    serie = session.execute(
        text(
            """
            SELECT
                sm.id AS serie_id,
                sm.localite_id,
                sm.grandeur_code AS grandeur_code_evaluee,
                sm.methode_collecte,
                s.fiabilite AS fiabilite_source
            FROM series_metadonnees sm
            JOIN sources s ON s.id = sm.source_id
            WHERE sm.code = :code
            """
        ),
        {"code": code_serie_evaluee},
    ).first()
    if serie is None:
        raise RuntimeError(
            f"Serie evaluee {code_serie_evaluee!r} introuvable dans series_metadonnees."
        )

    rows = session.execute(
        text(
            """
            SELECT niveau_confiance_derive,
                   coalesce(niveau_confiance_override, niveau_confiance_derive) AS niveau
            FROM mesures_ressource
            WHERE serie_id = :serie_id
              AND valide_au IS NULL
              AND statut <> 'deprecie'
            """
        ),
        {"serie_id": int(serie.serie_id)},
    ).all()
    niveaux_confiance: list[str] = [r.niveau_confiance_derive for r in rows]
    # L'indicateur ne peut pas être plus sûr que les mesures qu'il évalue.
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
        fiabilite_source=serie.fiabilite_source,
    )

    session.execute(
        text(
            """
            INSERT INTO grandeurs_metier (
                grandeur_code, localite_id, series_metadonnees_id,
                periode_type, annee_debut, annee_fin, mois,
                version_formule, valeur, niveau_confiance_derive
            )
            VALUES (
                :grandeur_code, :localite_id, :series_metadonnees_id,
                'statique', :annee_debut, :annee_fin, NULL,
                :version_formule, :valeur, :niveau
            )
            """
        ),
        {
            "grandeur_code": GRANDEUR_CODE_INDICATEUR,
            "localite_id": int(serie.localite_id),
            "series_metadonnees_id": int(serie.serie_id),
            "annee_debut": annee_debut,
            "annee_fin": annee_fin,
            "version_formule": version_formule,
            "valeur": score["score_discret"],
            "niveau": niveau_indicateur,
        },
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
