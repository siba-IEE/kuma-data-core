"""Grandeur ``ecart_relatif_dni_cams`` : écart inter-source sur le DNI.

Écart relatif mensuel entre le DNI de NASA POWER et celui de CAMS Radiation
(corrigé des aérosols), sur les mois communs aux deux séries :

    ecart = (nasa - cams) / cams x 100

CAMS, référence de l'écart, est au dénominateur, comme SARAH-3 dans
``ecart_relatif_referentiel`` dont ce module reprend les fonctions. Le signe
est un résultat empirique (environ -26 % en moyenne : NASA lit moins de DNI
que CAMS), pas un choix de conception. Niveau de confiance B : signal
indirect, combinaison de deux sources.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import TypedDict

from sqlalchemy.orm import Session

from kuma_data_core.services.grandeurs.referentiels import (
    _bulk_insert_grandeurs_metier,
    _calcul_ecart_relatif,
    _lire_mensuel,
)

GRANDEUR_ECART_DNI_CAMS: str = "ecart_relatif_dni_cams"
NIVEAU_CONFIANCE_DERIVE: str = "B"
VERSION_FORMULE: int = 1


class ContexteVilleEcartDniCams(TypedDict):
    """Contexte par localité pour le calcul de l'écart DNI CAMS."""

    localite_id: int
    code_serie_nasa: str
    code_serie_cams: str
    series_metadonnees_id: int


class ResultatEcartDniCams(TypedDict):
    """Résultat d'un appel à :func:`calculer_et_inserer_ecart_dni_cams`."""

    nb_insere: int


def calculer_et_inserer_ecart_dni_cams(
    *,
    session: Session,
    contextes_villes: Sequence[ContexteVilleEcartDniCams],
) -> ResultatEcartDniCams:
    """Calcule et insère l'écart relatif DNI NASA/CAMS dans ``grandeurs_metier``.

    Pour chaque localité, une ligne mensuelle par (année, mois) présent dans
    les deux séries de ``mesures_ressource_mensuelles`` ;
    ``series_metadonnees_id`` désigne la série calculée cible, qui doit déjà
    exister. Lève ``ValueError`` si une valeur CAMS est nulle. Fait un
    ``flush`` sans ``commit``.
    """
    nb_insere = 0

    for ctx in contextes_villes:
        nasa = _lire_mensuel(session, ctx["code_serie_nasa"])
        cams = _lire_mensuel(session, ctx["code_serie_cams"])

        lignes: list[dict[str, object]] = []
        for annee, mois in sorted(set(nasa) & set(cams)):
            ecart_pct = _calcul_ecart_relatif(nasa[(annee, mois)], cams[(annee, mois)])
            lignes.append(
                {
                    "grandeur_code": GRANDEUR_ECART_DNI_CAMS,
                    "localite_id": ctx["localite_id"],
                    "series_metadonnees_id": ctx["series_metadonnees_id"],
                    "periode_type": "mensuel",
                    "annee_debut": annee,
                    "annee_fin": annee,
                    "mois": mois,
                    "version_formule": VERSION_FORMULE,
                    "valeur": ecart_pct,
                    "niveau_confiance_derive": NIVEAU_CONFIANCE_DERIVE,
                }
            )
        _bulk_insert_grandeurs_metier(session, lignes)
        nb_insere += len(lignes)

    session.flush()
    return {"nb_insere": nb_insere}
