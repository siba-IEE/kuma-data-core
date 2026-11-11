# Contribuer à Kuma Data Core

Merci de votre intérêt. Ce dépôt est le moteur ; les données guinéennes
vivent dans [rds-guinee](https://github.com/siba-IEE/rds-guinee).

## Par où commencer

La [feuille de route](ROADMAP.md) décrit la direction. Les issues ouvertes
sont la tranche actionnable, classées par profil de contributeur :

- `pour:dev` : le moteur (API, schéma, ingestion, connecteurs).
- `pour:chercheur` : la méthode (contrôle qualité, incertitude, grille de
  confiance, calage terrain).
- `pour:institution` : la donnée et le terrain (RDS national, validation au sol).

Pour comprendre le modèle avant de contribuer, voir les guides dans
[docs/contribution/](docs/contribution/) : le [modèle de
données](docs/contribution/donnees.md), la [confiance et le statut
éditorial](docs/contribution/confiance-et-statuts.md), la [généricité
pays](docs/contribution/genericite-pays.md), et [amener son pays ou sa
station](docs/contribution/pays-et-terrain.md).

Pour une première contribution, cherchez le label `good first issue` : ces
issues précisent les fichiers concernés, le critère d'acceptation et le piège
connu.

Les labels et les issues sont en français, par cohérence avec le code et l'API
(le SQL et le domaine métier sont en français ; voir
[docs/conventions/01-naming.md](docs/conventions/01-naming.md)). Seuls les
labels d'accueil `good first issue` et `help wanted` gardent leur nom anglais,
que la plateforme reconnaît.

## Mise en place

Voir le démarrage rapide du [README](README.md). En résumé :
`uv sync --group dev`, services Docker, `uv run alembic upgrade head`.

## Avant d'ouvrir une pull request

Tout doit passer localement :

```bash
uv run ruff check . && uv run ruff format --check .
uv run mypy src
uv run pytest -m unit
uv run pytest -m "integration and not regression"
```

Si vous touchez au schéma : ajoutez une migration Alembic, puis vérifiez
`uv run alembic upgrade head` et `uv run alembic check`. Une migration
mergée est immuable ; toute correction passe par une nouvelle migration.

`pre-commit` est configuré (ruff, gitleaks, ...) :
`uv run pre-commit run --all-files`.

## Conventions

- SQL et identifiants métier en français ; technique en anglais. Voir
  [docs/conventions/01-naming.md](docs/conventions/01-naming.md).
- Clé primaire `id` sur toute table auditée, catégoriels en
  `VARCHAR + CHECK`, soft delete, colonnes d'audit. Voir
  [docs/conventions/](docs/conventions/).
- Chaque donnée porte source, méthode, confiance (A/B/C), validité et
  statut éditorial. La confiance A est réservée aux données validées au
  sol.
- Pas de mise à jour destructive : versionnement temporel.
- Le paquet est découpé en couches (`api`, `services`, `lecture`, `db`…) et
  chaque couche n'importe que celles qui lui sont permises ; les routes ne
  contiennent pas de SQL. Voir
  [ADR-0009](docs/decisions/0009-couches-et-sens-des-dependances.md).

## Style

Commits atomiques, message à l'impératif. Le code se lit comme le code
alentour : mêmes idiomes, pas de remplissage.

### Commentaires et docstrings

- Un commentaire dit pourquoi (contrainte non évidente, piège, référence à
  une source ou une norme), pas ce que fait le code.
- Docstring d'une ligne par défaut ; trois à cinq lignes quand le contrat
  n'est pas évident (unités, invariants, exceptions levées). Plus long
  seulement pour un texte servi (docstrings de routes et de modèles Pydantic,
  qui alimentent l'OpenAPI) ou un module dont la méthode scientifique doit
  être énoncée (formule et référence bibliographique).
- Pas d'historique du projet : ni phase, lot, étape, identifiant de dette,
  numéro de pull request ou de migration, ni récit de revue. Cela relève de
  l'historique git, du CHANGELOG et des décisions d'architecture.
- Pas de paraphrase des annotations de type, pas de bloc `Args:` /
  `Returns:` qui ne fait que répéter noms et types.
- À garder : références scientifiques, unités, conventions de signe, raison
  d'une valeur numérique.

### Textes servis

Ce qui sort de l'API (descriptions de routes et de champs, messages
d'erreur, mises en garde du champ `limite`) s'adresse à un utilisateur
extérieur : pas de code interne, pas de renvoi à un document de travail,
pas de décompte figé. Un test balaie le document OpenAPI et refuse ce
vocabulaire.

Les migrations mergées restent immuables : ces règles valent pour `src/`,
`tests/` et le code neuf.

## Accord de licence de contribution (CLA)

Toute contribution est soumise à l'[accord de licence de contribution
(CLA)](CLA.md). Vous conservez le droit d'auteur sur votre contribution ;
vous accordez au projet une licence large (incluant la double licence),
ce qui lui permet de rester distribuable et re-licenciable de façon
cohérente. La signature se fait une seule fois, à votre première pull
request : un robot (CLA Assistant) vous invite à confirmer votre accord et
bloque le merge tant que ce n'est pas fait.

## Données et licence

N'ajoutez aucun secret ni donnée personnelle ; les jeux de test sont
synthétiques ou issus de sources publiques ouvertes. Le code est distribué
sous AGPL-3.0-or-later (voir [LICENSE](LICENSE) et [NOTICE](NOTICE)) ;
l'attribution des données amont figure dans le [README](README.md).

## Signaler un problème

Bugs et propositions via les issues GitHub. Pour une faille de sécurité,
voir [SECURITY.md](SECURITY.md).
