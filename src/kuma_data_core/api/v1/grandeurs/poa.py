"""Irradiation sur plan incliné : ``poa_parametrable`` (mono-plan) et ``poa_bifacial``."""

from __future__ import annotations

from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, status
from fastapi.responses import Response
from sqlalchemy import text
from sqlalchemy.orm import Session

from kuma_data_core.api.codes_erreur import CodeErreur
from kuma_data_core.api.dependencies import CleApiValidee, parametres_requete
from kuma_data_core.api.erreurs import ExceptionKuma
from kuma_data_core.api.v1.grandeurs._commun import (
    SerieSourceResolue,
    _chercher_compagne,
    _construire_reponse,
    _exiger_serie_horaire,
    _lire_alignees,
    _lire_mesures_horaires_par_serie_id,
    _lire_mesures_par_serie_id,
    _lire_si_presente,
    _resoudre_coordonnees,
    _resoudre_serie_exigee,
)
from kuma_data_core.api.v1.schemas.grandeurs import (
    ParametresBifacial,
    ParametresPOA,
    ResultatJournalier,
)
from kuma_data_core.db.session import obtenir_session
from kuma_data_core.editorial.niveaux_confiance import NiveauxEntrees
from kuma_data_core.services.grandeurs.poa_bifacial import (
    PLAFOND_CONFIANCE as PLAFOND_POA_BIFACIAL,
)
from kuma_data_core.services.grandeurs.poa_bifacial import (
    MesureHeureBifacial,
    MesureJourBifacial,
    albedo_du_jour,
    calculer_poa_bifacial,
    calculer_poa_bifacial_horaire,
)
from kuma_data_core.services.grandeurs.poa_parametrable import (
    PLAFOND_CONFIANCE as PLAFOND_POA,
)
from kuma_data_core.services.grandeurs.poa_parametrable import (
    MesureHeurePOA,
    MesureJourPOA,
    calculer_poa_parametrable,
    calculer_poa_parametrable_horaire,
)

routeur = APIRouter()


# === Endpoint POA paramétrable ============================================


def _calculer_poa_parametrable_horaire(
    session: Session,
    serie: SerieSourceResolue,
    params: ParametresPOA,
    compagnes: tuple[int | None, int | None],
    coordonnees: tuple[float, float],
    *,
    niveaux: NiveauxEntrees,
) -> list[ResultatJournalier]:
    """Perez intégré par heure : lève le biais de moyennage (+16 % sur plan incliné).

    Exige une série source horaire ET les compagnes DNI/DHI horaires (pas de
    fallback Liu-Jordan en horaire).
    """
    _exiger_serie_horaire(serie, params.code_serie_source)
    dni_serie_id, dhi_serie_id = compagnes
    if dni_serie_id is None or dhi_serie_id is None:
        raise ExceptionKuma(
            code=CodeErreur.VALIDATION_VALEUR_INVALIDE,
            message=(
                "Le POA horaire (Perez) exige des series compagnes DNI et DHI "
                f"horaires pour la localite de {params.code_serie_source!r} ; absentes."
            ),
            statut_http=status.HTTP_400_BAD_REQUEST,
        )
    alignees = _lire_alignees(
        _lire_mesures_horaires_par_serie_id,
        session,
        (serie.serie_id, dni_serie_id, dhi_serie_id),
        params.periode_debut,
        params.periode_fin,
        niveaux=niveaux,
    )
    mesures: list[MesureHeurePOA] = [
        {"instant_mesure": instant, "ghi": ghi, "dni": dni, "dhi": dhi}
        for instant, (ghi, dni, dhi) in alignees
    ]
    latitude, longitude = coordonnees
    return calculer_poa_parametrable_horaire(
        mesures=mesures, latitude_deg=latitude, longitude_deg=longitude, parametres=params
    )


def _calculer_poa_parametrable_journalier(
    session: Session,
    serie: SerieSourceResolue,
    params: ParametresPOA,
    compagnes: tuple[int | None, int | None],
    coordonnees: tuple[float, float],
    *,
    niveaux: NiveauxEntrees,
) -> list[ResultatJournalier]:
    """POA journalier ; fallback Liu-Jordan dans la fonction pure si DNI/DHI absentes."""
    debut, fin = params.periode_debut, params.periode_fin
    ghi_par_jour = _lire_mesures_par_serie_id(session, serie.serie_id, debut, fin, niveaux=niveaux)
    dni_par_jour = _lire_si_presente(session, compagnes[0], debut, fin, niveaux=niveaux)
    dhi_par_jour = _lire_si_presente(session, compagnes[1], debut, fin, niveaux=niveaux)
    mesures: list[MesureJourPOA] = [
        {
            "instant_mesure": jour,
            "ghi": ghi,
            "dni": dni_par_jour.get(jour),
            "dhi": dhi_par_jour.get(jour),
        }
        for jour, ghi in ghi_par_jour.items()
    ]
    latitude, longitude = coordonnees
    return calculer_poa_parametrable(
        mesures=mesures, latitude_deg=latitude, longitude_deg=longitude, parametres=params
    )


@routeur.get(
    "/poa_parametrable",
    response_model=None,
    status_code=status.HTTP_200_OK,
    summary="POA paramétrable (modèle Perez 1990 + Liu-Jordan fallback)",
)
def grandeur_poa_parametrable(
    params: Annotated[ParametresPOA, Depends(parametres_requete(ParametresPOA))],
    _cle: CleApiValidee,
    session: Annotated[Session, Depends(obtenir_session)],
) -> Response:
    """Calcule la POA journalière à partir d'une série GHI (+ DNI/DHI compagnes).

    Pattern multi-séries automatique :

    - **Série principale attendue** : ``grandeur_code = 'ghi'``. Une série
      pointant une autre grandeur lève une 400
      ``INCOMPATIBILITE_SOURCE_GRANDEUR``.
    - **Séries compagnes cherchées automatiquement** : DNI et DHI sur la
      même ``localite_id`` + ``source_id`` (recherche par
      ``_chercher_serie_compagne``).
    - **Comportement si compagnes présentes** : modèle Perez 1990
      (décomposition diffus en 3 zones, calcul anisotropique).
    - **Comportement si DNI / DHI absentes** : fallback Liu-Jordan
      isotrope automatique (décomposition Erbs 1982 GHI -> DNI estimé +
      DHI estimé, puis transposition isotrope) : précision dégradée
      10-15% sous ciel partiellement couvert.
    - **Traçabilité limitée v1** : la réponse JSON n'indique pas
      explicitement quel modèle a été appliqué.
    """
    niveaux = NiveauxEntrees()
    serie = _resoudre_serie_exigee(session, params.code_serie_source, "ghi", "poa_parametrable")
    coordonnees = _resoudre_coordonnees(session, serie.localite_id)
    # Compagnes granularité-aware : en horaire, ce sont les séries DNI/DHI horaires.
    compagnes = (
        _chercher_compagne(session, serie, "dni"),
        _chercher_compagne(session, serie, "dhi"),
    )
    calculer = (
        _calculer_poa_parametrable_horaire
        if params.methode == "integration_horaire"
        else _calculer_poa_parametrable_journalier
    )
    return _construire_reponse(
        code_grandeur="poa_parametrable",
        code_serie_source=params.code_serie_source,
        parametres_appliques={
            "inclinaison_deg": params.inclinaison_deg,
            "orientation_deg": params.orientation_deg,
            "albedo_sol": params.albedo_sol,
            "methode": params.methode,
        },
        resultats=calculer(session, serie, params, compagnes, coordonnees, niveaux=niveaux),
        format_sortie=params.format_sortie,
        niveaux=niveaux,
        plafond=PLAFOND_POA,
    )


# === Endpoint POA bifacial (modèle infinite-sheds) ===============


def _resoudre_serie_albedo_journalier(
    session: Session, localite_id: int, source_id: int
) -> int | None:
    """Résout la série ``albedo_surface`` journalière de la localité + source.

    Indépendant de la période de la série GHI source : l'albédo n'existe qu'en
    **journalier** (et sert même en mode horaire, broadcast intra-jour),
    donc son ``periode_debut`` diffère de celui du GHI horaire - la recherche par
    compagne stricte ne convient pas. Renvoie ``None`` si absente (→ repli sur
    ``params.albedo_sol``).
    """
    row = session.execute(
        text(
            """
            SELECT id FROM series_metadonnees
            WHERE localite_id = :loc AND source_id = :src
              AND grandeur_code = 'albedo_surface' AND granularite = 'journalier'
              AND actif = TRUE
            ORDER BY periode_debut DESC
            LIMIT 1
            """
        ),
        {"loc": localite_id, "src": source_id},
    ).scalar()
    return int(row) if row is not None else None


def _exiger_dni_dhi_bifacial(
    session: Session, serie: SerieSourceResolue, code_serie_source: str
) -> tuple[int, int]:
    """Compagnes DNI et DHI obligatoires (pas de fallback) ; 400 si l'une manque."""
    dni_serie_id = _chercher_compagne(session, serie, "dni")
    dhi_serie_id = _chercher_compagne(session, serie, "dhi")
    if dni_serie_id is None or dhi_serie_id is None:
        raise ExceptionKuma(
            code=CodeErreur.INCOMPATIBILITE_SOURCE_GRANDEUR,
            message=(
                "Le POA bifacial (infinite-sheds) exige des series compagnes DNI et DHI "
                f"pour la localite de {code_serie_source!r} (pas de fallback) ; absentes."
            ),
            statut_http=status.HTTP_400_BAD_REQUEST,
        )
    return dni_serie_id, dhi_serie_id


def _calculer_poa_bifacial_horaire(
    session: Session,
    serie_ids: tuple[int, int, int],
    params: ParametresBifacial,
    albedo_jour: dict[date, float],
    coordonnees: tuple[float, float],
    *,
    niveaux: NiveauxEntrees,
) -> list[ResultatJournalier]:
    """POA bifacial heure par heure, albédo journalier diffusé aux heures du jour."""
    alignees = _lire_alignees(
        _lire_mesures_horaires_par_serie_id,
        session,
        serie_ids,
        params.periode_debut,
        params.periode_fin,
        niveaux=niveaux,
    )
    mesures: list[MesureHeureBifacial] = [
        {
            "instant_mesure": instant,
            "ghi": ghi,
            "dni": dni,
            "dhi": dhi,
            "albedo": albedo_du_jour(albedo_jour, instant.date(), params.albedo_sol),
        }
        for instant, (ghi, dni, dhi) in alignees
    ]
    latitude, longitude = coordonnees
    return calculer_poa_bifacial_horaire(
        mesures=mesures, latitude_deg=latitude, longitude_deg=longitude, parametres=params
    )


def _calculer_poa_bifacial_journalier(
    session: Session,
    serie_ids: tuple[int, int, int],
    params: ParametresBifacial,
    albedo_jour: dict[date, float],
    coordonnees: tuple[float, float],
    *,
    niveaux: NiveauxEntrees,
) -> list[ResultatJournalier]:
    """POA bifacial sur les moyennes journalières GHI / DNI / DHI."""
    alignees = _lire_alignees(
        _lire_mesures_par_serie_id,
        session,
        serie_ids,
        params.periode_debut,
        params.periode_fin,
        niveaux=niveaux,
    )
    mesures: list[MesureJourBifacial] = [
        {
            "instant_mesure": jour,
            "ghi": ghi,
            "dni": dni,
            "dhi": dhi,
            "albedo": albedo_du_jour(albedo_jour, jour, params.albedo_sol),
        }
        for jour, (ghi, dni, dhi) in alignees
    ]
    latitude, longitude = coordonnees
    return calculer_poa_bifacial(
        mesures=mesures, latitude_deg=latitude, longitude_deg=longitude, parametres=params
    )


@routeur.get(
    "/poa_bifacial",
    response_model=None,
    status_code=status.HTTP_200_OK,
    summary="POA bifacial (modèle infinite-sheds row-aware)",
)
def grandeur_poa_bifacial(
    params: Annotated[ParametresBifacial, Depends(parametres_requete(ParametresBifacial))],
    _cle: CleApiValidee,
    session: Annotated[Session, Depends(obtenir_session)],
) -> Response:
    """Calcule le POA global bifacial (modèle infinite-sheds row-aware).

    **Distinct du `poa_parametrable` mono-plan** : modèle de champ de rangées
    avec face arrière (gcr, hauteur, pitch, bifacialité). Série principale
    attendue : `grandeur_code='ghi'`. Compagnes **DNI + DHI obligatoires**
    (granularité-aware ; pas de fallback Liu-Jordan) → 400 si absentes. Albédo :
    série `albedo_surface` journalière (réel par localité ; repli `albedo_sol` si
    absente ; broadcast aux heures en mode horaire).
    """
    niveaux = NiveauxEntrees()
    serie = _resoudre_serie_exigee(session, params.code_serie_source, "ghi", "poa_bifacial")
    coordonnees = _resoudre_coordonnees(session, serie.localite_id)
    dni_serie_id, dhi_serie_id = _exiger_dni_dhi_bifacial(session, serie, params.code_serie_source)

    albedo_jour = _lire_si_presente(
        session,
        _resoudre_serie_albedo_journalier(session, serie.localite_id, serie.source_id),
        params.periode_debut,
        params.periode_fin,
        niveaux=niveaux,
    )
    if params.methode == "integration_horaire":
        _exiger_serie_horaire(serie, params.code_serie_source)
        calculer = _calculer_poa_bifacial_horaire
    else:
        calculer = _calculer_poa_bifacial_journalier
    resultats = calculer(
        session,
        (serie.serie_id, dni_serie_id, dhi_serie_id),
        params,
        albedo_jour,
        coordonnees,
        niveaux=niveaux,
    )

    return _construire_reponse(
        code_grandeur="poa_bifacial",
        code_serie_source=params.code_serie_source,
        parametres_appliques={
            "inclinaison_deg": params.inclinaison_deg,
            "orientation_deg": params.orientation_deg,
            "gcr": params.gcr,
            "hauteur_m": params.hauteur_m,
            "pitch_m": params.pitch_m,
            "bifacialite": params.bifacialite,
            "albedo_sol": params.albedo_sol,
            "methode": params.methode,
        },
        resultats=resultats,
        format_sortie=params.format_sortie,
        niveaux=niveaux,
        plafond=PLAFOND_POA_BIFACIAL,
    )
