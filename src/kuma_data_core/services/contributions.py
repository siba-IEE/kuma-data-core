"""Contributions d'études SolClim-3 : déposer, retirer, faire le bilan.

Une fiche est attachée à la clé qui l'a déposée et à l'identifiant aléatoire
de l'étude ; un nouvel envoi de la même étude la remplace (ADR-0006). Le
retrait est toujours possible pour l'auteur, licence ou non : c'est la
contrepartie du partage par défaut.

Outil d'administration, à lancer sur le serveur avec ``META_DB`` posée :

.. code-block:: text

    python -m kuma_data_core.services.contributions bilan
    python -m kuma_data_core.services.contributions exporter [--module pv-autonome]

``exporter`` écrit une fiche par ligne (JSON) sur la sortie standard, avec
un numéro de contributeur stable mais sans la clé ni son préfixe.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import delete, func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from kuma_data_core.api.v1.schemas.contributions import DemandeContribution
from kuma_data_core.db.meta import CleApi, ContributionEtude
from kuma_data_core.services.cles import hacher_cle


@dataclass(frozen=True)
class Depot:
    """Ce que le dépôt a laissé en base."""

    recue_le: datetime
    mise_a_jour_le: datetime
    nombre_envois: int

    @property
    def creee(self) -> bool:
        return self.nombre_envois == 1


def cle_active(session: Session, cle: str) -> CleApi | None:
    """La ligne ``cles_api`` active de cette clé ; ``None`` pour une clé d'environnement."""
    return session.execute(
        select(CleApi).where(CleApi.cle_hash == hacher_cle(cle), CleApi.actif.is_(True))
    ).scalar_one_or_none()


def deposer(
    session: Session,
    cle_api: CleApi,
    etude_uid: str,
    demande: DemandeContribution,
    maintenant: datetime,
) -> Depot:
    """Crée la fiche de l'étude, ou remplace celle que la même clé avait déposée."""
    fiche = demande.fiche.model_dump(mode="json")
    valeurs = {
        "module": demande.module,
        "format_fiche": demande.format,
        "version_logiciel": demande.fiche.logiciel.version,
        "fiche": fiche,
    }
    requete = (
        insert(ContributionEtude)
        .values(
            cle_api_id=cle_api.id,
            etude_uid=etude_uid,
            recue_le=maintenant,
            mise_a_jour_le=maintenant,
            **valeurs,
        )
        .on_conflict_do_update(
            index_elements=[ContributionEtude.cle_api_id, ContributionEtude.etude_uid],
            set_={
                **valeurs,
                "mise_a_jour_le": maintenant,
                "nombre_envois": ContributionEtude.nombre_envois + 1,
            },
        )
        .returning(
            ContributionEtude.recue_le,
            ContributionEtude.mise_a_jour_le,
            ContributionEtude.nombre_envois,
        )
    )
    ligne = session.execute(requete).one()
    session.commit()
    return Depot(
        recue_le=ligne.recue_le,
        mise_a_jour_le=ligne.mise_a_jour_le,
        nombre_envois=ligne.nombre_envois,
    )


def retirer(session: Session, cle_api: CleApi, etude_uid: str) -> bool:
    """Supprime la fiche de cette étude déposée par cette clé ; ``False`` si absente."""
    supprimees = session.execute(
        delete(ContributionEtude)
        .where(
            ContributionEtude.cle_api_id == cle_api.id,
            ContributionEtude.etude_uid == etude_uid,
        )
        .returning(ContributionEtude.id)
    ).all()
    session.commit()
    return bool(supprimees)


def _bilan(session: Session) -> list[str]:
    lignes = session.execute(
        select(
            ContributionEtude.module,
            func.count(),
            func.count(func.distinct(ContributionEtude.cle_api_id)),
            func.max(ContributionEtude.mise_a_jour_le),
        ).group_by(ContributionEtude.module)
    ).all()
    if not lignes:
        return ["Aucune fiche."]
    return [
        f"{module}  {fiches} fiche(s)  {auteurs} contributeur(s)  "
        f"dernière {derniere:%Y-%m-%d %H:%M}"
        for module, fiches, auteurs, derniere in lignes
    ]


def _exporter(session: Session, module: str | None) -> None:
    requete = select(
        ContributionEtude.cle_api_id,
        ContributionEtude.module,
        ContributionEtude.format_fiche,
        ContributionEtude.mise_a_jour_le,
        ContributionEtude.fiche,
    ).order_by(ContributionEtude.id)
    if module is not None:
        requete = requete.where(ContributionEtude.module == module)
    for contributeur, module_, format_, mise_a_jour_le, fiche in session.execute(requete):
        enregistrement = {
            "contributeur": contributeur,
            "module": module_,
            "format": format_,
            "mise_a_jour_le": mise_a_jour_le.isoformat(),
            "fiche": fiche,
        }
        sys.stdout.write(json.dumps(enregistrement, ensure_ascii=False) + "\n")


def principal(arguments: Sequence[str] | None = None) -> int:
    """Point d'entrée de l'outil d'administration."""
    analyseur = argparse.ArgumentParser(
        prog="python -m kuma_data_core.services.contributions",
        description="Contributions d'études SolClim-3 (base de service).",
    )
    actions = analyseur.add_subparsers(dest="action", required=True)
    actions.add_parser("bilan", help="fiches et contributeurs par module")
    e = actions.add_parser("exporter", help="une fiche par ligne (JSON), sans les clés")
    e.add_argument("--module")
    options = analyseur.parse_args(arguments)

    from kuma_data_core.core.config import get_settings
    from kuma_data_core.db.session import get_engine_meta

    if get_settings().meta_db is None:
        print("META_DB non configurée : pas de base de service ici.", file=sys.stderr)
        return 2
    with Session(get_engine_meta()) as session:
        if options.action == "bilan":
            print("\n".join(_bilan(session)))
        else:
            _exporter(session, options.module)
    return 0


if __name__ == "__main__":
    raise SystemExit(principal())
