# ADR-0009 : couches du moteur et sens des dépendances

Date : 2026-11-11. Statut : accepté.

## Contexte

Trois couplages rendaient le moteur difficile à faire évoluer et à reprendre
pour un autre pays.

- Les modules de calcul importaient les schémas de requête et de réponse de
  l'API : le calcul d'une grandeur ne se concevait pas sans le contrat HTTP
  `v1`.
- Les routes portaient le SQL : 38 requêtes dans sept fichiers, dont un de
  2 100 lignes. La même lecture était écrite à plusieurs endroits, avec des
  règles différentes sur les lignes à retenir, sans que l'écart se voie.
- 50 migrations sur 121 importent des fonctions de `src/`. Rejouer la chaîne
  exécute donc le code d'aujourd'hui, pas celui du jour où la migration a été
  écrite.

## Décision

1. **Le paquet est découpé en couches, et chaque couche ne peut importer que
   celles que la table lui accorde.**

   | Couche | Rôle | Peut importer |
   |---|---|---|
   | `core` | configuration, journalisation | rien |
   | `exceptions` | erreurs du domaine | rien |
   | `db` | modèles, sessions, seeds | `core` |
   | `editorial` | statuts, confiance, versionnement | `db`, `exceptions` |
   | `external` | clients des sources amont | `exceptions` |
   | `lecture` | SQL de lecture | `editorial` |
   | `publication` | manifeste de l'édition publique | rien |
   | `ingestion` | chargement des sources | `db`, `editorial`, `exceptions`, `external` |
   | `services` | calculs et cas d'usage | `core`, `db`, `editorial`, `exceptions`, `external` |
   | `api` | routes, schémas, erreurs HTTP | toutes les autres |

   Une flèche absente est interdite. En ajouter une se décide, et se fait en
   modifiant la table du test qui la vérifie.

2. **Les routes ne contiennent pas de SQL.** Les lectures vivent dans
   `lecture`, qui ignore HTTP et les schémas de réponse : une lecture qui ne
   trouve rien rend `None` ou une liste vide, et la route choisit le code
   d'erreur et le message.

3. **Chaque règle sur les lignes à retenir a une seule définition, nommée.**
   Les lecteurs disent laquelle ils appliquent : version en vigueur
   (`valide_au IS NULL`), version en vigueur de statut validé
   (`STATUTS_VALIDES`), ou vue des valeurs de grandeur en vigueur.

4. **Un calcul déclare ce qu'il lit.** Chaque calcul paramétrable nomme, dans
   un `Protocol`, les grandeurs physiques dont il a besoin ; les schémas de
   requête de l'API le satisfont sans en hériter. Les types que les calculs
   construisent sont définis avec eux, et l'API les reprend.

5. **Une migration n'importe pas le moteur.** À partir de la révision 122,
   une migration ne dépend que d'Alembic, de SQLAlchemy et de ses données
   compagnes (`migrations/donnees/`). Elle refait ainsi la même chose à chaque
   rejeu, quel que soit l'état du code.

Ces règles sont vérifiées par `tests/unit/test_architecture.py`.

## Hors périmètre

- **Les règles de sélection ne sont pas unifiées.** Les lectures journalières
  et mensuelles servent toute version en vigueur ; les lectures horaires ne
  servent que le validé ; l'atlas lit `grandeurs_metier` sans passer par la
  vue ; les calculs de grandeurs stockées écartent `deprecie` ; la capsule ne
  lit, en horaire, que `valide_auto`. Les nommer rend le choix visible ; le
  faire reste à décider.
- **Du SQL reste dans `services`** : calculs de grandeurs stockées, capsule,
  contrôle qualité horaire. Plusieurs de ces fonctions sont rejouées par des
  migrations antérieures et ne peuvent pas changer de signature.
- **L'enchaînement lecture, calcul, réponse reste dans les routes** des
  grandeurs paramétrables, avec son squelette répété d'une route à l'autre.
- **Les migrations antérieures à 122** gardent leurs imports jusqu'à ce que
  l'historique soit regroupé en une migration de base.
