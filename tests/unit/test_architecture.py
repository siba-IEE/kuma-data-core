"""Règles d'architecture : sens des dépendances entre couches, SQL hors des routes."""

from __future__ import annotations

import ast
import pathlib
import re

import pytest

pytestmark = pytest.mark.unit

RACINE = pathlib.Path(__file__).resolve().parents[2]
SRC = RACINE / "src" / "kuma_data_core"
MIGRATIONS = RACINE / "migrations" / "versions"
PAQUET = "kuma_data_core"

# Couche -> couches qu'elle peut importer (elle-même toujours admise).
# Une flèche absente est interdite : l'ajouter ici se décide, cela ne s'improvise pas.
DEPENDANCES_ADMISES: dict[str, frozenset[str]] = {
    "core": frozenset(),
    "exceptions": frozenset(),
    "db": frozenset({"core"}),
    "editorial": frozenset({"db", "exceptions"}),
    "external": frozenset({"exceptions"}),
    "lecture": frozenset({"editorial"}),
    "publication": frozenset(),
    "ingestion": frozenset({"db", "editorial", "exceptions", "external"}),
    "services": frozenset({"core", "db", "editorial", "exceptions", "external"}),
    "api": frozenset({"core", "db", "editorial", "exceptions", "external", "lecture", "services"}),
}

# Première révision soumise à la règle « une migration n'importe pas le code du moteur ».
PREMIERE_REVISION_AUTONOME = 122


def _couche(module: str) -> str:
    return module.split(".")[1]


def _modules_importes(fichier: pathlib.Path) -> set[str]:
    """Modules du paquet importés par le fichier, imports locaux à une fonction compris."""
    importes: set[str] = set()
    for noeud in ast.walk(ast.parse(fichier.read_text(encoding="utf-8"))):
        if isinstance(noeud, ast.ImportFrom):
            assert noeud.level == 0, f"import relatif dans {fichier}"
            if noeud.module and noeud.module.split(".")[0] == PAQUET:
                importes.add(noeud.module)
        elif isinstance(noeud, ast.Import):
            importes.update(a.name for a in noeud.names if a.name.split(".")[0] == PAQUET)
    return importes


def _bibliotheques_importees(fichier: pathlib.Path) -> set[str]:
    """Paquets de premier niveau importés par le fichier."""
    importes: set[str] = set()
    for noeud in ast.walk(ast.parse(fichier.read_text(encoding="utf-8"))):
        if isinstance(noeud, ast.ImportFrom) and noeud.module:
            importes.add(noeud.module.split(".")[0])
        elif isinstance(noeud, ast.Import):
            importes.update(a.name.split(".")[0] for a in noeud.names)
    return importes


def _fichiers_source() -> list[pathlib.Path]:
    return sorted(f for f in SRC.rglob("*.py") if f.parent != SRC or f.name == "exceptions.py")


def test_chaque_couche_est_declaree() -> None:
    couches = {f.relative_to(SRC).parts[0].removesuffix(".py") for f in _fichiers_source()}
    assert couches == set(DEPENDANCES_ADMISES)


def test_sens_des_dependances_entre_couches() -> None:
    violations = []
    for fichier in _fichiers_source():
        couche = fichier.relative_to(SRC).parts[0].removesuffix(".py")
        for module in _modules_importes(fichier):
            if module == PAQUET:
                continue
            cible = _couche(module)
            if cible != couche and cible not in DEPENDANCES_ADMISES[couche]:
                violations.append(f"{fichier.relative_to(SRC)} importe {module}")
    assert not violations, "\n".join(violations)


def test_pas_de_sql_dans_les_routes() -> None:
    """Les routes lisent par ``lecture`` ou ``services`` : ni ``text()`` ni ``.execute()``."""
    violations = []
    for fichier in sorted((SRC / "api").rglob("*.py")):
        for noeud in ast.walk(ast.parse(fichier.read_text(encoding="utf-8"))):
            if not isinstance(noeud, ast.Call):
                continue
            appel = noeud.func
            if (isinstance(appel, ast.Name) and appel.id == "text") or (
                isinstance(appel, ast.Attribute) and appel.attr == "execute"
            ):
                violations.append(f"{fichier.relative_to(SRC)}:{noeud.lineno}")
    assert not violations, "\n".join(violations)


def test_la_couche_de_lecture_ignore_http() -> None:
    for fichier in sorted((SRC / "lecture").rglob("*.py")):
        assert not _bibliotheques_importees(fichier) & {"fastapi", "starlette"}, fichier.name


def test_les_migrations_recentes_n_importent_pas_le_moteur() -> None:
    """Une migration rejouée plus tard doit refaire ce qu'elle a fait, quel que soit le code."""
    violations = []
    for fichier in sorted(MIGRATIONS.glob("*.py")):
        source = fichier.read_text(encoding="utf-8")
        revision = re.search(r'^revision: str = "(\d+)"', source, re.MULTILINE)
        assert revision is not None, fichier.name
        if int(revision.group(1)) >= PREMIERE_REVISION_AUTONOME and _modules_importes(fichier):
            violations.append(fichier.name)
    assert not violations, "\n".join(violations)
