# Confiance et statut éditorial

Chaque valeur du Core porte sa confiance et son statut éditorial comme des
propriétés de première classe. Ce document décrit les deux, à l'intention d'un
contributeur qui propose une donnée ou une méthode.

Périmètre : la confiance et le statut s'appliquent à `mesures_ressource` et
`grandeurs_metier`. Les référentiels (`sources`, `localites`, `unites`,
`grandeurs_referentiel`, `series_metadonnees`, `contributeurs`) n'ont pas de
statut ; leur retrait passe par un soft delete (`actif`, `desactive_le`).

## Confiance A/B/C

- **A** (haute) : donnée mesurée directement par un instrument de référence, ou
  calculée par une méthode reconnue à partir de mesures elles-mêmes A.
- **B** (moyenne) : donnée modélisée, interpolée ou extrapolée selon une
  méthodologie documentée, à partir d'une source de fiabilité haute ou moyenne.
- **C** (basse) : donnée estimée par expertise sans validation instrumentale, ou
  issue d'une source de fiabilité faible.

La confiance est dérivée par cinq règles, évaluées dans l'ordre ; la première
qui s'applique fixe la valeur :

| Ordre | Condition | Résultat |
|---|---|---|
| R1 | source de fiabilité `faible` | C |
| R2 | méthode de collecte `expertise_humaine` | C |
| R3 | méthode `mesure_directe` et source de fiabilité `haute` | A |
| P | méthode `calcul_derive`, niveaux des entrées connus | le plus bas des entrées et du plafond |
| R4 | tous les autres cas | B |

La règle P ([ADR-0008](../decisions/0008-propagation-de-la-confiance.md))
donne à une valeur calculée le niveau effectif (override compris) le plus bas
des valeurs dont elle est tirée, sur sa seule période, sans dépasser le
plafond de sa méthode. Le plafond est B, sauf pour un calcul exact sans modèle
ni hypothèse de l'utilisateur (HEP, fraction diffuse, humidex, variabilité
journalière, P50/P90), qui peut atteindre A à partir de mesures A. Les
grandeurs paramétrables, les proxys et les indicateurs restent au plus B et
descendent en C avec leurs entrées. La règle s'applique aux grandeurs stockées
comme aux calculs à la volée de `/v1/grandeurs` ; les indicateurs entre
sources (écarts, rangs, dégénérescence de pixel) gardent le B de leurs
migrations.

R4 est le cas par défaut : une donnée satellitaire ou de réanalyse (NASA POWER,
CAMS, ERA5) est en confiance B. Une décision éditoriale peut poser un override
sur une ligne, avec une justification obligatoire conservée dans le commentaire
éditorial.

**La confiance A est réservée aux données validées au sol** et aux calculs
exacts qui n'utilisent qu'elles. Un fait exact tiré d'une source satellitaire
reste B, avec un caveat documenté, tant qu'il n'a pas été confronté à une
mesure terrain. La définition publiée est rappelée dans la
[référence d'API](../architecture/06-api-reference-publique.md).

## Statut éditorial

Cinq états, dans un sens unique :

`brut` puis `valide_auto` puis `valide_humain` puis `publie`, avec `deprecie`
comme état terminal atteignable depuis n'importe quel état.

| État courant | Transitions autorisées |
|---|---|
| `brut` | `valide_auto`, `valide_humain`, `deprecie` |
| `valide_auto` | `valide_humain`, `deprecie` |
| `valide_humain` | `publie`, `deprecie` |
| `publie` | `deprecie` |
| `deprecie` | aucune (terminal) |

Trois principes : pas de régression (aucun retour à un état antérieur) ; les
sauts vers l'avant sont permis (`brut` vers `valide_humain`) ; `deprecie` est
terminal, une valeur retirée ne ressuscite pas, une nouvelle version est créée à
sa place.

## Validité temporelle

Aucune mise à jour destructive. Une valeur corrigée ou ré-ingérée ne remplace
pas l'ancienne en place : une nouvelle ligne est créée, l'ancienne est bornée
par `valide_au`, et les lectures ne renvoient que la version courante. L'histoire
reste vérifiable.
