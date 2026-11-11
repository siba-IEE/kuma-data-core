"""Les textes servis par l'API ne portent ni vocabulaire de chantier interne ni pays pilote.

Sont couverts, sans base de données : le document OpenAPI, les mises en garde
renvoyées dans le champ ``limite`` et les messages d'erreur des routes ``/v1``.
"""

from __future__ import annotations

import ast
import importlib
import inspect
import pkgutil
import re
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import get_args

import pytest

from kuma_data_core.api import v1 as routes_v1
from kuma_data_core.api.main import app
from kuma_data_core.api.v1 import grandeurs as routes_grandeurs
from kuma_data_core.api.v1.grandeurs import exceedance, incertitude
from kuma_data_core.services.grandeurs import pr_realiste, soiling_hsu
from kuma_data_core.services.grandeurs.types import ModeCorrectionPR
from tests.jargon import A_ADMETTRE, A_DETECTER, correspondances

pytestmark = pytest.mark.unit

_DOSSIER_ROUTES = Path(inspect.getfile(routes_v1)).parent


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


# Le moteur sert tout pays du référentiel : ses textes renvoient aux routes qui
# listent les codes, pas à un exemple pris dans le pays pilote.
_PAYS_PILOTE = re.compile(
    r"\bgin_|\bGIN\b|[Gg]uin[ée]e|guin[ée]en|Conakry|Kaloum|Kankan|Kindia|Mamou|Lab[ée]\b"
    r"|Nz[ée]r[ée]kor[ée]|Bok[ée]\b|Boffa|Tokounou"
)


@pytest.mark.parametrize(
    "texte",
    [
        "Code localite (ex. gin_kindia)",
        "Filtre pays ISO 3166-1 alpha-3 (ex. GIN, SEN)",
        "ex. gin pour villes guineennes",
        "Tokounou est plus proche de Kankan",
        "ressource solaire en Guinée",
    ],
)
def test_motif_detecte_le_pays_pilote(texte: str) -> None:
    assert _PAYS_PILOTE.search(texte), f"non détecté : {texte!r}"


@pytest.mark.parametrize(
    "texte",
    [
        "Code de la localité, tel que listé par /v1/localites.",
        "Série d'origine, marginale ou imaginée.",
        "Table des seuils du label.",
    ],
)
def test_motif_admet_un_texte_sans_pays(texte: str) -> None:
    assert _PAYS_PILOTE.search(texte) is None


def test_openapi_sans_exemple_du_pays_pilote() -> None:
    textes = dict(_chaines(app.openapi()))
    assert any(chemin.startswith("/paths//v1/localites") for chemin in textes)
    assert {chemin: t for chemin, t in textes.items() if _PAYS_PILOTE.search(t)} == {}


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
    appels: dict[str, list[Callable[[], str]]] = {
        "_construire_limite_ghi_exceedance": [
            lambda: exceedance._construire_limite_ghi_exceedance(["zzf_b", "zzf_c"]),
            lambda: exceedance._construire_limite_ghi_exceedance([]),
        ],
        "_construire_limite_incertitude_inter_source": [
            incertitude._construire_limite_incertitude_inter_source,
        ],
    }
    modules = [
        importlib.import_module(info.name)
        for info in pkgutil.walk_packages(
            routes_grandeurs.__path__, f"{routes_grandeurs.__name__}."
        )
    ]
    constructeurs = {
        nom for module in modules for nom in vars(module) if nom.startswith("_construire_limite_")
    }
    # Un nouveau constructeur de limite doit être ajouté ici, pas ignoré.
    assert constructeurs == set(appels)
    textes = {
        f"{nom}#{indice}": appel()
        for nom, liste in appels.items()
        for indice, appel in enumerate(liste)
    }
    assert "zzf_c" in textes["_construire_limite_ghi_exceedance#0"]
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
            chemin = fichier.relative_to(_DOSSIER_ROUTES).as_posix()
            yield f"{chemin}:{noeud.lineno}", " ".join(litteraux)


def test_messages_d_erreur_des_routes_sans_vocabulaire_interne() -> None:
    textes: dict[str, str] = {}
    for fichier in sorted(_DOSSIER_ROUTES.rglob("*.py")):
        textes.update(_messages_d_erreur(fichier))
    assert len(textes) > 20, "le parcours des messages d'erreur n'a presque rien trouvé"
    assert _fautifs(textes) == {}
