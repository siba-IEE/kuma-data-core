"""Règles d'architecture : couches, SQL hors des routes, sélection des lignes écrite une fois."""

from __future__ import annotations

import ast
import pathlib
import re
from collections.abc import Iterator

import pytest

pytestmark = pytest.mark.unit

RACINE = pathlib.Path(__file__).resolve().parents[2]
SRC = RACINE / "src" / "kuma_data_core"
SCRIPTS = RACINE / "scripts"
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

# Les règles de sélection des lignes servies s'écrivent dans ce seul module.
SELECTION = "src/kuma_data_core/editorial/selection.py"
MOTIF_SELECTION = re.compile(r"valide_au\s+IS\s+NULL", re.IGNORECASE)

# Chemin depuis la racine -> pourquoi le motif y reste écrit sur place.
# Un dossier vaut pour tous ses fichiers.
_GRANDEUR_STOCKEE = "calcul de grandeur stockée rejoué par des migrations : son SQL ne change pas"
SELECTION_ECRITE_SUR_PLACE: dict[str, str] = {
    "src/kuma_data_core/db/models": "le motif y borne un index et une contrainte, pas une lecture",
    "src/kuma_data_core/services/grandeurs/degenerescence_pixel.py": _GRANDEUR_STOCKEE,
    "src/kuma_data_core/services/grandeurs/fraction_diffuse.py": _GRANDEUR_STOCKEE,
    "src/kuma_data_core/services/grandeurs/hep.py": _GRANDEUR_STOCKEE,
    "src/kuma_data_core/services/grandeurs/humidex.py": _GRANDEUR_STOCKEE,
    "src/kuma_data_core/services/grandeurs/indicateur_qualite_donnees.py": _GRANDEUR_STOCKEE,
    "src/kuma_data_core/services/grandeurs/productible_specifique_theorique.py": _GRANDEUR_STOCKEE,
    "src/kuma_data_core/services/grandeurs/referentiels.py": _GRANDEUR_STOCKEE,
    "src/kuma_data_core/services/grandeurs/variabilite_journaliere.py": _GRANDEUR_STOCKEE,
    "src/kuma_data_core/services/qualite/qc_horaire.py": (
        "le contrôle qualité juge toute ligne en vigueur, quel que soit son statut"
    ),
    "scripts/etude_l_tr_6_biais_poa_horaire.py": "étude ponctuelle, hors des lectures servies",
}

# Ce qui sert des lignes : toute lecture d'une table versionnée y applique une règle.
LECTEURS_SERVIS = (
    "src/kuma_data_core/lecture",
    "src/kuma_data_core/api",
    "src/kuma_data_core/services/capsule",
    "scripts/exporter_rds_guinee.py",
    "scripts/exporter_explorateur_guinee.py",
)
LECTURE_DE_TABLE_VERSIONNEE = re.compile(
    r"\b(?:FROM|JOIN)\s+(?:mesures_ressource(?:_mensuelles|_horaires)?|grandeurs_metier)\b",
    re.IGNORECASE,
)
REGLES_DE_SELECTION = frozenset(
    {"lignes_en_vigueur", "lignes_en_vigueur_validees", "VUE_GRANDEURS_EN_VIGUEUR"}
)


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


def _fichiers_portant_le_motif_de_selection() -> list[str]:
    """Fichiers Python de ``src`` et de ``scripts`` qui écrivent le motif, depuis la racine."""
    return sorted(
        fichier.relative_to(RACINE).as_posix()
        for dossier in (SRC, SCRIPTS)
        for fichier in dossier.rglob("*.py")
        if MOTIF_SELECTION.search(fichier.read_text(encoding="utf-8"))
    )


def _couvert_par(fichier: str, chemin: str) -> bool:
    return fichier == chemin or fichier.startswith(f"{chemin}/")


def test_la_selection_des_lignes_servies_s_ecrit_une_seule_fois() -> None:
    """Hors ``editorial/selection.py``, ``valide_au IS NULL`` ne s'écrit que par exception motivée.

    Un lecteur qui récrit la règle sur place finit par diverger des autres.
    """
    violations = [
        fichier
        for fichier in _fichiers_portant_le_motif_de_selection()
        if fichier != SELECTION
        and not any(_couvert_par(fichier, chemin) for chemin in SELECTION_ECRITE_SUR_PLACE)
    ]
    assert not violations, "\n".join(violations)


def test_chaque_exception_de_selection_est_vivante_et_motivee() -> None:
    """Une exception dont le fichier a disparu, ou n'écrit plus le motif, se retire de la liste."""
    porteurs = _fichiers_portant_le_motif_de_selection()
    mortes = [
        chemin
        for chemin in SELECTION_ECRITE_SUR_PLACE
        if not any(_couvert_par(fichier, chemin) for fichier in porteurs)
    ]
    assert not mortes, "\n".join(mortes)
    assert all(raison.strip() for raison in SELECTION_ECRITE_SUR_PLACE.values())
    assert SELECTION in porteurs


def _noeuds_de_la_portee(portee: ast.AST) -> Iterator[ast.AST]:
    """Nœuds d'un module ou d'une fonction, sans ses docstrings ni les fonctions qu'il définit."""
    a_voir = list(ast.iter_child_nodes(portee))
    while a_voir:
        noeud = a_voir.pop()
        if isinstance(noeud, ast.Expr) and isinstance(noeud.value, ast.Constant):
            continue
        yield noeud
        if not isinstance(noeud, ast.FunctionDef | ast.AsyncFunctionDef):
            a_voir.extend(ast.iter_child_nodes(noeud))


def _lit_une_table_versionnee(portee: ast.AST) -> bool:
    """Une chaîne de la portée nomme une table versionnée après ``FROM`` ou ``JOIN``.

    Une f-string compte pour une seule chaîne, ses expressions remplacées par ``{}``.
    """
    for noeud in _noeuds_de_la_portee(portee):
        if isinstance(noeud, ast.JoinedStr):
            texte = "".join(
                partie.value if isinstance(partie, ast.Constant) else "{}"
                for partie in noeud.values
            )
        elif isinstance(noeud, ast.Constant) and isinstance(noeud.value, str):
            texte = noeud.value
        else:
            continue
        if LECTURE_DE_TABLE_VERSIONNEE.search(texte):
            return True
    return False


def _cite_une_regle_de_selection(portee: ast.AST) -> bool:
    return any(
        (isinstance(noeud, ast.Name) and noeud.id in REGLES_DE_SELECTION)
        or (isinstance(noeud, ast.Attribute) and noeud.attr in REGLES_DE_SELECTION)
        for noeud in _noeuds_de_la_portee(portee)
    )


def _lectures_de_tables_versionnees() -> list[tuple[str, bool]]:
    """``(fichier:fonction, cite une règle)`` pour chaque lecture faite par un lecteur servi."""
    lectures = []
    for chemin in LECTEURS_SERVIS:
        racine = RACINE / chemin
        assert racine.exists(), chemin
        for fichier in sorted(racine.rglob("*.py")) if racine.is_dir() else [racine]:
            arbre = ast.parse(fichier.read_text(encoding="utf-8"))
            portees: list[tuple[str, ast.AST]] = [("<module>", arbre)]
            portees += [
                (noeud.name, noeud)
                for noeud in ast.walk(arbre)
                if isinstance(noeud, ast.FunctionDef | ast.AsyncFunctionDef)
            ]
            lectures += [
                (f"{fichier.relative_to(RACINE).as_posix()}:{nom}", _cite_une_regle_de_selection(p))
                for nom, p in portees
                if _lit_une_table_versionnee(p)
            ]
    return lectures


def test_un_lecteur_servi_applique_une_regle_de_selection() -> None:
    """Une fonction servie qui lit une table versionnée cite une règle de ``editorial.selection``.

    La garde du motif ne voit pas un lecteur qui ne filtre rien ; celle-ci le voit.
    """
    lectures = _lectures_de_tables_versionnees()
    # Garde contre un parcours vide : un lecteur connu est bien vu.
    assert "src/kuma_data_core/lecture/mesures.py:lire_points_horaires" in dict(lectures)
    sans_regle = [lecture for lecture, cite_une_regle in lectures if not cite_une_regle]
    assert not sans_regle, "\n".join(sans_regle)


def test_les_regles_de_selection_citees_existent() -> None:
    """Les noms que la garde cherche sont ceux que ``editorial/selection.py`` définit."""
    arbre = ast.parse((RACINE / SELECTION).read_text(encoding="utf-8"))
    definis = {n.name for n in arbre.body if isinstance(n, ast.FunctionDef)} | {
        cible.id
        for n in arbre.body
        if isinstance(n, ast.Assign)
        for cible in n.targets
        if isinstance(cible, ast.Name)
    }
    assert definis >= REGLES_DE_SELECTION
