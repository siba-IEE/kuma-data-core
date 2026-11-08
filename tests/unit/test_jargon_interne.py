"""Motif ``JARGON_INTERNE`` (``tests/_jargon.py``) : vrais positifs et faux positifs écartés."""

from __future__ import annotations

import pytest

from tests._jargon import JARGON_INTERNE

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    "texte",
    [
        # Motifs de la migration 129.
        "GF-1 fortement applicable",
        "Convention de code DT-1 : ...",
        "fiches dédiées (DT-X potentielle)",
        "Coordonnées identiques (CdC § 5.3).",
        "Demographie NULL (D7) : a sourcer",
        "à confirmer en passe 2",
        "en passe de contact officiel",
        "à acter en future passe.",
        "Pattern stable sur toute la passe :",
        "verifiee par superviseur 2026-06-20",
        "[v2 corrigée post-audit : ...]",
        "Chef-lieu deja ingere (migration 011, Wikidata Q874317)",
        "cross-check β2",
        "Dettes éditoriales projet",
        # Chemin de dépôt relatif vers un document.
        "docs/methodologie/grandeurs/hep.md",
        "Note docs/methodologie/calage.md, script",
        # Motifs antérieurs.
        "dette D-29",
        "L-SOIL-3",
        "ADR-0004",
        "phase 1",
    ],
)
def test_jargon_detecte(texte: str) -> None:
    assert JARGON_INTERNE.search(texte) is not None


@pytest.mark.parametrize(
    "texte",
    [
        "https://github.com/siba-IEE/kuma-data-core/blob/main/docs/methodologie/grandeurs/hep.md",
        "1991-2020",
        "R1-R4",
        "confiance F1",
        "statut passe_plat_non_valide",
        "Donnees horaires passe-plat",
        "Centers for Disease Control (CDC)",
        "valeur D7 de la grille",
        "audit applicatif par triggers",
        "kuma_log_audit",
        "mise à jour en 2024",
        "IEC 61724-1:2021 Edition 2.0",
        "dette publique",
    ],
)
def test_texte_legitime_non_detecte(texte: str) -> None:
    assert JARGON_INTERNE.search(texte) is None
