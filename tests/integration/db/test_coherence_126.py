"""Commentaires de ``degenerescence_pixel`` : en clair, et d'accord avec la valeur. Lecture seule.

Le commentaire est servi tel quel par l'API (``degenerescence.note``). Il suit
l'un de trois modèles, et ce qu'il affirme (nombre et codes des localités de la
même cellule) doit correspondre à la valeur de la ligne.
"""

from __future__ import annotations

import re

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

from tests.jargon import correspondances

pytestmark = pytest.mark.integration

_FINALE = (
    " Constat exact (identité observée entre séries, sans modèle), en confiance B : la "
    "confiance A est réservée aux données validées par des mesures au sol, et l'échelle A/B/C "
    "qualifie la fiabilité d'une mesure, pas la certitude d'un constat de structure."
)
_PARTAGEE = re.compile(
    r"Cellule partagée : ce point tombe dans la même cellule .+ \(.+\) que "
    r"(?P<n>\d+) (?P<accord>autre point|autres points) \((?P<codes>[a-z0-9_, ]+)\)\. "
    r"Leurs séries (?P<grandeur>\w+) sont identiques : ne pas les présenter comme des mesures "
    r"indépendantes\."
)
_INTERPOLEE = re.compile(
    r"Source interpolée au point \(.+, (?P<res>.+)\) : les valeurs diffèrent d'un point à "
    r"l'autre par construction\. La résolution réelle reste de (?P=res) : la finesse apparente "
    r"sous la maille est illusoire \(limite de résolution, pas une dégénérescence mesurable\)\."
)
_SEUL = re.compile(
    r"Point résolu sur .+ \(.+\) : aucun autre point ne partage la cellule pour "
    r"(?P<grandeur>\w+)\."
)


def _lignes(db_session: Session) -> list[tuple[str, str, float, str]]:
    lignes = (
        db_session.execute(
            text(
                """
                SELECT l.code, sm.grandeur_code, gm.valeur, gm.commentaire_editorial
                FROM grandeurs_metier gm
                JOIN localites l ON l.id = gm.localite_id
                JOIN series_metadonnees sm ON sm.id = gm.series_metadonnees_id
                WHERE gm.grandeur_code = 'degenerescence_pixel'
                """
            )
        )
        .tuples()
        .all()
    )
    assert lignes
    return list(lignes)


def test_aucun_commentaire_ne_porte_de_vocabulaire_de_chantier(db_session: Session) -> None:
    fautifs = {
        commentaire: trouves
        for _, _, _, commentaire in _lignes(db_session)
        if (trouves := correspondances(commentaire or ""))
    }
    assert not fautifs


def test_chaque_commentaire_suit_un_modele_et_s_accorde_avec_la_valeur(
    db_session: Session,
) -> None:
    codes_connus = set(db_session.execute(text("SELECT code FROM localites")).scalars())
    modeles_vus = set()
    for code, grandeur, valeur, commentaire in _lignes(db_session):
        assert commentaire is not None and commentaire.endswith(_FINALE), code
        base = commentaire.removesuffix(_FINALE)
        if m := _PARTAGEE.fullmatch(base):
            modeles_vus.add("partagée")
            voisins = m["codes"].split(", ")
            assert int(m["n"]) == len(voisins) == int(valeur), commentaire
            assert m["accord"] == ("autre point" if len(voisins) == 1 else "autres points")
            assert set(voisins) <= codes_connus - {code}, commentaire
            assert m["grandeur"] == grandeur
        elif m := _SEUL.fullmatch(base):
            modeles_vus.add("seul")
            assert int(valeur) == 0 and m["grandeur"] == grandeur, commentaire
        else:
            modeles_vus.add("interpolée")
            assert _INTERPOLEE.fullmatch(base), f"{code} : commentaire hors modèle : {commentaire}"
            assert int(valeur) == 0, commentaire
    assert modeles_vus == {"partagée", "seul", "interpolée"}
