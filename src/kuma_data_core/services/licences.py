"""Licences SolClim-3 : accorder, retirer, prolonger, lister.

Une licence rattache une clé API (``cles_api``) à une personne et à son
organisation, et lui donne droit au bail signé de ``POST /v1/licence/bail``.
Le préfixe public de la clé (``kuma_xxxxxxxx``) sert d'identifiant : c'est
ce que la personne peut lire et transmettre sans livrer sa clé.

Outil d'administration, à lancer sur le serveur avec ``META_DB`` posée :

.. code-block:: text

    python -m kuma_data_core.services.licences accorder kuma_AbCdEfGh \\
        --titulaire "Prénom Nom" --organisation "Bureau d'études" [--expire 2027-12-31]
    python -m kuma_data_core.services.licences lister [--toutes]
    python -m kuma_data_core.services.licences prolonger kuma_AbCdEfGh --expire 2028-06-30
    python -m kuma_data_core.services.licences prolonger kuma_AbCdEfGh --sans-terme
    python -m kuma_data_core.services.licences retirer kuma_AbCdEfGh

Retirer une licence ne touche pas la clé : la personne garde l'API
publique, perd SolClim-3. Elle ne reçoit plus de bail ; son logiciel
passe en lecture seule à la fin du bail en cours.
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from datetime import UTC, date, datetime, time

from sqlalchemy import select
from sqlalchemy.orm import Session

from kuma_data_core.db.meta import CleApi, LicenceSolclim
from kuma_data_core.exceptions import KumaError
from kuma_data_core.services.cles import hacher_cle


class LicenceError(KumaError):
    """Opération impossible sur une licence (message destiné à l'administrateur)."""


def cle_active_par_prefixe(session: Session, prefixe: str) -> CleApi:
    """La clé active portant ce préfixe ; refuse l'absence comme l'ambiguïté."""
    cles = (
        session.execute(select(CleApi).where(CleApi.prefixe == prefixe, CleApi.actif.is_(True)))
        .scalars()
        .all()
    )
    if not cles:
        raise LicenceError(f"aucune clé active ne porte le préfixe {prefixe}")
    if len(cles) > 1:
        raise LicenceError(
            f"{len(cles)} clés actives portent le préfixe {prefixe} : "
            "révoquer les doublons avant d'accorder une licence"
        )
    return cles[0]


def _licence_active(session: Session, cle_api_id: int) -> LicenceSolclim | None:
    return session.execute(
        select(LicenceSolclim).where(
            LicenceSolclim.cle_api_id == cle_api_id, LicenceSolclim.actif.is_(True)
        )
    ).scalar_one_or_none()


def accorder(
    session: Session,
    prefixe: str,
    titulaire: str,
    organisation: str | None = None,
    expire_le: datetime | None = None,
    notes_internes: str | None = None,
) -> LicenceSolclim:
    """Accorde une licence à la clé de ce préfixe ; une seule active par clé."""
    if not titulaire.strip():
        raise LicenceError("le titulaire est obligatoire")
    cle = cle_active_par_prefixe(session, prefixe)
    if _licence_active(session, cle.id) is not None:
        raise LicenceError(f"la clé {prefixe} a déjà une licence active")
    licence = LicenceSolclim(
        cle_api_id=cle.id,
        titulaire=titulaire.strip(),
        organisation=organisation.strip() if organisation else None,
        expire_le=expire_le,
        notes_internes=notes_internes,
    )
    session.add(licence)
    session.commit()
    session.refresh(licence)
    return licence


def retirer(session: Session, prefixe: str) -> int:
    """Retire (soft delete) les licences actives des clés de ce préfixe."""
    licences = (
        session.execute(
            select(LicenceSolclim)
            .join(CleApi, CleApi.id == LicenceSolclim.cle_api_id)
            .where(CleApi.prefixe == prefixe, LicenceSolclim.actif.is_(True))
        )
        .scalars()
        .all()
    )
    for licence in licences:
        licence.actif = False
        licence.desactive_le = datetime.now(tz=UTC)
    session.commit()
    return len(licences)


def prolonger(session: Session, prefixe: str, expire_le: datetime | None) -> LicenceSolclim:
    """Change le terme de la licence active (``None`` = sans terme)."""
    cle = cle_active_par_prefixe(session, prefixe)
    licence = _licence_active(session, cle.id)
    if licence is None:
        raise LicenceError(f"la clé {prefixe} n'a pas de licence active")
    licence.expire_le = expire_le
    session.commit()
    session.refresh(licence)
    return licence


def lister(session: Session, toutes: bool = False) -> list[tuple[LicenceSolclim, CleApi]]:
    """Les licences (actives seules par défaut), avec leur clé, plus récentes d'abord."""
    requete = (
        select(LicenceSolclim, CleApi)
        .join(CleApi, CleApi.id == LicenceSolclim.cle_api_id)
        .order_by(LicenceSolclim.cree_le.desc())
    )
    if not toutes:
        requete = requete.where(LicenceSolclim.actif.is_(True))
    return [(licence, cle) for licence, cle in session.execute(requete).all()]


def licence_valide_pour_cle(
    session: Session, cle: str, maintenant: datetime
) -> tuple[LicenceSolclim, CleApi] | None:
    """La licence qui ouvre le bail pour cette clé, ou ``None``.

    Il faut à la fois une clé active, une licence active, et une licence
    dont le terme n'est pas passé.
    """
    trouve = session.execute(
        select(LicenceSolclim, CleApi)
        .join(CleApi, CleApi.id == LicenceSolclim.cle_api_id)
        .where(
            CleApi.cle_hash == hacher_cle(cle),
            CleApi.actif.is_(True),
            LicenceSolclim.actif.is_(True),
        )
    ).one_or_none()
    if trouve is None:
        return None
    licence, cle_api = trouve
    if licence.expire_le is not None and licence.expire_le <= maintenant:
        return None
    return licence, cle_api


def noter_bail(session: Session, licence: LicenceSolclim, maintenant: datetime) -> None:
    """Retient la date du dernier bail émis : qui se sert du logiciel."""
    licence.dernier_bail_le = maintenant
    session.commit()


# --------------------------------------------------------------------------- CLI


def _fin_de_journee(jour: str) -> datetime:
    """``AAAA-MM-JJ`` → la fin de ce jour en UTC : une licence vaut tout son dernier jour."""
    return datetime.combine(date.fromisoformat(jour), time(23, 59, 59), tzinfo=UTC)


def _texte_date(instant: datetime | None) -> str:
    return "-" if instant is None else instant.astimezone(UTC).strftime("%Y-%m-%d")


def _analyseur() -> argparse.ArgumentParser:
    analyseur = argparse.ArgumentParser(
        prog="python -m kuma_data_core.services.licences",
        description="Licences SolClim-3 : accorder, retirer, prolonger, lister.",
    )
    actions = analyseur.add_subparsers(dest="action", required=True)

    a = actions.add_parser("accorder", help="accorder une licence à une clé")
    a.add_argument("prefixe", help="préfixe public de la clé (kuma_xxxxxxxx)")
    a.add_argument("--titulaire", required=True)
    a.add_argument("--organisation")
    a.add_argument("--expire", help="dernier jour de validité, AAAA-MM-JJ (défaut : sans terme)")
    a.add_argument("--notes")

    r = actions.add_parser("retirer", help="retirer la licence d'une clé")
    r.add_argument("prefixe")

    p = actions.add_parser("prolonger", help="changer le terme d'une licence")
    p.add_argument("prefixe")
    terme = p.add_mutually_exclusive_group(required=True)
    terme.add_argument("--expire", help="nouveau dernier jour, AAAA-MM-JJ")
    terme.add_argument("--sans-terme", action="store_true")

    li = actions.add_parser("lister", help="lister les licences")
    li.add_argument("--toutes", action="store_true", help="inclure les licences retirées")
    return analyseur


def principal(arguments: Sequence[str] | None = None) -> int:
    """Point d'entrée de l'outil d'administration ; rend le code de sortie."""
    options = _analyseur().parse_args(arguments)

    from kuma_data_core.core.config import get_settings
    from kuma_data_core.db.session import get_engine_meta

    if get_settings().meta_db is None:
        print("META_DB non configurée : pas de base de service ici.", file=sys.stderr)
        return 2

    with Session(get_engine_meta()) as session:
        try:
            if options.action == "accorder":
                licence = accorder(
                    session,
                    options.prefixe,
                    options.titulaire,
                    options.organisation,
                    _fin_de_journee(options.expire) if options.expire else None,
                    options.notes,
                )
                print(
                    f"Licence accordée à {licence.titulaire} ({options.prefixe}), "
                    f"terme : {_texte_date(licence.expire_le)}."
                )
            elif options.action == "retirer":
                n = retirer(session, options.prefixe)
                if n == 0:
                    print(f"Aucune licence active pour {options.prefixe}.", file=sys.stderr)
                    return 1
                print(f"Licence retirée pour {options.prefixe}.")
            elif options.action == "prolonger":
                terme = None if options.sans_terme else _fin_de_journee(options.expire)
                licence = prolonger(session, options.prefixe, terme)
                print(f"Terme de {options.prefixe} : {_texte_date(licence.expire_le)}.")
            else:
                lignes = lister(session, toutes=options.toutes)
                if not lignes:
                    print("Aucune licence.")
                for licence, cle in lignes:
                    etat = "active" if licence.actif else "retirée"
                    print(
                        f"{cle.prefixe}  {licence.titulaire}  "
                        f"{licence.organisation or '-'}  {etat}  "
                        f"terme {_texte_date(licence.expire_le)}  "
                        f"dernier bail {_texte_date(licence.dernier_bail_le)}"
                    )
        except LicenceError as erreur:
            print(f"Refusé : {erreur}.", file=sys.stderr)
            return 1
    return 0


if __name__ == "__main__":
    sys.exit(principal())
