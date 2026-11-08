"""Salissure et PR réaliste : ``taux_salissure_proxy`` et ``pr_realiste``.

Les deux endpoints partagent le résolveur de la série de pluie et le garde-fou
de contiguïté du modèle HSU.
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import date, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, status
from sqlalchemy import text
from sqlalchemy.orm import Session

from kuma_data_core.api.codes_erreur import CodeErreur
from kuma_data_core.api.dependencies import CleApiValidee
from kuma_data_core.api.erreurs import ExceptionKuma
from kuma_data_core.api.v1.grandeurs._commun import (
    SerieSourceResolue,
    _chercher_compagne,
    _lire_mesures_par_serie_id,
    _resoudre_serie_exigee,
)
from kuma_data_core.api.v1.schemas.grandeurs import (
    MesureJourPR,
    ParametresPRRealiste,
    ReponsePRRealiste,
    ReponseTauxSalissureProxy,
)
from kuma_data_core.db.session import obtenir_session
from kuma_data_core.editorial.niveaux_confiance import (
    NiveauxEntrees,
    propager_niveau_confiance,
)
from kuma_data_core.services.grandeurs.pr_realiste import (
    PLAFOND_CONFIANCE as PLAFOND_PR_REALISTE,
)
from kuma_data_core.services.grandeurs.pr_realiste import (
    MesureJourPRRealiste,
    agreger_pr_mensuel,
    calculer_pr_realiste,
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

routeur = APIRouter()

# === Lecture commune (pluie, fenêtre, contiguïté) ===========================

_FENETRE_LARGE_DEBUT: date = date(2000, 1, 1)
_FENETRE_LARGE_FIN: date = date(2100, 1, 1)


def _chercher_serie_pluie_nasa(session: Session, serie_pm_id: int) -> int | None:
    """Série de précipitation journalière NASA POWER qui couvre la fenêtre de la série PM.

    Seul résolveur de pluie des calculs de salissure (proxy et PR réaliste) :
    le modèle HSU intègre la pluie sur les dates des PM, la série de pluie
    dépend donc de la série PM réellement lue, pas de la série GHI. La source
    est épinglée ; ordre stable sur ``periode_debut, id``.
    """
    row = session.execute(
        text(
            """
            SELECT sm.id FROM series_metadonnees sm
            JOIN sources s ON s.id = sm.source_id
            JOIN series_metadonnees pm ON pm.id = :serie_pm_id
            WHERE sm.localite_id = pm.localite_id
              AND s.code = 'nasa_power'
              AND sm.grandeur_code = 'precipitation'
              AND sm.granularite = 'journalier'
              AND sm.actif = TRUE
              AND sm.periode_debut <= pm.periode_debut
              AND (sm.periode_fin IS NULL
                   OR (pm.periode_fin IS NOT NULL AND sm.periode_fin >= pm.periode_fin))
            ORDER BY sm.periode_debut, sm.id
            LIMIT 1
            """
        ),
        {"serie_pm_id": serie_pm_id},
    ).first()
    return int(row.id) if row else None


def _lire_fenetre_large(
    session: Session, serie_ids: Iterable[int], *, niveaux: NiveauxEntrees
) -> list[dict[date, float]]:
    """Valeurs journalières utilisables de chaque série, sans borne de fenêtre effective."""
    return [
        _lire_mesures_par_serie_id(
            session, serie_id, _FENETRE_LARGE_DEBUT, _FENETRE_LARGE_FIN, niveaux=niveaux
        )
        for serie_id in serie_ids
    ]


def _verifier_contiguite_journaliere(dates: list[date], code_serie_source: str) -> None:
    """Garde-fou : le modèle HSU est path-dependant (il intègre la salissure depuis
    le début), l'index journalier doit être **trié croissant et sans trou** ; sinon
    l'accumulation est faussée. ``dates`` est supposé déjà trié."""
    for i in range(1, len(dates)):
        if dates[i] != dates[i - 1] + timedelta(days=1):
            raise ExceptionKuma(
                code=CodeErreur.PLAGE_TEMPORELLE_NON_DISPONIBLE,
                message=(
                    f"Serie source {code_serie_source!r} : trou dans l'index "
                    f"journalier (entre {dates[i - 1]} et {dates[i]}). Le modele "
                    "HSU est path-dependant et exige une serie sans trou ; le "
                    "calcul de salissure ne peut aboutir sur cette fenetre."
                ),
                statut_http=status.HTTP_422_UNPROCESSABLE_ENTITY,
            )


def _dates_communes(series: Iterable[dict[date, float]], code_serie_source: str) -> list[date]:
    """Dates présentes dans toutes les séries, triées, sans trou (sinon 422)."""
    premiere, *autres = series
    communes = set(premiere)
    for serie in autres:
        communes &= serie.keys()
    dates = sorted(communes)
    _verifier_contiguite_journaliere(dates, code_serie_source)
    return dates


def _niveaux_fenetre(niveaux: NiveauxEntrees, dates: Iterable[date]) -> set[str]:
    """Niveaux des entrées des jours retenus (modèle cumulatif de salissure)."""
    return {n for jour in dates for n in niveaux.du_jour(jour)}


def _periode(dates: list[date]) -> str:
    """Fenêtre effective ``debut/fin`` ISO, ``'aucune'`` si vide."""
    return f"{dates[0].isoformat()}/{dates[-1].isoformat()}" if dates else "aucune"


# === Endpoint taux_salissure_proxy (F1 calculee_volee, soiling) =======


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
    """Perte de transmission par salissure (% = (1 - ratio HSU) x 100), à la volée.

    Pipeline :

    1. ``code_serie_source`` = la série **PM2.5** (EAC4) ; résolution + contrôle de
       grandeur (400 si ce n'est pas une série ``pm2_5``).
    2. Compagne **PM10** (même source ``cams_eac4``, ``_chercher_serie_compagne``)
       + **precipitation** NASA POWER journalière couvrant la fenêtre de la série
       PM2.5. L'une absente -> 400.
    3. Lecture des 3 séries (mesures utilisables) ; alignement par
       **intersection des dates** (fenêtre effective = overlap PM ∩ pluie, bornée
       par les PM : 2021-01-01 à 2025-08-31) ; garde-fou de contiguïté (HSU
       path-dependant).
    4. Modèle HSU (pvlib) sur la fenêtre complète depuis le début (le spin-up n'est
       amorti qu'une fois) ; tilt / seuil de nettoyage = défauts F1 documentés.
    """
    niveaux = NiveauxEntrees()
    serie = _resoudre_serie_exigee(session, code_serie_source, "pm2_5", "taux_salissure_proxy")

    pm10_serie_id = _chercher_compagne(session, serie, "pm10")
    pluie_serie_id = _chercher_serie_pluie_nasa(session, serie.serie_id)
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

    pm2_5, pm10, pluie = _lire_fenetre_large(
        session, (serie.serie_id, pm10_serie_id, pluie_serie_id), niveaux=niveaux
    )
    dates = _dates_communes((pm2_5, pm10, pluie), code_serie_source)

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
        propager_niveau_confiance(_niveaux_fenetre(niveaux, dates), plafond=PLAFOND_SALISSURE)
        if dates
        else "B"
    )

    return ReponseTauxSalissureProxy(
        code_serie_source=code_serie_source,
        code_localite=serie.localite_code,
        periode=_periode(dates),
        surface_tilt_deg=SURFACE_TILT_DEFAUT,
        cleaning_threshold_mm=CLEANING_THRESHOLD_DEFAUT_MM,
        mesures=[m.model_copy(update={"niveau_confiance": niveau}) for m in resultat.mesures],
        limite=resultat.limite,
    )


# === Endpoint pr_realiste (F1 calculee_volee, PR réaliste saisonnier) =======


def _chercher_serie_pm_cams(session: Session, localite_id: int, grandeur_code: str) -> int | None:
    """Résout une série PM (``pm2_5`` / ``pm10``) journalière EAC4 d'une localité.

    Résolveur **cross-source dédié** : les PM sont ``cams_eac4``, source différente du
    GHI source (typiquement ``nasa_power``) ; ``_chercher_serie_compagne`` filtre sur
    ``source_id`` et les raterait. Source épinglée explicitement, ordre stable.
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


def _exiger_parametres_thermiques(params: ParametresPRRealiste) -> None:
    """422 ``VALIDATION_CHAMP_MANQUANT`` si une correction thermique manque NOCT ou gamma."""
    if params.noct_degc is None or params.coeff_temp_pourcent_par_degc is None:
        raise ExceptionKuma(
            code=CodeErreur.VALIDATION_CHAMP_MANQUANT,
            message=(
                f"correction={params.correction!r} requiert noct_degc et "
                "coeff_temp_pourcent_par_degc."
            ),
            statut_http=status.HTTP_422_UNPROCESSABLE_CONTENT,
        )


def _lire_t2m_pr_realiste(
    session: Session, serie: SerieSourceResolue, code_serie_source: str, niveaux: NiveauxEntrees
) -> dict[date, float]:
    """T2M compagne du GHI (même source) ; 400 si absente."""
    t2m_id = _chercher_compagne(session, serie, "t2m")
    if t2m_id is None:
        raise ExceptionKuma(
            code=CodeErreur.INCOMPATIBILITE_SOURCE_GRANDEUR,
            message=(
                "La correction temperature exige une serie T2M compagne pour la "
                f"localite de {code_serie_source!r} ; absente."
            ),
            statut_http=status.HTTP_400_BAD_REQUEST,
        )
    (t2m,) = _lire_fenetre_large(session, (t2m_id,), niveaux=niveaux)
    return t2m


def _lire_salissure_pr_realiste(
    session: Session, serie: SerieSourceResolue, code_serie_source: str, niveaux: NiveauxEntrees
) -> list[dict[date, float]]:
    """``[pluie, pm2_5, pm10]`` : PM EAC4 de la localité et pluie couvrant les PM ; 400 sinon."""
    pm2_5_id = _chercher_serie_pm_cams(session, serie.localite_id, "pm2_5")
    pm10_id = _chercher_serie_pm_cams(session, serie.localite_id, "pm10")
    pluie_id = None if pm2_5_id is None else _chercher_serie_pluie_nasa(session, pm2_5_id)
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
    return _lire_fenetre_large(session, (pluie_id, pm2_5_id, pm10_id), niveaux=niveaux)


def _propager_pr_realiste(
    mesures: list[MesureJourPR],
    niveaux: NiveauxEntrees,
    dates: list[date],
    besoin_salissure: bool,
) -> list[MesureJourPR]:
    """Règle P : sans salissure, chaque jour ne dépend que de ses entrées.

    La salissure est cumulative, chaque jour prend alors le niveau des entrées
    des jours retenus. Le mois prend celui de ses jours.
    """
    niveaux_fenetre = _niveaux_fenetre(niveaux, dates)
    return [
        m.model_copy(
            update={
                "niveau_confiance": propager_niveau_confiance(
                    niveaux_fenetre if besoin_salissure else niveaux.du_jour(m.instant),
                    plafond=PLAFOND_PR_REALISTE,
                )
            }
        )
        for m in mesures
    ]


@routeur.get(
    "/pr_realiste/{code_serie_source}",
    response_model=ReponsePRRealiste,
    status_code=status.HTTP_200_OK,
    summary="PR realiste saisonnier (PR effectif site-specifique, journalier + mensuel)",
    tags=["grandeurs-F1"],
)
def grandeur_pr_realiste(
    code_serie_source: str,
    params: Annotated[ParametresPRRealiste, Depends()],
    _cle: CleApiValidee,
    session: Annotated[Session, Depends(obtenir_session)],
) -> ReponsePRRealiste:
    """PR effectif = ``PR_fourni x ratio_T x (1 - salissure)`` selon le mode, à la volée.

    Source = série **GHI** (fournit G + l'index de dates ; 400 si grandeur != ghi).
    Compagnes selon le mode : T2M (même source que le GHI), PM2.5/PM10 (EAC4) et
    pluie NASA POWER journalière couvrant la fenêtre des PM, la même série que
    pour ``taux_salissure_proxy``. Alignement par intersection des séries du mode ; la fenêtre
    effective diverge donc par mode (les modes salissure sont bornés à l'overlap PM
    EAC4, 2025-08-31), avec garde-fou de contiguïté (HSU path-dependant). Sorties
    journalier + mensuel (la courbe mensuelle = la PR saisonnière).
    """
    niveaux = NiveauxEntrees()
    serie = _resoudre_serie_exigee(session, code_serie_source, "ghi", "pr_realiste")
    besoin_thermique = params.correction in ("temperature", "temperature_salissure")
    besoin_salissure = params.correction in ("salissure", "temperature_salissure")
    if besoin_thermique:
        _exiger_parametres_thermiques(params)

    (ghi,) = _lire_fenetre_large(session, (serie.serie_id,), niveaux=niveaux)
    series_du_mode = [ghi]
    t2m: dict[date, float] = {}
    if besoin_thermique:
        t2m = _lire_t2m_pr_realiste(session, serie, code_serie_source, niveaux)
        series_du_mode.append(t2m)
    pluie: dict[date, float] = {}
    pm2_5: dict[date, float] = {}
    pm10: dict[date, float] = {}
    if besoin_salissure:
        pluie, pm2_5, pm10 = _lire_salissure_pr_realiste(session, serie, code_serie_source, niveaux)
        series_du_mode += [pluie, pm2_5, pm10]
    dates = _dates_communes(series_du_mode, code_serie_source)

    # Hors mode, la compagne est vide : .get() rend None comme le mode l'exige.
    entrees: list[MesureJourPRRealiste] = [
        {
            "instant_mesure": jour,
            "ghi_kwh_par_m2_jour": ghi[jour] if besoin_thermique else None,
            "t_amb_degc": t2m.get(jour),
            "rainfall_mm": pluie.get(jour),
            "pm2_5": pm2_5.get(jour),
            "pm10": pm10.get(jour),
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
    mesures_jour = _propager_pr_realiste(resultat.mesures, niveaux, dates, besoin_salissure)

    return ReponsePRRealiste(
        code_serie_source=code_serie_source,
        code_localite=serie.localite_code,
        periode=_periode(dates),
        correction=params.correction,
        pr_fourni=params.pr_fourni,
        mesures_journalier=mesures_jour,
        mesures_mensuel=agreger_pr_mensuel(mesures_jour),
        limite=resultat.limite,
    )
