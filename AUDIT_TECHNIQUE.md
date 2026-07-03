# Audit Technique : Kuma Data Core

## 1. Synthèse de l'audit
Kuma Data Core est un moteur de données à "confiance tracée" extrêmement bien structuré. L'architecture repose sur une stack Python moderne (3.12, FastAPI, SQLAlchemy 2.0) et une doctrine de gestion de la donnée rigoureuse (versionnement temporel, audit systématique). Le dépôt présente un haut niveau de maturité technique, avec une couverture de tests significative et une documentation d'architecture exemplaire.

## 2. Analyse SWOT

### 🟢 Forces (Strengths)
- **Qualité du Code** : Utilisation de `mypy` (strict), `ruff`, et `pydantic v2`. Le code est lisible, bien typé et suit des conventions de nommage claires (`docs/conventions/01-naming.md`).
- **Traçabilité & Audit** : Le système d'audit par triggers PostgreSQL est "inviolable" depuis l'applicatif, capturant les snapshots JSONB avant/après.
- **Robustesse des Tests** : Présence de tests unitaires et d'intégration. Le "mode offline" pour l'ingestion (NASA POWER, SARAH-3) permet des tests déterministes et rapides en CI sans dépendance réseau.
- **Architecture de Données** : Utilisation experte des contraintes PostgreSQL (EXCLUDE BTree-GiST pour le versionnement temporel, CHECK constraints pour les énumérations).
- **Isolation de la Logique Métier** : Les modules de calcul (`services/grandeurs/`) sont purs et testables unitairement, isolés des entrées/sorties SQL.

### 🟡 Faiblesses (Weaknesses)
- **Gestion des Secrets** : Les clés API sont encore gérées par variables d'environnement. Bien que sécurisé, cela limite la flexibilité (révocation, quotas par utilisateur). *Note : La migration vers une table `cles_api` est déjà initiée/planifiée.*
- **Couplage Ingestion/Migrations** : L'ingestion initiale des données est portée par des migrations Alembic (seeds), ce qui peut ralentir le cycle de vie du schéma sur de gros volumes.
- **Table d'Audit Monolithique** : La table `audit_log` croît indéfiniment sans stratégie de partitionnement native pour l'instant.

### 🔵 Opportunités (Opportunities)
- **Généricité Multi-pays (Jalon 2)** : Le schéma est déjà agnostique du pays. Le découplage de l'ingestion permettra d'intégrer de nouveaux RDS (Référentiels de Données Solaires) sans toucher au Core.
- **Contrat OpenAPI** : Possibilité d'unifier davantage les types de retour pour une génération de documentation client (TypeScript/Zod) encore plus fluide.

### 🔴 Risques (Threats)
- **Performance de l'Audit** : À très haut volume d'écriture (ex: ingestion horaire massive sur 100+ villes), les triggers d'audit pourraient induire une latence.
- **Dépendances Amont** : La dépendance aux API tierces (NASA, PVGIS) est gérée par des retries, mais reste un point de fragilité pour le service "passe-plat".

---

## 3. Analyse détaillée par domaine

### 🏗️ Base de Données & Modèle
L'utilisation de SQLAlchemy 2.0 avec le typage `Mapped` est impeccable.
- **Versioning** : Le pattern `valide_du` / `valide_au` avec contrainte d'exclusion garantit l'intégrité temporelle (pas de recouvrement de lignes pour une même mesure).
- **Audit** : La fonction PL/pgSQL `kuma_log_audit()` est générique et performante. Elle respecte la convention de PK `id` obligatoire.

### 🧪 Logique Métier (Services)
Les grandeurs calculées (`hep`, `humidex`, `poa_parametrable`, `pr_realiste`) suivent une politique de complétude stricte.
- **Fiabilité numérique** : Les divisions par zéro sont évitées (`max(abs(v_seed), 1e-9)`), et les valeurs sont clampées physiquement quand nécessaire.
- **Modèles** : L'intégration de `pvlib` pour les calculs solaires (Perez, HSU) est faite dans les règles de l'art.

### 🌐 Couche API (FastAPI)
L'authentification par clé API est robuste (`secrets.compare_digest`).
- **Gestion des Erreurs** : Les exceptions sont centralisées (`ExceptionKuma`) et mappées vers des codes d'erreur stables (`CodeErreur`), assurant un contrat stable avec les consommateurs.
- **Validation** : Les `model_validator` Pydantic assurent la cohérence des paramètres (ex: `periode_fin >= periode_debut`).

---

## 4. Recommandations (Focus Jalon 4 - Robustesse)

### Priorité Haute 🚨
1. **Migration Clés API** : Finaliser le passage à la table `cles_api` pour permettre le self-service et la gestion fine des quotas (WP6/WP7).
2. **Découplage des Seeds** : Extraire l'ingestion massive des migrations Alembic. Utiliser un loader dédié qui consomme les fonctions de la couche `ingestion/` avec une session SQLAlchemy.

### Priorité Moyenne 🟠
3. **Partitionnement Audit** : Implémenter un partitionnement déclaratif (par mois ou année) sur la table `audit_log.horodatage` pour prévenir la dégradation des performances.
4. **Typage OpenAPI** : Remplacer les retours `Response` par des types Pydantic explicites dans tous les routeurs pour enrichir le `openapi.json` (notamment pour les formats CSV).

### Priorité Basse 🟢
5. **Logs de Performance** : Ajouter des traces sur le temps d'exécution des triggers d'audit lors des bulk inserts.
6. **Documentation des Modèles** : Compléter les `COMMENT ON TABLE / COLUMN` manquants pour une auto-documentation parfaite via les outils de DB (type SchemaSpy).

---

## 5. Conclusion
Le dépôt **Kuma Data Core** est une réalisation de haute qualité, exemplaire dans sa rigueur académique et logicielle. La dette technique est consciemment suivie (cf. ROADMAP et commentaires `D-xx`). Une fois le jalon 4 atteint, le moteur sera prêt pour une montée en charge significative et une ouverture multi-pays sans friction.
