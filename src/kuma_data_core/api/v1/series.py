"""Routes ``/v1/series`` : liste et détail.

- ``GET /v1/series`` : liste paginée des séries (filtres localité, grandeur,
  source, actif ; 100 par page, 1000 au plus).
- ``GET /v1/series/{code_serie}`` : détail d'une série et ses mesures (1000 par
  page, 10 000 au plus ; bornes ``from`` et ``to`` ; JSON ou CSV).

Les mesures viennent de ``mesures_ressource`` (journalier),
``mesures_ressource_mensuelles`` (mensuel) ou, pour une grandeur calculée, de
la vue ``v_grandeurs_metier_courantes``, qui ne rend que les valeurs courantes
et non dépréciées. Les séries horaires se lisent par ``/v1/horaire``.
"""

from __future__ import annotations

import csv
import io
from datetime import date, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Query, status
from fastapi.responses import JSONResponse, Response
from sqlalchemy.orm import Session

from kuma_data_core.api.codes_erreur import CodeErreur
from kuma_data_core.api.dependencies import CleApiValidee
from kuma_data_core.api.erreurs import ExceptionKuma
from kuma_data_core.api.v1.schemas.series import (
    GrandeurMetierValeur,
    MesureJournaliere,
    MesureLue,
    MesureMensuelle,
    SerieDetail,
    SerieListee,
    SerieListeePaginee,
)
from kuma_data_core.db.session import obtenir_session
from kuma_data_core.lecture.mesures import (
    lire_page_grandeurs_metier,
    lire_page_journaliere,
    lire_page_mensuelle,
)
from kuma_data_core.lecture.series import lire_page_series, lire_serie
from kuma_data_core.lecture.tables import (
    TableMesures,
    resolve_table_from_series_metadata,
)

routeur = APIRouter(prefix="/series", tags=["series"])


_LIMIT_DEFAUT_LISTING: int = 100
_LIMIT_MAX_LISTING: int = 1000
_LIMIT_DEFAUT_DETAIL: int = 1000
_LIMIT_MAX_DETAIL: int = 10_000

_FORMATS_SUPPORTES: tuple[str, ...] = ("json", "csv")


def _parser_borne_temporelle(valeur: str | None, nom_param: str) -> date | None:
    """Lit ``YYYY-MM-DD`` ou ``YYYY-MM`` (alors le 1er du mois) ; ``None`` reste ``None``.

    Lève 400 ``VALIDATION_FORMAT_DATE_INVALIDE`` si le format n'est pas reconnu.
    """
    if valeur is None:
        return None
    for fmt in ("%Y-%m-%d", "%Y-%m"):
        try:
            return datetime.strptime(valeur, fmt).date()
        except ValueError:
            continue
    raise ExceptionKuma(
        code=CodeErreur.VALIDATION_FORMAT_DATE_INVALIDE,
        message=(
            f"Parametre {nom_param!r} : format attendu YYYY-MM-DD ou YYYY-MM, recu {valeur!r}."
        ),
        statut_http=status.HTTP_400_BAD_REQUEST,
    )


def _valider_format(format_demande: str) -> str:
    """Lève 400 ``VALIDATION_FORMAT_NON_SUPPORTE`` si le format n'est ni json ni csv."""
    if format_demande not in _FORMATS_SUPPORTES:
        raise ExceptionKuma(
            code=CodeErreur.VALIDATION_FORMAT_NON_SUPPORTE,
            message=(
                f"Parametre format={format_demande!r} non supporte. "
                f"Valeurs autorisees : {list(_FORMATS_SUPPORTES)}."
            ),
            statut_http=status.HTTP_400_BAD_REQUEST,
        )
    return format_demande


@routeur.get(
    "",
    response_model=SerieListeePaginee,
    status_code=status.HTTP_200_OK,
    summary="Listing des series disponibles",
    description=(
        "Retourne la liste paginée des séries du catalogue, triée par code, "
        "dans une enveloppe `{items, total, limit, offset}`. Filtrage "
        "optionnel par localité, grandeur, source ou statut actif ; par "
        "défaut, seules les séries actives sont listées."
    ),
)
def lister_series(
    _cle: CleApiValidee,
    session: Annotated[Session, Depends(obtenir_session)],
    localite: Annotated[str | None, Query(description="Code localite (ex. gin_kindia)")] = None,
    grandeur: Annotated[str | None, Query(description="Code grandeur (ex. ghi, hep)")] = None,
    source: Annotated[
        str | None, Query(description="Code source (ex. nasa_power, kuma_calculs)")
    ] = None,
    actif: Annotated[
        bool | None, Query(description="Filtre actif (TRUE/FALSE), defaut TRUE")
    ] = True,
    limit: Annotated[int, Query(ge=1, le=_LIMIT_MAX_LISTING)] = _LIMIT_DEFAUT_LISTING,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> SerieListeePaginee:
    """Liste paginée des séries, triée par code ; ``actif`` vaut TRUE par défaut."""
    total, series = lire_page_series(
        session,
        localite=localite,
        grandeur=grandeur,
        source=source,
        actif=actif,
        limit=limit,
        offset=offset,
    )
    items = [
        SerieListee(
            id=serie.id,
            code=serie.code,
            libelle=serie.libelle,
            localite_id=serie.localite_id,
            localite_code=serie.localite_code,
            localite_nom=serie.localite_nom,
            localite_iso3=serie.localite_iso3,
            grandeur_code=serie.grandeur_code,
            grandeur_label=serie.grandeur_label,
            grandeur_unit=serie.grandeur_unit,
            source_id=serie.source_id,
            source_code=serie.source_code,
            source_label=serie.source_label,
            source_url=serie.source_url,
            periode_debut=serie.periode_debut,
            periode_fin=serie.periode_fin,
            methode_collecte=serie.methode_collecte,
            notes_fr=serie.notes_fr,
            created_at=serie.created_at,
            updated_at=serie.updated_at,
            actif=serie.actif,
        )
        for serie in series
    ]
    return SerieListeePaginee(items=items, total=total, limit=limit, offset=offset)


def _lire_mesures_journalier(
    session: Session,
    serie_id: int,
    bornes: tuple[date | None, date | None],
    limit: int,
    offset: int,
) -> list[MesureLue]:
    """Mesures journalières courantes de la série (``mesures_ressource``)."""
    return [
        MesureJournaliere(
            instant_mesure=ligne.instant_mesure,
            valeur=ligne.valeur,
            niveau_confiance_derive=ligne.niveau_confiance_derive,
            niveau_confiance_override=ligne.niveau_confiance_override,
            niveau_effectif=ligne.niveau_effectif,
            statut=ligne.statut,
        )
        for ligne in lire_page_journaliere(session, serie_id, bornes, limit, offset)
    ]


def _lire_mesures_mensuel(
    session: Session,
    serie_id: int,
    bornes: tuple[date | None, date | None],
    limit: int,
    offset: int,
) -> list[MesureLue]:
    """Mesures mensuelles courantes de la série (``mesures_ressource_mensuelles``)."""
    return [
        MesureMensuelle(
            annee=ligne.annee,
            mois=ligne.mois,
            valeur=ligne.valeur,
            niveau_confiance_derive=ligne.niveau_confiance_derive,
            niveau_confiance_override=ligne.niveau_confiance_override,
            niveau_effectif=ligne.niveau_effectif,
            statut=ligne.statut,
        )
        for ligne in lire_page_mensuelle(session, serie_id, bornes, limit, offset)
    ]


def _lire_mesures_grandeurs_metier(
    session: Session,
    serie_id: int,
    bornes: tuple[date | None, date | None],
    limit: int,
    offset: int,
) -> list[MesureLue]:
    """Valeurs de grandeur calculée de la série, par la vue ``v_grandeurs_metier_courantes``.

    La vue ne rend que les lignes courantes, de la version de formule actuelle
    et non dépréciées, avec leur ``niveau_effectif``.
    """
    return [
        GrandeurMetierValeur(
            periode_type=ligne.periode_type,
            annee_debut=ligne.annee_debut,
            annee_fin=ligne.annee_fin,
            mois=ligne.mois,
            version_formule=ligne.version_formule,
            valeur=ligne.valeur,
            niveau_confiance_derive=ligne.niveau_confiance_derive,
            niveau_confiance_override=ligne.niveau_confiance_override,
            niveau_effectif=ligne.niveau_effectif,
            statut=ligne.statut,
        )
        for ligne in lire_page_grandeurs_metier(session, serie_id, bornes, limit, offset)
    ]


def _serialiser_csv(serie_detail: SerieDetail) -> str:
    """Sérialise le détail d'une série en CSV."""
    buffer = io.StringIO()
    w = csv.writer(buffer)
    # Un seul en-tête pour les trois catégories de mesures.
    w.writerow(
        [
            "code_serie",
            "type",
            "annee",
            "mois",
            "instant_mesure",
            "periode_type",
            "annee_debut",
            "annee_fin",
            "version_formule",
            "valeur",
            "niveau_effectif",
            "statut",
        ]
    )
    for m in serie_detail.mesures:
        if isinstance(m, MesureJournaliere):
            w.writerow(
                [
                    serie_detail.code,
                    m.type,
                    "",
                    "",
                    m.instant_mesure.isoformat(),
                    "",
                    "",
                    "",
                    "",
                    m.valeur,
                    m.niveau_effectif,
                    m.statut,
                ]
            )
        elif isinstance(m, MesureMensuelle):
            w.writerow(
                [
                    serie_detail.code,
                    m.type,
                    m.annee,
                    m.mois,
                    "",
                    "",
                    "",
                    "",
                    "",
                    m.valeur,
                    m.niveau_effectif,
                    m.statut,
                ]
            )
        else:  # GrandeurMetierValeur
            w.writerow(
                [
                    serie_detail.code,
                    m.type,
                    "",
                    m.mois or "",
                    "",
                    m.periode_type,
                    m.annee_debut,
                    m.annee_fin,
                    m.version_formule,
                    m.valeur,
                    m.niveau_effectif,
                    m.statut,
                ]
            )
    return buffer.getvalue()


@routeur.get(
    "/{code_serie}",
    response_model=None,
    status_code=status.HTTP_200_OK,
    summary="Detail d'une serie avec ses mesures",
    description=(
        "Retourne le détail d'une série identifiée par son code, avec ses "
        "mesures : journalières, mensuelles ou valeurs de grandeur calculée "
        "selon la série. Bornes `from` et `to` facultatives, sortie JSON ou "
        "CSV. Les séries horaires se lisent par "
        "`/v1/horaire/{localite}/{grandeur}` : cette route répond 404 pour elles."
    ),
)
def detailler_serie(
    code_serie: str,
    _cle: CleApiValidee,
    session: Annotated[Session, Depends(obtenir_session)],
    from_: Annotated[
        str | None, Query(alias="from", description="Borne basse YYYY-MM ou YYYY-MM-DD")
    ] = None,
    to: Annotated[str | None, Query(description="Borne haute YYYY-MM ou YYYY-MM-DD")] = None,
    format_sortie: Annotated[
        str, Query(alias="format", description="Format de sortie : json (defaut) ou csv")
    ] = "json",
    limit: Annotated[int, Query(ge=1, le=_LIMIT_MAX_DETAIL)] = _LIMIT_DEFAUT_DETAIL,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> Response:
    """Détail d'une série avec ses mesures, en JSON ou en CSV."""
    _valider_format(format_sortie)
    from_d = _parser_borne_temporelle(from_, "from")
    to_d = _parser_borne_temporelle(to, "to")

    trouvee = lire_serie(session, code_serie)
    if trouvee is None:
        raise ExceptionKuma(
            code=CodeErreur.RESSOURCE_SERIE_INCONNUE,
            message=f"Serie {code_serie!r} introuvable.",
            statut_http=status.HTTP_404_NOT_FOUND,
        )
    serie = trouvee.catalogue

    table_cible = resolve_table_from_series_metadata(
        source_code=serie.source_code,
        granularite=trouvee.granularite,
    )

    bornes = (from_d, to_d)
    mesures: list[MesureLue]
    if table_cible == TableMesures.JOURNALIER:
        mesures = _lire_mesures_journalier(session, serie.id, bornes, limit, offset)
    elif table_cible == TableMesures.MENSUEL_RESSOURCE:
        mesures = _lire_mesures_mensuel(session, serie.id, bornes, limit, offset)
    elif table_cible == TableMesures.GRANDEURS_METIER:
        mesures = _lire_mesures_grandeurs_metier(session, serie.id, bornes, limit, offset)
    else:  # TableMesures.HORAIRE, servie par /v1/horaire
        raise ExceptionKuma(
            code=CodeErreur.RESSOURCE_INTROUVABLE,
            message=(
                "Les mesures horaires ne sont pas exposees via /v1/series ; "
                "l'acces horaire (valide ou passe-plat en repli) se fait par "
                "l'endpoint dedie /v1/horaire/{localite}/{grandeur}."
            ),
            statut_http=status.HTTP_404_NOT_FOUND,
        )

    detail = SerieDetail(
        id=serie.id,
        code=serie.code,
        libelle=serie.libelle,
        localite_id=serie.localite_id,
        localite_code=serie.localite_code,
        localite_nom=serie.localite_nom,
        localite_iso3=serie.localite_iso3,
        grandeur_code=serie.grandeur_code,
        grandeur_label=serie.grandeur_label,
        grandeur_unit=serie.grandeur_unit,
        source_id=serie.source_id,
        source_code=serie.source_code,
        source_label=serie.source_label,
        source_url=serie.source_url,
        periode_debut=serie.periode_debut,
        periode_fin=serie.periode_fin,
        methode_collecte=serie.methode_collecte,
        notes_fr=serie.notes_fr,
        created_at=serie.created_at,
        updated_at=serie.updated_at,
        actif=serie.actif,
        unite_code=trouvee.unite_code,
        mesures=mesures,
    )

    if format_sortie == "csv":
        return Response(content=_serialiser_csv(detail), media_type="text/csv")
    return JSONResponse(content=detail.model_dump(mode="json"))
