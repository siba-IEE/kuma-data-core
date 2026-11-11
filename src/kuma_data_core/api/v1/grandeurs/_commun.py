"""Partagé par les routes ``/v1/grandeurs``.

Résolution de la série source et de ses compagnes avec leurs erreurs HTTP,
contrôle de contiguïté, propagation du niveau de confiance (règle P) et
réponse JSON ou CSV des grandeurs paramétrables.
"""

from __future__ import annotations

import csv
import io
from collections.abc import Sequence
from datetime import date, timedelta
from typing import Literal

from fastapi import status
from fastapi.responses import JSONResponse, Response
from sqlalchemy.orm import Session

from kuma_data_core.api.codes_erreur import CodeErreur
from kuma_data_core.api.erreurs import ExceptionKuma
from kuma_data_core.api.v1.schemas.grandeurs import ReponseGrandeurF2
from kuma_data_core.editorial.niveaux_confiance import (
    NiveauConfiance,
    NiveauxEntrees,
    propager_niveau_confiance,
)
from kuma_data_core.lecture.localites import lire_coordonnees
from kuma_data_core.lecture.mesures import lire_valeurs_journalieres
from kuma_data_core.lecture.series import (
    SerieSourceResolue,
    chercher_serie_active,
    chercher_serie_compagne,
)
from kuma_data_core.services.grandeurs.types import ResultatJournalier, ResultatMensuel


def _resoudre_serie_source(session: Session, code_serie: str) -> SerieSourceResolue:
    """Métadonnées de la série active ``code_serie``.

    Lève 404 ``RESSOURCE_SERIE_INCONNUE`` si elle n'existe pas.
    """
    serie = chercher_serie_active(session, code_serie)
    if serie is None:
        raise ExceptionKuma(
            code=CodeErreur.RESSOURCE_SERIE_INCONNUE,
            message=f"Serie source {code_serie!r} introuvable.",
            statut_http=status.HTTP_404_NOT_FOUND,
        )
    return serie


def _resoudre_coordonnees(session: Session, localite_id: int) -> tuple[float, float]:
    """``(latitude, longitude)`` de la localité, en degrés.

    Lève 500 ``SERVEUR_ERREUR_INTERNE`` si elle n'a pas de coordonnées.
    """
    coordonnees = lire_coordonnees(session, localite_id)
    if coordonnees is None:
        raise ExceptionKuma(
            code=CodeErreur.SERVEUR_ERREUR_INTERNE,
            message=f"La localité id={localite_id} n'a pas de coordonnées enregistrées.",
            statut_http=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )
    return coordonnees


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
    t2m_serie_id = chercher_serie_compagne(
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
    return lire_valeurs_journalieres(
        session, t2m_serie_id, periode_debut, periode_fin, niveaux=niveaux
    )


# Bornes larges : le proxy de salissure et le PR réaliste lisent toute la série,
# sans fenêtre demandée.
_FENETRE_LARGE_DEBUT: date = date(2000, 1, 1)
_FENETRE_LARGE_FIN: date = date(2100, 1, 1)


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
