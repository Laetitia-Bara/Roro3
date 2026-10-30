# Architecture de Roro 3.0

## Responsabilités

| Module | Rôle |
|---|---|
| `models` | Modèles typés, instants UTC, politiques indépendantes |
| `config` | Configuration validée ; refus de tout connecteur autre que simulé |
| `storage` | SQLite, schéma versionné, historique et état persistant |
| `merchants` | Création, édition, activation et sélection ; créneaux manuels et estimés séparés |
| `ports` / `simulator` | Contrats et seules implémentations externes disponibles : factices |
| `observations` | Un cycle partagé entre collecte, notification et décision |
| `analysis` | Estimation descriptive par jour et quart d'heure |
| `history` / `history_ui` | Filtres, pagination et analyse de la sélection, sans mutation |
| `family_ui` / `family_access` | Carnet manuel sur réseau privé et accès HTTP/WebSocket protégé |
| `planning` | Prochaine fenêtre en calendrier Europe/Paris |
| `scheduler` | Admission des contrôles planifiés, cadence et session exclusive |
| `scheduler_ui` | Minuteur applicatif unique et panneau de surveillance |
| `reservations` | Frontière unique d'action, claim et résultat persistant |
| `ui` | Adaptateur NiceGUI local optionnel |
| `merchant_ui` | Formulaire temporaire validé, sans écriture avant Enregistrer |
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
La même transaction vérifie aussi que le commerçant existe, est actif et est sélectionné.
Le filtrage dans l'interface n'est jamais la seule protection. Le suivi ignore ces offres
avant d'enregistrer un relevé ou d'envoyer une notification.

Le claim est enregistré avant l'appel du simulateur. Une tentative `pending`, `unknown`
ou `failed` reste bloquante pour cette clé ; aucune reprise aveugle n'est effectuée. Un futur
connecteur autorisé devra réconcilier l'état distant et prévoir une reprise contrôlée.
Si le processus s'arrête entre le claim et la réponse, `pending` reste présent. Ce choix
privilégie l'absence de répétition plutôt qu'une réservation potentiellement perdue.

L'arrêt global et les modes sont lus depuis SQLite à chaque admission. Une action déjà
admise peut se terminer après un arrêt ; l'arrêt ne vaut ni annulation ni paiement. Les
changements de politique ne retirent pas les tentatives. Une base existante conserve son
état même si les variables d'environnement ont changé.

## Gestion et migration des commerçants

Le schéma SQLite 2 ajoute les champs `active` et `watched`. La migration depuis le
schéma 1 conserve les lignes, les historiques et les modes et donne aux anciens
commerçants l'état suivi qu'ils avaient implicitement. Les ajouts de colonnes et le
changement de version sont atomiques. Une version inconnue est refusée sans dégradation.

L'édition des horaires manuels relit le commerçant sous transaction, puis modifie
uniquement le nom et les créneaux manuels ; elle conserve les estimations actuelles.
Les commandes d'activation/sélection ne modifient que leur propre champ. Le recalcul
des estimations préserve à son tour les horaires manuels et les états. Aucun de ces
gestes ne déclenche de cycle ni ne modifie la politique globale.

Un commerçant désactivé reste consultable, avec tout son historique. Son choix de suivi
est conservé pour une réactivation ultérieure. Il n'existe pas de suppression destructive
dans l'interface. Les créneaux manuels identiques ou qui se chevauchent sont refusés ;
les créneaux adjacents et les recouvrements entre un manuel et une estimation sont permis.

Le simulateur lit le catalogue au moment du contrôle. Ses identifiants reposent sur les
identités immuables des commerces, pas sur leur nom ou position. Le retrait quotidien
est stable, en réutilisant une occurrence déjà connue quand elle existe, pour préserver
la continuité avec la première démonstration. Une horloge injectable garde la CLI
reproductible tout en permettant à l'interface de changer de journée sans redémarrage.

## Surveillance planifiée

Le schéma SQLite 3 ajoute la fréquence, la session de surveillance et le dernier passage
admis par commerçant. Les migrations 1/2 vers 3 sont transactionnelles et conservent les
données existantes. Le démarrage reste une action explicite : construire un service
ou ouvrir une page n'adopte jamais une ancienne session enregistrée.

Un unique `app.timer` NiceGUI interroge le planificateur chaque seconde, indépendamment
des clients. Les minuteurs de chaque page ne servent qu'à l'affichage. Les historiques
et compteurs se mettent à jour sans recréer les formulaires en cours de saisie.

Les instances partagent un bail exclusif de 15 secondes en SQLite, renouvelé à chaque
tick, même hors créneau. La prise d'une session et l'admission des commerçants sont
transactionnelles. Un contrôle est admis au plus une fois par commerçant et par cadence ;
les fenêtres manuelles et estimées forment une union. La cadence est appliquée avant
la recherche de la prochaine fenêtre, pour ne pas annoncer de passage hors créneau.

Un bail expiré exige un nouveau démarrage explicite. Un ancien propriétaire ne peut pas
arrêter la nouvelle session lors de sa fermeture. Après la lecture du simulateur, une
garde rejette les résultats d'un propriétaire remplacé ou arrêté. Un cycle déjà admis
peut toutefois terminer avant qu'un arrêt soit observé : aucune annulation rétroactive
n'est promise. Le connecteur reste exclusivement simulé et synchrone.

Le chemin planifié appelle l'orchestrateur avec une liste de commerçants dus et le mode
`observation_only`. Ce chemin exige Observation et ne notifie ni ne réserve, quelle que
soit la politique des cycles manuels. Désactiver Observation ou activer l'arrêt global
désarme la session dans la même transaction ; réactiver un mode ne la redémarre pas.

Les erreurs du contrôle consomment leur passage pour éviter une boucle de reprises.
Seul un message générique est conservé ; l'exception externe brute n'est pas journalisée.
Le prochain essai respecte la cadence et les fenêtres restantes.

`dry_run` crée un aperçu seulement, sans méthode de mutation du connecteur. Désactiver
`dry_run` autorise uniquement une commande au simulateur : aucun connecteur réel ne fait
partie du paquet. Le contrôle de capacité complète l'absence d'implémentation réseau ;
ce n'est pas une protection contre du code Python malveillant installé par l'utilisateur.

## Observations et temps

Le schéma 4 ajoute le type de jeu de données : `simulated` pour les démonstrations
existantes, `family` pour une nouvelle base familiale. La migration conserve les tables
métier et les politiques. Les deux modes refusent d'ouvrir la base de l'autre.
La frontière de réservation et l'orchestrateur bloquent le mode familial, même si une
politique de réservation y est forcée. Les offres simulées ne peuvent pas y être insérées.

Les saisies familiales passent par une transaction qui valide le commerce, l'arrêt global,
le stock entier et l'ordre temporel. Elles prennent l'heure du serveur. Une clé de journée
locale regroupe les relevés d'un commerce : la colonne historique `pickup_start` y est
uniquement cette clé interne, pas une heure de retrait fournie par une plateforme.
Une première présence chaque jour reste distincte d'un passage observé de zéro à disponible.

Le service d'historique lit les relevés en un SELECT, trie les instants UTC puis les
identifiants et applique les dates dans le fuseau local. Comptes et groupes sont calculés
avant pagination. Le traitement est en mémoire et destiné aux petits volumes familiaux ;
une pagination SQL sera nécessaire pour un historique important. Les filtres ne modifient
ni les estimations enregistrées ni les modes. Aucun connecteur n'est appelé.

Le serveur familial se lie à une IPv4 privée choisie explicitement ou détectée localement.
Un middleware ASGI vérifie l'hôte, l'origine et une session signée pour les requêtes et
WebSockets, y compris les ressources NiceGUI. Le code local est aléatoire, jamais placé
dans une URL et jamais affiché dans les journaux. Les essais de connexion sont limités.
La session dure douze heures ; son expiration est aussi vérifiée à la réception des messages.
Le transport HTTP exige un réseau de confiance et n'assure pas de chiffrement ni d'isolation
entre membres de la famille. Aucun compte de plateforme n'est connecté.

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

1. Couverture des contrôles et qualité des recommandations statistiques.
2. Notifications simulées intégrées à la planification, si ce périmètre est validé.
3. Suivi simulé des annulations/expirations et des résultats en attente.
4. Adaptateur de notification réel si explicitement activé, avec protection des secrets.
5. Toute connexion de plateforme uniquement après confirmation d'un mécanisme autorisé.

La consultation de relevés manuels ou une démonstration fictive ne prouve pas
un fonctionnement réel avec la plateforme. Aucun service d'arrière-plan, publication
Internet ou déploiement Internet n'est créé ici.
