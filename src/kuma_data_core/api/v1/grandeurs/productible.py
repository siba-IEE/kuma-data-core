"""Productible PV : ``productible_correction_thermique`` et ``productible_pr_fourni``."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, status
from fastapi.responses import Response
from sqlalchemy.orm import Session

from kuma_data_core.api.codes_erreur import CodeErreur
from kuma_data_core.api.dependencies import CleApiValidee, parametres_requete
from kuma_data_core.api.erreurs import ExceptionKuma
from kuma_data_core.api.services.serie_lecture import (
    TableMesures,
    resolve_table_from_series_metadata,
)
from kuma_data_core.api.v1.grandeurs._commun import (
    SerieSourceResolue,
    _construire_reponse,
    _exiger_grandeur,
    _exiger_serie_horaire,
    _lire_ghi_t2m_horaires,
    _lire_ghi_t2m_journaliers,
    _lire_mesures_horaires_par_serie_id,
    _lire_mesures_mensuel_par_serie_id,
    _lire_mesures_par_serie_id,
    _lire_t2m_compagne,
    _resoudre_serie_exigee,
    _resoudre_serie_source,
)
from kuma_data_core.api.v1.schemas.grandeurs import (
    ParametresProductibleCorrectionThermique,
    ParametresProductiblePRFourni,
    ResultatJournalier,
    ResultatMensuel,
)
from kuma_data_core.db.session import obtenir_session
from kuma_data_core.editorial.niveaux_confiance import NiveauxEntrees
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


# === Endpoint productible correction thermique ============================


def _calculer_thermique_horaire(
    session: Session,
    serie: SerieSourceResolue,
    params: ParametresProductibleCorrectionThermique,
    *,
    niveaux: NiveauxEntrees,
) -> list[ResultatJournalier]:
    """NOCT appliqué par heure (T_cell sur le GHI horaire réel) : lève le biais de moyennage.

    Exige GHI horaire + T2M horaire compagne.
    """
    _exiger_serie_horaire(serie, params.code_serie_source)
    alignees = _lire_ghi_t2m_horaires(
        session, serie, params, "'productible_correction_thermique'", niveaux=niveaux
    )
    mesures: list[MesureHeureThermique] = [
        {"instant_mesure": instant, "t_amb_degc": t2m, "irradiance_w_par_m2": ghi}
        for instant, (ghi, t2m) in alignees
    ]
    return calculer_productible_correction_thermique_horaire(mesures=mesures, parametres=params)


def _calculer_thermique_journalier(
    session: Session,
    serie: SerieSourceResolue,
    params: ParametresProductibleCorrectionThermique,
    *,
    niveaux: NiveauxEntrees,
) -> list[ResultatJournalier]:
    """NOCT appliqué aux moyennes journalières GHI / T2M."""
    mesures: list[MesureJourThermique] = [
        {"instant_mesure": jour, "t_amb_degc": t2m, "irradiance_kwh_par_m2_jour": ghi}
        for jour, ghi, t2m in _lire_ghi_t2m_journaliers(
            session, serie, params, "productible_correction_thermique", niveaux=niveaux
        )
    ]
    return calculer_productible_correction_thermique(mesures=mesures, parametres=params)


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
    """Calcule le productible thermique-corrigé (NOCT simple Ross 1980).

    Pattern multi-séries automatique :

    - **Série principale attendue** : ``grandeur_code = 'ghi'``.
    - **Série compagne cherchée** : T2M (même localité + même source).
    - **Comportement si T2M présente** : modèle NOCT simple appliqué
      ligne par ligne (T_cell = T_amb + (NOCT - 20) * G / 800, puis
      P_AC corrigée).
    - **Comportement si T2M absente** : 400
      ``INCOMPATIBILITE_SOURCE_GRANDEUR`` (la correction thermique ne
      peut être calculée sans température ambiante).

    Note : un mode ``faiman`` (Faiman 2008, dépendant du vent) a été
    codé et testé puis retiré de l'API : Faiman relève du régime
    terrain, calibration locale u0/u1 requise pour éviter une fausse
    confiance B.
    """
    niveaux = NiveauxEntrees()
    serie = _resoudre_serie_exigee(
        session, params.code_serie_source, "ghi", "productible_correction_thermique"
    )
    calculer = (
        _calculer_thermique_horaire
        if params.methode == "integration_horaire"
        else _calculer_thermique_journalier
    )
    return _construire_reponse(
        code_grandeur="productible_correction_thermique",
        code_serie_source=params.code_serie_source,
        parametres_appliques={
            "noct_degc": params.noct_degc,
            "coeff_temp_pourcent_par_degc": params.coeff_temp_pourcent_par_degc,
            "puissance_stc_wc": params.puissance_stc_wc,
            "methode": params.methode,
        },
        resultats=calculer(session, serie, params, niveaux=niveaux),
        format_sortie=params.format_sortie,
        niveaux=niveaux,
        plafond=PLAFOND_THERMIQUE,
    )


# === Endpoint productible PR fourni =======================================


def _exiger_table_brute(table_cible: TableMesures, code_serie_source: str) -> None:
    """Une série calculée Kuma n'est pas admissible comme source brute (400)."""
    if table_cible == TableMesures.GRANDEURS_METIER:
        raise ExceptionKuma(
            code=CodeErreur.INCOMPATIBILITE_SOURCE_GRANDEUR,
            message=(
                f"Endpoint 'productible_pr_fourni' n'accepte pas de serie source "
                f"calculee Kuma (source.code='kuma_calculs'). Serie {code_serie_source!r} "
                "pointe sur 'grandeurs_metier'."
            ),
            statut_http=status.HTTP_400_BAD_REQUEST,
        )


def _calculer_pr_fourni_horaire(
    session: Session,
    serie: SerieSourceResolue,
    params: ParametresProductiblePRFourni,
    *,
    niveaux: NiveauxEntrees,
) -> list[ResultatJournalier]:
    """PR appliqué par heure.

    Pour PR_T (Dierauf) lève le biais de Jensen (T_cell non-linéaire) ; pour PR
    brut (linéaire) identique au journalier (exposé pour cohérence d'interface).
    Exige une série source horaire (+ T2M horaire si correction='temperature').
    """
    _exiger_serie_horaire(serie, params.code_serie_source)
    mesures: list[MesureHeurePRFourni]
    if params.correction == "temperature":
        alignees = _lire_ghi_t2m_horaires(
            session,
            serie,
            params,
            "'productible_pr_fourni' en correction='temperature' horaire",
            niveaux=niveaux,
        )
        mesures = [
            {"instant_mesure": instant, "irradiance_w_par_m2": ghi, "t_amb_degc": t2m}
            for instant, (ghi, t2m) in alignees
        ]
    else:
        ghi_h = _lire_mesures_horaires_par_serie_id(
            session, serie.serie_id, params.periode_debut, params.periode_fin, niveaux=niveaux
        )
        mesures = [
            {"instant_mesure": instant, "irradiance_w_par_m2": ghi, "t_amb_degc": None}
            for instant, ghi in ghi_h.items()
        ]
    return calculer_productible_pr_fourni_horaire(mesures=mesures, parametres=params)


def _calculer_pr_fourni_mensuel(
    session: Session,
    serie: SerieSourceResolue,
    params: ParametresProductiblePRFourni,
    *,
    niveaux: NiveauxEntrees,
) -> list[ResultatMensuel]:
    """Branche mensuelle climato, ``correction='aucune'`` seulement.

    Sortie « productible quotidien moyen pour le mois » ; le mode
    ``'temperature'`` (non-linéaire) est incompatible avec une moyenne climato.
    """
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
    mesures: list[MesureMoisPRFourni] = [
        {"annee": annee, "mois": mois, "irradiance_kwh_par_m2_jour": ghi}
        for (annee, mois), ghi in ghi_par_mois.items()
    ]
    return calculer_productible_pr_fourni_mensuel(mesures=mesures, parametres=params)


def _calculer_pr_fourni_journalier(
    session: Session,
    serie: SerieSourceResolue,
    params: ParametresProductiblePRFourni,
    *,
    niveaux: NiveauxEntrees,
) -> list[ResultatJournalier]:
    """PR brut ou PR_T sur les moyennes journalières (T2M compagne si 'temperature')."""
    ghi_par_jour = _lire_mesures_par_serie_id(
        session, serie.serie_id, params.periode_debut, params.periode_fin, niveaux=niveaux
    )
    t2m_par_jour = (
        _lire_t2m_compagne(
            session,
            serie,
            params.code_serie_source,
            "productible_pr_fourni",
            params.periode_debut,
            params.periode_fin,
            niveaux=niveaux,
        )
        if params.correction == "temperature"
        else {}
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
    return calculer_productible_pr_fourni(mesures=mesures, parametres=params)


def _parametres_pr_fourni(params: ParametresProductiblePRFourni) -> dict[str, object]:
    """Paramètres appliqués ; NOCT et coefficient thermique en correction='temperature'."""
    parametres: dict[str, object] = {
        "pr_fourni": params.pr_fourni,
        "correction": params.correction,
        "puissance_stc_wc": params.puissance_stc_wc,
        "methode": params.methode,
    }
    if params.correction == "temperature":
        parametres["noct_degc"] = params.noct_degc
        parametres["coeff_temp_pourcent_par_degc"] = params.coeff_temp_pourcent_par_degc
    return parametres


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
    """Calcule le productible avec PR fourni (brut Marion 2005 / PR_T Dierauf 2013).

    Pattern multi-séries automatique selon ``correction`` :

    - **Série principale attendue** : ``grandeur_code = 'ghi'``.
    - **Si ``correction = 'aucune'``** : aucune compagne cherchée. PR brut
      appliqué directement (E_AC = P_STC * G * PR).
    - **Si ``correction = 'temperature'``** :
      - Série T2M cherchée (même localité + même source).
      - Si T2M présente : PR_T appliqué (correction NOCT + facteur
        thermique).
      - Si T2M absente : 400 ``INCOMPATIBILITE_SOURCE_GRANDEUR``.

    Dispatch table-cible via ``resolve_table_from_series_metadata`` :

    - ``JOURNALIER`` (``mesures_ressource``) : flow journalier ci-dessus.
    - ``MENSUEL_RESSOURCE`` (``mesures_ressource_mensuelles``) : branche
      mensuelle climato, mode ``correction='aucune'`` uniquement. Sortie
      :class:`ResultatMensuel` au format ``instant='YYYY-MM'``, sémantique
      « productible quotidien moyen pour le mois ». Mode ``'temperature'``
      sur mensuel rejeté 400 ``INCOMPATIBILITE_SOURCE_GRANDEUR``
      (non-linéarité cubique NOCT incompatible avec moyenne climato).
    - ``GRANDEURS_METIER`` (série calculée Kuma) : rejeté 400
      ``INCOMPATIBILITE_SOURCE_GRANDEUR`` (une série F1 calculée Kuma
      n'est pas admissible comme source brute d'un calcul F2).

    Variantes PR_W et PR_C non exposées v1 (TMY Guinée non disponible).
    """
    niveaux = NiveauxEntrees()
    serie = _resoudre_serie_source(session, params.code_serie_source)

    # Dispatch table-cible avant vérification grandeur_code : toute série
    # kuma_calculs porte une grandeur_code != 'ghi', l'ordre inverse
    # masquerait le message explicite « source kuma_calculs non admissible ».
    table_cible = resolve_table_from_series_metadata(
        source_code=serie.source_code,
        granularite=serie.granularite,
    )
    _exiger_table_brute(table_cible, params.code_serie_source)
    _exiger_grandeur(serie.grandeur_code, "ghi", params.code_serie_source, "productible_pr_fourni")

    resultats: list[ResultatJournalier] | list[ResultatMensuel]
    if params.methode == "integration_horaire":
        resultats = _calculer_pr_fourni_horaire(session, serie, params, niveaux=niveaux)
    elif table_cible == TableMesures.MENSUEL_RESSOURCE:
        resultats = _calculer_pr_fourni_mensuel(session, serie, params, niveaux=niveaux)
    else:
        resultats = _calculer_pr_fourni_journalier(session, serie, params, niveaux=niveaux)

    return _construire_reponse(
        code_grandeur="productible_pr_fourni",
        code_serie_source=params.code_serie_source,
        parametres_appliques=_parametres_pr_fourni(params),
        resultats=resultats,
        format_sortie=params.format_sortie,
        niveaux=niveaux,
        plafond=PLAFOND_PR_FOURNI,
    )
