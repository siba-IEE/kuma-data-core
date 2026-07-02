#!/usr/bin/env bash
# =============================================================================
# provisionner-serveur.sh
#
# Provisionne les objets PostgreSQL de service du serveur public
# (ADR-0003, WP3). Idempotent : rejouable sans dégât, une ré-exécution
# fait tourner les mots de passe (rotation).
#
#   1. Rôle kuma_api_ro : LOGIN, lecture seule. Il ne reçoit AUCUN droit
#      ici : les grants SELECT sur chaque base d'édition sont posés par
#      publier-edition.sh à chaque publication (ADR-0003 D2).
#   2. Rôle kuma_api_service : LOGIN, écriture confinée à la base de
#      service (émission de clés WP6, D2/D3).
#   3. Base kuma_api_meta : hors lignée Alembic (ADR-0003 D3), schéma
#      peuplé par WP6. Persiste à travers les bascules d'édition.
#      CONNECT révoqué à PUBLIC et à kuma_api_ro : seul kuma_api_service
#      y écrit, personne d'autre n'y entre.
#
# Usage :
#   API_RO_PASSWORD=... API_SERVICE_PASSWORD=... ./provisionner-serveur.sh
#
# Environnement :
#   KUMA_PG_CONTENEUR     conteneur PostgreSQL (défaut : kuma-postgres)
#   PGUSER / PGPASSWORD   rôle administrateur du serveur
#   API_RO_PASSWORD       mot de passe du rôle lecture seule
#   API_SERVICE_PASSWORD  mot de passe du rôle de service
# =============================================================================

set -euo pipefail

CONTENEUR="${KUMA_PG_CONTENEUR:-kuma-postgres}"
PG_USER="${PGUSER:-postgres}"

erreur() { echo "ERREUR : $*" >&2; exit 1; }

[ -n "${API_RO_PASSWORD:-}" ] || erreur "API_RO_PASSWORD requis"
[ -n "${API_SERVICE_PASSWORD:-}" ] || erreur "API_SERVICE_PASSWORD requis"

# psql avec variables client (:'var') : les mots de passe ne transitent
# jamais par une chaîne SQL construite à la main.
psql_srv() {
    docker exec -i -e PGPASSWORD="${PGPASSWORD:-}" "$CONTENEUR" \
        psql -v ON_ERROR_STOP=1 -q -U "$PG_USER" -d "$1" -tA "${@:2}"
}

role_existe() {
    echo "SELECT 1 FROM pg_roles WHERE rolname = '$1';" | psql_srv postgres
}

# --- 1. Rôle lecture seule kuma_api_ro ---------------------------------------
if [ -z "$(role_existe kuma_api_ro)" ]; then
    echo "CREATE ROLE kuma_api_ro LOGIN PASSWORD :'mdp';" \
        | psql_srv postgres -v mdp="$API_RO_PASSWORD"
    echo "Rôle kuma_api_ro créé."
else
    echo "ALTER ROLE kuma_api_ro PASSWORD :'mdp';" \
        | psql_srv postgres -v mdp="$API_RO_PASSWORD"
    echo "Rôle kuma_api_ro existant : mot de passe tourné."
fi

# --- 2. Rôle de service kuma_api_service --------------------------------------
if [ -z "$(role_existe kuma_api_service)" ]; then
    echo "CREATE ROLE kuma_api_service LOGIN PASSWORD :'mdp';" \
        | psql_srv postgres -v mdp="$API_SERVICE_PASSWORD"
    echo "Rôle kuma_api_service créé."
else
    echo "ALTER ROLE kuma_api_service PASSWORD :'mdp';" \
        | psql_srv postgres -v mdp="$API_SERVICE_PASSWORD"
    echo "Rôle kuma_api_service existant : mot de passe tourné."
fi

# --- 3. Base de service kuma_api_meta ------------------------------------------
META_EXISTE="$(echo "SELECT 1 FROM pg_database WHERE datname = 'kuma_api_meta';" | psql_srv postgres)"
if [ -z "$META_EXISTE" ]; then
    echo "CREATE DATABASE kuma_api_meta;" | psql_srv postgres
    echo "Base kuma_api_meta créée."
else
    echo "Base kuma_api_meta déjà présente."
fi

# Droits : personne n'entre dans la base de service sauf le rôle de
# service (et l'admin). Les ALTER DEFAULT PRIVILEGES couvrent les tables
# que WP6 créera plus tard via l'admin.
psql_srv postgres <<'SQL'
REVOKE CONNECT ON DATABASE kuma_api_meta FROM PUBLIC;
GRANT CONNECT ON DATABASE kuma_api_meta TO kuma_api_service;
SQL

psql_srv kuma_api_meta <<SQL
REVOKE ALL ON SCHEMA public FROM PUBLIC;
GRANT USAGE ON SCHEMA public TO kuma_api_service;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO kuma_api_service;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO kuma_api_service;
ALTER DEFAULT PRIVILEGES FOR ROLE $PG_USER IN SCHEMA public
    GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO kuma_api_service;
ALTER DEFAULT PRIVILEGES FOR ROLE $PG_USER IN SCHEMA public
    GRANT USAGE, SELECT ON SEQUENCES TO kuma_api_service;
SQL

echo "Provisioning serveur terminé (kuma_api_ro, kuma_api_service, kuma_api_meta)."
echo "Grants d'édition : posés par publier-edition.sh à chaque publication."
