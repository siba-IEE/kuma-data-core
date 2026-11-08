"""Tests d'intégration de la migration 134 (diffus supérieur au global, NASA POWER).

- Chaque série DHI NASA POWER journalière ou mensuelle dont au moins un pas
  présente un DHI supérieur au GHI de la même fenêtre porte la mise en garde ;
  les autres ne la portent pas.
- Les chiffres de la note (pas comparés, cas, pourcentage) sont ceux du
  recompte en base, et tous les cas sont antérieurs à 2001 comme le dit la
  phrase.
- La fraction diffuse calculée n'est pas concernée : aucune valeur au-dessus
  de 1, aucune période antérieure à 2001.

Les séries horaires restent hors du périmètre : leur contenu dépend de
l'environnement (ingestion de masse sautée en CI).
"""

from __future__ import annotations

import re

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

from tests._jargon import JARGON_INTERNE

pytestmark = pytest.mark.integration

_MISE_EN_GARDE = re.compile(
    r" Mise en garde : sur les (?P<n>[\d ]+) (?P<pas>jours|mois) ou l'irradiation globale "
    r"et l'irradiation diffuse sont toutes deux disponibles, (?P<v>[\d ]+) "
    r"\((?P<pct>\d+,\d) %\) presente(nt)? une (moyenne d')?irradiation diffuse superieure "
    r"a (celle de )?l'irradiation globale, ce qui est physiquement impossible\. "
    r"(Ces (jours|mois) sont tous anterieurs|Ce (jour|mois) est anterieur) a 2001, "
    r"periode pour laquelle NASA POWER fournit un rayonnement issu du jeu satellitaire "
    r"GEWEX SRB ; les valeurs sont conservees telles que fournies par la source\. Pour "
    r"ces? (jours?|mois), utiliser la part diffuse avec prudence, par exemple en la "
    r"limitant a l'irradiation globale\.$"
)

_PAIRES = """
SELECT sm_dhi.code, {annee} AS annee, d.valeur AS dhi, g.valeur AS ghi
FROM {table} g
JOIN series_metadonnees sm_ghi ON sm_ghi.id = g.serie_id
JOIN series_metadonnees sm_dhi
     ON sm_dhi.localite_id = sm_ghi.localite_id
    AND sm_dhi.source_id = sm_ghi.source_id
    AND sm_dhi.periode_debut = sm_ghi.periode_debut
    AND sm_dhi.periode_fin IS NOT DISTINCT FROM sm_ghi.periode_fin
    AND sm_dhi.granularite IS NOT DISTINCT FROM sm_ghi.granularite
    AND sm_dhi.grandeur_code = 'dhi'
JOIN {table} d ON d.serie_id = sm_dhi.id AND {jointure}
JOIN sources s ON s.id = sm_ghi.source_id
WHERE s.code = 'nasa_power' AND sm_ghi.grandeur_code = 'ghi'
  AND g.valide_au IS NULL AND d.valide_au IS NULL
"""


def _recompte(session: Session) -> dict[str, tuple[int, int, int]]:
    """Code de série DHI -> (pas comparés, cas DHI > GHI, cas en 2001 ou après)."""
    journalier = _PAIRES.format(
        table="mesures_ressource",
        annee="CAST(extract(YEAR FROM g.instant_mesure) AS int)",
        jointure="d.instant_mesure = g.instant_mesure",
    )
    mensuel = _PAIRES.format(
        table="mesures_ressource_mensuelles",
        annee="g.annee",
        jointure="d.annee = g.annee AND d.mois = g.mois",
    )
    lignes = session.execute(
        text(
            f"""
            SELECT code, count(*) AS n, count(*) FILTER (WHERE dhi > ghi) AS v,
                   count(*) FILTER (WHERE dhi > ghi AND annee >= 2001) AS recents
            FROM ({journalier} UNION ALL {mensuel}) AS p
            GROUP BY code
            """
        )
    ).all()
    return {r.code: (r.n, r.v, r.recents) for r in lignes}


def _notes_dhi_nasa(session: Session, granularites: tuple[str, ...]) -> dict[str, str]:
    return dict(
        session.execute(
            text(
                """
                SELECT sm.code, sm.note_publique FROM series_metadonnees sm
                JOIN sources s ON s.id = sm.source_id
                WHERE s.code = 'nasa_power' AND sm.grandeur_code = 'dhi'
                  AND sm.granularite = ANY(:g)
                """
            ),
            {"g": list(granularites)},
        ).all()
    )


def _entier(texte: str) -> int:
    return int(texte.replace(" ", ""))


def test_mise_en_garde_sur_les_seules_series_touchees(db_session: Session) -> None:
    comptes = _recompte(db_session)
    notes = _notes_dhi_nasa(db_session, ("journalier", "mensuel"))
    touchees = {c for c, (_, v, _) in comptes.items() if v > 0}
    porteuses = {c for c, note in notes.items() if "Mise en garde : sur les" in note}
    assert porteuses == touchees
    assert len(touchees) == 37
    assert sum(1 for c in touchees if "_journalier_" in c) == 34


def test_chiffres_de_la_note_egaux_au_recompte(db_session: Session) -> None:
    comptes = _recompte(db_session)
    notes = _notes_dhi_nasa(db_session, ("journalier", "mensuel"))
    for code, (n, v, recents) in comptes.items():
        if v == 0:
            continue
        m = _MISE_EN_GARDE.search(notes[code])
        assert m is not None, code
        assert (_entier(m["n"]), _entier(m["v"])) == (n, v), code
        assert m["pct"] == f"{100 * v / n:.1f}".replace(".", ","), code
        assert m["pas"] == ("jours" if "_journalier_" in code else "mois"), code
        assert recents == 0, f"{code} : {recents} cas en 2001 ou après"


def test_mise_en_garde_sans_jargon_et_unique(db_session: Session) -> None:
    notes = _notes_dhi_nasa(db_session, ("journalier", "mensuel", "horaire"))
    for code, note in notes.items():
        assert note.count("Mise en garde : sur les") <= 1, code
        assert JARGON_INTERNE.search(note) is None, code


def test_series_horaires_hors_perimetre(db_session: Session) -> None:
    notes = _notes_dhi_nasa(db_session, ("horaire",))
    assert len(notes) == 34
    assert not [c for c, note in notes.items() if "GEWEX SRB" in note]


def test_fraction_diffuse_non_concernee(db_session: Session) -> None:
    """La fraction diffuse ne lit que des DHI de 2001 et après : aucune valeur au-dessus de 1."""
    hors_borne, anterieures = db_session.execute(
        text(
            """
            SELECT count(*) FILTER (WHERE valeur > 1), count(*) FILTER (WHERE annee_debut < 2001)
            FROM grandeurs_metier WHERE grandeur_code = 'fraction_diffuse' AND valide_au IS NULL
            """
        )
    ).one()
    assert (hors_borne, anterieures) == (0, 0)
    notes = db_session.execute(
        text(
            "SELECT count(*) FROM series_metadonnees "
            "WHERE grandeur_code = 'fraction_diffuse' AND note_publique ~ 'GEWEX SRB'"
        )
    ).scalar_one()
    assert notes == 0
