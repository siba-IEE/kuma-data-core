"""Tests unitaires sur le module ``SOURCES_SEED``.

Tests sans DB, sur le module Python directement. Couvrent :

1. Structure : 9 entrées exactement.
2. Codes uniques.
3. Codes attendus : énumération nominative exhaustive.
4. Schéma : chaque entrée a les clés attendues.
5. Année dans le code : 4 sources avec année (regex strict) +
   5 sans année.
6. DOI Vol I : ``wmo_8_2024.doi`` se termine par ``/1``.
7. ISBN format : ISBN respecte le regex
   ``^(97[89][0-9]{10}|[0-9]{9}[0-9X])$`` pour les 4 sources avec ISBN
   (cohérent avec le CHECK constraint SQL ``ck_sources_isbn_format``).
8. Acknowledgement : pattern ``(?i)(acknowledgement|citation)``
   présent dans ``notes`` pour les 9 sources.

Tests unitaires : pas de fixture DB, exécution rapide, validation
référentielle du module sans dépendance Postgres.
"""

from __future__ import annotations

import re

import pytest

from kuma_data_core.db.seeds.sources_seed_data import SOURCES_SEED

pytestmark = pytest.mark.unit


_CODES_ATTENDUS: tuple[str, ...] = (
    "nasa_power",
    "ecmwf_era5",
    "anm_guinee_stations",
    "iec_61724_1_2021",
    "wmo_8_2024",
    "wmo_grdc",
    "wwf_hydrosheds",
    "iec_60041_1991",
    "wmo_168_2008",
)

_CODES_AVEC_ANNEE: tuple[str, ...] = (
    "iec_61724_1_2021",
    "wmo_8_2024",
    "iec_60041_1991",
    "wmo_168_2008",
)

_CODES_SANS_ANNEE: tuple[str, ...] = (
    "nasa_power",
    "ecmwf_era5",
    "anm_guinee_stations",
    "wmo_grdc",
    "wwf_hydrosheds",
)

_CLES_ATTENDUES: frozenset[str] = frozenset(
    {
        "code",
        "titre",
        "auteurs",
        "organisation",
        "type_source",
        "annee_publication",
        "date_consultation",
        "url",
        "doi",
        "isbn",
        "metadonnees",
        "fiabilite",
        "langue",
        "notes",
    }
)

# Regex CHECK constraint SQL ``ck_sources_isbn_format`` (cf. modèle
# ``Source``) : ISBN-13 préfixé 978/979 (12 chiffres restants) OU ISBN-10
# (9 chiffres + 1 caractère X-ou-chiffre).
_ISBN_REGEX = re.compile(r"^(97[89][0-9]{10}|[0-9]{9}[0-9X])$")


# ---------------------------------------------------------------------------
# 1. Structure
# ---------------------------------------------------------------------------


def test_01_structure_9_entrees() -> None:
    assert len(SOURCES_SEED) == 9


# ---------------------------------------------------------------------------
# 2. Codes uniques
# ---------------------------------------------------------------------------


def test_02_codes_uniques() -> None:
    codes = [entry["code"] for entry in SOURCES_SEED]
    assert len(codes) == len(set(codes)), (
        f"Codes dupliqués détectés : {[c for c in codes if codes.count(c) > 1]}"
    )


# ---------------------------------------------------------------------------
# 3. Codes attendus (énumération nominative exhaustive)
# ---------------------------------------------------------------------------


def test_03_codes_attendus_enumeration_exhaustive() -> None:
    codes_observes = {entry["code"] for entry in SOURCES_SEED}
    assert codes_observes == set(_CODES_ATTENDUS), (
        f"Différence codes : "
        f"observés={sorted(codes_observes)} vs attendus={sorted(_CODES_ATTENDUS)}"
    )


# ---------------------------------------------------------------------------
# 4. Schéma : chaque entrée a les clés attendues
# ---------------------------------------------------------------------------


def test_04_schema_cles_attendues() -> None:
    for entry in SOURCES_SEED:
        cles_observees = frozenset(entry.keys())
        assert cles_observees == _CLES_ATTENDUES, (
            f"{entry.get('code', '?')} : clés observées={sorted(cles_observees)} "
            f"vs attendues={sorted(_CLES_ATTENDUES)}"
        )


# ---------------------------------------------------------------------------
# 5. Année dans le code (regex strict)
# ---------------------------------------------------------------------------


def test_05_dt11_codes_avec_annee_regex() -> None:
    pattern = re.compile(r"_(19|20)\d{2}$")
    codes_avec_annee = {entry["code"] for entry in SOURCES_SEED if pattern.search(entry["code"])}
    assert codes_avec_annee == set(_CODES_AVEC_ANNEE)


def test_05_dt11_codes_sans_annee_regex() -> None:
    pattern = re.compile(r"_(19|20)\d{2}$")
    codes_sans_annee = {
        entry["code"] for entry in SOURCES_SEED if not pattern.search(entry["code"])
    }
    assert codes_sans_annee == set(_CODES_SANS_ANNEE)


def test_05_dt11_annee_publication_coherente_avec_code() -> None:
    """Pour chaque code avec année, ``annee_publication`` correspond au
    suffixe du code.
    """
    pattern = re.compile(r"_(?P<annee>(?:19|20)\d{2})$")
    for entry in SOURCES_SEED:
        match = pattern.search(entry["code"])
        if match is None:
            continue
        annee_code = int(match.group("annee"))
        assert entry["annee_publication"] == annee_code, (
            f"{entry['code']} : annee_publication={entry['annee_publication']!r}, "
            f"attendu {annee_code} (cohérent avec suffixe du code)"
        )


# ---------------------------------------------------------------------------
# 6. Scope Vol I WMO
# ---------------------------------------------------------------------------


def test_06_dt12_wmo_8_2024_doi_suffixe_vol_i() -> None:
    entry = next(e for e in SOURCES_SEED if e["code"] == "wmo_8_2024")
    assert entry["doi"] == "10.59327/WMO/CIMO/1"
    assert entry["doi"].endswith("/1")


def test_06_dt12_wmo_168_2008_isbn_vol_i_distinct() -> None:
    """``wmo_168_2008`` retient l'ISBN Vol I distinct du Vol II
    (le suffixe « 168 » de l'ISBN reflète le numéro WMO).
    """
    entry = next(e for e in SOURCES_SEED if e["code"] == "wmo_168_2008")
    assert entry["isbn"] == "9789263101686"


# ---------------------------------------------------------------------------
# 7. ISBN format (cohérent avec CHECK constraint SQL)
# ---------------------------------------------------------------------------


def test_07_dt9_isbn_format_regex_check_sql() -> None:
    """Pour chaque source avec ISBN, le format respecte le regex du
    CHECK constraint SQL ``ck_sources_isbn_format``.
    """
    codes_avec_isbn = {
        "iec_61724_1_2021": "9782832210025",
        "iec_60041_1991": "283182222X",
        "wmo_8_2024": "9789263100085",
        "wmo_168_2008": "9789263101686",
    }
    for entry in SOURCES_SEED:
        code = entry["code"]
        isbn = entry["isbn"]
        if code in codes_avec_isbn:
            assert isbn == codes_avec_isbn[code], (
                f"{code} : isbn={isbn!r}, attendu {codes_avec_isbn[code]!r}"
            )
            assert _ISBN_REGEX.match(isbn), (
                f"{code} : isbn={isbn!r} ne respecte pas le regex CHECK SQL "
                f"^(97[89][0-9]{{10}}|[0-9]{{9}}[0-9X])$"
            )
        else:
            assert isbn is None, f"{code} : isbn attendu None, trouvé {isbn!r}"


# ---------------------------------------------------------------------------
# 8. Acknowledgement présent dans notes
# ---------------------------------------------------------------------------


def test_08_dt10_acknowledgement_present_dans_notes() -> None:
    pattern = re.compile(r"(acknowledgement|citation)", re.IGNORECASE)
    for entry in SOURCES_SEED:
        notes = entry["notes"]
        assert notes is not None and notes.strip(), entry["code"]
        assert pattern.search(notes) is not None, (
            f"{entry['code']} : aucun pattern (acknowledgement|citation) trouvé dans notes"
        )
