"""Écart relatif mensuel du DNI ``(nasa - cams) / cams x 100``, 2004-2020.

CAMS Radiation (DNI corrigé des aérosols) sert de référence au dénominateur.
Le signe est un constat (NASA lit en moyenne 26 % de DNI en moins), pas un
choix. Confiance ``B`` : signal indirect. Calcul depuis la base, sans réseau.
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

# === Constantes module =====================================================

GRANDEUR_ECART_DNI_CAMS: str = "ecart_relatif_dni_cams"
NIVEAU_CONFIANCE_DERIVE: str = "B"
VERSION_FORMULE: int = 1


# === Types ================================================================


class ContexteVilleEcartDniCams(TypedDict):
    """Contexte par localité pour le calcul de l'écart DNI CAMS."""

    localite_id: int
    code_serie_nasa: str
    code_serie_cams: str
    series_metadonnees_id: int


class ResultatEcartDniCams(TypedDict):
    """Résultat d'un appel à :func:`calculer_et_inserer_ecart_dni_cams`."""

    nb_insere: int


# === Orchestrateur I/O ====================================================


def calculer_et_inserer_ecart_dni_cams(
    *,
    session: Session,
    contextes_villes: Sequence[ContexteVilleEcartDniCams],
) -> ResultatEcartDniCams:
    """Insère une ligne par mois commun aux deux séries (flush, sans commit).

    CAMS n'a pas 2004-01 : seuls les mois présents des deux côtés sont calculés.
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
