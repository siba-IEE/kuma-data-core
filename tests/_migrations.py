"""Aller-retour Alembic sur une base PostgreSQL éphémère, créée puis supprimée par test.

La migration 046 lève ``NotImplementedError`` au downgrade : la base de test
partagée, à head, ne peut pas redescendre sous 046. Chaque aller-retour
part donc d'une base vide, la monte jusqu'à la cible, applique les
migrations testées, redescend, remonte, et compare les états. La base
partagée n'est jamais touchée : Alembic n'est lancé que si la
configuration pointe effectivement sur la base éphémère.
"""

from __future__ import annotations

import os
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from uuid import uuid4

from alembic import command
from alembic.config import Config
from sqlalchemy import Connection, Engine, create_engine, make_url, text
from sqlalchemy.engine import URL
from sqlalchemy.pool import NullPool

_RACINE_DEPOT = Path(__file__).resolve().parents[1]
PREFIXE_BASE_EPHEMERE = "kuma_regr_"

# Variables posées le temps d'une commande Alembic : la base éphémère, et
# l'ingestion servie par les seeds committés (décomptes déterministes, aucun
# appel réseau).
_VARIABLES_FORCEES: dict[str, str] = {"KUMA_INGESTION_MODE": "offline"}
# EDITION_DB primerait sur POSTGRES_DB ; le court-circuit NASA viderait les séries.
_VARIABLES_RETIREES: tuple[str, ...] = ("EDITION_DB", "KUMA_SKIP_NASA_POWER_INGESTION")

# audit_log grossit à chaque INSERT/DELETE audité ; alembic_version est
# contrôlée à part.
_TABLES_HORS_EMPREINTE = frozenset({"audit_log", "alembic_version"})

_SQL_SCHEMA: dict[str, str] = {
    "colonnes": """
        SELECT table_name || '.' || column_name || ' ' || data_type || ' '
               || is_nullable || ' ' || coalesce(column_default, '')
        FROM information_schema.columns WHERE table_schema = 'public'
    """,
    "contraintes": """
        SELECT conrelid::regclass::text || '.' || conname || ' '
               || pg_get_constraintdef(oid)
        FROM pg_constraint WHERE connamespace = 'public'::regnamespace
    """,
    "index": "SELECT indexdef FROM pg_indexes WHERE schemaname = 'public'",
    "vues": "SELECT viewname || ' ' || definition FROM pg_views WHERE schemaname = 'public'",
    "declencheurs": """
        SELECT pg_get_triggerdef(oid) FROM pg_trigger WHERE NOT tgisinternal
    """,
    "fonctions": """
        SELECT proname || '(' || pg_get_function_identity_arguments(oid) || ') '
               || md5(coalesce(prosrc, ''))
        FROM pg_proc WHERE pronamespace = 'public'::regnamespace
    """,
    "commentaires": """
        SELECT d.objoid::regclass::text || '.' || d.objsubid || ' ' || d.description
        FROM pg_description d
        JOIN pg_class c ON c.oid = d.objoid AND d.classoid = 'pg_class'::regclass
        WHERE c.relnamespace = 'public'::regnamespace
    """,
    "extensions": "SELECT extname FROM pg_extension",
}


@dataclass(frozen=True)
class Empreinte:
    """Schéma public et contenu des tables (décompte + md5 des lignes triées)."""

    schema: dict[str, tuple[str, ...]]
    donnees: dict[str, tuple[int, str]]


def _colonnes_comparables(conn: Connection, table: str, *, exacte: bool) -> list[str]:
    """Colonnes de ``table`` ; hors mode exact, sans identifiants ni horodatages serveur.

    Une ligne supprimée puis réinsérée reçoit un nouvel ``id`` (et les clés
    étrangères qui la visent changent) ainsi qu'un nouveau ``now()`` : ces
    colonnes ne peuvent être identiques qu'entre deux états sans réinsertion.
    """
    lignes = conn.execute(
        text(
            """
            SELECT column_name, data_type, column_default
            FROM information_schema.columns
            WHERE table_schema = 'public' AND table_name = :t
            ORDER BY ordinal_position
            """
        ),
        {"t": table},
    ).all()
    if exacte:
        return [r.column_name for r in lignes]
    return [
        r.column_name
        for r in lignes
        if r.column_name != "id"
        and not r.column_name.endswith("_id")
        and not (r.data_type.startswith("timestamp") and r.column_default is not None)
    ]


def empreinte(conn: Connection, *, exacte: bool) -> Empreinte:
    """Empreinte de la base ; ``exacte`` inclut identifiants et horodatages."""
    schema = {
        cle: tuple(sorted(conn.execute(text(sql)).scalars().all()))
        for cle, sql in _SQL_SCHEMA.items()
    }
    tables = conn.execute(
        text(
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_schema = 'public' AND table_type = 'BASE TABLE'"
        )
    ).scalars()
    quote = conn.dialect.identifier_preparer.quote
    donnees: dict[str, tuple[int, str]] = {}
    for table in sorted(set(tables) - _TABLES_HORS_EMPREINTE):
        colonnes = ", ".join(quote(c) for c in _colonnes_comparables(conn, table, exacte=exacte))
        n, md5 = conn.execute(
            text(
                f"SELECT count(*), md5(coalesce(string_agg(r::text, E'\\n' ORDER BY r::text), '')) "
                f"FROM (SELECT {colonnes} FROM {quote(table)}) r"
            )
        ).one()
        donnees[table] = (int(n), str(md5))
    return Empreinte(schema=schema, donnees=donnees)


@contextmanager
def _settings_pointant_sur(nom_base: str) -> Iterator[None]:
    """Fait pointer ``get_settings()`` sur ``nom_base`` le temps du bloc, puis restaure."""
    from kuma_data_core.core.config import get_settings

    noms = ("POSTGRES_DB", *_VARIABLES_FORCEES, *_VARIABLES_RETIREES)
    sauvegarde = {nom: os.environ.get(nom) for nom in noms}
    try:
        os.environ["POSTGRES_DB"] = nom_base
        os.environ.update(_VARIABLES_FORCEES)
        for nom in _VARIABLES_RETIREES:
            os.environ.pop(nom, None)
        get_settings.cache_clear()
        base_effective = make_url(get_settings().database_url).database
        if base_effective != nom_base:
            raise RuntimeError(
                f"Alembic viserait {base_effective!r} au lieu de la base éphémère "
                f"{nom_base!r} (EDITION_DB dans .env ?) : aller-retour refusé."
            )
        yield
    finally:
        for nom, valeur in sauvegarde.items():
            if valeur is None:
                os.environ.pop(nom, None)
            else:
                os.environ[nom] = valeur
        get_settings.cache_clear()


class BaseEphemere:
    """Base vide dédiée à un test, pilotée par Alembic."""

    def __init__(self, nom: str, url: URL) -> None:
        self.nom = nom
        self.engine: Engine = create_engine(url, poolclass=NullPool)

    def _alembic(self, commande: Callable[[Config, str], None], revision: str) -> None:
        # Config sans fichier : env.py ne rejoue pas fileConfig, qui
        # désactiverait les loggers des tests suivants.
        cfg = Config()
        cfg.set_main_option("script_location", str(_RACINE_DEPOT / "migrations"))
        with _settings_pointant_sur(self.nom):
            commande(cfg, revision)

    def upgrade(self, revision: str) -> None:
        self._alembic(command.upgrade, revision)

    def downgrade(self, revision: str) -> None:
        self._alembic(command.downgrade, revision)

    def revision(self) -> str | None:
        with self.engine.connect() as conn:
            return conn.execute(text("SELECT version_num FROM alembic_version")).scalar()

    def scalar(self, sql: str, **params: Any) -> Any:
        with self.engine.connect() as conn:
            return conn.execute(text(sql), params).scalar()

    def empreinte(self, *, exacte: bool) -> Empreinte:
        with self.engine.connect() as conn:
            return empreinte(conn, exacte=exacte)


@contextmanager
def base_alembic_ephemere() -> Iterator[BaseEphemere]:
    """Crée ``kuma_regr_<hex>`` sur le serveur de test, la supprime en sortie, même en échec."""
    from kuma_data_core.core.config import get_settings

    url = make_url(get_settings().database_url)
    nom = f"{PREFIXE_BASE_EPHEMERE}{uuid4().hex[:12]}"
    admin = create_engine(
        url.set(database="postgres"), isolation_level="AUTOCOMMIT", poolclass=NullPool
    )
    quote = admin.dialect.identifier_preparer.quote
    try:
        with admin.connect() as conn:
            conn.exec_driver_sql(f"CREATE DATABASE {quote(nom)} OWNER {quote(url.username)}")
        base = BaseEphemere(nom, url.set(database=nom))
        try:
            yield base
        finally:
            base.engine.dispose()
    finally:
        with admin.connect() as conn:
            conn.execute(
                text(
                    "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                    "WHERE datname = :nom AND pid <> pg_backend_pid()"
                ),
                {"nom": nom},
            )
            conn.exec_driver_sql(f"DROP DATABASE IF EXISTS {quote(nom)} WITH (FORCE)")
        admin.dispose()


def ecarts(attendue: Empreinte, obtenue: Empreinte) -> list[str]:
    """Éléments de schéma et tables qui diffèrent entre deux empreintes."""
    resultat: list[str] = []
    for cle in sorted(attendue.schema.keys() | obtenue.schema.keys()):
        avant = set(attendue.schema.get(cle, ()))
        apres = set(obtenue.schema.get(cle, ()))
        resultat += [f"{cle} disparu : {e}" for e in sorted(avant - apres)]
        resultat += [f"{cle} apparu : {e}" for e in sorted(apres - avant)]
    for table in sorted(attendue.donnees.keys() | obtenue.donnees.keys()):
        avant_t = attendue.donnees.get(table)
        apres_t = obtenue.donnees.get(table)
        if avant_t != apres_t:
            resultat.append(f"table {table} : {avant_t} -> {apres_t}")
    return resultat


def verifier_aller_retour(
    base: BaseEphemere,
    *,
    cible: str,
    testee: str,
    controler_cible: Callable[[BaseEphemere], None],
    controler_testee: Callable[[BaseEphemere], None],
) -> None:
    """``upgrade cible`` → ``upgrade testee`` → ``downgrade cible`` → ``upgrade testee``.

    Après le downgrade, la base doit être identique à l'état ``cible``
    initial (schéma et lignes, identifiants compris). Après le second
    upgrade, elle doit être identique au premier état ``testee`` (schéma
    et contenu, hors identifiants et horodatages serveur). Les contrôles
    métier propres au test tournent à chaque passage.
    """
    base.upgrade(cible)
    assert base.revision() == cible
    controler_cible(base)
    etat_cible = base.empreinte(exacte=True)

    base.upgrade(testee)
    assert base.revision() == testee
    controler_testee(base)
    etat_testee = base.empreinte(exacte=False)

    base.downgrade(cible)
    assert base.revision() == cible
    controler_cible(base)
    differences = ecarts(etat_cible, base.empreinte(exacte=True))
    assert not differences, f"downgrade {testee} -> {cible} non réversible : {differences}"

    base.upgrade(testee)
    assert base.revision() == testee
    controler_testee(base)
    differences = ecarts(etat_testee, base.empreinte(exacte=False))
    assert not differences, f"second upgrade {cible} -> {testee} divergent : {differences}"
