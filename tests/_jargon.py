"""Motif du vocabulaire de chantier interne interdit dans un texte publié.

Un texte publié (notes et descriptions servies, commentaires du catalogue
emportés par ``pg_dump``, document OpenAPI, réponses de l'API) ne renvoie ni
aux PR, étapes, vagues, lots, dettes, caveats, ADR ou phases du chantier, ni
à un document ``*.md`` par son chemin dans le dépôt (seul un lien complet
vers le dépôt public est admis). Chaque motif a été vérifié sans faux
positif sur l'ensemble des textes publiés ; ``CdC``, ``(Dn)`` et ``Temps n``
sont sensibles à la casse, et un code d'étape exige une lettre collée au
second nombre (``1-2b`` oui, ``1991-2020`` non).
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
    r"|densification\s+pr[ée]fectorale"
    r"|parit[ée]\s+[AB]\d"
    # Codes d'étape et de cadrage, renvois internes.
    r"|\b\d-\d{1,2}[A-Za-z]\b"
    r"|\bcycle\s+\d+-\d+"
    r"|\bcadrage\s+(Q\d|phase)"
    r"|\bQ\d+\s+v\d"
    r"|\bspec\s+[a-z]"
    r"|\bpost-\d+-\d+"
    r"|\bADR-\d+"
    r"|\bphase\s+\d\b"
    # Document du dépôt cité par chemin (un lien vers le dépôt public est admis).
    r"|(?<!\S)(?!https://github\.com/siba-IEE/kuma-data-core/)\S*\.md\b"
    # Fiches de compilation des sources et localités.
    r"|\bGF-\d+"
    r"|\bDT-(\d+|X)\b"
    r"|(?-i:\bCdC\b)"
    r"|(?-i:\(D\d+\))"
    r"|\bpasses?\s+(\d|de\s+contact|consolidation|ult[ée]rieure|compl[ée]mentaire)"
    r"|\b(future|toute\s+la|de\s+la)\s+passe\b"
    r"|\bsuperviseur"
    r"|\bpost-audit"
    r"|\bmigrations?\s+\d{3}\b"
    r"|β\d"
    r"|\bdettes?\s+[ée]ditoriales?"
    # Étape de l'atlas d'incertitude (« Temps 1 ») ; « temps 1 h » reste admis.
    r"|(?-i:\bTemps\s+\d))",
    re.IGNORECASE,
)
