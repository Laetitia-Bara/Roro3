# Deuxième jalon — commerçants et horaires configurables

## Parcours disponible

1. Ouvrir l'interface et choisir **Ajouter un commerçant**.
2. Donner un nom (1 à 100 caractères) et ajouter les jours/plages manuelles souhaités.
3. Enregistrer ; le commerce apparaît immédiatement. Aucun contrôle ne part automatiquement.
4. Utiliser **Modifier** pour changer le nom ou les plages, **Suivre ce commerçant** pour
   sélectionner le suivi et **Désactiver** pour conserver une fiche hors suivi.
5. Lancer un cycle fictif pour observer uniquement les commerçants actifs et sélectionnés.

Un formulaire invalide reste ouvert et ne sauvegarde rien. Les créneaux adjacents sont
acceptés, les chevauchements du même jour refusés. Annuler ne change aucune donnée.
Un commerce sans créneau peut être observé manuellement ; aucune surveillance planifiée
n'est encore exécutée dans ce jalon.

## Horaires manuels et estimations

Les créneaux manuels expriment un choix de l'utilisateur. Les estimations proviennent
uniquement des transitions de disponibilité enregistrées. Le bouton de recalcul conserve
les créneaux manuels et remplace seulement les estimations, avec un seuil de trois journées
distinctes observées. Si les données sont insuffisantes, aucune estimation n'est affichée.

Une modification manuelle conserve les estimations, même si elles recouvrent le même
horaire. Les deux origines restent visibles. Les estimations indiquent des disponibilités
observées, jamais une heure exacte de publication ni une probabilité certifiée.

## Persistance et protections

Le schéma SQLite passe de 1 à 2, dans une transaction. Il conserve les commerçants,
observations, tentatives, modes et arrêt global existants. Les bases actuelles ont été
sauvegardées et vérifiées avant ce changement ; les copies privées restent hors Git.

Un commerçant désactivé garde son choix de suivi, ses horaires et son historique. Le
réactiver n'efface rien et ne déclenche aucun cycle. Le contrôle de sélection est appliqué
dans le suivi et répété dans la transaction de réservation, y compris si celle-ci est
appelée directement. L'arrêt global, le dry-run et l'unicité des tentatives restent actifs.

Le catalogue du simulateur tient compte d'un nouveau commerce immédiatement. Ajouter,
renommer ou réordonner des commerçants ne change pas l'identité des autres paniers. Les
retraits quotidiens restent stables et la CLI conserve son horloge fixe pour les démonstrations.

## Vérifications réalisées

121 tests réussis dans l'environnement de développement, puis sur le paquet installé
dans un second environnement. Contrôles de qualité, formatage et dépendances réussis.
Les tests couvrent notamment migration, sélection à la frontière d'action, absence de
sauvegarde partielle, conservation des estimations et stabilité des offres fictives.

Les parcours ont aussi été vérifiés dans un vrai navigateur, sur une base de contrôle
séparée : ajout de deux plages, édition, erreurs, Annuler, rechargement et sélection.
Aucune erreur JavaScript ni requête externe observée. Tableau de bord et formulaire
contrôlés à 390 pixels sans débordement horizontal. Aucun ordre n'a été créé par ces essais.

Un contrôle des journaux serveur a révélé une notification de succès appelée après la
destruction du dialogue. Son ordre a été corrigé, puis création et édition ont été
retestées avec une confirmation explicitement visible à chaque fois. L'exception de
contexte du formulaire ne se reproduit plus. Une réinitialisation de socket Windows a
été observée à la fermeture du navigateur de contrôle ; elle n'a affecté ni l'enregistrement
ni la persistance et n'est pas masquée par le code applicatif.

![Formulaire de commerçant](images/merchant-editor.png)

[Vue complète du tableau de bord vérifié](images/merchants-dashboard.png).

## Limites conservées

Aucune connexion réelle, notification Telegram réelle, réservation réelle ou surveillance
en arrière-plan. La sélection et les créneaux préparent le prochain jalon : la planification
d'un suivi simulé avec cadence bornée. Les horaires traversant minuit ne sont pas encore
pris en charge. Les anciens projets Roro2 et Roland ne sont pas modifiés.
