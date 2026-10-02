# ADR-0005 : licences SolClim-3 et bail signé

Date : 2026-10-01. Statut : accepté.

## Contexte

SolClim-3 (Solar Bridge) travaille en grande partie hors ligne : les
340 sous-préfectures de la base intégrée, les moteurs et les rapports
n'appellent pas le serveur. Jusqu'ici, rien ne bornait son usage :

- une clé d'API publique, obtenue en libre-service par `POST /v1/cles`,
  ouvrait aussi les fonctions en ligne du logiciel ;
- une copie installée fonctionnait indéfiniment, sans clé, sur la base
  intégrée ;
- on ne pouvait pas retirer l'accès à une personne sans toucher aux
  autres (la clé d'environnement `API_CLE_SOLAR_BRIDGE` est partagée).

Le logiciel doit rester utilisable sur le terrain sans réseau pendant
des semaines, et l'accès doit pouvoir être retiré à une personne.

## Décision

1. **Une licence par personne**, table `licences_solclim` dans la base
   de service `kuma_api_meta`, à côté de `cles_api` (hors lignée
   Alembic, comme elle : état du serveur, pas donnée d'édition). Une
   licence rattache une clé à un titulaire et à son organisation, avec
   un terme facultatif. Une seule licence active par clé. Une clé
   d'API publique seule n'ouvre pas SolClim-3.
2. **Un bail signé** : `POST /v1/licence/bail` remet à une clé porteuse
   d'une licence active un bail Ed25519 de 30 jours (configurable),
   plafonné par le terme de la licence, portant titulaire,
   organisation, préfixe de clé, émission, fin et version minimale du
   logiciel. La graine privée (`LICENCE_CLE_SIGNATURE`) ne quitte pas
   le serveur ; la clé publique est embarquée dans le logiciel et le
   service de calage, qui vérifient sans appeler le serveur.
3. **Côté logiciel** (dépôt `kuma-bridges`) : le bail est renouvelé à
   chaque connexion ; à son terme, ou sous la version minimale, le
   logiciel passe en **lecture seule** (les études se rouvrent et se
   consultent, sans calcul ni rapport ni enregistrement).
4. **Administration** par l'outil en ligne de commande
   `python -m kuma_data_core.services.licences` (accorder, lister,
   prolonger, retirer), lancé sur le serveur. Pas d'endpoint
   d'administration : aucune surface publique de plus.
5. **Retirer ≠ révoquer** : retirer la licence ôte SolClim-3 et laisse
   l'API publique ; révoquer la clé (`DELETE /v1/cles/{prefixe}`) coupe
   tout. Dans les deux cas, le bail n'est plus renouvelé : l'accès en
   ligne cesse aussitôt, le logiciel passe en lecture seule au plus
   tard au terme du bail en cours (30 jours).

## Conséquences

- La clé partagée `API_CLE_SOLAR_BRIDGE` n'obtient pas de bail ; elle
  peut être retirée de l'environnement de production.
- Délai de révocation hors ligne : au plus la durée du bail. C'est le
  prix du travail sans réseau, choisi à 30 jours.
- Changer de paire de signature invalide tous les baux en circulation
  à leur prochaine vérification.
- Limite assumée : un logiciel de bureau peut toujours être forcé par
  quelqu'un de déterminé. Le bail arrête l'usage ordinaire et rend la
  révocation effective ; la licence d'utilisation écrite le complète.

## Hors périmètre

Chiffrement de la base intégrée du logiciel, interface web
d'administration, quotas propres aux licences.
