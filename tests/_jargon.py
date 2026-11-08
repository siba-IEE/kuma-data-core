"""Motif partagé du vocabulaire de chantier interne interdit dans un texte publié.

Un texte publié (note publique d'une série, description d'une grandeur,
commentaire du catalogue emporté par ``pg_dump``, texte des données publiées,
document OpenAPI et réponses de l'API) est auto-portant : il ne renvoie ni aux
PR, specs, étapes, cohortes, vagues, lots, dettes ``D-n``, caveats
``L-XXX-n``, ADR ou phases du chantier, ni à ses documents (``*.md``) par un
chemin de dépôt. Seul un lien complet vers le dépôt public
(``https://github.com/siba-IEE/kuma-data-core/...``) peut viser un document
``*.md``.

Les motifs de la deuxième partie (codes d'étape ``1-2b``, ``1-5D-i``,
``cycle 1-7b``, ``cadrage Q7``, ``Q7 v1.3``, ``spec mecaniques-...``,
``post-1-2b``, ``ADR-0004``, ``phase 1``, ``*.md``) ont été vérifiés sans
faux positif sur l'ensemble des textes publiés au moment de la migration
127 (« 1-6 », « 1991-2020 », « 3-horaire », « F1 », « R1-R4 » ne matchent
pas : un code d'étape exige une lettre collée au second nombre).

Ceux de la troisième partie (migration 129) visent le vocabulaire des fiches
de compilation des sources et des localités : garde-fous ``GF-n``, décisions
techniques ``DT-n``, cahier des charges ``CdC`` et ses décisions ``(D7)``,
passes de compilation, supervision, audit et renvois aux migrations, statut
``β2`` du vecteur hydro, dettes éditoriales. ``CdC`` et ``(Dn)`` sont
sensibles à la casse. Vérifiés sans faux positif sur toutes les valeurs de
texte publiées (tables publiées et colonnes non masquées des tables
assainies), sur les commentaires du catalogue et sur le document OpenAPI au
moment de la migration 129.
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
    # Codes d'étape et de cadrage, renvois internes (migration 127).
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
    # Fiches de compilation des sources et localités (migration 129).
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
    r"|\bdettes?\s+[ée]ditoriales?)",
    re.IGNORECASE,
)
