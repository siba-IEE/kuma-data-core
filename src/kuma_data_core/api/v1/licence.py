"""Endpoint ``POST /v1/licence/bail`` - le bail d'usage de SolClim-3.

Le logiciel le demande au démarrage et à intervalles réguliers tant qu'il
est en ligne ; il le garde pour travailler hors ligne jusqu'à son terme.
Le bail n'est remis qu'à une clé active **porteuse d'une licence active**
(``licences_solclim``) : une clé d'API publique seule, la clé partagée
d'environnement ou la clé administrateur n'y donnent pas droit.

Retirer la licence ou révoquer la clé tarit le bail : le logiciel ne le
renouvelle plus et passe en lecture seule au terme du bail en cours.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, status
from sqlalchemy.orm import Session

from kuma_data_core.api.codes_erreur import CodeErreur
from kuma_data_core.api.dependencies import CleApiValidee
from kuma_data_core.api.erreurs import ExceptionKuma
from kuma_data_core.api.v1.schemas.licence import ReponseBail
from kuma_data_core.core.config import get_settings
from kuma_data_core.services.bail import charger_cle_privee, construire_charge, signer
from kuma_data_core.services.licences import licence_valide_pour_cle, noter_bail

routeur = APIRouter(prefix="/licence", tags=["licence"])


@routeur.post(
    "/bail",
    response_model=ReponseBail,
    status_code=status.HTTP_200_OK,
    summary="Émettre le bail d'usage de SolClim-3",
    description=(
        "Remet un bail signé (Ed25519) à une clé porteuse d'une licence "
        "SolClim-3 active. Le bail vaut la durée nominale, sans dépasser "
        "le terme de la licence."
    ),
)
def emettre_bail(cle: CleApiValidee) -> ReponseBail:
    """Émet le bail de la licence attachée à la clé présentée."""
    settings = get_settings()
    # Une variable présente mais vide (``LICENCE_CLE_SIGNATURE=``) vaut
    # absence : sans ce garde, une graine vide ferait une erreur 500.
    graine = (
        settings.licence_cle_signature.get_secret_value()
        if settings.licence_cle_signature is not None
        else ""
    )
    if settings.meta_db is None or not graine:
        raise ExceptionKuma(
            code=CodeErreur.LICENCE_NON_ACTIVEE,
            message="L'emission de bail SolClim-3 n'est pas activee sur ce deploiement.",
            statut_http=status.HTTP_404_NOT_FOUND,
        )

    from kuma_data_core.db.session import get_engine_meta

    maintenant = datetime.now(tz=UTC)
    with Session(get_engine_meta()) as session:
        trouve = licence_valide_pour_cle(session, cle, maintenant)
        if trouve is None:
            raise ExceptionKuma(
                code=CodeErreur.LICENCE_ABSENTE,
                message="Aucune licence SolClim-3 active n'est attachee a cette cle.",
                statut_http=status.HTTP_403_FORBIDDEN,
            )
        licence, cle_api = trouve
        charge = construire_charge(
            prefixe_cle=cle_api.prefixe,
            titulaire=licence.titulaire,
            organisation=licence.organisation,
            fin_licence=licence.expire_le,
            maintenant=maintenant,
            duree=timedelta(days=settings.licence_duree_jours),
            version_minimale=settings.licence_version_minimale,
        )
        noter_bail(session, licence, maintenant)

    bail = signer(charge, charger_cle_privee(graine))
    return ReponseBail(
        charge=bail.charge,
        signature=bail.signature,
        titulaire=str(charge["titulaire"]),
        expire_le=str(charge["expire_le"]),
    )
