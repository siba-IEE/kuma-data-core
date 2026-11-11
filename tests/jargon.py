"""Motif du vocabulaire de chantier interne, interdit dans un texte servi par l'API.

Un texte servi (description OpenAPI, message d'erreur, mise en garde du champ
``limite``) s'adresse à l'utilisateur de l'API : il ne cite ni code de dette ou de
limite, ni étape de chantier, ni document interne, ni outil de fabrication.
``(Dn)`` et ``Temps n`` sont sensibles à la casse ; un code d'étape exige une
lettre collée au second nombre (``1-2b`` oui, ``1991-2020`` non).
"""

from __future__ import annotations

import re

JARGON_INTERNE = re.compile(
    r"(PR\s*#\d+"
    r"|spec\s+\d+-\d+"
    r"|[ée]tape\s+\d+"
    r"|cohorte"
    r"|vague\s+\d"
    r"|volet\s+[A-Z]\b"
    r"|\blot\s+[A-Z0-9]"
    r"|\bD-\d+\b"
    r"|\bTI-\d+\b"
    r"|\bL-[A-Z]+-\d+\b"
    r"|note\s+(méthodologique\s+)?amont"
    r"|parit[ée]\s+[AB]\d"
    r"|\b\d-\d{1,2}[A-Za-z]\b"
    r"|\bcycle\s+\d+-\d+"
    r"|\bcadrage\s+(Q\d|phase)"
    r"|\bQ\d+\s+v\d"
    r"|\bpost-\d+-\d+"
    r"|\bADR-\d+"
    r"|\bphase\s+\d\b"
    r"|(?<!\S)(?!https?://)\S*\.md\b"
    r"|\bGF-\d+"
    r"|\bDT-(\d+|X)\b"
    r"|(?-i:\bCdC\b)"
    r"|(?-i:\(D\d+\))"
    r"|\bpasses?\s+(\d|de\s+contact|consolidation|ult[ée]rieure|compl[ée]mentaire)"
    r"|\bsuperviseur"
    r"|\bpost-audit"
    r"|\bmigrations?\s+\d{3}\b"
    r"|β\d"
    r"|\bdettes?\s+([ée]ditoriales?|D\b)"
    r"|(?-i:\bTemps\s+\d)"
    r"|\bWP\d"
    r"|\bpentest"
    r"|\bfinding\b"
    r"|\bbrief\s+de\s+chantier"
    r"|\br[ée]sidu\s+\d"
    r"|\bvilles?\s+pilotes?"
    r"|\bun\s+poil\b"
    r"|\bZod\b"
    r"|\bSQLAlchemy\b"
    r"|\bself-JOIN\b"
    r"|\bspin-up\b"
    r"|\boverlap\b"
    r"|\bcaveats?\b)",
    re.IGNORECASE,
)

A_DETECTER = [
    "Vague 4 Lot B : DNI",
    "cf. PR #53",
    "phase 1-2b",
    "(D-29 generalise)",
    "caveat L-SOIL-4",
    "CdC § 5.3",
    "Demographie NULL (D7)",
    "atlas Temps 1",
    "voir docs/methodologie/hep.md",
    "Cf. ADR-0004",
    "leçon GF-6",
    "herite du biais L-TR-6",
    "terrain, dette D-67",
    "les 6 villes pilotes phase 1",
    "residu 2 du brief de chantier",
    "finding F-05 pentest",
    "un poil optimiste",
    "son schéma Zod",
    "modèle SQLAlchemy",
    "dénormalisé via self-JOIN",
    "premiers jours sous-estimes (spin-up)",
    "bornee a l'overlap PM EAC4",
    "ADR-0003, D2 / WP6",
]
A_ADMETTRE = [
    "climatologie 1991-2020",
    "rang de 1 à 34",
    "pas de temps 1 h",
    "Temps de réponse",
    "grandeur F1",
    "règles R1-R4",
    "grille 0,75°",
    "/v1/grandeurs/pr_realiste/{code_serie_source}",
    "amorçage du modèle",
    "calée sur des mesures au sol",
    "voir https://exemple.org/depot/docs/guide.md",
    "plan pilote",
    "format YYYY-MM-DD/YYYY-MM-DD",
]


def correspondances(texte: str) -> list[str]:
    """Fragments du texte qui relèvent du vocabulaire interne."""
    return [m.group(0) for m in JARGON_INTERNE.finditer(texte)]
