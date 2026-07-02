#!/usr/bin/env bash
# =============================================================================
# durcir-vps.sh
#
# Durcissement système d'un VPS Ubuntu/Debian fraîchement provisionné, AVANT
# tout déploiement de l'API (ADR-0003, WP8). À exécuter une fois, en root,
# sur le serveur nu. Idempotent : rejouable sans dégât.
#
# Ce script pose le socle machine ; le déploiement applicatif (Docker Compose
# prod, provisionner-serveur.sh, publier-edition.sh) vient ensuite.
#
# Principe : le VPS ne détient rien de non-reconstructible (ADR-0003 D1). Ce
# durcissement ne protège pas des données irremplaçables - il n'y en a pas -
# mais réduit la surface d'attaque et coupe les portes d'entrée classiques.
#
# CE QUE CE SCRIPT NE FAIT PAS (à faire à la main, décisions humaines) :
#   - Créer l'utilisateur admin et déposer sa clé SSH publique (fais-le
#     AVANT de couper l'accès root/mot de passe, sinon tu te verrouilles).
#   - Choisir le port SSH (paramètre PORT_SSH ci-dessous).
#
# Usage : PORT_SSH=2222 ADMIN_USER=siba bash durcir-vps.sh
# =============================================================================

set -euo pipefail

PORT_SSH="${PORT_SSH:-22}"
ADMIN_USER="${ADMIN_USER:-}"

[ "$(id -u)" -eq 0 ] || { echo "ERREUR : exécuter en root." >&2; exit 1; }

echo "== 1. Mises à jour système + upgrades automatiques =="
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get upgrade -y -qq
apt-get install -y -qq unattended-upgrades fail2ban ufw
# Applique automatiquement les correctifs de sécurité.
dpkg-reconfigure -f noninteractive unattended-upgrades

echo "== 2. Pare-feu UFW : tout fermé sauf SSH + HTTP/HTTPS =="
# PostgreSQL (5432) et Redis (6379) ne sont JAMAIS ouverts : ils ne vivent
# que sur le réseau Docker interne. C'est la barrière système en plus du
# non-mapping de ports du compose prod.
ufw --force reset
ufw default deny incoming
ufw default allow outgoing
ufw allow "${PORT_SSH}"/tcp comment 'SSH'
ufw allow 80/tcp comment 'HTTP (redirige vers HTTPS via Caddy)'
ufw allow 443/tcp comment 'HTTPS'
ufw --force enable
ufw status verbose

echo "== 3. Durcissement SSH =="
# Sécurités : root non connectable, mot de passe désactivé (clé seulement).
# NE PAS exécuter cette partie sans avoir vérifié qu'un utilisateur non-root
# avec clé SSH fonctionne déjà, sous peine de verrouillage.
if [ -n "$ADMIN_USER" ] && id "$ADMIN_USER" >/dev/null 2>&1; then
    # Préfixe 00- pour être lu AVANT le 50-cloud-init.conf des images cloud :
    # sshd retient la PREMIÈRE valeur de chaque paramètre, donc notre
    # PasswordAuthentication no doit primer sur le PasswordAuthentication yes
    # que cloud-init pose (sinon le mot de passe reste activé, cf. go-live
    # 2026-07-02 où un fichier 99- arrivait trop tard).
    CONF=/etc/ssh/sshd_config.d/00-kuma-durcissement.conf
    cat > "$CONF" <<EOF
Port ${PORT_SSH}
PermitRootLogin no
PasswordAuthentication no
KbdInteractiveAuthentication no
PubkeyAuthentication yes
X11Forwarding no
AllowUsers ${ADMIN_USER}
EOF
    sshd -t && systemctl reload ssh
    echo "SSH durci (port ${PORT_SSH}, root off, mot de passe off, AllowUsers ${ADMIN_USER})."
else
    echo "ATTENTION : ADMIN_USER absent ou inexistant -> durcissement SSH NON appliqué."
    echo "Crée l'utilisateur, dépose sa clé publique, teste la connexion, puis relance."
fi

echo "== 4. fail2ban (protection anti-bruteforce SSH) =="
systemctl enable --now fail2ban

echo "== 5. Docker (moteur d'exécution de l'API) =="
if ! command -v docker >/dev/null 2>&1; then
    curl -fsSL https://get.docker.com | sh
    if [ -n "$ADMIN_USER" ] && id "$ADMIN_USER" >/dev/null 2>&1; then
        usermod -aG docker "$ADMIN_USER"
    fi
fi
systemctl enable --now docker

echo ""
echo "Durcissement terminé."
echo "Rappels avant déploiement :"
echo "  - Vérifie la connexion SSH par clé sur le port ${PORT_SSH} AVANT de fermer ta session."
echo "  - Configure un ping externe (UptimeRobot) sur https://<domaine>/v1/health."
echo "  - Les pg_dump de la base LOCALE (la référence) doivent partir hors du VPS."
echo "  - Déploiement : docker compose -f docker/docker-compose.prod.yml up -d,"
echo "    puis provisionner-serveur.sh, python -m kuma_data_core.db.meta, publier-edition.sh."
