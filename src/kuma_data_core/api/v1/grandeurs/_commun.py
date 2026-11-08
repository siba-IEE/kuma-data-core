"""Étapes communes des endpoints de grandeurs calculées à la volée.

Résolution de la série source et de ses séries compagnes, lecture des
mesures utilisables (journalières, horaires, mensuelles) avec rangement des
niveaux de confiance d'entrée, alignement des séries sur leurs instants
communs, propagation de la confiance (règle P) et sérialisation JSON / CSV.
"""

from __future__ import annotations

import csv
import io
from collections.abc import Callable, Sequence
from datetime import UTC, date, datetime
from typing import Literal, NamedTuple

from fastapi import status
from fastapi.responses import JSONResponse, Response
from sqlalchemy import text
from sqlalchemy.orm import Session

from kuma_data_core.api.codes_erreur import CodeErreur
from kuma_data_core.api.erreurs import ExceptionKuma
from kuma_data_core.api.v1.schemas.grandeurs import (
    ParametresCommunsF2,
    ReponseGrandeurF2,
    ResultatJournalier,
    ResultatMensuel,
)
from kuma_data_core.editorial.niveaux_confiance import (
    NiveauConfiance,
    NiveauxEntrees,
    propager_niveau_confiance,
)
from kuma_data_core.editorial.statuts import (
    filtre_mesure_horaire_utilisable,
    filtre_mesure_utilisable,
)

# === Résolution série + localité ===========================================


class SerieSourceResolue(NamedTuple):
    """Résultat de ``_resoudre_serie_source`` (accès par attribut).

    Champ ``source_code`` alimente le dispatch table-cible
    (JOURNALIER / MENSUEL_RESSOURCE / GRANDEURS_METIER).
    Champ ``granularite`` : filtre des séries compagnes par granularité
    ET dispatch table-cible par granularité (la table horaire partage
    ``periode_debut = 2021-01-01`` avec la journalière ; seule la
    granularité les distingue).
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
    """Résout ``code_serie_source`` vers les métadonnées de la série.

    Le champ ``periode_debut`` est utilisé par les endpoints F2 pour
    matcher la fenêtre temporelle des séries compagnes (cf.
    ``_chercher_serie_compagne``) - nécessaire depuis l'ajout de séries
    climato mensuelle 1991-2020 / 2001-2020 qui coexistent avec les
    séries journalières 2021-2025 pour les mêmes couples (localité,
    grandeur, source).

    Le champ ``source_code`` alimente le dispatch table-cible via
    ``resolve_table_from_series_metadata`` pour les endpoints F2 à
    entrée polymorphe journalier/mensuel.

    Raises:
        ExceptionKuma : HTTP 404 ``RESSOURCE_SERIE_INCONNUE`` si série
            absente.
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
    """Résout ``localite_id`` vers ``(latitude_deg, longitude_deg)``.

    Raises:
        ExceptionKuma : HTTP 500 ``SERVEUR_ERREUR_INTERNE`` si localité
            absente (incohérence FK théoriquement impossible).
    """
    row = session.execute(
        text("SELECT latitude, longitude FROM localites WHERE id = :id"),
        {"id": localite_id},
    ).first()
    if row is None or row.latitude is None or row.longitude is None:
        raise ExceptionKuma(
            code=CodeErreur.SERVEUR_ERREUR_INTERNE,
            message=(
                f"Localite id={localite_id} sans coordonnees latitude/longitude "
                "(incoherence FK ou seed incomplet)."
            ),
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
    """Cherche une série compagne (même localité + source, grandeur différente).

    Deux filtres garantissent que la compagne appartient à la même
    "famille temporelle" que la source :

    - ``periode_debut = :periode_debut_source`` distingue les fenêtres
      climato (1991/2001) de la journalière (2021).
    - ``granularite IS NOT DISTINCT FROM :granularite_source`` distingue
      journalier / mensuel / horaire pour un même ``periode_debut``
      (séries horaires, periode_debut=2021-01-01 partagé
      avec les journalières : sans ce filtre une compagne horaire serait
      sélectionnée pour un calcul journalier et lue dans la mauvaise
      table).

    Renvoie ``serie_id`` ou ``None`` si aucune trouvée.
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


def _chercher_compagne(
    session: Session, serie: SerieSourceResolue, grandeur_code_compagne: str
) -> int | None:
    """Compagne de ``serie`` : même localité, source, ``periode_debut`` et granularité."""
    return _chercher_serie_compagne(
        session,
        serie.localite_id,
        serie.source_id,
        grandeur_code_compagne,
        serie.periode_debut,
        serie.granularite,
    )


def _exiger_grandeur(
    grandeur_code: str,
    code_attendu: str,
    code_serie: str,
    endpoint: str,
) -> None:
    """Vérifie que la série source correspond à la grandeur attendue.

    Raises:
        ExceptionKuma : HTTP 400 ``INCOMPATIBILITE_SOURCE_GRANDEUR`` si
            ``grandeur_code != code_attendu``.
    """
    if grandeur_code != code_attendu:
        raise ExceptionKuma(
            code=CodeErreur.INCOMPATIBILITE_SOURCE_GRANDEUR,
            message=(
                f"Endpoint {endpoint!r} attend une serie source de grandeur "
                f"{code_attendu!r}, mais {code_serie!r} pointe vers {grandeur_code!r}."
            ),
            statut_http=status.HTTP_400_BAD_REQUEST,
        )


def _resoudre_serie_exigee(
    session: Session, code_serie: str, code_attendu: str, endpoint: str
) -> SerieSourceResolue:
    """Résout la série source (404 si absente) et exige sa grandeur (400 sinon)."""
    serie = _resoudre_serie_source(session, code_serie)
    _exiger_grandeur(serie.grandeur_code, code_attendu, code_serie, endpoint)
    return serie


def _exiger_serie_horaire(
    serie: SerieSourceResolue, code_serie_source: str, complement: str = ""
) -> None:
    """400 ``VALIDATION_VALEUR_INVALIDE`` si ``methode='integration_horaire'`` vise une
    série source non horaire ; ``complement`` prolonge le message."""
    if serie.granularite != "horaire":
        raise ExceptionKuma(
            code=CodeErreur.VALIDATION_VALEUR_INVALIDE,
            message=(
                "methode='integration_horaire' exige une serie source horaire "
                f"(granularite='horaire'), mais {code_serie_source!r} est de "
                f"granularite {serie.granularite!r}.{complement}"
            ),
            statut_http=status.HTTP_400_BAD_REQUEST,
        )


# === Lecture des mesures ===================================================


def _lire_mesures_par_serie_id(
    session: Session,
    serie_id: int,
    periode_debut: date,
    periode_fin: date,
    *,
    niveaux: NiveauxEntrees,
) -> dict[date, float]:
    """Lit les valeurs journalières d'une série sur la fenêtre.

    Renvoie un dict ``{instant_mesure: valeur}`` pour indexation rapide
    par date (utilisé pour aligner GHI/DNI/DHI/T2M lors des calculs
    multi-séries). Range le niveau effectif de chaque valeur lue dans
    ``niveaux`` (règle de propagation P).
    """
    rows = session.execute(
        text(
            f"""
            SELECT instant_mesure, valeur,
                   coalesce(niveau_confiance_override, niveau_confiance_derive) AS niveau
            FROM mesures_ressource
            WHERE serie_id = :serie_id
              AND {filtre_mesure_utilisable()}
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
    """Lit les valeurs horaires **validées** d'une série sur la fenêtre.

    Lit les mesures horaires utilisables (passées par le contrôle qualité),
    renvoie ``{instant_mesure: valeur}`` indexé par datetime
    UTC. Utilisé par l'intégration horaire DJC
    (``methode='integration_horaire'``). Borne de fenêtre sur la date UTC,
    cohérente avec la lecture journalière. Range le niveau effectif de
    chaque valeur lue sous son jour UTC dans ``niveaux``.
    """
    rows = session.execute(
        text(
            f"""
            SELECT instant_mesure, valeur,
                   coalesce(niveau_confiance_override, niveau_confiance_derive) AS niveau
            FROM mesures_ressource_horaires
            WHERE serie_id = :serie_id
              AND {filtre_mesure_horaire_utilisable()}
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
    """Lit les valeurs mensuelles d'une série sur la fenêtre.

    Renvoie un dict ``{(annee, mois): valeur}`` indexé par couple
    année/mois (pattern aligné sur ``mesures_ressource_mensuelles.annee``
    + ``mois`` SMALLINT séparés). Bornes inclusives traduites en
    comparaisons lexicographiques ``(annee, mois) >= (from_y, from_m)``
    et ``<=`` (cf. ``api/v1/series.py:_lire_mesures_mensuel``).

    Réutilisé par les endpoints F2 à entrée polymorphe journalier /
    mensuel (dispatch via ``resolve_table_from_series_metadata``). Range le
    niveau effectif de chaque valeur lue sous son mois dans ``niveaux``.
    """
    rows = session.execute(
        text(
            f"""
            SELECT annee, mois, valeur,
                   coalesce(niveau_confiance_override, niveau_confiance_derive) AS niveau
            FROM mesures_ressource_mensuelles
            WHERE serie_id = :serie_id
              AND {filtre_mesure_utilisable()}
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


def _lire_si_presente(
    session: Session,
    serie_id: int | None,
    periode_debut: date,
    periode_fin: date,
    *,
    niveaux: NiveauxEntrees,
) -> dict[date, float]:
    """Valeurs journalières d'une compagne facultative, ``{}`` si elle est absente."""
    if serie_id is None:
        return {}
    return _lire_mesures_par_serie_id(
        session, serie_id, periode_debut, periode_fin, niveaux=niveaux
    )


def _lire_alignees[Instant: date](
    lire: Callable[..., dict[Instant, float]],
    session: Session,
    serie_ids: Sequence[int],
    periode_debut: date,
    periode_fin: date,
    *,
    niveaux: NiveauxEntrees,
) -> list[tuple[Instant, list[float]]]:
    """Lit plusieurs séries et garde les instants présents dans toutes.

    ``lire`` est l'un des lecteurs journalier ou horaire. Renvoie
    ``[(instant, [v_serie_0, v_serie_1, ...])]`` dans l'ordre chronologique
    de la première série ; les niveaux de toutes les valeurs lues sont rangés,
    y compris celles des instants écartés.
    """
    series = [
        lire(session, serie_id, periode_debut, periode_fin, niveaux=niveaux)
        for serie_id in serie_ids
    ]
    premiere, autres = series[0], series[1:]
    return [
        (instant, [valeur, *(serie[instant] for serie in autres)])
        for instant, valeur in premiere.items()
        if all(instant in serie for serie in autres)
    ]


def _lire_t2m_compagne(
    session: Session,
    serie: SerieSourceResolue,
    code_serie_source: str,
    endpoint: str,
    periode_debut: date,
    periode_fin: date,
    *,
    niveaux: NiveauxEntrees,
) -> dict[date, float]:
    """Cherche et lit la série T2M journalière compagne de ``serie``.

    La compagne partage la fenêtre temporelle ET la granularité de la série
    source (cf. ``_chercher_serie_compagne``).

    Raises:
        ExceptionKuma : HTTP 400 ``INCOMPATIBILITE_SOURCE_GRANDEUR`` si
            aucune série T2M compagne trouvée.
    """
    t2m_serie_id = _chercher_compagne(session, serie, "t2m")
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


def _lire_ghi_t2m_horaires(
    session: Session,
    serie: SerieSourceResolue,
    params: ParametresCommunsF2,
    intitule: str,
    *,
    niveaux: NiveauxEntrees,
) -> list[tuple[datetime, list[float]]]:
    """``[(instant, [ghi, t2m])]`` horaires alignés ; 400 si la T2M horaire compagne manque.

    ``intitule`` désigne l'endpoint dans le message (nom entre quotes et mode).
    """
    t2m_serie_id = _chercher_compagne(session, serie, "t2m")
    if t2m_serie_id is None:
        raise ExceptionKuma(
            code=CodeErreur.INCOMPATIBILITE_SOURCE_GRANDEUR,
            message=(
                f"Endpoint {intitule} requiert une serie T2M horaire compagne de "
                f"{params.code_serie_source!r}. Aucune trouvee."
            ),
            statut_http=status.HTTP_400_BAD_REQUEST,
        )
    return _lire_alignees(
        _lire_mesures_horaires_par_serie_id,
        session,
        (serie.serie_id, t2m_serie_id),
        params.periode_debut,
        params.periode_fin,
        niveaux=niveaux,
    )


def _lire_ghi_t2m_journaliers(
    session: Session,
    serie: SerieSourceResolue,
    params: ParametresCommunsF2,
    endpoint: str,
    *,
    niveaux: NiveauxEntrees,
) -> list[tuple[date, float, float]]:
    """``[(jour, ghi, t2m)]`` sur les jours communs ; 400 si la T2M compagne manque."""
    ghi_par_jour = _lire_mesures_par_serie_id(
        session, serie.serie_id, params.periode_debut, params.periode_fin, niveaux=niveaux
    )
    t2m_par_jour = _lire_t2m_compagne(
        session,
        serie,
        params.code_serie_source,
        endpoint,
        params.periode_debut,
        params.periode_fin,
        niveaux=niveaux,
    )
    return [
        (jour, ghi, t2m_par_jour[jour])
        for jour, ghi in ghi_par_jour.items()
        if jour in t2m_par_jour
    ]


# === Confiance et sérialisation ============================================


def _serialiser_csv_journalier(reponse: ReponseGrandeurF2) -> str:
    """Sérialise une réponse à résultats journaliers en CSV."""
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
