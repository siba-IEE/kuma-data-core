"""Grandeurs paramétrables de productible : correction thermique et PR fourni."""

from __future__ import annotations

from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, status
from fastapi.responses import Response
from sqlalchemy.orm import Session

from kuma_data_core.api.codes_erreur import CodeErreur
from kuma_data_core.api.dependencies import CleApiValidee, parametres_requete
from kuma_data_core.api.erreurs import ExceptionKuma
from kuma_data_core.api.v1.grandeurs._commun import (
    _construire_reponse,
    _exiger_grandeur,
    _lire_t2m_compagne,
    _resoudre_serie_source,
)
from kuma_data_core.api.v1.schemas.grandeurs import (
    ParametresProductibleCorrectionThermique,
    ParametresProductiblePRFourni,
)
from kuma_data_core.db.session import obtenir_session
from kuma_data_core.editorial.niveaux_confiance import NiveauxEntrees
from kuma_data_core.lecture.mesures import (
    lire_valeurs_horaires,
    lire_valeurs_journalieres,
    lire_valeurs_mensuelles,
)
from kuma_data_core.lecture.series import chercher_serie_compagne
from kuma_data_core.lecture.tables import TableMesures, resolve_table_from_series_metadata
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

routeur = APIRouter()


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
        t2m_serie_id = chercher_serie_compagne(
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
        ghi_h = lire_valeurs_horaires(
            session,
            serie.serie_id,
            params.periode_debut,
            params.periode_fin,
            fuseau=serie.fuseau_horaire,
            niveaux=niveaux,
        )
        t2m_h = lire_valeurs_horaires(
            session,
            t2m_serie_id,
            params.periode_debut,
            params.periode_fin,
            fuseau=serie.fuseau_horaire,
            niveaux=niveaux,
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
        ghi_par_jour = lire_valeurs_journalieres(
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
        ghi_h = lire_valeurs_horaires(
            session,
            serie.serie_id,
            params.periode_debut,
            params.periode_fin,
            fuseau=serie.fuseau_horaire,
            niveaux=niveaux,
        )
        mesures_horaires: list[MesureHeurePRFourni]
        if params.correction == "temperature":
            t2m_serie_id = chercher_serie_compagne(
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
            t2m_h = lire_valeurs_horaires(
                session,
                t2m_serie_id,
                params.periode_debut,
                params.periode_fin,
                fuseau=serie.fuseau_horaire,
                niveaux=niveaux,
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
        ghi_par_mois = lire_valeurs_mensuelles(
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

    ghi_par_jour = lire_valeurs_journalieres(
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
