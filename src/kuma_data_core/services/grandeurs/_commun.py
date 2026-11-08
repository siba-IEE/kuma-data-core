"""Briques partagées des grandeurs calculées stockées dans ``grandeurs_metier``.

Garde de version de formule, résolution et contrôle des séries, lecture des
mesures utilisables, construction et insertion des lignes, et règle de
complétude au jour civil près.
"""

from __future__ import annotations

import calendar
from collections.abc import Mapping, Sequence
from collections.abc import Set as AbstractSet
from datetime import date
from typing import NamedTuple, TypedDict

from sqlalchemy import text
from sqlalchemy.orm import Session

from kuma_data_core.editorial.niveaux_confiance import (
    NiveauConfiance,
    NiveauxEntrees,
    calculer_niveau_confiance_derive,
)
from kuma_data_core.editorial.statuts import filtre_mesure_utilisable

_COLONNES_GRANDEURS_METIER: tuple[str, ...] = (
    "grandeur_code",
    "localite_id",
    "series_metadonnees_id",
    "periode_type",
    "annee_debut",
    "annee_fin",
    "mois",
    "version_formule",
    "valeur",
    "niveau_confiance_derive",
)

_SQL_SERIE_CIBLE: str = """
    SELECT
        sm.id AS serie_id,
        sm.localite_id,
        sm.grandeur_code,
        sm.methode_collecte,
        s.fiabilite AS fiabilite_source
    FROM series_metadonnees sm
    JOIN sources s ON s.id = sm.source_id
    WHERE sm.{cle} = :valeur
"""


class CibleConfiance(NamedTuple):
    """Méthode de la série calculée et fiabilité de sa source (entrées de R1-R4)."""

    methode_collecte: str | None
    fiabilite_source: str | None


class SerieCible(NamedTuple):
    """Série calculée qui reçoit les lignes."""

    serie_id: int
    localite_id: int
    confiance: CibleConfiance


class SerieAmont(NamedTuple):
    """Série d'entrée d'un calcul."""

    serie_id: int
    localite_id: int


class LignePeriode(TypedDict):
    """Valeur agrégée sur une période, avant matérialisation."""

    periode_type: str
    annee_debut: int
    annee_fin: int
    mois: int | None
    valeur: float


def ligne_mensuelle(annee: int, mois: int, valeur: float) -> LignePeriode:
    """Ligne d'un mois civil."""
    return {
        "periode_type": "mensuel",
        "annee_debut": annee,
        "annee_fin": annee,
        "mois": mois,
        "valeur": valeur,
    }


def ligne_annuelle(annee: int, valeur: float) -> LignePeriode:
    """Ligne d'une année civile."""
    return {
        "periode_type": "annuel",
        "annee_debut": annee,
        "annee_fin": annee,
        "mois": None,
        "valeur": valeur,
    }


def jours_attendus_mois(annee: int, mois: int) -> int:
    """Jours civils du mois : un mois n'est complet qu'avec chacun d'eux."""
    return calendar.monthrange(annee, mois)[1]


def jours_attendus_annee(annee: int) -> int:
    """Jours civils de l'année (366 si bissextile)."""
    return 366 if calendar.isleap(annee) else 365


def verifier_version_formule(session: Session, grandeur_code: str, version_formule: int) -> None:
    """``RuntimeError`` si la grandeur manque au référentiel ou si sa version diffère."""
    version_actuelle = session.execute(
        text("SELECT version_formule_actuelle FROM grandeurs_referentiel WHERE code = :code"),
        {"code": grandeur_code},
    ).scalar()
    if version_actuelle is None:
        raise RuntimeError(f"Grandeur {grandeur_code!r} introuvable dans grandeurs_referentiel.")
    if version_formule != int(version_actuelle):
        raise RuntimeError(
            f"Desalignement version_formule : argument={version_formule}, "
            f"version_formule_actuelle pour {grandeur_code!r}={int(version_actuelle)}."
        )


def resoudre_serie_cible(
    session: Session,
    code: str,
    *,
    message_introuvable: str,
    grandeur_attendue: str | None = None,
    methode_attendue: str | None = None,
) -> SerieCible:
    """Série ``code`` et la confiance de sa source.

    ``RuntimeError`` (``message_introuvable``) si absente, ou si sa grandeur
    ou sa méthode diffère de celle attendue (contrôle omis si ``None``).
    """
    row = session.execute(text(_SQL_SERIE_CIBLE.format(cle="code")), {"valeur": code}).first()
    if row is None:
        raise RuntimeError(message_introuvable)
    if grandeur_attendue is not None and row.grandeur_code != grandeur_attendue:
        raise RuntimeError(
            f"Serie cible {code!r} : grandeur_code="
            f"{row.grandeur_code!r}, attendu {grandeur_attendue!r}."
        )
    if methode_attendue is not None and row.methode_collecte != methode_attendue:
        raise RuntimeError(
            f"Serie cible {code!r} : methode_collecte="
            f"{row.methode_collecte!r}, attendu {methode_attendue!r}."
        )
    return SerieCible(
        int(row.serie_id),
        int(row.localite_id),
        CibleConfiance(row.methode_collecte, row.fiabilite_source),
    )


def lire_cible(session: Session, serie_id: int) -> CibleConfiance:
    """Confiance de la série calculée ``serie_id`` (``NoResultFound`` si absente)."""
    row = session.execute(text(_SQL_SERIE_CIBLE.format(cle="id")), {"valeur": serie_id}).one()
    return CibleConfiance(row.methode_collecte, row.fiabilite_source)


def resoudre_serie_amont(
    session: Session, code: str, *, libelle: str, grandeur_attendue: str
) -> SerieAmont:
    """Série d'entrée ``code`` ; ``RuntimeError`` si absente ou d'une autre grandeur."""
    row = session.execute(
        text(
            "SELECT id AS serie_id, localite_id, grandeur_code "
            "FROM series_metadonnees WHERE code = :code"
        ),
        {"code": code},
    ).first()
    if row is None:
        raise RuntimeError(f"Serie {libelle} amont {code!r} introuvable.")
    if row.grandeur_code != grandeur_attendue:
        raise RuntimeError(
            f"Serie {code!r} : grandeur_code={row.grandeur_code!r}, attendu {grandeur_attendue!r}."
        )
    return SerieAmont(int(row.serie_id), int(row.localite_id))


def verifier_localite_amont(
    *, code_cible: str, cible: SerieCible, code_amont: str, libelle: str, amont: SerieAmont
) -> None:
    """``RuntimeError`` si la série d'entrée n'est pas de la localité de la cible."""
    if amont.localite_id != cible.localite_id:
        raise RuntimeError(
            f"Incoherence localite : serie cible {code_cible!r} "
            f"localite_id={cible.localite_id} vs serie {libelle} amont "
            f"{code_amont!r} localite_id={amont.localite_id}."
        )


def lire_mesures_journalieres(
    session: Session, serie_id: int, niveaux: NiveauxEntrees
) -> list[tuple[date, float]]:
    """Mesures utilisables d'une série par date, leurs niveaux effectifs rangés dans ``niveaux``."""
    rows = session.execute(
        text(
            f"""
            SELECT instant_mesure, valeur,
                   coalesce(niveau_confiance_override, niveau_confiance_derive) AS niveau
            FROM mesures_ressource
            WHERE serie_id = :serie_id
              AND {filtre_mesure_utilisable()}
            ORDER BY instant_mesure
            """
        ),
        {"serie_id": serie_id},
    ).all()
    mesures = [(r.instant_mesure, float(r.valeur)) for r in rows]
    for r in rows:
        niveaux.ajouter(r.instant_mesure, r.niveau)
    return mesures


def ligne_grandeur_metier(
    *,
    grandeur_code: str,
    cible: SerieCible,
    version_formule: int,
    ligne: LignePeriode,
    plafond: NiveauConfiance,
    niveaux_entrees: AbstractSet[str],
) -> dict[str, object]:
    """Paramètres d'insertion d'une ligne, niveau dérivé par R1-R4 et la règle P."""
    return {
        "grandeur_code": grandeur_code,
        "localite_id": cible.localite_id,
        "series_metadonnees_id": cible.serie_id,
        "periode_type": ligne["periode_type"],
        "annee_debut": ligne["annee_debut"],
        "annee_fin": ligne["annee_fin"],
        "mois": ligne["mois"],
        "version_formule": version_formule,
        "valeur": ligne["valeur"],
        "niveau_confiance_derive": calculer_niveau_confiance_derive(
            methode_collecte=cible.confiance.methode_collecte,
            fiabilite_source=cible.confiance.fiabilite_source,
            plafond=plafond,
            niveaux_entrees=niveaux_entrees,
        ),
    }


def inserer_lignes_grandeurs_metier(
    session: Session,
    lignes: Sequence[Mapping[str, object]],
    colonnes_supplementaires: Sequence[str] = (),
) -> None:
    """Insert bulk dans ``grandeurs_metier``, sans flush ; rien si ``lignes`` est vide.

    Les colonnes non listées (statut, validité, override, audit) gardent leur défaut.
    """
    if not lignes:
        return
    colonnes = (*_COLONNES_GRANDEURS_METIER, *colonnes_supplementaires)
    session.execute(
        text(
            f"INSERT INTO grandeurs_metier ({', '.join(colonnes)}) "
            f"VALUES ({', '.join(':' + c for c in colonnes)})"
        ),
        lignes,
    )


def inserer_periodes(
    session: Session,
    *,
    grandeur_code: str,
    cible: SerieCible,
    version_formule: int,
    lignes: Sequence[LignePeriode],
    plafond: NiveauConfiance,
    niveaux: NiveauxEntrees,
) -> None:
    """Insère les lignes, chacune au niveau des entrées de sa période, puis flush.

    Rien (pas même de flush) si ``lignes`` est vide.
    """
    if not lignes:
        return
    inserer_lignes_grandeurs_metier(
        session,
        [
            ligne_grandeur_metier(
                grandeur_code=grandeur_code,
                cible=cible,
                version_formule=version_formule,
                ligne=ligne,
                plafond=plafond,
                niveaux_entrees=niveaux.de_periode(
                    ligne["annee_debut"], ligne["annee_fin"], ligne["mois"]
                ),
            )
            for ligne in lignes
        ],
    )
    session.flush()
