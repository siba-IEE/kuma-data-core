"""Les textes servis par l'API ne portent pas de vocabulaire de chantier interne.

Sont couverts, sans base de données : le document OpenAPI, les mises en garde
renvoyées dans le champ ``limite`` et les messages d'erreur des routes ``/v1``.
"""

from __future__ import annotations

import ast
import inspect
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import get_args

import pytest

from kuma_data_core.api.main import app
from kuma_data_core.api.v1 import grandeurs as routes_grandeurs
from kuma_data_core.api.v1.schemas.grandeurs import ModeCorrectionPR
from kuma_data_core.services.grandeurs import pr_realiste, soiling_hsu
from kuma_data_core.services.grandeurs.ghi_exceedance import PAIRES_COLOCALISEES_D29
from tests.jargon import A_ADMETTRE, A_DETECTER, correspondances

pytestmark = pytest.mark.unit

_DOSSIER_ROUTES = Path(inspect.getfile(routes_grandeurs)).parent


def _chaines(noeud: object, chemin: str = "") -> Iterator[tuple[str, str]]:
    """Toutes les chaînes (clés comprises) d'un document JSON, avec leur chemin."""
    if isinstance(noeud, dict):
        for cle, valeur in noeud.items():
            yield f"{chemin}/{cle} (clé)", str(cle)
            yield from _chaines(valeur, f"{chemin}/{cle}")
    elif isinstance(noeud, list):
        for indice, valeur in enumerate(noeud):
            yield from _chaines(valeur, f"{chemin}/{indice}")
    elif isinstance(noeud, str):
        yield chemin, noeud


def _fautifs(textes: dict[str, str]) -> dict[str, list[str]]:
    return {nom: correspondances(t) for nom, t in textes.items() if correspondances(t)}


@pytest.mark.parametrize("texte", A_DETECTER)
def test_motif_detecte_le_vocabulaire_interne(texte: str) -> None:
    assert correspondances(texte), f"non détecté : {texte!r}"


@pytest.mark.parametrize("texte", A_ADMETTRE)
def test_motif_admet_le_vocabulaire_public(texte: str) -> None:
    assert correspondances(texte) == []


def test_openapi_sans_vocabulaire_interne() -> None:
    document = app.openapi()
    textes = dict(_chaines(document))
    # Garde contre un parcours vide : le document décrit bien les routes /v1.
    assert any(chemin.startswith("/paths//v1/grandeurs/") for chemin in textes)
    assert _fautifs(textes) == {}


def test_mises_en_garde_des_services_sans_vocabulaire_interne() -> None:
    textes: dict[str, str] = {}
    for module in (pr_realiste, soiling_hsu):
        constantes = {
            f"{module.__name__}.{nom}": valeur
            for nom, valeur in vars(module).items()
            if "CAVEAT" in nom and isinstance(valeur, str)
        }
        assert constantes, f"aucune mise en garde trouvée dans {module.__name__}"
        textes.update(constantes)
    for mode in get_args(ModeCorrectionPR):
        textes[f"pr_realiste._limite({mode!r})"] = pr_realiste._limite(mode)
    assert all(texte.strip() for texte in textes.values())
    assert _fautifs(textes) == {}


def test_limites_des_routes_grandeurs_sans_vocabulaire_interne() -> None:
    jumelee = next(iter(PAIRES_COLOCALISEES_D29))
    appels: dict[str, list[Callable[[], str]]] = {
        "_construire_limite_ghi_exceedance": [
            lambda: routes_grandeurs._construire_limite_ghi_exceedance(jumelee),
            lambda: routes_grandeurs._construire_limite_ghi_exceedance("gin_conakry_kaloum"),
        ],
        "_construire_limite_incertitude_inter_source": [
            routes_grandeurs._construire_limite_incertitude_inter_source,
        ],
    }
    constructeurs = {nom for nom in vars(routes_grandeurs) if nom.startswith("_construire_limite_")}
    # Un nouveau constructeur de limite doit être ajouté ici, pas ignoré.
    assert constructeurs == set(appels)
    textes = {
        f"{nom}#{indice}": appel()
        for nom, liste in appels.items()
        for indice, appel in enumerate(liste)
    }
    assert PAIRES_COLOCALISEES_D29[jumelee] in textes["_construire_limite_ghi_exceedance#0"]
    assert _fautifs(textes) == {}


def _messages_d_erreur(fichier: Path) -> Iterator[tuple[str, str]]:
    """Parties littérales des ``message=`` passés à ``ExceptionKuma`` dans un module."""
    for noeud in ast.walk(ast.parse(fichier.read_text(encoding="utf-8"))):
        if not (isinstance(noeud, ast.Call) and ast.unparse(noeud.func) == "ExceptionKuma"):
            continue
        for argument in noeud.keywords:
            if argument.arg != "message":
                continue
            litteraux = [
                c.value
                for c in ast.walk(argument.value)
                if isinstance(c, ast.Constant) and isinstance(c.value, str)
            ]
            yield f"{fichier.name}:{noeud.lineno}", " ".join(litteraux)


def test_messages_d_erreur_des_routes_sans_vocabulaire_interne() -> None:
    textes: dict[str, str] = {}
    for fichier in sorted(_DOSSIER_ROUTES.glob("*.py")):
        textes.update(_messages_d_erreur(fichier))
    assert len(textes) > 20, "le parcours des messages d'erreur n'a presque rien trouvé"
    assert _fautifs(textes) == {}
