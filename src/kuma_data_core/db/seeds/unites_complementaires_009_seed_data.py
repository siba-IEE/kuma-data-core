"""Données de seed des 4 unités complémentaires de la migration 009.

Complète les 153 unités (migration 002, ``unites_seed_data.py``)
par les 4 unités strictement nécessaires au seed des 15 grandeurs
(migration 010, ``grandeurs_referentiel_seed_data.py``) :

- ``kwh_par_kwc_jour`` - productible spécifique journalier (PV).
- ``kwh_par_kwc_mois`` - productible spécifique mensuel (PV).
- ``heure_equivalente_pleine`` - convention internationale EFLH.
- ``degre_jour`` - base pour les calculs thermiques (ISO 15927-6).

Pattern reproduit de ``unites_seed_data.py`` : dicts prêts pour
``op.bulk_insert``, ``cree_par`` et ``modifie_par`` laissés à NULL,
``actif``/``cree_le``/``modifie_le`` laissés aux ``server_default``.

Facteurs de conversion SI calculés en ``Decimal`` quantisés à 30
décimales pour aligner sur ``Numeric(60, 30)`` du modèle ``Unite``.
"""

from __future__ import annotations

from decimal import Decimal, getcontext
from typing import Any

# Marge de précision pour l'arrondi à 30 décimales.
getcontext().prec = 35

D = Decimal

# Conventions temporelles IUPAC alignées sur ``annee_calendaire``
# (= 31 556 952 s exactement, soit 365,2425 jours grégoriens) :
# - 1 jour  = 86 400 s
# - 1 mois moyen = annee / 12 = 2 629 746 s
_FACTEUR_KWH_PAR_KWC_JOUR: Decimal = (D("3600") / D("86400")).quantize(D("1E-30"))
_FACTEUR_KWH_PAR_KWC_MOIS: Decimal = (D("3600") / D("2629746")).quantize(D("1E-30"))


UNITES_COMPLEMENTAIRES_009_SEED: list[dict[str, Any]] = [
    {
        "code": "kwh_par_kwc_jour",
        "libelle": "kilowattheure par kilowatt-crête par jour",
        "symbole": "kWh/kWc/jour",
        "grandeur": "productible_specifique_quotidien",
        "systeme": "composee_mixte",
        "est_unite_de_base": False,
        "facteur_conversion_si": _FACTEUR_KWH_PAR_KWC_JOUR,
        "decalage_conversion_si": D("0"),
        "code_unite_si": "sans_unite",
        "note_methodologique": (
            "Productible spécifique journalier d'un système photovoltaïque. "
            "Énergie produite par kilowatt-crête installé sur une journée. "
            "Standard IEC 61724-1, IEA PVPS Task 13. Cadence éditoriale Kuma "
            "pour le productible journalier."
        ),
        "references_normatives": [
            "IEC 61724-1 (Photovoltaic system performance - Part 1 : Monitoring)",
            "IEA PVPS Task 13",
            "IRENA Country Profiles",
        ],
    },
    {
        "code": "kwh_par_kwc_mois",
        "libelle": "kilowattheure par kilowatt-crête par mois",
        "symbole": "kWh/kWc/mois",
        "grandeur": "productible_specifique_mensuel",
        "systeme": "composee_mixte",
        "est_unite_de_base": False,
        "facteur_conversion_si": _FACTEUR_KWH_PAR_KWC_MOIS,
        "decalage_conversion_si": D("0"),
        "code_unite_si": "sans_unite",
        "note_methodologique": (
            "Productible spécifique mensuel d'un système photovoltaïque. "
            "Cumul mensuel de l'énergie produite par kilowatt-crête installé. "
            "Utilisé pour caractériser la saisonnalité énergétique d'un site."
        ),
        "references_normatives": [
            "IEC 61724-1 (Photovoltaic system performance - Part 1 : Monitoring)",
            "IEA PVPS Task 13",
            "IRENA Country Profiles",
        ],
    },
    {
        "code": "heure_equivalente_pleine",
        "libelle": "heure équivalente pleine",
        "symbole": "HEP",
        "grandeur": "productivite_solaire",
        "systeme": "composee_mixte",
        "est_unite_de_base": False,
        "facteur_conversion_si": D("3600"),
        "decalage_conversion_si": D("0"),
        "code_unite_si": "seconde",
        "note_methodologique": (
            "Convention internationale Equivalent Full Load Hours (EFLH). "
            "Quotient de l'énergie produite par la puissance crête nominale, "
            "exprimé en heures équivalentes. Distincte sémantiquement de "
            'l\'unité "heure" bien que dimensionnellement identique '
            "(facteur SI = 3600). Standard pour caractériser la productivité "
            "d'un site PV."
        ),
        "references_normatives": [
            "IEC 61724-1 (Photovoltaic system performance - Part 1 : Monitoring)",
            "IEA PVPS Task 13",
            "IRENA Country Profiles",
        ],
    },
    {
        "code": "degre_jour",
        "libelle": "degré-jour",
        "symbole": "°C·jour",
        "grandeur": "duree_temperature",
        "systeme": "composee_mixte",
        "est_unite_de_base": False,
        "facteur_conversion_si": D("1"),
        "decalage_conversion_si": D("0"),
        "code_unite_si": "degre_jour",
        "note_methodologique": (
            "Cumul des écarts entre une température de référence (base) et "
            "la température journalière moyenne. Unité de base pour les "
            "calculs de besoins thermiques de chauffage ou de climatisation. "
            "Dimension SI exacte : kelvin × seconde (différentiel de "
            "température cumulé sur durée). Code unite_si autoréférent dans "
            "Kuma, faute d'unité SI scalaire directe."
        ),
        "references_normatives": [
            "ISO 15927-6 (Hygrothermal performance of buildings - "
            "Calculation and presentation of climatic data - Part 6 : "
            "Accumulated temperature differences (degree-days))",
            "ASHRAE Fundamentals Handbook (Climatic Design Information)",
        ],
    },
]


assert len(UNITES_COMPLEMENTAIRES_009_SEED) == 4, (
    f"Expected 4 unités complémentaires, got {len(UNITES_COMPLEMENTAIRES_009_SEED)}"
)

_codes_seen: set[str] = set()
for _entry in UNITES_COMPLEMENTAIRES_009_SEED:
    _code = _entry["code"]
    assert _code not in _codes_seen, (
        f"Code dupliqué dans UNITES_COMPLEMENTAIRES_009_SEED : {_code!r}"
    )
    _codes_seen.add(_code)
del _codes_seen, _entry, _code
