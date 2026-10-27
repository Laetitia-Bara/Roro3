# Architecture du premier jalon

## Responsabilités

| Module | Rôle |
|---|---|
| `models` | Modèles typés, instants UTC, politiques indépendantes |
| `config` | Configuration validée ; refus de tout connecteur autre que simulé |
| `storage` | SQLite, schéma versionné, historique et état persistant |
| `ports` / `simulator` | Contrats et seules implémentations externes disponibles : factices |
| `observations` | Un cycle partagé entre collecte, notification et décision |
| `analysis` | Estimation descriptive par jour et quart d'heure |
| `planning` | Prochaine fenêtre en calendrier Europe/Paris |
| `reservations` | Frontière unique d'action, claim et résultat persistant |
| `ui` | Adaptateur NiceGUI local optionnel |
| `demo` / `__main__` | Données fictives, composition et commandes reproductibles |

L'interface ne contient pas la décision de réservation. Le cœur n'importe jamais NiceGUI
ni un client de plateforme. Aucun code d'accès externe des anciens dépôts n'est recopié.
Les opérations utiles de Roro2 sont représentées par les contrats ; leur migration effective
reste subordonnée à un mécanisme autorisé et à la validation de l'environnement historique.

## Invariants vérifiés

L'activation de la réservation est contrôlée dans une transaction SQLite juste avant
l'admission d'une tentative. `BEGIN IMMEDIATE` et une contrainte unique empêchent deux
instances du service de prendre le même panier/créneau pour le même compte fictif.
La clé inclut l'instant de début de retrait en UTC et le type aperçu/simulation.
Un commerçant n'est donc pas bloqué définitivement pour tous ses paniers à venir.

Le claim est enregistré avant l'appel du simulateur. Une tentative `pending`, `unknown`
ou `failed` reste bloquante pour cette clé ; aucune reprise aveugle n'est effectuée. Un futur
connecteur autorisé devra réconcilier l'état distant et prévoir une reprise contrôlée.
Si le processus s'arrête entre le claim et la réponse, `pending` reste présent. Ce choix
privilégie l'absence de répétition plutôt qu'une réservation potentiellement perdue.

L'arrêt global et les modes sont lus depuis SQLite à chaque admission. Une action déjà
admise peut se terminer après un arrêt ; l'arrêt ne vaut ni annulation ni paiement. Les
changements de politique ne retirent pas les tentatives. Une base existante conserve son
état même si les variables d'environnement ont changé.

`dry_run` crée un aperçu seulement, sans méthode de mutation du connecteur. Désactiver
`dry_run` autorise uniquement une commande au simulateur : aucun connecteur réel ne fait
partie du paquet. Le contrôle de capacité complète l'absence d'implémentation réseau ;
ce n'est pas une protection contre du code Python malveillant installé par l'utilisateur.

## Observations et temps

Chaque contrôle est conservé, y compris les absences. Une transition de disponibilité
est distinguée d'une première présence et d'un simple relevé d'un stock déjà présent.
Les notifications de disponibilité suivent les transitions, pas chaque scan répété.
La remise en vente après annulation reste une cause possible de disponibilité.

Les estimations nécessitent trois journées distinctes dans un même créneau hebdomadaire.
Elles ne calculent pas de probabilité et ne prouvent pas un horaire de publication.
La couverture complète et les interruptions doivent être prises en compte avant une
recommandation plus avancée. Les exemples historiques sont explicitement fictifs.

Les instants sont UTC ; les créneaux sont des heures locales avec un jour de semaine.
Le planificateur ignore une occurrence à heure inexistante au printemps et choisit la
première occurrence à l'automne. Les fenêtres traversant minuit ne sont pas encore prises
en charge ; le dernier quart d'heure finissant à minuit n'est pas estimé dans ce jalon.
Ces limites sont explicites et testables.

## Étapes suivantes, hors de ce jalon

1. Édition complète des commerçants et créneaux, couverture des contrôles et qualité des données.
2. Planification d'un suivi fictif avec cadence bornée et arrêt coopératif.
3. Suivi simulé des annulations/expirations et des résultats en attente.
4. Adaptateur de notification réel si explicitement activé, avec protection des secrets.
5. Toute connexion de plateforme uniquement après confirmation d'un mécanisme autorisé.

La consultation de trois derniers relevés ou une démonstration fictive ne prouve pas
un fonctionnement réel avec la plateforme. Aucun service d'arrière-plan, publication
Internet ou déploiement n'est créé ici.
