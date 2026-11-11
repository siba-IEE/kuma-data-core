"""PR réaliste : PR fourni corrigé de la température et de la salissure."""

from __future__ import annotations

from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from kuma_data_core.api.codes_erreur import CodeErreur
from kuma_data_core.api.dependencies import CleApiValidee, parametres_requete
from kuma_data_core.api.erreurs import ExceptionKuma
from kuma_data_core.api.v1.grandeurs._commun import (
    _FENETRE_LARGE_DEBUT,
    _FENETRE_LARGE_FIN,
    _exiger_grandeur,
    _resoudre_serie_source,
    _verifier_contiguite_journaliere,
)
from kuma_data_core.api.v1.schemas.grandeurs import ParametresPRRealiste, ReponsePRRealiste
from kuma_data_core.db.session import obtenir_session
from kuma_data_core.editorial.niveaux_confiance import NiveauxEntrees, propager_niveau_confiance
from kuma_data_core.lecture.mesures import lire_valeurs_journalieres
from kuma_data_core.lecture.series import chercher_serie_compagne, chercher_serie_pm_cams_eac4
from kuma_data_core.services.grandeurs.pr_realiste import (
    PLAFOND_CONFIANCE as PLAFOND_PR_REALISTE,
)
from kuma_data_core.services.grandeurs.pr_realiste import (
    MesureJourPRRealiste,
    agreger_pr_mensuel,
    calculer_pr_realiste,
)

routeur = APIRouter()


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

    ghi = lire_valeurs_journalieres(
        session, serie.serie_id, _FENETRE_LARGE_DEBUT, _FENETRE_LARGE_FIN, niveaux=niveaux
    )
    ensembles_dates: list[set[date]] = [set(ghi.keys())]

    t2m: dict[date, float] = {}
    if besoin_thermique:
        t2m_id = chercher_serie_compagne(
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
        t2m = lire_valeurs_journalieres(
            session, t2m_id, _FENETRE_LARGE_DEBUT, _FENETRE_LARGE_FIN, niveaux=niveaux
        )
        ensembles_dates.append(set(t2m.keys()))

    pluie: dict[date, float] = {}
    pm2_5: dict[date, float] = {}
    pm10: dict[date, float] = {}
    if besoin_salissure:
        pluie_id = chercher_serie_compagne(
            session,
            serie.localite_id,
            serie.source_id,
            "precipitation",
            serie.periode_debut,
            serie.granularite,
        )
        pm2_5_id = chercher_serie_pm_cams_eac4(session, serie.localite_id, "pm2_5")
        pm10_id = chercher_serie_pm_cams_eac4(session, serie.localite_id, "pm10")
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
        pluie = lire_valeurs_journalieres(
            session, pluie_id, _FENETRE_LARGE_DEBUT, _FENETRE_LARGE_FIN, niveaux=niveaux
        )
        pm2_5 = lire_valeurs_journalieres(
            session, pm2_5_id, _FENETRE_LARGE_DEBUT, _FENETRE_LARGE_FIN, niveaux=niveaux
        )
        pm10 = lire_valeurs_journalieres(
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
