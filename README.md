# Kuma Data Core

[![License: AGPL v3](https://img.shields.io/badge/License-AGPL_v3-blue.svg)](https://www.gnu.org/licenses/agpl-3.0)
[![CI](https://github.com/siba-IEE/kuma-data-core/actions/workflows/ci.yml/badge.svg)](https://github.com/siba-IEE/kuma-data-core/actions/workflows/ci.yml)
[![DOI](https://zenodo.org/badge/DOI/10.5281/zenodo.21117158.svg)](https://doi.org/10.5281/zenodo.21117158)

Moteur de données à confiance tracée : chaque valeur porte sa source, sa
méthode, son niveau de confiance (A/B/C), ses dates de validité et son
statut éditorial. Versionnement temporel non destructif, audit applicatif
par triggers. Base PostgreSQL, API FastAPI. Domaine pilote : la ressource
solaire en Guinée.

## Le problème

Dans une grande partie de l'Afrique francophone, dimensionner un projet
solaire revient à s'appuyer sur une moyenne nationale ou sur des produits
satellitaires qui divergent, sans vérité de terrain ni incertitude
documentée. Kuma Data Core traite la provenance, l'incertitude et le
statut éditorial comme des propriétés de première classe de la donnée, pas
comme des métadonnées optionnelles.

## Ce que fait le moteur

- **Schéma générique.** Localités, sources, unités, grandeurs, mesures,
  audit, versionnement : un socle unique. Un domaine (solaire, hydro, ...)
  est un axe de classification, pas une base séparée.
- **Confiance A/B/C.** A = validé au sol (terrain), B = satellite ou
  réanalyse, C = littérature. Le niveau est dérivé de règles explicites
  (R1-R4) et porté par chaque série.
- **Non destructif.** Aucune mise à jour en place : rotation temporelle
  (`valide_du` / `valide_au`). L'historique éditorial est conservé.
- **Audité.** Chaque écriture est tracée par des triggers PostgreSQL vers
  une table d'audit, avec l'identifiant applicatif de l'auteur.
- **Grandeurs calculées.** Des modules par grandeur (fraction diffuse,
  heures équivalentes pleines, POA, productible avec correction thermique,
  P50/P90, salissure, PR réaliste, ...) s'appuient sur des modèles publiés,
  avec leurs limites documentées.
- **API.** FastAPI (auth Bearer) : catalogue de séries, lecture,
  localités, grandeurs métier, données horaires validées par contrôle
  qualité.

## Les données

Le moteur est ici, sous licence AGPL. Les données guinéennes produites avec
lui sont publiées à part, en accès ouvert (CC-BY) avec DOI, dans le dépôt
**rds-guinee** : [github.com/siba-IEE/rds-guinee](https://github.com/siba-IEE/rds-guinee).
Toutes les sources amont sont ouvertes : NASA POWER, PVGIS/SARAH-3,
Copernicus (CAMS et ERA5-Land), stations sol ESMAP/WAPP.

## Attribution des données amont

Ce dépôt inclut des jeux de données seed dérivés (transformés) de sources
ouvertes. Leur redistribution est autorisée sous réserve des mentions
suivantes :

- **NASA POWER** (CC BY 4.0) : données du NASA Langley Research Center (LaRC)
  POWER Project, financé par le programme NASA Applied Sciences.
- **Copernicus / CAMS** (CC-BY) : « Contains modified Copernicus Atmosphere
  Monitoring Service information 2004-2023 » (radiation et aérosols EAC4).
- **Copernicus / ERA5-Land** (CC-BY) : « Contains modified Copernicus Climate
  Change Service information 2001-2025 ».
- **EUMETSAT CM SAF / SARAH-3**, via **PVGIS** : « © 2021-2023 EUMETSAT »,
  using data from EUMETSAT's Satellite Application Facility on Climate
  Monitoring (CM SAF) ; accès via PVGIS (Commission européenne, JRC), source
  JRC/PVGIS reconnue.
- **ESMAP / WAPP** (CC BY 4.0) : stations sol de Kankan et Tarambaly,
  energydata.info, World Bank Group / ESMAP (campagne « Solar Development in
  Sub-Saharan Africa », WAPP ; opérateur CSP Services).

Ni Copernicus, ni EUMETSAT / CM SAF, ni le JRC ne sauraient être tenus
responsables de l'usage fait de ces données transformées.

## Démarrage rapide

Pré-requis : Python 3.12, [uv](https://docs.astral.sh/uv/), Docker.

```bash
git clone https://github.com/siba-IEE/kuma-data-core.git
cd kuma-data-core
uv sync --group dev
cp docker/.env.example .env      # renseigner les mots de passe (champs changeme_*) et les clés API
docker compose -f docker/docker-compose.yml --env-file .env up -d
uv run alembic upgrade head
uv run uvicorn kuma_data_core.api.main:app --reload
```

L'API écoute sur `http://127.0.0.1:8000` (`/docs` en dev). Sous Windows, des
scripts PowerShell équivalents sont fournis (`scripts/services-start.ps1`,
`scripts/api-demarrer.ps1`). Détails d'environnement :
[docs/architecture/02-environnement-local.md](docs/architecture/02-environnement-local.md).

Génération des clés API de développement :

```bash
python -c "import secrets; print(f'kuma_dev_solar_{secrets.token_urlsafe(32)}')"
python -c "import secrets; print(f'kuma_dev_admin_{secrets.token_urlsafe(32)}')"
```

## API

Après authentification Bearer :

- `GET /v1/series` : catalogue paginé (filtres localité, grandeur, source).
- `GET /v1/series/{code}` : détail d'une série, mesures incluses (JSON ou CSV).
- `GET /v1/localites` : référentiel des localités.
- `GET /v1/grandeurs/...` : grandeurs métier calculées (POA, productible,
  P50/P90, salissure, PR réaliste, ...).
- `GET /v1/horaire/{localite}/{grandeur}` : séries horaires validées par
  contrôle qualité.

Référence complète :
[docs/architecture/06-api-reference-publique.md](docs/architecture/06-api-reference-publique.md).

## Stack

Python 3.12, PostgreSQL 16, FastAPI, SQLAlchemy 2.x, Alembic, Redis, Docker
Compose, uv, ruff, mypy, pytest. CI GitHub Actions (lint, types, tests
unitaires et d'intégration, contrôle de cohérence Alembic).

## Structure

| Chemin | Rôle |
|---|---|
| `src/kuma_data_core/db/` | Modèles SQLAlchemy, sessions, seeds de référentiels |
| `src/kuma_data_core/api/` | Application FastAPI (auth Bearer) |
| `src/kuma_data_core/services/grandeurs/` | Modules de calcul par grandeur |
| `src/kuma_data_core/ingestion/` | Ingestion des sources externes |
| `src/kuma_data_core/editorial/` | Statuts éditoriaux, confiance A/B/C, versionnement |
| `migrations/versions/` | Migrations Alembic |
| `tests/` | Tests unitaires, d'intégration, de régression |
| `docs/` | Architecture, conventions, méthodologie |

## Conventions et contribution

Le SQL et les identifiants métier sont en français. Toute évolution du
schéma passe par une migration Alembic. Détails dans
[docs/conventions/](docs/conventions/) et [CONTRIBUTING.md](CONTRIBUTING.md).

## Licence

Kuma Data Core est distribué sous licence **AGPL-3.0-or-later** (voir
[LICENSE](LICENSE)). Vous pouvez l'utiliser, l'étudier, le modifier et le
redistribuer ; exploité comme service en réseau, l'AGPL impose de publier
vos modifications sous la même licence.

Le projet est développé, opéré et soutenu par **Kuma Science**
([kumascience.com](https://kumascience.com)), qui propose par ailleurs des
services, une API hébergée et des jeux de données validés au sol. Pour un
usage sous d'autres termes, une licence commerciale est envisageable.

## Contact

Siba Kalivogui, Kuma Science.
