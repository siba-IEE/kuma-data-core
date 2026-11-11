"""Routes ``/v1/horaire/{localite}/{grandeur}`` : données horaires.

- ``GET /v1/horaire/{localite}/{grandeur}`` : valeurs horaires sur une fenêtre.
- ``GET /v1/horaire/{localite}/{grandeur}/disponibilite`` : plage disponible.

La route de données sert les mesures horaires stockées et validées quand une
série couvre la fenêtre. Sinon elle relaie la demande au service amont
(passe-plat, valeurs non validées), sauf en profil édition figée, où le
serveur ne fait aucun appel sortant (ADR-0003).

Les codes d'erreur, les messages et les exemples servis ne nomment pas la
source amont.

La fin de la plage disponible est calculée sans appel externe : la date du
jour, moins 5 mois (latence observée de la source amont), moins 1 jour.
"""

from __future__ import annotations

import csv
import io
from datetime import UTC, date, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, status
from fastapi.responses import JSONResponse, Response
from sqlalchemy import text
from sqlalchemy.orm import Session

from kuma_data_core.api.codes_erreur import CodeErreur
from kuma_data_core.api.dependencies import CleApiValidee, parametres_requete
from kuma_data_core.api.erreurs import ExceptionKuma
from kuma_data_core.api.v1.schemas.horaire import (
    DATE_DEBUT_DISPONIBILITE,
    ParametresHoraire,
    PlageTemporelle,
    ReponseDisponibilite,
    ReponseHoraire,
    ResultatHoraire,
)
from kuma_data_core.core.config import get_settings
from kuma_data_core.db.session import obtenir_session
from kuma_data_core.exceptions import (
    NasaPowerHttpError,
    NasaPowerPayloadError,
    NasaPowerRateLimitError,
    NasaPowerTimeoutError,
)
from kuma_data_core.external.nasa_power import fetch_hourly
from kuma_data_core.services.horaire import (
    code_parametre_amont,
    convertir_valeurs_amont_en_resultats,
    filtrer_resultats_par_plage,
    unite_cible,
)
from kuma_data_core.services.localites import coordonnees_localite

routeur = APIRouter(prefix="/horaire", tags=["horaire-passe-plat"])


_PREFIXE_ALIAS_HISTORIQUE: str = "gin_"
"""Préfixe ajouté à un code court (``kankan``, ``kindia``...) pour retrouver le
code complet de la table ``localites``. Compatibilité seulement : l'usage
normal est le code complet."""


def _resoudre_localite(session: Session, localite: str) -> str:
    """Code complet de la localité du chemin.

    Le code est pris tel quel s'il existe, sinon préfixé de ``gin_``. Lève 404
    ``RESSOURCE_LOCALITE_INCONNUE`` si aucun des deux n'existe.
    """
    for candidat in (localite, f"{_PREFIXE_ALIAS_HISTORIQUE}{localite}"):
        existe = session.execute(
            text("SELECT 1 FROM localites WHERE code = :code AND actif = TRUE"),
            {"code": candidat},
        ).first()
        if existe is not None:
            return candidat
    raise ExceptionKuma(
        code=CodeErreur.RESSOURCE_LOCALITE_INCONNUE,
        message=f"Localite '{localite}' introuvable dans le referentiel.",
        statut_http=status.HTTP_404_NOT_FOUND,
    )


_LATENCE_NRT_MOIS: int = 5
"""Latence observée de la source amont, en mois."""


def _calculer_plage_disponible(aujourdhui: date | None = None) -> PlageTemporelle:
    """Plage disponible : du 2001-01-01 à la date du jour moins 5 mois moins 1 jour."""
    reference = aujourdhui if aujourdhui is not None else date.today()
    # « 5 mois » compté comme 5 x 30 jours.
    fin = reference - timedelta(days=_LATENCE_NRT_MOIS * 30 + 1)
    return PlageTemporelle(debut=DATE_DEBUT_DISPONIBILITE, fin=fin)


def _serialiser_csv(resultats: list[ResultatHoraire]) -> str:
    """Sérialise une liste de ResultatHoraire en CSV."""
    buffer = io.StringIO()
    w = csv.writer(buffer)
    w.writerow(["instant", "valeur", "unite", "statut_editorial"])
    for r in resultats:
        valeur_str = "" if r.valeur is None else str(r.valeur)
        w.writerow([r.instant.isoformat(), valeur_str, r.unite, r.statut_editorial])
    return buffer.getvalue()


def _gerer_erreur_amont(exc: Exception) -> None:
    """Convertit une erreur du client externe en 503 ``PASSE_PLAT_INDISPONIBLE``.

    Le message ne nomme pas la source amont. Toute autre exception est relevée
    telle quelle.
    """
    if isinstance(
        exc,
        NasaPowerTimeoutError
        | NasaPowerRateLimitError
        | NasaPowerHttpError
        | NasaPowerPayloadError,
    ):
        raise ExceptionKuma(
            code=CodeErreur.PASSE_PLAT_INDISPONIBLE,
            message="Le service passe-plat horaire est temporairement indisponible.",
            statut_http=status.HTTP_503_SERVICE_UNAVAILABLE,
        ) from exc
    raise exc


def _chercher_serie_horaire_stockee(
    session: Session, localite_code_complet: str, grandeur: str
) -> tuple[int, date, date] | None:
    """``(serie_id, periode_debut, periode_fin)`` de la série horaire stockée, ou ``None``.

    Seules comptent les séries actives qui portent des mesures : une série sans
    aucune ligne dans ``mesures_ressource_horaires`` couvrirait la fenêtre
    demandée et ferait répondre 200 sans résultat. ``ORDER BY sm.id`` rend le
    choix déterministe si plusieurs séries conviennent. La jointure sur
    ``localites.code`` évite de dépendre du nom de la série.
    """
    row = session.execute(
        text(
            """
            SELECT sm.id, sm.periode_debut, sm.periode_fin
            FROM series_metadonnees sm
            JOIN localites l ON l.id = sm.localite_id
            WHERE l.code = :localite
              AND sm.grandeur_code = :grandeur
              AND sm.granularite = 'horaire'
              AND sm.actif = TRUE
              AND EXISTS (
                  SELECT 1 FROM mesures_ressource_horaires m
                  WHERE m.serie_id = sm.id
              )
            ORDER BY sm.id
            LIMIT 1
            """
        ),
        {"localite": localite_code_complet, "grandeur": grandeur},
    ).first()
    if row is None or row.periode_fin is None:
        return None
    return int(row.id), row.periode_debut, row.periode_fin


def _lire_horaire_validee(
    session: Session,
    serie_id: int,
    grandeur: str,
    periode_debut: date,
    periode_fin: date,
) -> list[ResultatHoraire]:
    """Points horaires validés d'une série sur la plage.

    Les lignes rejetées par le contrôle qualité (statut ``brut``) sont exclues.
    Instant rendu en UTC sans fuseau, comme le passe-plat.
    """
    rows = session.execute(
        text(
            """
            SELECT instant_mesure, valeur
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
    unite = unite_cible(grandeur)
    return [
        ResultatHoraire(
            instant=r.instant_mesure.astimezone(UTC).replace(tzinfo=None),
            valeur=float(r.valeur),
            unite=unite,
            statut_editorial="valide_auto",
        )
        for r in rows
    ]


def _repondre_horaire(params: ParametresHoraire, resultats: list[ResultatHoraire]) -> Response:
    """Sérialise une liste de ResultatHoraire en JSON (défaut) ou CSV."""
    if params.format_sortie == "csv":
        return Response(content=_serialiser_csv(resultats), media_type="text/csv")
    reponse = ReponseHoraire(
        localite=params.localite,
        grandeur=params.grandeur,
        periode_demandee=PlageTemporelle(debut=params.periode_debut, fin=params.periode_fin),
        resultats=resultats,
    )
    return JSONResponse(content=reponse.model_dump(mode="json"))


@routeur.get(
    "/{localite}/{grandeur}",
    response_model=None,
    status_code=status.HTTP_200_OK,
    summary="Donnees horaires passe-plat sur une fenetre temporelle",
)
def grandeur_horaire(
    params: Annotated[ParametresHoraire, Depends(parametres_requete(ParametresHoraire))],
    _cle: CleApiValidee,
    session: Annotated[Session, Depends(obtenir_session)],
) -> Response:
    """Valeurs horaires d'une grandeur pour une localité, sur une plage de dates.

    Quand une série horaire stockée couvre toute la plage, la route sert ses
    valeurs validées (``statut_editorial`` ``valide_auto``). Sinon elle relaie
    la demande au service amont et rend les valeurs sans validation
    (``passe_plat_non_valide``), une valeur manquante valant ``null``. Sur une
    édition publiée figée, ce relais n'existe pas.

    La plage demandée doit être incluse dans la plage disponible, donnée par la
    route ``/disponibilite``.

    Erreurs :

    - 401 ``AUTH_HEADER_MANQUANT`` / ``AUTH_CLE_INVALIDE`` ;
    - 422 ``VALIDATION_VALEUR_INVALIDE`` (paramètre invalide) ;
    - 400 ``PLAGE_TEMPORELLE_NON_DISPONIBLE`` (plage hors disponibilité ou,
      sur une édition figée, non couverte par les données stockées) ;
    - 404 ``RESSOURCE_LOCALITE_INCONNUE`` (localité absente du référentiel) ;
    - 503 ``PASSE_PLAT_INDISPONIBLE`` (service amont indisponible).
    """
    plage_disponible = _calculer_plage_disponible()
    if params.periode_debut < plage_disponible.debut or params.periode_fin > plage_disponible.fin:
        raise ExceptionKuma(
            code=CodeErreur.PLAGE_TEMPORELLE_NON_DISPONIBLE,
            message="La plage demandee n'est pas disponible.",
            statut_http=status.HTTP_400_BAD_REQUEST,
            details={
                "plage_demandee": f"{params.periode_debut} / {params.periode_fin}",
                "plage_disponible": f"{plage_disponible.debut} / {plage_disponible.fin}",
            },
        )

    localite_complet = _resoudre_localite(session, params.localite)

    # Si une série horaire stockée couvre la plage, servir ses valeurs
    # validées plutôt que relayer la source amont.
    serie_stockee = _chercher_serie_horaire_stockee(session, localite_complet, params.grandeur)
    if serie_stockee is not None:
        serie_id, periode_debut_serie, periode_fin_serie = serie_stockee
        if periode_debut_serie <= params.periode_debut and params.periode_fin <= periode_fin_serie:
            resultats_stockes = _lire_horaire_validee(
                session, serie_id, params.grandeur, params.periode_debut, params.periode_fin
            )
            return _repondre_horaire(params, resultats_stockes)

    # Édition figée (ADR-0003) : aucun appel sortant depuis le serveur
    # public ; une plage non couverte par les données stockées est indisponible.
    if get_settings().edition_figee:
        raise ExceptionKuma(
            code=CodeErreur.PLAGE_TEMPORELLE_NON_DISPONIBLE,
            message=(
                "La plage demandee n'est pas couverte par les donnees stockees de cette edition."
            ),
            statut_http=status.HTTP_400_BAD_REQUEST,
            details={
                "plage_demandee": f"{params.periode_debut} / {params.periode_fin}",
                "raison": "edition_figee_sans_relais_temps_reel",
            },
        )

    # Repli passe-plat (relais NASA POWER, non validé éditorialement).
    latitude, longitude = coordonnees_localite(localite_complet)
    code_amont = code_parametre_amont(params.grandeur)

    try:
        reponse_amont = fetch_hourly(
            latitude=latitude,
            longitude=longitude,
            parameters=[code_amont],
            start=params.periode_debut,
            end=params.periode_fin,
        )
    except Exception as exc:
        _gerer_erreur_amont(exc)
        raise  # unreachable, _gerer_erreur_amont raise toujours

    valeurs_par_cle = reponse_amont.properties.parameter.get(code_amont, {})
    resultats_bruts = convertir_valeurs_amont_en_resultats(
        valeurs_par_cle=valeurs_par_cle,
        grandeur=params.grandeur,
    )
    resultats = filtrer_resultats_par_plage(
        resultats=resultats_bruts,
        periode_debut=params.periode_debut,
        periode_fin=params.periode_fin,
    )
    return _repondre_horaire(params, resultats)


@routeur.get(
    "/{localite}/{grandeur}/disponibilite",
    response_model=ReponseDisponibilite,
    status_code=status.HTTP_200_OK,
    summary="Plage temporelle disponible pour le passe-plat horaire",
)
def disponibilite_horaire(
    localite: str,
    grandeur: str,
    _cle: CleApiValidee,
) -> ReponseDisponibilite:
    """Plage de dates disponible pour les données horaires.

    Le début est fixé au 2001-01-01. La fin vaut la date du jour moins 5 mois
    moins 1 jour, délai de mise à disposition de la source amont. La plage est
    la même pour tous les couples : la route ne vérifie ni la localité ni la
    grandeur.
    """
    plage = _calculer_plage_disponible()
    return ReponseDisponibilite(
        localite=localite,
        grandeur=grandeur,
        plage_disponible=plage,
    )
