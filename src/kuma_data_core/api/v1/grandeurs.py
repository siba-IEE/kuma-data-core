"""Routes ``/v1/grandeurs/<code>``.

Six grandeurs paramétrables (POA mono-plan et bifacial, productible avec
correction thermique ou avec PR fourni, énergie utile ECS, degrés-jours de
climatisation) et cinq routes calculées ou assemblées à la volée (P50/P90 du
GHI, proxy de salissure, PR réaliste, fiche d'incertitude inter-source par
localité et en collection).

Une route paramétrable résout la série source et sa localité, lit ses mesures
et celles des séries compagnes nécessaires (même localité, même source, même
début de période et même granularité), appelle la fonction de calcul de
``services.grandeurs`` puis rend du JSON ou du CSV (paramètre ``format``). Le
niveau de confiance de chaque résultat suit la règle de propagation P
(ADR-0008).
"""

from __future__ import annotations

import csv
import io
from collections.abc import Sequence
from datetime import UTC, date, datetime, timedelta
from typing import Annotated, Literal, NamedTuple

from fastapi import APIRouter, Depends, Query, status
from fastapi.responses import JSONResponse, Response
from sqlalchemy import text
from sqlalchemy.orm import Session

from kuma_data_core.api.codes_erreur import CodeErreur
from kuma_data_core.api.dependencies import CleApiValidee, parametres_requete
from kuma_data_core.api.erreurs import ExceptionKuma
from kuma_data_core.api.services.serie_lecture import (
    TableMesures,
    resolve_table_from_series_metadata,
)
from kuma_data_core.api.v1.schemas.grandeurs import (
    DegenerescenceFiche,
    EcartPaireInterSource,
    FichePointIncertitude,
    ParametresBifacial,
    ParametresDegreJourClimatisation,
    ParametresEnergieUtileECS,
    ParametresPOA,
    ParametresProductibleCorrectionThermique,
    ParametresProductiblePRFourni,
    ParametresPRRealiste,
    ReponseGhiExceedance,
    ReponseGrandeurF2,
    ReponseIncertitudeInterSource,
    ReponseIncertitudeInterSourceCollection,
    ReponsePRRealiste,
    ReponseTauxSalissureProxy,
    ResultatJournalier,
    ResultatMensuel,
)
from kuma_data_core.db.session import obtenir_session
from kuma_data_core.editorial.niveaux_confiance import (
    NiveauConfiance,
    NiveauxEntrees,
    propager_niveau_confiance,
)
from kuma_data_core.services.grandeurs.degre_jour_climatisation import (
    PLAFOND_CONFIANCE as PLAFOND_DJC,
)
from kuma_data_core.services.grandeurs.degre_jour_climatisation import (
    MesureHeureTemperature,
    MesureJourTemperature,
    calculer_degre_jour_climatisation,
    calculer_degre_jour_climatisation_horaire,
)
from kuma_data_core.services.grandeurs.energie_utile_ecs import (
    PLAFOND_CONFIANCE as PLAFOND_ECS,
)
from kuma_data_core.services.grandeurs.energie_utile_ecs import (
    MesureHeureECS,
    MesureJourECS,
    calculer_energie_utile_ecs,
    calculer_energie_utile_ecs_horaire,
)
from kuma_data_core.services.grandeurs.ghi_exceedance import (
    ANNEE_DEBUT_CLIMATOLOGIE,
    ANNEE_FIN_CLIMATOLOGIE,
    METHODE_PERCENTILE,
    NOMBRE_ANNEES_BASE,
    PAIRES_COLOCALISEES_D29,
    UNITE_GHI_EXCEEDANCE,
    calculer_ghi_exceedance,
    calculer_totaux_annuels,
)
from kuma_data_core.services.grandeurs.ghi_exceedance import (
    PLAFOND_CONFIANCE as PLAFOND_GHI_EXCEEDANCE,
)
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
from kuma_data_core.services.grandeurs.pr_realiste import (
    PLAFOND_CONFIANCE as PLAFOND_PR_REALISTE,
)
from kuma_data_core.services.grandeurs.pr_realiste import (
    MesureJourPRRealiste,
    agreger_pr_mensuel,
    calculer_pr_realiste,
)
from kuma_data_core.services.grandeurs.productible_correction_thermique import (
    PLAFOND_CONFIANCE as PLAFOND_THERMIQUE,
)
from kuma_data_core.services.grandeurs.productible_correction_thermique import (
    MesureHeureThermique,
    MesureJourThermique,
    calculer_productible_correction_thermique,
    calculer_productible_correction_thermique_horaire,
)
from kuma_data_core.services.grandeurs.productible_pr_fourni import (
    PLAFOND_CONFIANCE as PLAFOND_PR_FOURNI,
)
from kuma_data_core.services.grandeurs.productible_pr_fourni import (
    MesureHeurePRFourni,
    MesureJourPRFourni,
    MesureMoisPRFourni,
    calculer_productible_pr_fourni,
    calculer_productible_pr_fourni_horaire,
    calculer_productible_pr_fourni_mensuel,
)
from kuma_data_core.services.grandeurs.soiling_hsu import (
    CLEANING_THRESHOLD_DEFAUT_MM,
    SURFACE_TILT_DEFAUT,
    MesureEntreeSoiling,
    calculer_taux_salissure_proxy,
)
from kuma_data_core.services.grandeurs.soiling_hsu import (
    PLAFOND_CONFIANCE as PLAFOND_SALISSURE,
)

routeur = APIRouter(prefix="/grandeurs", tags=["grandeurs-F2"])


class SerieSourceResolue(NamedTuple):
    """Métadonnées de la série source.

    ``source_code`` et ``granularite`` déterminent la table de mesures à lire.
    ``granularite`` sert aussi à choisir les séries compagnes : séries horaires
    et journalières peuvent partager le même ``periode_debut``.
    """

    serie_id: int
    localite_id: int
    source_id: int
    grandeur_code: str
    localite_code: str
    periode_debut: date
    source_code: str
    granularite: str | None
    periode_fin: date | None


def _resoudre_serie_source(session: Session, code_serie: str) -> SerieSourceResolue:
    """Métadonnées de la série active ``code_serie``.

    Lève 404 ``RESSOURCE_SERIE_INCONNUE`` si elle n'existe pas.
    """
    row = session.execute(
        text(
            """
            SELECT sm.id, sm.localite_id, sm.source_id, sm.grandeur_code,
                   l.code AS localite_code, sm.periode_debut,
                   s.code AS source_code, sm.granularite, sm.periode_fin
            FROM series_metadonnees sm
            JOIN localites l ON l.id = sm.localite_id
            JOIN sources s ON s.id = sm.source_id
            WHERE sm.code = :code
              AND sm.actif = TRUE
            """
        ),
        {"code": code_serie},
    ).first()
    if row is None:
        raise ExceptionKuma(
            code=CodeErreur.RESSOURCE_SERIE_INCONNUE,
            message=f"Serie source {code_serie!r} introuvable.",
            statut_http=status.HTTP_404_NOT_FOUND,
        )
    return SerieSourceResolue(
        serie_id=int(row.id),
        localite_id=int(row.localite_id),
        source_id=int(row.source_id),
        grandeur_code=row.grandeur_code,
        localite_code=row.localite_code,
        periode_debut=row.periode_debut,
        source_code=row.source_code,
        granularite=row.granularite,
        periode_fin=row.periode_fin,
    )


def _resoudre_coordonnees(session: Session, localite_id: int) -> tuple[float, float]:
    """``(latitude, longitude)`` de la localité, en degrés.

    Lève 500 ``SERVEUR_ERREUR_INTERNE`` si elle n'a pas de coordonnées.
    """
    row = session.execute(
        text("SELECT latitude, longitude FROM localites WHERE id = :id"),
        {"id": localite_id},
    ).first()
    if row is None or row.latitude is None or row.longitude is None:
        raise ExceptionKuma(
            code=CodeErreur.SERVEUR_ERREUR_INTERNE,
            message=f"La localité id={localite_id} n'a pas de coordonnées enregistrées.",
            statut_http=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )
    return float(row.latitude), float(row.longitude)


def _chercher_serie_compagne(
    session: Session,
    localite_id: int,
    source_id: int,
    grandeur_code_compagne: str,
    periode_debut_source: date,
    granularite_source: str | None,
) -> int | None:
    """Identifiant de la série d'une autre grandeur, même localité et même source, ou ``None``.

    La compagne doit avoir le même ``periode_debut`` que la source (ce qui sépare
    les séries climatologiques des séries récentes) et la même granularité :
    séries horaires et journalières partagent leur ``periode_debut``, et sans ce
    second filtre une compagne horaire serait lue dans la table journalière.
    """
    row = session.execute(
        text(
            """
            SELECT id FROM series_metadonnees
            WHERE localite_id = :localite_id
              AND source_id = :source_id
              AND grandeur_code = :grandeur_code
              AND periode_debut = :periode_debut_source
              AND granularite IS NOT DISTINCT FROM :granularite_source
              AND actif = TRUE
            ORDER BY id
            LIMIT 1
            """
        ),
        {
            "localite_id": localite_id,
            "source_id": source_id,
            "grandeur_code": grandeur_code_compagne,
            "periode_debut_source": periode_debut_source,
            "granularite_source": granularite_source,
        },
    ).first()
    return int(row.id) if row else None


def _exiger_grandeur(
    grandeur_code: str,
    code_attendu: str,
    code_serie: str,
    endpoint: str,
) -> None:
    """Lève 400 ``INCOMPATIBILITE_SOURCE_GRANDEUR`` si la série ne porte pas ``code_attendu``."""
    if grandeur_code != code_attendu:
        raise ExceptionKuma(
            code=CodeErreur.INCOMPATIBILITE_SOURCE_GRANDEUR,
            message=(
                f"Endpoint {endpoint!r} attend une serie source de grandeur "
                f"{code_attendu!r}, mais {code_serie!r} pointe vers {grandeur_code!r}."
            ),
            statut_http=status.HTTP_400_BAD_REQUEST,
        )


def _lire_mesures_par_serie_id(
    session: Session,
    serie_id: int,
    periode_debut: date,
    periode_fin: date,
    *,
    niveaux: NiveauxEntrees,
) -> dict[date, float]:
    """Valeurs journalières courantes d'une série sur la fenêtre, indexées par date.

    Range le niveau de confiance effectif de chaque valeur lue dans ``niveaux``.
    """
    rows = session.execute(
        text(
            """
            SELECT instant_mesure, valeur,
                   coalesce(niveau_confiance_override, niveau_confiance_derive) AS niveau
            FROM mesures_ressource
            WHERE serie_id = :serie_id
              AND valide_au IS NULL
              AND instant_mesure >= :debut
              AND instant_mesure <= :fin
            ORDER BY instant_mesure
            """
        ),
        {"serie_id": serie_id, "debut": periode_debut, "fin": periode_fin},
    ).all()
    for r in rows:
        niveaux.ajouter(r.instant_mesure, r.niveau)
    return {r.instant_mesure: float(r.valeur) for r in rows}


def _lire_mesures_horaires_par_serie_id(
    session: Session,
    serie_id: int,
    periode_debut: date,
    periode_fin: date,
    *,
    niveaux: NiveauxEntrees,
) -> dict[datetime, float]:
    """Valeurs horaires validées et courantes d'une série, indexées par instant.

    Les lignes rejetées par le contrôle qualité (statut ``brut``) sont exclues.
    La fenêtre porte sur la date UTC. Range le niveau effectif de chaque valeur
    lue sous son jour UTC dans ``niveaux``.
    """
    rows = session.execute(
        text(
            """
            SELECT instant_mesure, valeur,
                   coalesce(niveau_confiance_override, niveau_confiance_derive) AS niveau
            FROM mesures_ressource_horaires
            WHERE serie_id = :serie_id
              AND statut IN ('valide_auto', 'valide_humain', 'publie')
              AND valide_au IS NULL
              AND (instant_mesure AT TIME ZONE 'UTC')::date >= :debut
              AND (instant_mesure AT TIME ZONE 'UTC')::date <= :fin
            ORDER BY instant_mesure
            """
        ),
        {"serie_id": serie_id, "debut": periode_debut, "fin": periode_fin},
    ).all()
    for r in rows:
        niveaux.ajouter(r.instant_mesure.astimezone(UTC).date(), r.niveau)
    return {r.instant_mesure: float(r.valeur) for r in rows}


def _lire_mesures_mensuel_par_serie_id(
    session: Session,
    serie_id: int,
    periode_debut: date,
    periode_fin: date,
    *,
    niveaux: NiveauxEntrees,
) -> dict[tuple[int, int], float]:
    """Valeurs mensuelles courantes d'une série, indexées par ``(annee, mois)``, bornes incluses.

    Range le niveau effectif de chaque valeur lue sous son mois dans ``niveaux``.
    """
    rows = session.execute(
        text(
            """
            SELECT annee, mois, valeur,
                   coalesce(niveau_confiance_override, niveau_confiance_derive) AS niveau
            FROM mesures_ressource_mensuelles
            WHERE serie_id = :serie_id
              AND valide_au IS NULL
              AND (annee, mois) >= (:from_y, :from_m)
              AND (annee, mois) <= (:to_y, :to_m)
            ORDER BY annee, mois
            """
        ),
        {
            "serie_id": serie_id,
            "from_y": periode_debut.year,
            "from_m": periode_debut.month,
            "to_y": periode_fin.year,
            "to_m": periode_fin.month,
        },
    ).all()
    for r in rows:
        niveaux.ajouter((int(r.annee), int(r.mois)), r.niveau)
    return {(int(r.annee), int(r.mois)): float(r.valeur) for r in rows}


def _serialiser_csv_journalier(reponse: ReponseGrandeurF2) -> str:
    """Sérialise en CSV les résultats, journaliers ou mensuels, d'une réponse."""
    buffer = io.StringIO()
    w = csv.writer(buffer)
    w.writerow(["granularite", "instant", "valeur", "unite", "niveau_confiance"])
    for r in reponse.resultats:
        instant = r.instant.isoformat() if isinstance(r, ResultatJournalier) else r.instant
        w.writerow([r.granularite, instant, r.valeur, r.unite, r.niveau_confiance])
    return buffer.getvalue()


def _propager(
    resultats: Sequence[ResultatJournalier | ResultatMensuel],
    niveaux: NiveauxEntrees,
    plafond: NiveauConfiance,
) -> list[ResultatJournalier | ResultatMensuel]:
    """Règle P : chaque résultat prend le niveau des entrées de son jour ou de son mois.

    Le niveau ne dépasse pas le plafond de la grandeur. Un résultat dont le
    jour n'a pas d'entrée rangée (calcul horaire groupé dans un autre fuseau
    que l'UTC des lecteurs) prend, par prudence, le niveau de toutes les
    entrées.
    """
    propages: list[ResultatJournalier | ResultatMensuel] = []
    for r in resultats:
        if isinstance(r, ResultatJournalier):
            entrees = niveaux.du_jour(r.instant)
        else:
            annee, mois = (int(x) for x in r.instant.split("-"))
            entrees = niveaux.du_mois(annee, mois)
        niveau = propager_niveau_confiance(
            entrees or niveaux.tous() or {r.niveau_confiance}, plafond=plafond
        )
        propages.append(r.model_copy(update={"niveau_confiance": niveau}))
    return propages


def _construire_reponse(
    code_grandeur: str,
    code_serie_source: str,
    parametres_appliques: dict[str, object],
    resultats: Sequence[ResultatJournalier | ResultatMensuel],
    format_sortie: Literal["json", "csv"],
    *,
    niveaux: NiveauxEntrees,
    plafond: NiveauConfiance,
) -> Response:
    """Construit la réponse HTTP finale (JSON par défaut, CSV si demandé).

    Le niveau de confiance de chaque résultat suit la règle P à partir des
    niveaux des entrées lues et du plafond de la grandeur (ADR-0008).
    """
    reponse = ReponseGrandeurF2(
        code_grandeur=code_grandeur,
        code_serie_source=code_serie_source,
        parametres_appliques=parametres_appliques,
        resultats=_propager(resultats, niveaux, plafond),
    )
    if format_sortie == "csv":
        return Response(
            content=_serialiser_csv_journalier(reponse),
            media_type="text/csv",
        )
    return JSONResponse(content=reponse.model_dump(mode="json"))


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
    """Irradiation journalière dans le plan des modules (POA), à partir d'une série GHI.

    La série source doit être une série GHI, sinon la route répond 400
    ``INCOMPATIBILITE_SOURCE_GRANDEUR``. Les séries DNI et DHI de la même
    localité et de la même source sont utilisées quand elles existent : le
    calcul suit alors le modèle de Perez (1990). Sinon, en méthode journalière,
    le DNI et le DHI sont estimés à partir du GHI (corrélation d'Erbs 1982) et
    la transposition est isotrope (Liu-Jordan 1963), ce qui est moins précis
    sous ciel partiellement couvert. La réponse n'indique pas lequel des deux
    modèles a été appliqué.

    Avec ``methode=integration_horaire``, la série source doit être horaire et
    les séries DNI et DHI horaires sont obligatoires (400
    ``VALIDATION_VALEUR_INVALIDE`` sinon).
    """
    niveaux = NiveauxEntrees()
    serie = _resoudre_serie_source(session, params.code_serie_source)
    _exiger_grandeur(serie.grandeur_code, "ghi", params.code_serie_source, "poa_parametrable")

    latitude, longitude = _resoudre_coordonnees(session, serie.localite_id)

    dni_serie_id = _chercher_serie_compagne(
        session, serie.localite_id, serie.source_id, "dni", serie.periode_debut, serie.granularite
    )
    dhi_serie_id = _chercher_serie_compagne(
        session, serie.localite_id, serie.source_id, "dhi", serie.periode_debut, serie.granularite
    )

    if params.methode == "integration_horaire":
        # Pas de repli Liu-Jordan en horaire : les séries DNI et DHI sont exigées.
        if serie.granularite != "horaire":
            raise ExceptionKuma(
                code=CodeErreur.VALIDATION_VALEUR_INVALIDE,
                message=(
                    "methode='integration_horaire' exige une serie source horaire "
                    f"(granularite='horaire'), mais {params.code_serie_source!r} est de "
                    f"granularite {serie.granularite!r}."
                ),
                statut_http=status.HTTP_400_BAD_REQUEST,
            )
        if dni_serie_id is None or dhi_serie_id is None:
            raise ExceptionKuma(
                code=CodeErreur.VALIDATION_VALEUR_INVALIDE,
                message=(
                    "Le POA horaire (Perez) exige des series compagnes DNI et DHI "
                    f"horaires pour la localite de {params.code_serie_source!r} ; absentes."
                ),
                statut_http=status.HTTP_400_BAD_REQUEST,
            )
        ghi_h = _lire_mesures_horaires_par_serie_id(
            session, serie.serie_id, params.periode_debut, params.periode_fin, niveaux=niveaux
        )
        dni_h = _lire_mesures_horaires_par_serie_id(
            session, dni_serie_id, params.periode_debut, params.periode_fin, niveaux=niveaux
        )
        dhi_h = _lire_mesures_horaires_par_serie_id(
            session, dhi_serie_id, params.periode_debut, params.periode_fin, niveaux=niveaux
        )
        mesures_horaires: list[MesureHeurePOA] = [
            {"instant_mesure": instant, "ghi": ghi, "dni": dni_h[instant], "dhi": dhi_h[instant]}
            for instant, ghi in ghi_h.items()
            if instant in dni_h and instant in dhi_h
        ]
        resultats = calculer_poa_parametrable_horaire(
            mesures=mesures_horaires,
            latitude_deg=latitude,
            longitude_deg=longitude,
            parametres=params,
        )
    else:
        ghi_par_jour = _lire_mesures_par_serie_id(
            session, serie.serie_id, params.periode_debut, params.periode_fin, niveaux=niveaux
        )
        # Sans DNI ou DHI, la fonction de calcul applique le repli Liu-Jordan.
        dni_par_jour: dict[date, float] = (
            _lire_mesures_par_serie_id(
                session, dni_serie_id, params.periode_debut, params.periode_fin, niveaux=niveaux
            )
            if dni_serie_id is not None
            else {}
        )
        dhi_par_jour: dict[date, float] = (
            _lire_mesures_par_serie_id(
                session, dhi_serie_id, params.periode_debut, params.periode_fin, niveaux=niveaux
            )
            if dhi_serie_id is not None
            else {}
        )
        mesures: list[MesureJourPOA] = [
            {
                "instant_mesure": jour,
                "ghi": ghi,
                "dni": dni_par_jour.get(jour),
                "dhi": dhi_par_jour.get(jour),
            }
            for jour, ghi in ghi_par_jour.items()
        ]
        resultats = calculer_poa_parametrable(
            mesures=mesures,
            latitude_deg=latitude,
            longitude_deg=longitude,
            parametres=params,
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
        resultats=resultats,
        format_sortie=params.format_sortie,
        niveaux=niveaux,
        plafond=PLAFOND_POA,
    )


def _resoudre_serie_albedo_journalier(
    session: Session, localite_id: int, source_id: int
) -> int | None:
    """Série ``albedo_surface`` journalière de la localité et de la source, ou ``None``.

    L'albédo n'existe qu'en journalier, y compris pour un calcul horaire : son
    ``periode_debut`` diffère de celui d'un GHI horaire et
    ``_chercher_serie_compagne`` ne le trouverait pas.
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
    """Irradiation journalière dans le plan des modules d'un champ de rangées bifacial.

    Modèle infinite-sheds : à la différence de ``poa_parametrable`` (plan seul),
    il tient compte des rangées (gcr, hauteur, pas entre rangées) et de la face
    arrière. La série source doit être une série GHI ; les séries DNI et DHI de
    la même localité et de la même source sont obligatoires (400
    ``INCOMPATIBILITE_SOURCE_GRANDEUR`` si l'une manque). L'albédo vient de la
    série journalière ``albedo_surface`` de la même localité et de la même
    source ; les jours où elle n'a pas de valeur, ``albedo_sol`` est utilisé.

    Avec ``methode=integration_horaire``, la série source doit être horaire (400
    ``VALIDATION_VALEUR_INVALIDE`` sinon) et l'albédo du jour vaut pour chacune
    de ses heures.
    """
    niveaux = NiveauxEntrees()
    serie = _resoudre_serie_source(session, params.code_serie_source)
    _exiger_grandeur(serie.grandeur_code, "ghi", params.code_serie_source, "poa_bifacial")
    latitude, longitude = _resoudre_coordonnees(session, serie.localite_id)

    dni_serie_id = _chercher_serie_compagne(
        session, serie.localite_id, serie.source_id, "dni", serie.periode_debut, serie.granularite
    )
    dhi_serie_id = _chercher_serie_compagne(
        session, serie.localite_id, serie.source_id, "dhi", serie.periode_debut, serie.granularite
    )
    if dni_serie_id is None or dhi_serie_id is None:
        raise ExceptionKuma(
            code=CodeErreur.INCOMPATIBILITE_SOURCE_GRANDEUR,
            message=(
                "Le POA bifacial (infinite-sheds) exige des series compagnes DNI et DHI "
                f"pour la localite de {params.code_serie_source!r} (pas de fallback) ; absentes."
            ),
            statut_http=status.HTTP_400_BAD_REQUEST,
        )

    albedo_serie_id = _resoudre_serie_albedo_journalier(session, serie.localite_id, serie.source_id)
    albedo_jour: dict[date, float] = (
        _lire_mesures_par_serie_id(
            session, albedo_serie_id, params.periode_debut, params.periode_fin, niveaux=niveaux
        )
        if albedo_serie_id is not None
        else {}
    )

    if params.methode == "integration_horaire":
        if serie.granularite != "horaire":
            raise ExceptionKuma(
                code=CodeErreur.VALIDATION_VALEUR_INVALIDE,
                message=(
                    "methode='integration_horaire' exige une serie source horaire "
                    f"(granularite='horaire'), mais {params.code_serie_source!r} est de "
                    f"granularite {serie.granularite!r}."
                ),
                statut_http=status.HTTP_400_BAD_REQUEST,
            )
        ghi_h = _lire_mesures_horaires_par_serie_id(
            session, serie.serie_id, params.periode_debut, params.periode_fin, niveaux=niveaux
        )
        dni_h = _lire_mesures_horaires_par_serie_id(
            session, dni_serie_id, params.periode_debut, params.periode_fin, niveaux=niveaux
        )
        dhi_h = _lire_mesures_horaires_par_serie_id(
            session, dhi_serie_id, params.periode_debut, params.periode_fin, niveaux=niveaux
        )
        mesures_horaires: list[MesureHeureBifacial] = [
            {
                "instant_mesure": instant,
                "ghi": ghi,
                "dni": dni_h[instant],
                "dhi": dhi_h[instant],
                "albedo": albedo_du_jour(albedo_jour, instant.date(), params.albedo_sol),
            }
            for instant, ghi in ghi_h.items()
            if instant in dni_h and instant in dhi_h
        ]
        resultats = calculer_poa_bifacial_horaire(
            mesures=mesures_horaires,
            latitude_deg=latitude,
            longitude_deg=longitude,
            parametres=params,
        )
    else:
        ghi_j = _lire_mesures_par_serie_id(
            session, serie.serie_id, params.periode_debut, params.periode_fin, niveaux=niveaux
        )
        dni_j = _lire_mesures_par_serie_id(
            session, dni_serie_id, params.periode_debut, params.periode_fin, niveaux=niveaux
        )
        dhi_j = _lire_mesures_par_serie_id(
            session, dhi_serie_id, params.periode_debut, params.periode_fin, niveaux=niveaux
        )
        mesures: list[MesureJourBifacial] = [
            {
                "instant_mesure": jour,
                "ghi": ghi,
                "dni": dni_j[jour],
                "dhi": dhi_j[jour],
                "albedo": albedo_du_jour(albedo_jour, jour, params.albedo_sol),
            }
            for jour, ghi in ghi_j.items()
            if jour in dni_j and jour in dhi_j
        ]
        resultats = calculer_poa_bifacial(
            mesures=mesures,
            latitude_deg=latitude,
            longitude_deg=longitude,
            parametres=params,
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


def _lire_t2m_compagne(
    session: Session,
    localite_id: int,
    source_id: int,
    code_serie_source: str,
    endpoint: str,
    periode_debut: date,
    periode_fin: date,
    periode_debut_source: date,
    granularite_source: str | None,
    *,
    niveaux: NiveauxEntrees,
) -> dict[date, float]:
    """Valeurs journalières de la série T2M compagne (même localité, même source).

    Lève 400 ``INCOMPATIBILITE_SOURCE_GRANDEUR`` si elle n'existe pas.
    """
    t2m_serie_id = _chercher_serie_compagne(
        session, localite_id, source_id, "t2m", periode_debut_source, granularite_source
    )
    if t2m_serie_id is None:
        raise ExceptionKuma(
            code=CodeErreur.INCOMPATIBILITE_SOURCE_GRANDEUR,
            message=(
                f"Endpoint {endpoint!r} requiert une serie T2M compagne de "
                f"{code_serie_source!r} (meme localite et source). Aucune trouvee."
            ),
            statut_http=status.HTTP_400_BAD_REQUEST,
        )
    return _lire_mesures_par_serie_id(
        session, t2m_serie_id, periode_debut, periode_fin, niveaux=niveaux
    )


@routeur.get(
    "/productible_correction_thermique",
    response_model=None,
    status_code=status.HTTP_200_OK,
    summary="Productible avec correction thermique (NOCT simple, Ross 1980)",
)
def grandeur_productible_correction_thermique(
    params: Annotated[
        ParametresProductibleCorrectionThermique,
        Depends(parametres_requete(ParametresProductibleCorrectionThermique)),
    ],
    _cle: CleApiValidee,
    session: Annotated[Session, Depends(obtenir_session)],
) -> Response:
    """Productible journalier avec correction thermique (modèle NOCT simple, Ross 1980).

    La série source doit être une série GHI. La série T2M de la même localité
    et de la même source est obligatoire, la correction dépendant de la
    température ambiante (400 ``INCOMPATIBILITE_SOURCE_GRANDEUR`` si elle
    manque). Température de cellule : ``T_cell = T_amb + (NOCT - 20) x G / 800``.

    Avec ``methode=integration_horaire``, la série source et la série T2M
    doivent être horaires.
    """
    niveaux = NiveauxEntrees()
    serie = _resoudre_serie_source(session, params.code_serie_source)
    _exiger_grandeur(
        serie.grandeur_code, "ghi", params.code_serie_source, "productible_correction_thermique"
    )

    if params.methode == "integration_horaire":
        if serie.granularite != "horaire":
            raise ExceptionKuma(
                code=CodeErreur.VALIDATION_VALEUR_INVALIDE,
                message=(
                    "methode='integration_horaire' exige une serie source horaire "
                    f"(granularite='horaire'), mais {params.code_serie_source!r} est de "
                    f"granularite {serie.granularite!r}."
                ),
                statut_http=status.HTTP_400_BAD_REQUEST,
            )
        t2m_serie_id = _chercher_serie_compagne(
            session,
            serie.localite_id,
            serie.source_id,
            "t2m",
            serie.periode_debut,
            serie.granularite,
        )
        if t2m_serie_id is None:
            raise ExceptionKuma(
                code=CodeErreur.INCOMPATIBILITE_SOURCE_GRANDEUR,
                message=(
                    "Endpoint 'productible_correction_thermique' requiert une serie T2M "
                    f"horaire compagne de {params.code_serie_source!r}. Aucune trouvee."
                ),
                statut_http=status.HTTP_400_BAD_REQUEST,
            )
        ghi_h = _lire_mesures_horaires_par_serie_id(
            session, serie.serie_id, params.periode_debut, params.periode_fin, niveaux=niveaux
        )
        t2m_h = _lire_mesures_horaires_par_serie_id(
            session, t2m_serie_id, params.periode_debut, params.periode_fin, niveaux=niveaux
        )
        mesures_horaires: list[MesureHeureThermique] = [
            {"instant_mesure": instant, "t_amb_degc": t2m_h[instant], "irradiance_w_par_m2": ghi}
            for instant, ghi in ghi_h.items()
            if instant in t2m_h
        ]
        resultats = calculer_productible_correction_thermique_horaire(
            mesures=mesures_horaires, parametres=params
        )
    else:
        ghi_par_jour = _lire_mesures_par_serie_id(
            session, serie.serie_id, params.periode_debut, params.periode_fin, niveaux=niveaux
        )
        t2m_par_jour = _lire_t2m_compagne(
            session,
            serie.localite_id,
            serie.source_id,
            params.code_serie_source,
            "productible_correction_thermique",
            params.periode_debut,
            params.periode_fin,
            serie.periode_debut,
            serie.granularite,
            niveaux=niveaux,
        )
        mesures: list[MesureJourThermique] = [
            {
                "instant_mesure": jour,
                "t_amb_degc": t2m_par_jour[jour],
                "irradiance_kwh_par_m2_jour": ghi,
            }
            for jour, ghi in ghi_par_jour.items()
            if jour in t2m_par_jour
        ]
        resultats = calculer_productible_correction_thermique(mesures=mesures, parametres=params)

    parametres_appliques: dict[str, object] = {
        "noct_degc": params.noct_degc,
        "coeff_temp_pourcent_par_degc": params.coeff_temp_pourcent_par_degc,
        "puissance_stc_wc": params.puissance_stc_wc,
        "methode": params.methode,
    }

    return _construire_reponse(
        code_grandeur="productible_correction_thermique",
        code_serie_source=params.code_serie_source,
        parametres_appliques=parametres_appliques,
        resultats=resultats,
        format_sortie=params.format_sortie,
        niveaux=niveaux,
        plafond=PLAFOND_THERMIQUE,
    )


@routeur.get(
    "/productible_pr_fourni",
    response_model=None,
    status_code=status.HTTP_200_OK,
    summary="Productible avec PR fourni (brut Marion 2005 + PR_T Dierauf 2013)",
)
def grandeur_productible_pr_fourni(
    params: Annotated[
        ParametresProductiblePRFourni, Depends(parametres_requete(ParametresProductiblePRFourni))
    ],
    _cle: CleApiValidee,
    session: Annotated[Session, Depends(obtenir_session)],
) -> Response:
    """Productible avec un PR fourni par l'appelant, brut ou corrigé de la température.

    La série source doit être une série GHI.

    - ``correction=aucune`` : PR brut (Marion 2005),
      ``E_AC = P_STC x G / G_STC x PR``, sans autre série.
    - ``correction=temperature`` : PR_T (Dierauf 2013). La série T2M de la même
      localité et de la même source est obligatoire (400
      ``INCOMPATIBILITE_SOURCE_GRANDEUR`` si elle manque).

    Une série source mensuelle (climatologie) n'est acceptée qu'avec
    ``correction=aucune`` : le résultat est alors un productible quotidien moyen
    par mois (``instant`` au format ``YYYY-MM``). La correction thermique, non
    linéaire, ne s'applique pas à une moyenne mensuelle (400). Une série
    calculée par Kuma (source ``kuma_calculs``) n'est pas acceptée comme source
    (400). Avec ``methode=integration_horaire``, la série source doit être
    horaire.

    Les variantes PR_W et PR_C de Dierauf 2013 ne sont pas proposées.
    """
    niveaux = NiveauxEntrees()
    serie = _resoudre_serie_source(session, params.code_serie_source)

    # La nature de la source est vérifiée avant sa grandeur : une série
    # kuma_calculs ne porte jamais 'ghi', et l'ordre inverse masquerait le
    # message « série calculée non admise ».
    table_cible = resolve_table_from_series_metadata(
        source_code=serie.source_code,
        granularite=serie.granularite,
    )

    if table_cible == TableMesures.GRANDEURS_METIER:
        raise ExceptionKuma(
            code=CodeErreur.INCOMPATIBILITE_SOURCE_GRANDEUR,
            message=(
                f"Endpoint 'productible_pr_fourni' n'accepte pas de serie source "
                f"calculee Kuma (source.code='kuma_calculs'). Serie {params.code_serie_source!r} "
                "pointe sur 'grandeurs_metier'."
            ),
            statut_http=status.HTTP_400_BAD_REQUEST,
        )

    _exiger_grandeur(serie.grandeur_code, "ghi", params.code_serie_source, "productible_pr_fourni")

    if params.methode == "integration_horaire":
        if serie.granularite != "horaire":
            raise ExceptionKuma(
                code=CodeErreur.VALIDATION_VALEUR_INVALIDE,
                message=(
                    "methode='integration_horaire' exige une serie source horaire "
                    f"(granularite='horaire'), mais {params.code_serie_source!r} est de "
                    f"granularite {serie.granularite!r}."
                ),
                statut_http=status.HTTP_400_BAD_REQUEST,
            )
        ghi_h = _lire_mesures_horaires_par_serie_id(
            session, serie.serie_id, params.periode_debut, params.periode_fin, niveaux=niveaux
        )
        mesures_horaires: list[MesureHeurePRFourni]
        if params.correction == "temperature":
            t2m_serie_id = _chercher_serie_compagne(
                session,
                serie.localite_id,
                serie.source_id,
                "t2m",
                serie.periode_debut,
                serie.granularite,
            )
            if t2m_serie_id is None:
                raise ExceptionKuma(
                    code=CodeErreur.INCOMPATIBILITE_SOURCE_GRANDEUR,
                    message=(
                        "Endpoint 'productible_pr_fourni' en correction='temperature' horaire "
                        f"requiert une serie T2M horaire compagne de {params.code_serie_source!r}. "
                        "Aucune trouvee."
                    ),
                    statut_http=status.HTTP_400_BAD_REQUEST,
                )
            t2m_h = _lire_mesures_horaires_par_serie_id(
                session, t2m_serie_id, params.periode_debut, params.periode_fin, niveaux=niveaux
            )
            mesures_horaires = [
                {
                    "instant_mesure": instant,
                    "irradiance_w_par_m2": ghi,
                    "t_amb_degc": t2m_h[instant],
                }
                for instant, ghi in ghi_h.items()
                if instant in t2m_h
            ]
        else:
            mesures_horaires = [
                {"instant_mesure": instant, "irradiance_w_par_m2": ghi, "t_amb_degc": None}
                for instant, ghi in ghi_h.items()
            ]
        resultats = calculer_productible_pr_fourni_horaire(
            mesures=mesures_horaires, parametres=params
        )
        return _construire_reponse(
            code_grandeur="productible_pr_fourni",
            code_serie_source=params.code_serie_source,
            parametres_appliques={
                "pr_fourni": params.pr_fourni,
                "correction": params.correction,
                "puissance_stc_wc": params.puissance_stc_wc,
                "methode": params.methode,
                **(
                    {
                        "noct_degc": params.noct_degc,
                        "coeff_temp_pourcent_par_degc": params.coeff_temp_pourcent_par_degc,
                    }
                    if params.correction == "temperature"
                    else {}
                ),
            },
            resultats=resultats,
            format_sortie=params.format_sortie,
            niveaux=niveaux,
            plafond=PLAFOND_PR_FOURNI,
        )

    if table_cible == TableMesures.MENSUEL_RESSOURCE:
        if params.correction == "temperature":
            raise ExceptionKuma(
                code=CodeErreur.INCOMPATIBILITE_SOURCE_GRANDEUR,
                message=(
                    "Endpoint 'productible_pr_fourni' sur serie mensuelle climato "
                    "n'accepte que correction='aucune' (le mode 'temperature' est "
                    "non-lineaire et incompatible avec une moyenne quotidienne "
                    "agregee sur le mois)."
                ),
                statut_http=status.HTTP_400_BAD_REQUEST,
            )
        ghi_par_mois = _lire_mesures_mensuel_par_serie_id(
            session, serie.serie_id, params.periode_debut, params.periode_fin, niveaux=niveaux
        )
        mesures_mensuel: list[MesureMoisPRFourni] = [
            {
                "annee": annee,
                "mois": mois,
                "irradiance_kwh_par_m2_jour": ghi,
            }
            for (annee, mois), ghi in ghi_par_mois.items()
        ]
        resultats_mensuel = calculer_productible_pr_fourni_mensuel(
            mesures=mesures_mensuel, parametres=params
        )
        return _construire_reponse(
            code_grandeur="productible_pr_fourni",
            code_serie_source=params.code_serie_source,
            parametres_appliques={
                "pr_fourni": params.pr_fourni,
                "correction": params.correction,
                "puissance_stc_wc": params.puissance_stc_wc,
                "methode": params.methode,
            },
            resultats=resultats_mensuel,
            format_sortie=params.format_sortie,
            niveaux=niveaux,
            plafond=PLAFOND_PR_FOURNI,
        )

    ghi_par_jour = _lire_mesures_par_serie_id(
        session, serie.serie_id, params.periode_debut, params.periode_fin, niveaux=niveaux
    )
    t2m_par_jour: dict[date, float] = {}
    if params.correction == "temperature":
        t2m_par_jour = _lire_t2m_compagne(
            session,
            serie.localite_id,
            serie.source_id,
            params.code_serie_source,
            "productible_pr_fourni",
            params.periode_debut,
            params.periode_fin,
            serie.periode_debut,
            serie.granularite,
            niveaux=niveaux,
        )

    mesures: list[MesureJourPRFourni] = [
        {
            "instant_mesure": jour,
            "irradiance_kwh_par_m2_jour": ghi,
            "t_amb_degc": t2m_par_jour.get(jour),
        }
        for jour, ghi in ghi_par_jour.items()
        if (params.correction == "aucune") or (jour in t2m_par_jour)
    ]
    resultats = calculer_productible_pr_fourni(mesures=mesures, parametres=params)
    return _construire_reponse(
        code_grandeur="productible_pr_fourni",
        code_serie_source=params.code_serie_source,
        parametres_appliques={
            "pr_fourni": params.pr_fourni,
            "correction": params.correction,
            "puissance_stc_wc": params.puissance_stc_wc,
            "methode": params.methode,
            **(
                {
                    "noct_degc": params.noct_degc,
                    "coeff_temp_pourcent_par_degc": params.coeff_temp_pourcent_par_degc,
                }
                if params.correction == "temperature"
                else {}
            ),
        },
        resultats=resultats,
        format_sortie=params.format_sortie,
        niveaux=niveaux,
        plafond=PLAFOND_PR_FOURNI,
    )


@routeur.get(
    "/energie_utile_ecs",
    response_model=None,
    status_code=status.HTTP_200_OK,
    summary="Énergie utile ECS bord-capteur (Hottel-Whillier-Bliss)",
)
def grandeur_energie_utile_ecs(
    params: Annotated[
        ParametresEnergieUtileECS, Depends(parametres_requete(ParametresEnergieUtileECS))
    ],
    _cle: CleApiValidee,
    session: Annotated[Session, Depends(obtenir_session)],
) -> Response:
    """Énergie utile d'un capteur solaire thermique pour l'eau chaude sanitaire.

    Énergie en sortie de capteur, par l'équation de Hottel-Whillier-Bliss :
    ``eta = eta0 - a1 x dT / G - a2 x dT² / G``, puis ``Q_utile = eta x G``. La
    série source doit être une série GHI. La série T2M de la même localité et de
    la même source est obligatoire, le rendement dépendant de l'écart entre la
    température du fluide et la température ambiante (400
    ``INCOMPATIBILITE_SOURCE_GRANDEUR`` si elle manque).

    Avec ``methode=integration_horaire``, la série source et la série T2M
    doivent être horaires.
    """
    niveaux = NiveauxEntrees()
    serie = _resoudre_serie_source(session, params.code_serie_source)
    _exiger_grandeur(serie.grandeur_code, "ghi", params.code_serie_source, "energie_utile_ecs")

    if params.methode == "integration_horaire":
        if serie.granularite != "horaire":
            raise ExceptionKuma(
                code=CodeErreur.VALIDATION_VALEUR_INVALIDE,
                message=(
                    "methode='integration_horaire' exige une serie source horaire "
                    f"(granularite='horaire'), mais {params.code_serie_source!r} est de "
                    f"granularite {serie.granularite!r}."
                ),
                statut_http=status.HTTP_400_BAD_REQUEST,
            )
        t2m_serie_id = _chercher_serie_compagne(
            session,
            serie.localite_id,
            serie.source_id,
            "t2m",
            serie.periode_debut,
            serie.granularite,
        )
        if t2m_serie_id is None:
            raise ExceptionKuma(
                code=CodeErreur.INCOMPATIBILITE_SOURCE_GRANDEUR,
                message=(
                    "Endpoint 'energie_utile_ecs' horaire requiert une serie T2M horaire "
                    f"compagne de {params.code_serie_source!r}. Aucune trouvee."
                ),
                statut_http=status.HTTP_400_BAD_REQUEST,
            )
        ghi_h = _lire_mesures_horaires_par_serie_id(
            session, serie.serie_id, params.periode_debut, params.periode_fin, niveaux=niveaux
        )
        t2m_h = _lire_mesures_horaires_par_serie_id(
            session, t2m_serie_id, params.periode_debut, params.periode_fin, niveaux=niveaux
        )
        mesures_horaires: list[MesureHeureECS] = [
            {"instant_mesure": instant, "t_amb_degc": t2m_h[instant], "irradiance_w_par_m2": ghi}
            for instant, ghi in ghi_h.items()
            if instant in t2m_h
        ]
        resultats = calculer_energie_utile_ecs_horaire(mesures=mesures_horaires, parametres=params)
        return _construire_reponse(
            code_grandeur="energie_utile_ecs",
            code_serie_source=params.code_serie_source,
            parametres_appliques={
                "rendement_optique_eta0": params.rendement_optique_eta0,
                "pertes_lineaires_a1": params.pertes_lineaires_a1,
                "pertes_quadratiques_a2": params.pertes_quadratiques_a2,
                "temperature_fluide_entree_degc": params.temperature_fluide_entree_degc,
                "methode": params.methode,
            },
            resultats=resultats,
            format_sortie=params.format_sortie,
            niveaux=niveaux,
            plafond=PLAFOND_ECS,
        )

    ghi_par_jour = _lire_mesures_par_serie_id(
        session, serie.serie_id, params.periode_debut, params.periode_fin, niveaux=niveaux
    )
    t2m_par_jour = _lire_t2m_compagne(
        session,
        serie.localite_id,
        serie.source_id,
        params.code_serie_source,
        "energie_utile_ecs",
        params.periode_debut,
        params.periode_fin,
        serie.periode_debut,
        serie.granularite,
        niveaux=niveaux,
    )

    mesures: list[MesureJourECS] = [
        {
            "instant_mesure": jour,
            "t_amb_degc": t2m_par_jour[jour],
            "irradiance_kwh_par_m2_jour": ghi,
        }
        for jour, ghi in ghi_par_jour.items()
        if jour in t2m_par_jour
    ]
    resultats = calculer_energie_utile_ecs(mesures=mesures, parametres=params)
    return _construire_reponse(
        code_grandeur="energie_utile_ecs",
        code_serie_source=params.code_serie_source,
        parametres_appliques={
            "rendement_optique_eta0": params.rendement_optique_eta0,
            "pertes_lineaires_a1": params.pertes_lineaires_a1,
            "pertes_quadratiques_a2": params.pertes_quadratiques_a2,
            "temperature_fluide_entree_degc": params.temperature_fluide_entree_degc,
            "methode": params.methode,
        },
        resultats=resultats,
        format_sortie=params.format_sortie,
        niveaux=niveaux,
        plafond=PLAFOND_ECS,
    )


@routeur.get(
    "/degre_jour_climatisation",
    response_model=None,
    status_code=status.HTTP_200_OK,
    summary="Degrés-jours de climatisation (moyenne journalière ou intégration horaire)",
)
def grandeur_degre_jour_climatisation(
    params: Annotated[
        ParametresDegreJourClimatisation,
        Depends(parametres_requete(ParametresDegreJourClimatisation)),
    ],
    _cle: CleApiValidee,
    session: Annotated[Session, Depends(obtenir_session)],
) -> Response:
    """Degrés-jours de climatisation par mois, pour une température de base ``T_b``.

    La série source doit être une série T2M, sinon la route répond 400
    ``INCOMPATIBILITE_SOURCE_GRANDEUR`` ; aucune autre série n'est lue. Les
    résultats sont mensuels (``instant`` au format ``YYYY-MM``) : somme sur le
    mois des écarts positifs à ``T_b``, calculés sur la température moyenne du
    jour (``methode=moyenne_journaliere``) ou heure par heure
    (``methode=integration_horaire``, Erbs 1983, série source horaire exigée).
    """
    niveaux = NiveauxEntrees()
    serie = _resoudre_serie_source(session, params.code_serie_source)
    _exiger_grandeur(
        serie.grandeur_code, "t2m", params.code_serie_source, "degre_jour_climatisation"
    )

    if params.methode == "integration_horaire":
        if serie.granularite != "horaire":
            raise ExceptionKuma(
                code=CodeErreur.VALIDATION_VALEUR_INVALIDE,
                message=(
                    "methode='integration_horaire' exige une serie source horaire "
                    f"(granularite='horaire'), mais {params.code_serie_source!r} est de "
                    f"granularite {serie.granularite!r}. Fournir une serie T2M horaire "
                    "ou utiliser methode='moyenne_journaliere'."
                ),
                statut_http=status.HTTP_400_BAD_REQUEST,
            )
        t2m_par_heure = _lire_mesures_horaires_par_serie_id(
            session, serie.serie_id, params.periode_debut, params.periode_fin, niveaux=niveaux
        )
        mesures_horaires: list[MesureHeureTemperature] = [
            {"instant_mesure": instant, "t_degc": valeur}
            for instant, valeur in t2m_par_heure.items()
        ]
        resultats = calculer_degre_jour_climatisation_horaire(
            mesures=mesures_horaires, parametres=params
        )
    else:
        t2m_par_jour = _lire_mesures_par_serie_id(
            session, serie.serie_id, params.periode_debut, params.periode_fin, niveaux=niveaux
        )
        mesures: list[MesureJourTemperature] = [
            {"instant_mesure": jour, "t_moy_degc": valeur} for jour, valeur in t2m_par_jour.items()
        ]
        resultats = calculer_degre_jour_climatisation(mesures=mesures, parametres=params)

    return _construire_reponse(
        code_grandeur="degre_jour_climatisation",
        code_serie_source=params.code_serie_source,
        parametres_appliques={
            "base_temperature_degc": params.base_temperature_degc,
            "methode": params.methode,
        },
        resultats=resultats,
        format_sortie=params.format_sortie,
        niveaux=niveaux,
        plafond=PLAFOND_DJC,
    )


def _resoudre_serie_ghi_mensuelle_1991_2020(
    session: Session, code_localite: str
) -> tuple[int, str]:
    """``(serie_id, code_serie)`` de la série GHI NASA POWER de la localité débutant en 1991.

    Lève 404 ``RESSOURCE_LOCALITE_INCONNUE`` si aucune n'est rattachée à la
    localité (ou si la localité n'existe pas).
    """
    row = session.execute(
        text(
            """
            SELECT sm.id AS serie_id, sm.code AS code_serie
            FROM series_metadonnees sm
            JOIN localites l ON l.id = sm.localite_id
            JOIN sources s ON s.id = sm.source_id
            WHERE l.code = :code_localite
              AND sm.grandeur_code = 'ghi'
              AND s.code = 'nasa_power'
              AND EXTRACT(YEAR FROM sm.periode_debut) = :annee_debut
              AND sm.actif = TRUE
            ORDER BY sm.id
            LIMIT 1
            """
        ),
        {"code_localite": code_localite, "annee_debut": ANNEE_DEBUT_CLIMATOLOGIE},
    ).first()
    if row is None:
        raise ExceptionKuma(
            code=CodeErreur.RESSOURCE_LOCALITE_INCONNUE,
            message=(
                f"Aucune série GHI mensuelle {ANNEE_DEBUT_CLIMATOLOGIE}-"
                f"{ANNEE_FIN_CLIMATOLOGIE} n'est rattachée à la localité "
                f"{code_localite!r}."
            ),
            statut_http=status.HTTP_404_NOT_FOUND,
        )
    return int(row.serie_id), str(row.code_serie)


def _lire_mensuelles_brutes(
    session: Session, serie_id: int, *, niveaux: NiveauxEntrees
) -> list[tuple[int, int, float]]:
    """Mesures mensuelles courantes d'une série, en tuples ``(annee, mois, valeur)`` triés.

    Tout est chargé d'un coup (360 lignes pour une série 1991-2020 complète).
    Range le niveau effectif de chaque valeur lue dans ``niveaux``.
    """
    rows = session.execute(
        text(
            """
            SELECT annee, mois, valeur,
                   coalesce(niveau_confiance_override, niveau_confiance_derive) AS niveau
            FROM mesures_ressource_mensuelles
            WHERE serie_id = :serie_id AND valide_au IS NULL
            ORDER BY annee, mois
            """
        ),
        {"serie_id": serie_id},
    ).all()
    for r in rows:
        niveaux.ajouter((int(r.annee), int(r.mois)), r.niveau)
    return [(int(r.annee), int(r.mois), float(r.valeur)) for r in rows]


def _construire_limite_ghi_exceedance(code_localite: str) -> str:
    """Champ ``limite`` de la réponse.

    Nomme la localité jumelle quand deux localités tombent dans la même cellule
    CERES SYN1deg et ont donc les mêmes P50 et P90.
    """
    base = (
        "Exceedance inter-annuelle uniquement (variabilité d'une année à l'autre sur "
        f"{NOMBRE_ANNEES_BASE} ans). Ne propage pas l'incertitude du modèle "
        "satellitaire NASA POWER : ce n'est pas un P90 bancable complet "
        "(qui nécessiterait un modèle d'erreur explicite, de type PRUVE, et "
        "idéalement un calage sur des mesures au sol)."
    )
    jumelle = PAIRES_COLOCALISEES_D29.get(code_localite)
    if jumelle is not None:
        base += (
            f" Cette localité et {jumelle!r} tombent dans la même cellule de la "
            f"grille CERES SYN1deg de NASA POWER (environ 110 km de côté) : leurs "
            f"séries GHI mensuelles 1991-2020 sont strictement identiques, "
            f"et leurs P50 et P90 aussi."
        )
    return base


@routeur.get(
    "/ghi_exceedance/{code_localite}",
    response_model=ReponseGhiExceedance,
    status_code=status.HTTP_200_OK,
    summary="Exceedance inter-annuelle P50 / P90 de l'irradiation annuelle (GHI)",
    tags=["grandeurs-F1"],
)
def grandeur_ghi_exceedance(
    code_localite: str,
    _cle: CleApiValidee,
    session: Annotated[Session, Depends(obtenir_session)],
) -> ReponseGhiExceedance:
    """P50 et P90 de l'irradiation annuelle (GHI) d'une localité, calculés à chaque appel.

    La route lit la série GHI mensuelle 1991-2020 NASA POWER de la localité, en
    tire les totaux annuels (kWh/m²/an, années bissextiles comprises), puis
    leurs percentiles : P50 est la médiane, P90 la valeur dépassée neuf années
    sur dix (10e percentile), donc inférieure à P50. 404
    ``RESSOURCE_LOCALITE_INCONNUE`` si aucune série de ce type n'est rattachée à
    la localité.

    Le champ ``limite`` rappelle que seule la variabilité d'une année à l'autre
    est prise en compte ; il signale aussi le cas de deux localités situées dans
    la même cellule de la source, dont les valeurs sont identiques.
    """
    niveaux = NiveauxEntrees()
    serie_id, code_serie = _resoudre_serie_ghi_mensuelle_1991_2020(session, code_localite)
    mensuelles = _lire_mensuelles_brutes(session, serie_id, niveaux=niveaux)
    totaux_par_annee = calculer_totaux_annuels(mensuelles)
    resultat = calculer_ghi_exceedance(list(totaux_par_annee.values()))
    return ReponseGhiExceedance(
        code_localite=code_localite,
        code_serie_source=code_serie,
        periode=f"{ANNEE_DEBUT_CLIMATOLOGIE}-{ANNEE_FIN_CLIMATOLOGIE}",
        base_annees=len(totaux_par_annee),
        p50=resultat.p50,
        p90=resultat.p90,
        unite=UNITE_GHI_EXCEEDANCE,
        methode_percentile=METHODE_PERCENTILE,
        niveau_confiance=propager_niveau_confiance(niveaux.tous(), plafond=PLAFOND_GHI_EXCEEDANCE),
        limite=_construire_limite_ghi_exceedance(code_localite),
    )


# Bornes larges : ces routes lisent toute la série, sans fenêtre demandée.
_FENETRE_LARGE_DEBUT: date = date(2000, 1, 1)
_FENETRE_LARGE_FIN: date = date(2100, 1, 1)


def _chercher_serie_pluie_nasa(
    session: Session,
    localite_id: int,
    periode_debut: date,
    periode_fin: date | None,
) -> int | None:
    """Série de précipitation journalière NASA POWER de la localité, ou ``None``.

    La pluie vient de ``nasa_power`` et les PM de ``cams_eac4`` :
    ``_chercher_serie_compagne``, qui filtre sur la source, ne la trouverait
    pas. Une localité peut porter plusieurs séries de pluie NASA sur des
    périodes successives : est retenue la première, par ``periode_debut`` puis
    ``id``, dont la plage recouvre celle de la série PM appelante.
    """
    row = session.execute(
        text(
            """
            SELECT sm.id FROM series_metadonnees sm
            JOIN sources s ON s.id = sm.source_id
            WHERE sm.localite_id = :localite_id
              AND s.code = 'nasa_power'
              AND sm.grandeur_code = 'precipitation'
              AND sm.granularite = 'journalier'
              AND sm.actif = TRUE
              AND (sm.periode_fin IS NULL OR sm.periode_fin >= :periode_debut)
              AND (CAST(:periode_fin AS DATE) IS NULL OR sm.periode_debut <= :periode_fin)
            ORDER BY sm.periode_debut, sm.id
            LIMIT 1
            """
        ),
        {
            "localite_id": localite_id,
            "periode_debut": periode_debut,
            "periode_fin": periode_fin,
        },
    ).first()
    return int(row.id) if row else None


def _verifier_contiguite_journaliere(dates: list[date], code_serie_source: str) -> None:
    """Lève 422 ``PLAGE_TEMPORELLE_NON_DISPONIBLE`` si ``dates`` (triées) comporte un trou.

    Le modèle HSU cumule la salissure jour après jour : un trou fausserait
    l'accumulation.
    """
    for i in range(1, len(dates)):
        if dates[i] != dates[i - 1] + timedelta(days=1):
            raise ExceptionKuma(
                code=CodeErreur.PLAGE_TEMPORELLE_NON_DISPONIBLE,
                message=(
                    f"Série source {code_serie_source!r} : il manque des jours "
                    f"entre {dates[i - 1]} et {dates[i]}. Le modèle HSU cumule la "
                    "salissure jour après jour et exige une série sans trou ; le "
                    "calcul de salissure ne peut pas aboutir sur cette fenêtre."
                ),
                statut_http=status.HTTP_422_UNPROCESSABLE_ENTITY,
            )


@routeur.get(
    "/taux_salissure_proxy/{code_serie_source}",
    response_model=ReponseTauxSalissureProxy,
    status_code=status.HTTP_200_OK,
    summary="Proxy de salissure (perte de transmission %, modele HSU)",
    tags=["grandeurs-F1"],
)
def grandeur_taux_salissure_proxy(
    code_serie_source: str,
    _cle: CleApiValidee,
    session: Annotated[Session, Depends(obtenir_session)],
) -> ReponseTauxSalissureProxy:
    """Perte de transmission par salissure des modules (% = (1 - ratio HSU) x 100).

    Calculée à chaque appel. ``code_serie_source`` désigne la série PM2.5 (EAC4)
    de la localité ; une série d'une autre grandeur donne 400
    ``INCOMPATIBILITE_SOURCE_GRANDEUR``. La route lit aussi la série PM10 de la
    même source et la série de précipitation journalière NASA POWER de la
    localité (400 si l'une manque). Le calcul porte sur les jours où les trois
    séries ont une valeur ; ces jours doivent se suivre sans trou (422
    ``PLAGE_TEMPORELLE_NON_DISPONIBLE`` sinon), le modèle HSU cumulant la
    salissure jour après jour.

    Le modèle part de modules propres au premier jour : les premiers jours de la
    fenêtre sont sous-estimés. L'inclinaison et le seuil de pluie nettoyante
    sont fixes ; la réponse les rappelle.
    """
    niveaux = NiveauxEntrees()
    serie = _resoudre_serie_source(session, code_serie_source)
    _exiger_grandeur(serie.grandeur_code, "pm2_5", code_serie_source, "taux_salissure_proxy")

    pm10_serie_id = _chercher_serie_compagne(
        session, serie.localite_id, serie.source_id, "pm10", serie.periode_debut, serie.granularite
    )
    pluie_serie_id = _chercher_serie_pluie_nasa(
        session, serie.localite_id, serie.periode_debut, serie.periode_fin
    )
    if pm10_serie_id is None or pluie_serie_id is None:
        raise ExceptionKuma(
            code=CodeErreur.INCOMPATIBILITE_SOURCE_GRANDEUR,
            message=(
                "Le proxy de salissure (HSU) exige la compagne PM10 (meme source EAC4) "
                "et la serie de precipitation journaliere (source nasa_power) pour la "
                f"localite de {code_serie_source!r} ; au moins une est absente."
            ),
            statut_http=status.HTTP_400_BAD_REQUEST,
        )

    pm2_5 = _lire_mesures_par_serie_id(
        session, serie.serie_id, _FENETRE_LARGE_DEBUT, _FENETRE_LARGE_FIN, niveaux=niveaux
    )
    pm10 = _lire_mesures_par_serie_id(
        session, pm10_serie_id, _FENETRE_LARGE_DEBUT, _FENETRE_LARGE_FIN, niveaux=niveaux
    )
    pluie = _lire_mesures_par_serie_id(
        session, pluie_serie_id, _FENETRE_LARGE_DEBUT, _FENETRE_LARGE_FIN, niveaux=niveaux
    )

    dates = sorted(pm2_5.keys() & pm10.keys() & pluie.keys())
    _verifier_contiguite_journaliere(dates, code_serie_source)

    entrees: list[MesureEntreeSoiling] = [
        {
            "instant_mesure": jour,
            "rainfall_mm": pluie[jour],
            "pm2_5": pm2_5[jour],
            "pm10": pm10[jour],
        }
        for jour in dates
    ]
    resultat = calculer_taux_salissure_proxy(entrees)
    # Modèle cumulatif : un jour dépend des jours précédents depuis le dernier
    # nettoyage, chaque jour prend le niveau des entrées des jours retenus (règle P).
    niveau = (
        propager_niveau_confiance(
            {n for jour in dates for n in niveaux.du_jour(jour)}, plafond=PLAFOND_SALISSURE
        )
        if dates
        else "B"
    )
    periode = f"{dates[0].isoformat()}/{dates[-1].isoformat()}" if dates else "aucune"

    return ReponseTauxSalissureProxy(
        code_serie_source=code_serie_source,
        code_localite=serie.localite_code,
        periode=periode,
        surface_tilt_deg=SURFACE_TILT_DEFAUT,
        cleaning_threshold_mm=CLEANING_THRESHOLD_DEFAUT_MM,
        mesures=[m.model_copy(update={"niveau_confiance": niveau}) for m in resultat.mesures],
        limite=resultat.limite,
    )


def _chercher_serie_pm_cams(session: Session, localite_id: int, grandeur_code: str) -> int | None:
    """Série journalière ``pm2_5`` ou ``pm10`` EAC4 de la localité, ou ``None``.

    Les PM viennent de ``cams_eac4``, pas de la source du GHI :
    ``_chercher_serie_compagne``, qui filtre sur la source, ne les trouverait pas.
    """
    row = session.execute(
        text(
            """
            SELECT sm.id FROM series_metadonnees sm
            JOIN sources s ON s.id = sm.source_id
            WHERE sm.localite_id = :localite_id
              AND s.code = 'cams_eac4'
              AND sm.grandeur_code = :grandeur_code
              AND sm.granularite = 'journalier'
              AND sm.actif = TRUE
            ORDER BY sm.periode_debut, sm.id
            LIMIT 1
            """
        ),
        {"localite_id": localite_id, "grandeur_code": grandeur_code},
    ).first()
    return int(row.id) if row else None


@routeur.get(
    "/pr_realiste/{code_serie_source}",
    response_model=ReponsePRRealiste,
    status_code=status.HTTP_200_OK,
    summary="PR realiste saisonnier (PR effectif site-specifique, journalier + mensuel)",
    tags=["grandeurs-F1"],
)
def grandeur_pr_realiste(
    code_serie_source: str,
    params: Annotated[ParametresPRRealiste, Depends(parametres_requete(ParametresPRRealiste))],
    _cle: CleApiValidee,
    session: Annotated[Session, Depends(obtenir_session)],
) -> ReponsePRRealiste:
    """PR effectif journalier et mensuel : ``PR_fourni x ratio_T x (1 - salissure)``.

    Calculé à chaque appel, selon ``correction``. ``code_serie_source`` désigne
    une série GHI (400 ``INCOMPATIBILITE_SOURCE_GRANDEUR`` sinon). Selon le
    mode, la route lit aussi la série T2M et la série de précipitation de la
    même source, et les séries PM2.5 et PM10 EAC4 de la localité (400 si une
    série nécessaire manque). Les modes thermiques exigent ``noct_degc`` et
    ``coeff_temp_pourcent_par_degc`` (422 ``VALIDATION_CHAMP_MANQUANT`` sinon).

    Le calcul porte sur les jours communs aux séries du mode, qui doivent se
    suivre sans trou (422 ``PLAGE_TEMPORELLE_NON_DISPONIBLE`` sinon). La fenêtre
    dépend donc du mode : avec salissure, elle s'arrête là où s'arrêtent les
    séries PM. La moyenne mensuelle donne la courbe saisonnière du PR.
    """
    niveaux = NiveauxEntrees()
    serie = _resoudre_serie_source(session, code_serie_source)
    _exiger_grandeur(serie.grandeur_code, "ghi", code_serie_source, "pr_realiste")
    besoin_thermique = params.correction in ("temperature", "temperature_salissure")
    besoin_salissure = params.correction in ("salissure", "temperature_salissure")

    if besoin_thermique and (
        params.noct_degc is None or params.coeff_temp_pourcent_par_degc is None
    ):
        raise ExceptionKuma(
            code=CodeErreur.VALIDATION_CHAMP_MANQUANT,
            message=(
                f"correction={params.correction!r} requiert noct_degc et "
                "coeff_temp_pourcent_par_degc."
            ),
            statut_http=status.HTTP_422_UNPROCESSABLE_CONTENT,
        )

    ghi = _lire_mesures_par_serie_id(
        session, serie.serie_id, _FENETRE_LARGE_DEBUT, _FENETRE_LARGE_FIN, niveaux=niveaux
    )
    ensembles_dates: list[set[date]] = [set(ghi.keys())]

    t2m: dict[date, float] = {}
    if besoin_thermique:
        t2m_id = _chercher_serie_compagne(
            session,
            serie.localite_id,
            serie.source_id,
            "t2m",
            serie.periode_debut,
            serie.granularite,
        )
        if t2m_id is None:
            raise ExceptionKuma(
                code=CodeErreur.INCOMPATIBILITE_SOURCE_GRANDEUR,
                message=(
                    "La correction temperature exige une serie T2M compagne pour la "
                    f"localite de {code_serie_source!r} ; absente."
                ),
                statut_http=status.HTTP_400_BAD_REQUEST,
            )
        t2m = _lire_mesures_par_serie_id(
            session, t2m_id, _FENETRE_LARGE_DEBUT, _FENETRE_LARGE_FIN, niveaux=niveaux
        )
        ensembles_dates.append(set(t2m.keys()))

    pluie: dict[date, float] = {}
    pm2_5: dict[date, float] = {}
    pm10: dict[date, float] = {}
    if besoin_salissure:
        pluie_id = _chercher_serie_compagne(
            session,
            serie.localite_id,
            serie.source_id,
            "precipitation",
            serie.periode_debut,
            serie.granularite,
        )
        pm2_5_id = _chercher_serie_pm_cams(session, serie.localite_id, "pm2_5")
        pm10_id = _chercher_serie_pm_cams(session, serie.localite_id, "pm10")
        if pluie_id is None or pm2_5_id is None or pm10_id is None:
            raise ExceptionKuma(
                code=CodeErreur.INCOMPATIBILITE_SOURCE_GRANDEUR,
                message=(
                    "La correction salissure exige les compagnes PM2.5/PM10 (EAC4) et "
                    f"precipitation (nasa_power) pour la localite de {code_serie_source!r} ; "
                    "au moins une est absente."
                ),
                statut_http=status.HTTP_400_BAD_REQUEST,
            )
        pluie = _lire_mesures_par_serie_id(
            session, pluie_id, _FENETRE_LARGE_DEBUT, _FENETRE_LARGE_FIN, niveaux=niveaux
        )
        pm2_5 = _lire_mesures_par_serie_id(
            session, pm2_5_id, _FENETRE_LARGE_DEBUT, _FENETRE_LARGE_FIN, niveaux=niveaux
        )
        pm10 = _lire_mesures_par_serie_id(
            session, pm10_id, _FENETRE_LARGE_DEBUT, _FENETRE_LARGE_FIN, niveaux=niveaux
        )
        ensembles_dates += [set(pluie.keys()), set(pm2_5.keys()), set(pm10.keys())]

    dates_communes = ensembles_dates[0]
    for autre in ensembles_dates[1:]:
        dates_communes = dates_communes & autre
    dates = sorted(dates_communes)
    _verifier_contiguite_journaliere(dates, code_serie_source)

    entrees: list[MesureJourPRRealiste] = [
        {
            "instant_mesure": jour,
            "ghi_kwh_par_m2_jour": ghi[jour] if besoin_thermique else None,
            "t_amb_degc": t2m.get(jour) if besoin_thermique else None,
            "rainfall_mm": pluie.get(jour) if besoin_salissure else None,
            "pm2_5": pm2_5.get(jour) if besoin_salissure else None,
            "pm10": pm10.get(jour) if besoin_salissure else None,
        }
        for jour in dates
    ]
    resultat = calculer_pr_realiste(
        entrees,
        pr_fourni=params.pr_fourni,
        correction=params.correction,
        noct_degc=params.noct_degc,
        gamma_pmax_pct=params.coeff_temp_pourcent_par_degc,
    )
    # Règle P : sans salissure, chaque jour ne dépend que de ses entrées ; la
    # salissure est cumulative, chaque jour prend alors le niveau des entrées
    # des jours retenus. Le mois prend celui de ses jours.
    niveaux_fenetre = {n for jour in dates for n in niveaux.du_jour(jour)}
    mesures_jour = [
        m.model_copy(
            update={
                "niveau_confiance": propager_niveau_confiance(
                    niveaux_fenetre if besoin_salissure else niveaux.du_jour(m.instant),
                    plafond=PLAFOND_PR_REALISTE,
                )
            }
        )
        for m in resultat.mesures
    ]
    periode = f"{dates[0].isoformat()}/{dates[-1].isoformat()}" if dates else "aucune"

    return ReponsePRRealiste(
        code_serie_source=code_serie_source,
        code_localite=serie.localite_code,
        periode=periode,
        correction=params.correction,
        pr_fourni=params.pr_fourni,
        mesures_journalier=mesures_jour,
        mesures_mensuel=agreger_pr_mensuel(mesures_jour),
        limite=resultat.limite,
    )


_AN_DEBUT_ATLAS = 2021
_AN_FIN_ATLAS = 2023
_FENETRE_ATLAS_STR = "2021-2023"
_GRILLE_CERES = "CERES SYN1deg (1 deg / 110 km)"
# (grandeur exposée, grandeur_code de l'écart enregistré, libellé de la paire).
_PAIRES_ECART_ATLAS: tuple[tuple[Literal["ghi", "dni"], str, str], ...] = (
    ("ghi", "ecart_relatif_referentiel", "NASA POWER vs PVGIS-SARAH3"),
    ("dni", "ecart_relatif_dni_cams", "NASA POWER vs CAMS"),
)


def _mediane_abs(valeurs: Sequence[float]) -> float:
    """Médiane des valeurs absolues ; ``valeurs`` ne doit pas être vide."""
    absolues = sorted(abs(v) for v in valeurs)
    n = len(absolues)
    milieu = n // 2
    if n % 2 == 1:
        return absolues[milieu]
    return (absolues[milieu - 1] + absolues[milieu]) / 2.0


def _lire_ecart_paire_recent(
    session: Session, code_localite: str, grandeur_ecart: str
) -> tuple[list[float], list[tuple[str, str | None]]]:
    """Écarts mensuels 2021-2023 d'une localité pour une grandeur d'écart.

    Le filtre sur ``annee_debut`` écarte les écarts calculés sur d'autres fenêtres
    (climatologie DNI 2004-2020). Renvoie ``(valeurs_signees, niveaux)`` sur les
    mois renseignés, ou ``([], [])`` si la localité n'en a pas.
    """
    rows = session.execute(
        text(
            """
            SELECT gm.valeur, gm.niveau_confiance_derive AS derive,
                   gm.niveau_confiance_override AS override
            FROM grandeurs_metier gm
            JOIN localites l ON l.id = gm.localite_id
            WHERE l.code = :loc AND gm.grandeur_code = :g
              AND gm.annee_debut BETWEEN :a1 AND :a2
              AND gm.valide_au IS NULL
            ORDER BY gm.annee_debut, gm.mois
            """
        ),
        {"loc": code_localite, "g": grandeur_ecart, "a1": _AN_DEBUT_ATLAS, "a2": _AN_FIN_ATLAS},
    ).all()
    valeurs = [float(r.valeur) for r in rows if r.valeur is not None]
    niveaux = [(str(r.derive), r.override) for r in rows if r.valeur is not None]
    return valeurs, niveaux


def _lire_degenerescence_localite(
    session: Session, code_localite: str
) -> tuple[DegenerescenceFiche | None, list[tuple[str, str | None]]]:
    """Dégénérescence de pixel de la localité sur la grille CERES de NASA POWER.

    GHI et DNI partagent cette grille : la ligne de la série ``ghi`` de
    ``nasa_power`` vaut pour les deux. Renvoie ``(fiche, niveaux)`` ou
    ``(None, [])``.
    """
    row = session.execute(
        text(
            """
            SELECT gm.valeur, gm.commentaire_editorial AS note,
                   gm.niveau_confiance_derive AS derive,
                   gm.niveau_confiance_override AS override
            FROM grandeurs_metier gm
            JOIN localites l ON l.id = gm.localite_id
            JOIN series_metadonnees sm ON sm.id = gm.series_metadonnees_id
            JOIN sources s ON s.id = sm.source_id
            WHERE l.code = :loc AND gm.grandeur_code = 'degenerescence_pixel'
              AND s.code = 'nasa_power' AND sm.grandeur_code = 'ghi'
              AND gm.valide_au IS NULL
            """
        ),
        {"loc": code_localite},
    ).first()
    if row is None or row.valeur is None:
        return None, []
    fiche = DegenerescenceFiche(
        n_jumeaux=int(row.valeur), grille=_GRILLE_CERES, note=str(row.note or "")
    )
    return fiche, [(str(row.derive), row.override)]


def _assurer_confiance_b(
    niveaux: Sequence[tuple[str, str | None]], code_localite: str
) -> Literal["B"]:
    """Renvoie ``'B'`` si toutes les lignes lues sont en confiance effective B, sinon lève 500.

    La fiche n'affiche ainsi jamais un niveau que ses données ne portent pas.
    """
    effectifs = {(override if override is not None else derive) for derive, override in niveaux}
    if effectifs != {"B"}:
        raise ExceptionKuma(
            code=CodeErreur.SERVEUR_ERREUR_INTERNE,
            message=(
                f"Incohérence de confiance pour {code_localite!r} : la fiche inter-source "
                f"attend des données en confiance B, trouvé {sorted(effectifs)}. "
                "L'atlas compare des sources entre elles (confiance B) ; A est réservée "
                "aux données validées par des mesures au sol."
            ),
            statut_http=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )
    return "B"


def _construire_limite_incertitude_inter_source() -> str:
    """Champ ``limite`` des fiches d'incertitude inter-source."""
    return (
        "Incertitude inter-source, donc relative : divergence entre NASA POWER et les "
        "références satellite (SARAH-3 pour le GHI, CAMS pour le DNI), fenêtre 2021-2023, "
        "confiance B. Ne quantifie pas l'incertitude absolue par rapport à des mesures au "
        "sol : ce n'est pas une barre d'erreur calée au sol."
    )


@routeur.get(
    "/incertitude_inter_source/{code_localite}",
    response_model=ReponseIncertitudeInterSource,
    status_code=status.HTTP_200_OK,
    summary="Fiche d'incertitude inter-source (ecart + degenerescence de pixel)",
    tags=["grandeurs-F1"],
)
def grandeur_incertitude_inter_source(
    code_localite: str,
    _cle: CleApiValidee,
    session: Annotated[Session, Depends(obtenir_session)],
) -> ReponseIncertitudeInterSource:
    """Fiche d'incertitude inter-source d'une localité.

    Assemblée à partir de grandeurs déjà calculées, elle porte deux informations
    distinctes :

    - ``ecarts`` : écart entre NASA POWER et une source de référence, par
      grandeur (GHI : SARAH-3 ; DNI : CAMS), sur 2021-2023. ``ecart_abs_pct``
      (médiane des écarts mensuels absolus) est l'indicateur à retenir ;
      ``ecart_signe_pct`` n'indique qu'un sens.
    - ``degenerescence`` : nombre d'autres localités qui partagent la cellule
      de la grille CERES de NASA POWER.

    Confiance B : la fiche compare des sources entre elles, pas à des mesures au
    sol. 404 ``RESSOURCE_LOCALITE_INCONNUE`` si aucun écart inter-source n'est
    enregistré pour la localité sur la période.
    """
    ecarts: list[EcartPaireInterSource] = []
    niveaux: list[tuple[str, str | None]] = []
    for grandeur, grandeur_ecart, paire in _PAIRES_ECART_ATLAS:
        valeurs, niv = _lire_ecart_paire_recent(session, code_localite, grandeur_ecart)
        if not valeurs:
            continue
        ecarts.append(
            EcartPaireInterSource(
                grandeur=grandeur,
                paire=paire,
                ecart_abs_pct=round(_mediane_abs(valeurs), 4),
                ecart_signe_pct=round(sum(valeurs) / len(valeurs), 4),
                n_mois=len(valeurs),
            )
        )
        niveaux += niv

    if not ecarts:
        raise ExceptionKuma(
            code=CodeErreur.RESSOURCE_LOCALITE_INCONNUE,
            message=(
                f"Localité {code_localite!r} non couverte par l'atlas d'incertitude "
                "inter-source : aucun écart entre sources n'est enregistré pour elle "
                "sur 2021-2023."
            ),
            statut_http=status.HTTP_404_NOT_FOUND,
        )

    degenerescence, niv_degen = _lire_degenerescence_localite(session, code_localite)
    if degenerescence is None:
        raise ExceptionKuma(
            code=CodeErreur.SERVEUR_ERREUR_INTERNE,
            message=(
                f"Incoherence : ecart inter-source present pour {code_localite!r} mais "
                "degenerescence_pixel (NASA/ghi) absente."
            ),
            statut_http=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )
    niveaux += niv_degen

    return ReponseIncertitudeInterSource(
        code_localite=code_localite,
        fenetre=_FENETRE_ATLAS_STR,
        ecarts=ecarts,
        degenerescence=degenerescence,
        niveau_confiance=_assurer_confiance_b(niveaux, code_localite),
        limite=_construire_limite_incertitude_inter_source(),
    )


def _lister_points_atlas(session: Session) -> list[tuple[int, str]]:
    """``(localite_id, code)`` des localités qui ont un écart inter-source depuis 2021.

    Triées par code. La liste suit la donnée, pas une énumération fixe.
    """
    rows = session.execute(
        text(
            """
            SELECT DISTINCT l.id, l.code
            FROM grandeurs_metier gm
            JOIN localites l ON l.id = gm.localite_id
            WHERE gm.grandeur_code IN ('ecart_relatif_referentiel', 'ecart_relatif_dni_cams')
              AND gm.annee_debut >= :a1 AND gm.valide_au IS NULL
            ORDER BY l.code
            """
        ),
        {"a1": _AN_DEBUT_ATLAS},
    ).all()
    return [(int(r.id), str(r.code)) for r in rows]


def _assembler_fiche_point(
    session: Session, localite_id: int, code_localite: str
) -> FichePointIncertitude:
    """Fiche d'un point pour la collection : celle de la route par localité, plus les coordonnées.

    Lève 500 si le point n'a pas d'écart ou pas de dégénérescence.
    """
    ecarts: list[EcartPaireInterSource] = []
    niveaux: list[tuple[str, str | None]] = []
    for grandeur, grandeur_ecart, paire in _PAIRES_ECART_ATLAS:
        valeurs, niv = _lire_ecart_paire_recent(session, code_localite, grandeur_ecart)
        if not valeurs:
            continue
        ecarts.append(
            EcartPaireInterSource(
                grandeur=grandeur,
                paire=paire,
                ecart_abs_pct=round(_mediane_abs(valeurs), 4),
                ecart_signe_pct=round(sum(valeurs) / len(valeurs), 4),
                n_mois=len(valeurs),
            )
        )
        niveaux += niv

    degenerescence, niv_degen = _lire_degenerescence_localite(session, code_localite)
    if not ecarts or degenerescence is None:
        raise ExceptionKuma(
            code=CodeErreur.SERVEUR_ERREUR_INTERNE,
            message=(
                f"Incohérence dans la collection de l'atlas : le point {code_localite!r} "
                "n'a pas d'écart ou pas de dégénérescence enregistrés."
            ),
            statut_http=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )
    niveaux += niv_degen
    latitude, longitude = _resoudre_coordonnees(session, localite_id)
    return FichePointIncertitude(
        code_localite=code_localite,
        fenetre=_FENETRE_ATLAS_STR,
        ecarts=ecarts,
        degenerescence=degenerescence,
        niveau_confiance=_assurer_confiance_b(niveaux, code_localite),
        limite=_construire_limite_incertitude_inter_source(),
        latitude_deg=latitude,
        longitude_deg=longitude,
    )


@routeur.get(
    "/incertitude_inter_source",
    response_model=ReponseIncertitudeInterSourceCollection,
    status_code=status.HTTP_200_OK,
    summary="Collection des fiches d'incertitude inter-source (points de l'atlas)",
    tags=["grandeurs-F1"],
)
def grandeur_incertitude_inter_source_collection(
    _cle: CleApiValidee,
    session: Annotated[Session, Depends(obtenir_session)],
    limit: Annotated[int, Query(ge=1, le=1000)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> ReponseIncertitudeInterSourceCollection:
    """Fiches d'incertitude inter-source de tous les points de l'atlas, paginées.

    Chaque élément est la fiche de
    ``/v1/grandeurs/incertitude_inter_source/{code_localite}``, complétée de la
    latitude et de la longitude du point : un seul appel suffit pour dessiner
    une carte. Les points sont les localités qui ont un écart inter-source
    depuis 2021, triées par code. Même enveloppe paginée que ``/v1/series``
    (``items``, ``total``, ``limit``, ``offset``).
    """
    points = _lister_points_atlas(session)
    total = len(points)
    page = points[offset : offset + limit]
    items = [_assembler_fiche_point(session, loc_id, code) for loc_id, code in page]
    return ReponseIncertitudeInterSourceCollection(
        items=items, total=total, limit=limit, offset=offset
    )
