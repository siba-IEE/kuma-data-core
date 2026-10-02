# ADR-0006 : contributions d'études SolClim-3

Date : 2026-10-02. Statut : accepté.

## Contexte

Les études faites dans SolClim-3 portent ce que les bases publiques
n'ont pas : les appareils qu'un ménage déclare, les prix que les
installateurs pratiquent en Guinée, le matériel retenu et ce que le
calcul en tire. Recueillies, elles nourrissent les profils de
consommation, l'observatoire des prix et le calage du moteur.

Une étude appartient pourtant à son auteur, et souvent à son client :
on ne la recueille ni à son insu, ni avec ce qui identifie une personne
ou un lieu précis.

## Décision

1. **Une fiche par étude**, distincte du fichier de l'étude : le
   logiciel la construit à l'enregistrement. Elle porte la version du
   logiciel et le jour, le lieu, les panneaux, le mode de la ressource,
   les appareils, le système, les prix saisis et, si le calcul a été
   lancé, ses valeurs de synthèse. Elle ne porte **ni le nom de
   l'étude, ni celui de la localité, ni le chemin du fichier, ni les
   séries horaires**.
2. **Le lieu situe sans identifier** : la sous-préfecture choisie dans
   la base (son code), ou, pour un point saisi à la main, ses
   coordonnées **arrondies à 0,1°** (environ 11 km). Le serveur
   arrondit de nouveau, quoi que le client envoie.
3. **Le contrat est fermé** : la fiche est validée strictement, un champ
   que le contrat ne nomme pas est refusé (422). Une version du logiciel
   qui enverrait plus que convenu échoue au lieu de fuir. Le nom d'un
   appareil, texte libre, est coupé à 40 caractères.
4. **Partage par défaut, annoncé, réversible** : la clause est acceptée
   à l'activation ; une étude cochée « confidentielle » ne part pas, et
   une fiche déjà partagée se retire. L'utilisateur peut voir la fiche
   exacte avant qu'elle parte.
5. **Une ligne par étude et par clé** (`contributions_etudes`, base de
   service, hors lignée Alembic) : chaque envoi remplace la fiche
   précédente. L'identifiant de l'étude est aléatoire (UUID), tiré par
   le logiciel ; l'unicité par clé interdit à quiconque de remplacer la
   fiche d'un autre.
6. **Routes** : `POST /v1/contributions/{etude_uid}` dépose ou remplace
   (clé porteuse d'une licence active, comme le bail) ;
   `POST /v1/contributions/{etude_uid}/retrait` retire (la clé suffit :
   le retrait reste possible après la fin de la licence). Les deux sont
   en `POST`, la seule méthode d'écriture que le CORS ouvre aux vues web.
7. **La source reste interne** : la fiche est rattachée à la clé qui l'a
   déposée, pour qualifier une donnée ou écarter une source douteuse.
   L'export d'administration
   (`python -m kuma_data_core.services.contributions exporter`) remplace
   la clé par un numéro de contributeur ; aucune donnée publiée ne la
   porte.

## Formats

- `pv-autonome@1` (2026-10-02) : Photovoltaïque autonome.
- `minireseau@1` (2026-10-02) : mini-réseau. La charge y part poste par
  poste, avec son profil sur 24 heures ; le groupe, avec le prix du litre
  de carburant ; les résultats, avec le LCOE et ses parts. Mêmes règles :
  lieu arrondi, noms de postes coupés à 40 caractères, ni nom de site, ni
  textes du rapport, ni séries de la ressource.

## Conséquences

- Le schéma de table ne nomme pas les modules : un module de plus
  (mini-réseau, conception de champ PV) ajoute un format de fiche, pas
  une migration.
- Les fiches arrivent hors ligne avec retard : le logiciel les garde et
  les envoie à la connexion suivante.
- Retirer la licence arrête les dépôts ; révoquer la clé arrête tout,
  retrait compris (les fiches déjà reçues restent, rattachées à une clé
  révoquée).

## Hors périmètre

Publication des données agrégées, normalisation des noms d'appareils,
contrepartie offerte aux contributeurs (comparaison de leurs prix à la
médiane régionale) : sujets suivants, une fois les premières fiches
reçues.
