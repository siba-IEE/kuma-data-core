"""Test de non-fuite de l'édition publique (ADR-0003, D5 / WP9).

Rejoue le SQL **réel** de construction d'une édition (WP1) sur la base
d'intégration, dans une transaction annulée à la fin - le DDL
PostgreSQL est transactionnel, la base ressort intacte. Couvre :

1. La garde anti-fuite générée (bloc ``DO`` de ``sql_controles``)
   passe après construction : chaque exclusion et chaque règle
   d'assainissement est effective.
2. Vérifications directes indépendantes de la garde : ``audit_log``
   absente, fonction et triggers d'audit absents, tous les e-mails de
   ``contributeurs`` neutralisés, tables publiées toujours présentes.
3. Le rollback restitue l'audit : le test ne laisse aucune trace.

C'est la version CI de ce que ``exporter-edition.ps1`` (garde locale)
et ``publier-edition.sh`` (smoke serveur) vérifient en opération : si
le manifeste ou le générateur SQL régressent, la CI casse ici sans
qu'aucune édition n'ait à être construite.
"""

from __future__ import annotations

import pytest
from sqlalchemy import text

from kuma_data_core.db.session import get_engine
from kuma_data_core.publication.manifeste import (
    FONCTION_AUDIT,
    TABLES_EXCLUES,
    tables_dumpees,
)
from kuma_data_core.publication.sql_edition import (
    instructions_construction,
    sql_controles,
)

pytestmark = pytest.mark.integration


def test_construction_puis_garde_anti_fuite_sur_base_reelle() -> None:
    engine = get_engine()
    with engine.connect() as connexion:
        transaction = connexion.begin()
        try:
            for instruction in instructions_construction():
                connexion.execute(text(instruction))

            # 1. La garde générée passe (elle lève sinon).
            connexion.execute(text(sql_controles()))

            # 2. Vérifications directes, indépendantes de la garde.
            for table in TABLES_EXCLUES:
                assert (
                    connexion.execute(text(f"SELECT to_regclass('public.{table}')")).scalar()
                    is None
                ), f"table exclue {table} encore présente"
            n_fonction = connexion.execute(
                text("SELECT count(*) FROM pg_proc WHERE proname = :f"),
                {"f": FONCTION_AUDIT},
            ).scalar()
            assert n_fonction == 0
            n_triggers = connexion.execute(
                text(
                    "SELECT count(*) FROM pg_trigger "
                    "WHERE NOT tgisinternal AND tgname LIKE 'trg_audit_%'"
                )
            ).scalar()
            assert n_triggers == 0
            emails = (
                connexion.execute(text("SELECT email_principal FROM contributeurs")).scalars().all()
            )
            assert emails, "contributeurs vide : l'assainissement n'a rien traité"
            assert all(str(e).endswith("@retire.invalid") for e in emails)
            for table in tables_dumpees():
                assert (
                    connexion.execute(text(f"SELECT to_regclass('public.{table}')")).scalar()
                    is not None
                ), f"table publiée {table} manquante après construction"
        finally:
            # 3. Rollback : la base d'intégration ressort intacte.
            transaction.rollback()

        assert (
            connexion.execute(text("SELECT to_regclass('public.audit_log')")).scalar() is not None
        )
        n_fonction_apres = connexion.execute(
            text("SELECT count(*) FROM pg_proc WHERE proname = :f"),
            {"f": FONCTION_AUDIT},
        ).scalar()
        assert n_fonction_apres == 1
