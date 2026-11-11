# Généricité pays

Note d'architecture à l'intention des contributeurs : **le pays est une donnée,
pas une constante.** Le moteur ne reçoit aucun profil de pays, ni codé ni
configuré : il lit le pays, le fuseau et les localités dans la base. La Guinée
est le pays pilote ; ses données occupent ce dépôt, elles ne sont pas câblées
dans le moteur.

## Le pays est un niveau de la hiérarchie

Les localités forment une hiérarchie à sept niveaux :

`continent`, `region_supranationale`, `pays`, `region_administrative`,
`prefecture`, `commune`, `site`.

Un pays est une localité de type `pays`. Une localité porte le code `pays_iso3`
de son pays (ISO 3166-1 alpha-3), son fuseau horaire (nom IANA) et un code
métier de la forme `<code_pays>_<slug>` (par exemple `gin_conakry`). La
cohérence parent-enfant est validée côté base.

## Ce que le moteur lit dans la base

- **Le préfixe d'un code court.** `/v1/horaire/{localite}/{grandeur}` accepte
  un code sans son préfixe de pays. Le préfixe est cherché parmi les codes des
  localités de type `pays` ; un code court porté par des localités de plusieurs
  pays est refusé (404, avec la liste des codes complets).
- **Le jour local.** Les grandeurs calculées par intégration horaire
  (`methode=integration_horaire`) bornent leur fenêtre, regroupent les heures
  et propagent la confiance par jour du fuseau de la localité. La capsule
  (`/v1/etudes/capsule`) exprime les mois et les heures de sa séquence horaire
  dans ce fuseau. Une localité sans fuseau est lue en UTC.
  `/v1/horaire/{localite}/{grandeur}` reste en UTC : c'est son contrat.
- **Les localités d'une même cellule.** `/v1/grandeurs/ghi_exceedance` nomme
  les localités dont la série GHI mensuelle est identique à celle de la
  localité demandée. Elles sont reconnues à leurs données, pas à une liste.

## Ce qu'un nouveau pays branche

Le socle est partagé : sources, grandeurs, unités, confiance, statut,
versionnement, audit. Ajouter un pays revient à :

1. créer ses localités (la racine pays, puis ses descendants, avec leur
   fuseau) ;
2. rattacher ses séries et ses mesures aux sources et aux grandeurs du
   référentiel ;
3. laisser la machinerie de confiance et de statut s'appliquer telle quelle.

Ni migration de schéma ni changement de code ne sont nécessaires.

## La preuve : un pays fictif

[`tests/integration/api/test_pays_fictif.py`](../../tests/integration/api/test_pays_fictif.py)
crée un pays fictif (code `zzf`, fuseau à UTC+1) par de simples insertions,
dans une transaction annulée en fin de test, et le relit par l'API. Il
vérifie :

- la liste et le détail de ses localités, avec leur fuseau, et de ses séries
  journalière et mensuelle ;
- le code court d'une de ses localités, et le refus d'un code court qu'il
  partage avec une commune guinéenne ;
- des degrés-jours horaires comptés au jour local, là où le jour UTC donnerait
  un autre résultat ;
- deux localités de même cellule nommées l'une à l'autre par `ghi_exceedance`,
  sans effet sur une localité guinéenne ;
- la résolution d'un point et la capsule, en heures locales.

Ce test répond à
l'[issue #6](https://github.com/siba-IEE/kuma-data-core/issues/6). Il porte sur
un fuseau sans heure d'été.

## Ce qui reste propre à l'instance Guinée

Ce dépôt porte le moteur et l'instance du pays pilote. Restent guinéens :

- les données : les seeds (`src/kuma_data_core/db/seeds/`) et les migrations
  de données (`migrations/`) ;
- les sondes d'ingestion `src/kuma_data_core/ingestion/canari_*.py`, dont les
  listes de localités sont guinéennes ;
- deux constantes du moteur : la fenêtre d'années de l'atlas d'incertitude
  (`api/v1/grandeurs/incertitude.py`) et le rang spatial, défini sur six
  villes (`services/grandeurs/referentiels.py`) ;
- l'inclinaison fixe du proxy de salissure, choisie proche de la latitude de
  la Guinée (`services/grandeurs/soiling_hsu.py`) ;
- dans les fiches de contribution (`api/v1/schemas/contributions.py`), la
  monnaie `GNF` de la liste fermée des monnaies et le format du code de
  sous-préfecture, celui des codes guinéens ;
- la colonne facultative `localites.code_administratif_national`, au format
  de la codification guinéenne (trois majuscules) ;
- les commentaires du catalogue de la base (tables et colonnes), qui citent
  des exemples guinéens.

## Un produit-données par pays

Les données nationales sont publiées dans un dépôt RDS par pays
([rds-guinee](https://github.com/siba-IEE/rds-guinee), puis d'autres). Le Core
est le moteur commun ; chaque RDS est un produit éditorial. Le pont qui verse un
RDS national dans le Core est en construction (voir la [feuille de
route](../../ROADMAP.md)).

Pour contribuer les données ou une station de votre pays, voir
[amener son pays ou sa station](pays-et-terrain.md).
