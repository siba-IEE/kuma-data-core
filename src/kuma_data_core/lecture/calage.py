"""Lecture des référentiels de calage satellite/sol et de leur couverture."""

from __future__ import annotations

from typing import NamedTuple

from sqlalchemy import text
from sqlalchemy.orm import Session


class ReferentielCalage(NamedTuple):
    """Référentiel de calage actif, tel que listé : station, grandeur, version, série sol."""

    code: str
    localite: str
    grandeur_code: str
    version: str
    serie_sol: str


class SaisonReferentiel(NamedTuple):
    """Saison d'un référentiel de calage ; chaque ligne répète les attributs du référentiel.

    ``biais`` est le biais relatif moyen satellite moins sol.
    """

    code: str
    saison: str
    mois: list[int]
    biais: float
    provenance: str
    portee: str
    version: str
    serie_sol: str


class LocaliteCouverte(NamedTuple):
    """Localité où un référentiel de calage peut être transporté, et pourquoi."""

    code: str
    justification: str


def lister_referentiels(session: Session) -> list[ReferentielCalage]:
    """Référentiels de calage actifs, un par ``(code, localité, grandeur)``, triés par code."""
    rows = session.execute(
        text(
            """
            SELECT rc.code, l.code AS localite, rc.grandeur_code,
                   MIN(rc.version) AS version, MIN(rc.serie_sol) AS serie_sol
            FROM referentiels_calage rc
            JOIN localites l ON l.id = rc.localite_id
            WHERE rc.actif = TRUE
            GROUP BY rc.code, l.code, rc.grandeur_code
            ORDER BY rc.code
            """
        )
    ).all()
    return [
        ReferentielCalage(
            code=str(r.code),
            localite=str(r.localite),
            grandeur_code=str(r.grandeur_code),
            version=str(r.version),
            serie_sol=str(r.serie_sol),
        )
        for r in rows
    ]


def lire_couvertures_par_referentiel(session: Session) -> dict[str, list[str]]:
    """Codes triés des localités couvertes, par code de référentiel (couvertures actives)."""
    rows = session.execute(
        text(
            """
            SELECT cc.referentiel_code, l.code
            FROM calage_couverture cc
            JOIN localites l ON l.id = cc.localite_id
            WHERE cc.actif = TRUE
            ORDER BY cc.referentiel_code, l.code
            """
        )
    ).all()
    par_referentiel: dict[str, list[str]] = {}
    for r in rows:
        par_referentiel.setdefault(str(r.referentiel_code), []).append(str(r.code))
    return par_referentiel


def lire_saisons_referentiel(
    session: Session, localite: str, grandeur: str
) -> list[SaisonReferentiel]:
    """Saisons du référentiel actif d'une station et d'une grandeur, triées par identifiant.

    Liste vide si aucun référentiel actif n'existe pour le couple.
    """
    rows = session.execute(
        text(
            """
            SELECT rc.code, rc.saison, rc.mois, rc.biais, rc.provenance,
                   rc.portee, rc.version, rc.serie_sol
            FROM referentiels_calage rc
            JOIN localites l ON l.id = rc.localite_id
            WHERE l.code = :localite
              AND rc.grandeur_code = :grandeur
              AND rc.actif = TRUE
            ORDER BY rc.id
            """
        ),
        {"localite": localite, "grandeur": grandeur},
    ).all()
    return [
        SaisonReferentiel(
            code=str(r.code),
            saison=str(r.saison),
            mois=[int(m) for m in r.mois],
            biais=float(r.biais),
            provenance=str(r.provenance),
            portee=str(r.portee),
            version=str(r.version),
            serie_sol=str(r.serie_sol),
        )
        for r in rows
    ]


def lire_couverture_referentiel(session: Session, code: str) -> list[LocaliteCouverte]:
    """Localités couvertes par un référentiel (couvertures actives), triées par code."""
    rows = session.execute(
        text(
            """
            SELECT l.code, cc.justification
            FROM calage_couverture cc
            JOIN localites l ON l.id = cc.localite_id
            WHERE cc.referentiel_code = :code
              AND cc.actif = TRUE
            ORDER BY l.code
            """
        ),
        {"code": code},
    ).all()
    return [LocaliteCouverte(code=str(r.code), justification=str(r.justification)) for r in rows]
