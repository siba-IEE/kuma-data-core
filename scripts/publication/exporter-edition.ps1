# =============================================================================
# exporter-edition.ps1
#
# Construit une édition publique du Core (ADR-0003, WP1) :
#
#   1. Vérifie l'environnement (Docker, .env, conteneur kuma-postgres).
#   2. Copie la base de référence vers une base d'édition intermédiaire
#      LOCALE (CREATE DATABASE ... TEMPLATE) - coupe d'abord les connexions
#      à la référence (fermer l'API locale avant d'exporter).
#   3. Applique le SQL de construction généré depuis le manifeste
#      (purge audit + tables exclues + assainissement) - aucune règle de
#      filtre n'est encodée ici, tout vient de publication/sql_edition.py.
#   4. Injecte les métadonnées d'édition (id daté, révision git).
#   5. Exécute la garde anti-fuite (bloc DO qui lève si purge incomplète).
#   6. pg_dump (format custom -Fc) vers out/publication/ + fichier JSON
#      de métadonnées (sha256, taille).
#   7. Supprime la base intermédiaire (sauf -ConserverBaseIntermediaire).
#
# Le VPS ne reçoit jamais rien à nettoyer : tout l'assainissement se fait
# ici, en local, avant le dump (ADR-0003, D5).
#
# Usage : .\scripts\publication\exporter-edition.ps1
#         [-BaseIntermediaire kuma_edition_build] [-ConserverBaseIntermediaire]
# =============================================================================

param(
    [string]$BaseIntermediaire = 'kuma_edition_build',
    [switch]$ConserverBaseIntermediaire
)

$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
# UTF-8 SANS BOM : ce script pipe du SQL vers psql via stdin, et l'encodeur
# UTF8 par défaut préfixerait chaque flux d'un BOM que psql rejette.
$OutputEncoding = [System.Text.UTF8Encoding]::new($false)

# Se replace à la racine du dépôt quel que soit le CWD de l'utilisateur.
$RepoRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
Set-Location $RepoRoot

$Conteneur = 'kuma-postgres'

# -----------------------------------------------------------------------------
# 1. Environnement : Docker, .env, conteneur.
# -----------------------------------------------------------------------------
Write-Host "Vérification de l'environnement..." -ForegroundColor Cyan

try {
    docker info --format '{{.ServerVersion}}' | Out-Null
    if ($LASTEXITCODE -ne 0) { throw "docker info a échoué (code $LASTEXITCODE)." }
} catch {
    Write-Host "Docker ne répond pas. Démarrez Docker Desktop puis réessayez." -ForegroundColor Red
    exit 1
}

$EnvFile = Join-Path $RepoRoot '.env'
if (-not (Test-Path $EnvFile)) {
    Write-Host "Fichier .env introuvable à la racine du dépôt." -ForegroundColor Red
    exit 1
}

# Lecture minimale du .env (clé=valeur, commentaires # ignorés).
$EnvVars = @{}
foreach ($ligne in Get-Content $EnvFile) {
    if ($ligne -match '^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)\s*$') {
        $EnvVars[$Matches[1]] = $Matches[2].Trim('"').Trim("'")
    }
}
foreach ($cle in @('POSTGRES_USER', 'POSTGRES_PASSWORD', 'POSTGRES_DB')) {
    if (-not $EnvVars.ContainsKey($cle)) {
        Write-Host "Variable $cle absente du .env." -ForegroundColor Red
        exit 1
    }
}
$PgUser = $EnvVars['POSTGRES_USER']
$PgPassword = $EnvVars['POSTGRES_PASSWORD']
$BaseReference = $EnvVars['POSTGRES_DB']

$EtatConteneur = docker inspect -f '{{.State.Running}}' $Conteneur 2>$null
if ($EtatConteneur -ne 'true') {
    Write-Host "Conteneur $Conteneur non démarré. Lancez .\scripts\services-start.ps1." -ForegroundColor Red
    exit 1
}
Write-Host "Environnement OK (référence : $BaseReference)." -ForegroundColor Green

# -----------------------------------------------------------------------------
# Helper : exécute du SQL (stdin) dans le conteneur, échoue au premier problème.
# -----------------------------------------------------------------------------
function Invoke-SqlEdition {
    param(
        [Parameter(Mandatory = $true)][string]$Base,
        [Parameter(Mandatory = $true)][string]$Sql,
        [Parameter(Mandatory = $true)][string]$Etiquette
    )
    $Sql | docker exec -i -e PGPASSWORD=$PgPassword $Conteneur `
        psql -v ON_ERROR_STOP=1 -q -U $PgUser -d $Base
    if ($LASTEXITCODE -ne 0) {
        Write-Host "Échec SQL ($Etiquette) sur $Base (code $LASTEXITCODE)." -ForegroundColor Red
        exit 1
    }
}

# -----------------------------------------------------------------------------
# 2. Identité de l'édition : date + révision git.
# -----------------------------------------------------------------------------
$Revision = (git rev-parse --short=12 HEAD).Trim()
if ($LASTEXITCODE -ne 0) {
    Write-Host "Impossible de lire la révision git." -ForegroundColor Red
    exit 1
}
$Sale = git status --porcelain
if ($Sale) {
    Write-Host "AVERTISSEMENT : working tree non propre - la révision $Revision ne décrit pas exactement l'état exporté." -ForegroundColor Yellow
}
$EditionId = "edition_$(Get-Date -Format yyyyMMdd)"
$DatePublication = Get-Date -Format yyyy-MM-dd
Write-Host "Édition : $EditionId (révision $Revision)." -ForegroundColor Cyan

# -----------------------------------------------------------------------------
# 3. Base d'édition intermédiaire : coupe les connexions à la référence,
#    recrée la copie depuis TEMPLATE (rapide, transactionnellement cohérente).
# -----------------------------------------------------------------------------
Write-Host "Construction de la base intermédiaire $BaseIntermediaire..." -ForegroundColor Cyan
$SqlPreparation = @"
SELECT pg_terminate_backend(pid) FROM pg_stat_activity
WHERE datname IN ('$BaseReference', '$BaseIntermediaire') AND pid <> pg_backend_pid();
DROP DATABASE IF EXISTS $BaseIntermediaire;
CREATE DATABASE $BaseIntermediaire TEMPLATE $BaseReference;
"@
Invoke-SqlEdition -Base 'postgres' -Sql $SqlPreparation -Etiquette 'copie de la référence'

# -----------------------------------------------------------------------------
# 4. Filtre de publication : SQL généré depuis le manifeste, jamais écrit ici.
# -----------------------------------------------------------------------------
Write-Host "Application du filtre de publication (manifeste)..." -ForegroundColor Cyan
$SqlConstruction = uv run python -m kuma_data_core.publication.sql_edition construction | Out-String
if ($LASTEXITCODE -ne 0) {
    Write-Host "Échec de la génération du SQL de construction." -ForegroundColor Red
    exit 1
}
Invoke-SqlEdition -Base $BaseIntermediaire -Sql $SqlConstruction -Etiquette 'construction'

Write-Host "Injection des métadonnées d'édition..." -ForegroundColor Cyan
$SqlMetadonnees = uv run python -m kuma_data_core.publication.sql_edition metadonnees `
    --edition-id $EditionId --date-publication $DatePublication --revision-source $Revision | Out-String
if ($LASTEXITCODE -ne 0) {
    Write-Host "Échec de la génération du SQL de métadonnées." -ForegroundColor Red
    exit 1
}
Invoke-SqlEdition -Base $BaseIntermediaire -Sql $SqlMetadonnees -Etiquette 'métadonnées'

Write-Host "Garde anti-fuite..." -ForegroundColor Cyan
$SqlControles = uv run python -m kuma_data_core.publication.sql_edition controles | Out-String
if ($LASTEXITCODE -ne 0) {
    Write-Host "Échec de la génération du SQL de contrôles." -ForegroundColor Red
    exit 1
}
Invoke-SqlEdition -Base $BaseIntermediaire -Sql $SqlControles -Etiquette 'garde anti-fuite'
Write-Host "Garde anti-fuite : OK." -ForegroundColor Green

# -----------------------------------------------------------------------------
# 5. Dump : pg_dump -Fc dans le conteneur, puis docker cp (jamais de
#    redirection PowerShell sur un flux binaire : elle le corromprait).
# -----------------------------------------------------------------------------
$RepertoireSortie = Join-Path $RepoRoot 'out/publication'
New-Item -ItemType Directory -Force $RepertoireSortie | Out-Null
$NomDump = "${EditionId}_$Revision.dump"
$CheminDump = Join-Path $RepertoireSortie $NomDump
$DumpConteneur = "/tmp/$NomDump"

Write-Host "pg_dump de $BaseIntermediaire..." -ForegroundColor Cyan
docker exec -e PGPASSWORD=$PgPassword $Conteneur `
    pg_dump -U $PgUser -Fc -d $BaseIntermediaire -f $DumpConteneur
if ($LASTEXITCODE -ne 0) {
    Write-Host "Échec de pg_dump (code $LASTEXITCODE)." -ForegroundColor Red
    exit 1
}
docker cp "${Conteneur}:$DumpConteneur" $CheminDump | Out-Null
if ($LASTEXITCODE -ne 0) {
    Write-Host "Échec de docker cp." -ForegroundColor Red
    exit 1
}
docker exec $Conteneur rm $DumpConteneur | Out-Null

# Métadonnées d'export : le fichier compagnon que WP2 vérifiera côté VPS.
$Sha256 = (Get-FileHash -Algorithm SHA256 $CheminDump).Hash.ToLower()
$TailleOctets = (Get-Item $CheminDump).Length
$Metadonnees = [ordered]@{
    edition_id       = $EditionId
    date_publication = $DatePublication
    revision_source  = $Revision
    fichier          = $NomDump
    sha256           = $Sha256
    taille_octets    = $TailleOctets
}
$CheminJson = Join-Path $RepertoireSortie "${EditionId}_$Revision.json"
$Metadonnees | ConvertTo-Json | Out-File -Encoding utf8 $CheminJson

# -----------------------------------------------------------------------------
# 6. Nettoyage de la base intermédiaire.
# -----------------------------------------------------------------------------
if (-not $ConserverBaseIntermediaire) {
    Invoke-SqlEdition -Base 'postgres' `
        -Sql "DROP DATABASE IF EXISTS $BaseIntermediaire;" -Etiquette 'nettoyage'
} else {
    Write-Host "Base intermédiaire $BaseIntermediaire conservée (inspection)." -ForegroundColor Yellow
}

Write-Host ""
Write-Host "Édition exportée." -ForegroundColor Green
Write-Host "  Dump        : $CheminDump ($([math]::Round($TailleOctets / 1MB, 1)) Mo)"
Write-Host "  Métadonnées : $CheminJson"
Write-Host "  SHA-256     : $Sha256"
Write-Host "Prochaine étape : transfert vers le VPS puis publier-edition.sh (WP2)."
