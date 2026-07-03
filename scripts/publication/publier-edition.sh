#!/usr/bin/env bash
# =============================================================================
# publier-edition.sh
#
# Publie une édition du Core sur le serveur (ADR-0003, WP2). S'exécute sur
# la machine qui héberge le conteneur PostgreSQL de service (VPS ; testable
# en local contre le conteneur de dev, même pattern Docker).
#
#   1. Vérifie le couple dump + JSON compagnon (SHA-256).
#   2. Restaure dans une base NEUVE kuma_<edition_id>_<revision> (jamais
#      d'écrasement : publier = créer puis repointer, ADR-0003 D1).
#   3. Smoke checks : edition_metadonnees cohérente avec le JSON, table
#      d'audit absente (non-fuite), tables coeur non vides.
#   4. Si le rôle kuma_api_ro existe (WP3), lui accorde SELECT.
#   5. Bascule : met à jour la ligne EDITION_DB=<base> dans le fichier
#      d'environnement de l'API (.env.prod), le seul que le conteneur lise
#      (docker-compose injecte EDITION_DB, config.py le lit). La bascule
#      prend effet en recréant le conteneur API (docker compose up -d api).
#   6. Réserve N-1 : conserve la base précédemment active, supprime les
#      éditions plus anciennes. Retour arrière = remettre l'ancien nom dans
#      EDITION_DB et recréer le conteneur API.
#
# Usage :
#   ./publier-edition.sh <chemin/edition_AAAAMMJJ_rev.dump> <fichier_env_api>
#
# Environnement :
#   KUMA_PG_CONTENEUR  conteneur PostgreSQL (défaut : kuma-postgres)
#   PGUSER             rôle propriétaire pour la restauration (défaut : postgres)
#   PGPASSWORD         mot de passe du rôle (transmis au conteneur)
# =============================================================================

set -euo pipefail

CONTENEUR="${KUMA_PG_CONTENEUR:-kuma-postgres}"
PG_USER="${PGUSER:-postgres}"

erreur() { echo "ERREUR : $*" >&2; exit 1; }

[ "$#" -eq 2 ] || erreur "usage : publier-edition.sh <dump> <fichier_env_api>"
DUMP="$1"
FICHIER_ENV="$2"

[ -f "$DUMP" ] || erreur "dump introuvable : $DUMP"
JSON="${DUMP%.dump}.json"
[ -f "$JSON" ] || erreur "JSON compagnon introuvable : $JSON"

# --- Lecture du JSON compagnon --------------------------------------------
# JSON plat produit par exporter-edition.ps1 (nos clés, nos formats) : un
# extracteur grep/sed suffit et évite toute dépendance (python absent des
# VPS minimaux comme de Git Bash Windows). Les valeurs extraites sont de
# toute façon revalidées par regex ci-dessous.
lire_json() { grep -o "\"$1\": *\"[^\"]*\"" "$JSON" | head -1 | sed 's/.*: *"\(.*\)"/\1/'; }
EDITION_ID="$(lire_json edition_id)"
REVISION="$(lire_json revision_source)"
SHA_ATTENDU="$(lire_json sha256)"

echo "$EDITION_ID" | grep -Eq '^edition_[0-9]{8}$' || erreur "edition_id inattendu : $EDITION_ID"
echo "$REVISION" | grep -Eq '^[0-9a-f]{7,40}$' || erreur "revision_source inattendue : $REVISION"

# --- 1. Intégrité du dump ----------------------------------------------------
SHA_REEL="$(sha256sum "$DUMP" | cut -d' ' -f1)"
[ "$SHA_REEL" = "$SHA_ATTENDU" ] || erreur "SHA-256 divergent (attendu $SHA_ATTENDU, obtenu $SHA_REEL)"
echo "Intégrité du dump vérifiée ($EDITION_ID, révision $REVISION)."

psql_srv() { # psql sur le conteneur, échec au premier problème
    docker exec -i -e PGPASSWORD="${PGPASSWORD:-}" "$CONTENEUR" \
        psql -v ON_ERROR_STOP=1 -q -U "$PG_USER" -d "$1" -tA
}

# --- 2. Restauration dans une base neuve ------------------------------------
BASE_CIBLE="kuma_${EDITION_ID}_${REVISION}"
EXISTE="$(echo "SELECT 1 FROM pg_database WHERE datname = '$BASE_CIBLE';" | psql_srv postgres)"
[ -z "$EXISTE" ] || erreur "la base $BASE_CIBLE existe déjà (édition déjà publiée ?)"

echo "CREATE DATABASE $BASE_CIBLE;" | psql_srv postgres
DUMP_CONTENEUR="/tmp/$(basename "$DUMP")"
docker cp "$DUMP" "$CONTENEUR:$DUMP_CONTENEUR"
docker exec -e PGPASSWORD="${PGPASSWORD:-}" "$CONTENEUR" \
    pg_restore -U "$PG_USER" --no-owner -d "$BASE_CIBLE" "$DUMP_CONTENEUR" \
    || { docker exec "$CONTENEUR" rm -f "$DUMP_CONTENEUR"; erreur "pg_restore a échoué"; }
docker exec "$CONTENEUR" rm -f "$DUMP_CONTENEUR"
echo "Restauration dans $BASE_CIBLE terminée."

# --- 3. Smoke checks ----------------------------------------------------------
smoke() { echo "$1" | psql_srv "$BASE_CIBLE"; }

ID_RESTAURE="$(smoke "SELECT edition_id FROM edition_metadonnees;")"
[ "$ID_RESTAURE" = "$EDITION_ID" ] \
    || erreur "edition_metadonnees ($ID_RESTAURE) ne correspond pas au JSON ($EDITION_ID)"

FUITE="$(smoke "SELECT count(*) FROM pg_tables WHERE schemaname='public' AND tablename='audit_log';")"
[ "$FUITE" = "0" ] || erreur "non-fuite : audit_log présente dans l'édition restaurée"

for table in localites sources series_metadonnees mesures_ressource_mensuelles; do
    N="$(smoke "SELECT count(*) FROM $table;")"
    N="${N:-0}"
    [ "$N" -gt 0 ] 2>/dev/null || erreur "smoke : table coeur $table vide ou illisible"
done
echo "Smoke checks : OK."

# --- 4. Droits de lecture (si le rôle WP3 existe déjà) ------------------------
RO_EXISTE="$(echo "SELECT 1 FROM pg_roles WHERE rolname = 'kuma_api_ro';" | psql_srv postgres)"
if [ -n "$RO_EXISTE" ]; then
    smoke "GRANT CONNECT ON DATABASE $BASE_CIBLE TO kuma_api_ro;
           GRANT USAGE ON SCHEMA public TO kuma_api_ro;
           GRANT SELECT ON ALL TABLES IN SCHEMA public TO kuma_api_ro;" > /dev/null
    echo "Droits SELECT accordés à kuma_api_ro."
else
    echo "AVERTISSEMENT : rôle kuma_api_ro absent (WP3 non provisionné), aucun grant posé."
fi

# --- 5. Bascule : mise à jour de EDITION_DB dans le fichier d'environnement ----
[ -f "$FICHIER_ENV" ] || erreur "fichier d'environnement introuvable : $FICHIER_ENV"
# Lire l'édition précédente AVANT de réécrire (réserve N-1).
BASE_PRECEDENTE="$(grep -E '^EDITION_DB=' "$FICHIER_ENV" | head -1 | cut -d= -f2 || true)"
# Mise à jour en place de la seule ligne EDITION_DB (les autres secrets du
# fichier sont préservés). Ajout si la ligne n'existe pas encore.
if grep -qE '^EDITION_DB=' "$FICHIER_ENV"; then
    sed -i "s|^EDITION_DB=.*|EDITION_DB=$BASE_CIBLE|" "$FICHIER_ENV"
else
    printf 'EDITION_DB=%s\n' "$BASE_CIBLE" >> "$FICHIER_ENV"
fi
echo "EDITION_DB mis à jour dans $FICHIER_ENV -> $BASE_CIBLE."
echo "Recréer le conteneur API pour prise en compte : docker compose -f docker/docker-compose.prod.yml --env-file $FICHIER_ENV up -d api"

# --- 6. Réserve N-1 : garder la base précédente, purger le reste ---------------
# mapfile hors pipe : le corps de boucle s'exécute dans le shell courant (pas
# un sous-shell), et chaque échec de DROP est collecté au lieu d'être avalé.
mapfile -t BASES_EDITION < <(
    echo "SELECT datname FROM pg_database WHERE datname LIKE 'kuma_edition_%';" | psql_srv postgres
)
ECHECS_PURGE=0
for base in "${BASES_EDITION[@]}"; do
    [ -n "$base" ] || continue
    if [ "$base" != "$BASE_CIBLE" ] && [ "$base" != "$BASE_PRECEDENTE" ]; then
        echo "Purge de l'édition ancienne $base."
        if ! echo "DROP DATABASE $base;" | psql_srv postgres; then
            echo "AVERTISSEMENT : échec du DROP de $base (connexions actives ?), base conservée." >&2
            ECHECS_PURGE=$((ECHECS_PURGE + 1))
        fi
    fi
done
[ "$ECHECS_PURGE" -eq 0 ] \
    || echo "AVERTISSEMENT : $ECHECS_PURGE base(s) ancienne(s) non purgée(s), à nettoyer manuellement." >&2
if [ -n "$BASE_PRECEDENTE" ] && [ "$BASE_PRECEDENTE" != "$BASE_CIBLE" ]; then
    echo "Réserve N-1 : $BASE_PRECEDENTE (rollback = remettre EDITION_DB=$BASE_PRECEDENTE dans $FICHIER_ENV + recréer le conteneur API)."
fi

echo "Édition $EDITION_ID publiée (base active : $BASE_CIBLE)."
