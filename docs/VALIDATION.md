# Validation du socle — 27 octobre 2026

Ce document décrit des vérifications exécutées localement. Le workflow GitHub est
préparé mais n'a pas été exécuté sur un dépôt distant ; rien n'a été publié.


## Environnement

Windows x64, Python 3.14.4, NiceGUI 3.18.0, pytest 9.1.1, Ruff 0.17.3, SQLite fourni
par Python. Les 55 dépendances résolues sont figées dans `requirements-lock.txt`.
Une seconde installation non éditable a été réalisée dans un environnement neuf,
puis utilisée depuis un autre dossier pour éviter de tester accidentellement les sources.

## Résultats exécutés

| Vérification | Résultat |
|---|---|
| Suite pytest, environnement de développement | 73 tests réussis |
| Même suite, seconde installation non éditable | 73 tests réussis |
| Cohérence des dépendances, deux environnements | Aucun conflit |
| Contrôle Ruff et formatage | Réussis |
| Démonstration CLI sans réseau, répétée | Résultat stable, aucun ordre par défaut |
| Modes sans réservation et dry-run | Aucun appel de réservation |
| Deux services concurrents, même panier/retrait | Une seule commande fictive |
| Redémarrage, tentative en attente ou résultat inconnu | Aucune répétition automatique |
| Arrêt global et reprise | État persistant, historique conservé |
| Panier expiré | Refus à la borne de fin et après |
| Heure Paris, changements d'heure et clés UTC | Cas ciblés réussis |
| Recherche ciblée des anciennes valeurs sensibles dans les nouveaux textes | Aucune correspondance |

Les tests métier bloquent les connexions sortantes. La recherche de secrets est un
contrôle ciblé supplémentaire ; elle ne prétend pas reconnaître toutes les formes
possibles de données sensibles.

## Interface réelle

Un navigateur Edge sans fenêtre a testé les commandes de l'écran : observation,
aperçu sans commande, commande fictive, répétition sans doublon, arrêt, reprise et
persistance après rechargement. Affichages 1440 et 390 pixels contrôlés, sans
débordement horizontal sur petit écran. Aucune erreur JavaScript ni requête de page
vers un hôte externe n'a été observée. Voir [le détail et la capture](CHOIX_INTERFACE.md).

État de la démo remis à la fin : observation active, notifications et réservation
désactivées, dry-run actif et arrêt global désactivé. Les tentatives de contrôle
restent visibles et clairement fictives.
## Ce qui reste hors de cette validation

Aucune connexion à une plateforme ou Telegram, réservation réelle ou annulation réelle
n'a été testée. L'application n'est pas déployée sur Internet. La surveillance planifiée
en arrière-plan et la couverture statistique appartiennent aux prochains jalons.
Les audits et sauvegardes privés restent hors de la démonstration publique.
