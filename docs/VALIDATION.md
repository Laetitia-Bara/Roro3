# Validation de Roro 3.0 — 27 octobre 2026

Ce document décrit les vérifications exécutées localement. Les résultats GitHub Actions
se consultent séparément dans l'onglet **Actions** du dépôt ; ils ne sont pas déduits des
résultats locaux.

## Environnement

Windows x64, Python 3.14.4, NiceGUI 3.18.0, pytest 9.1.1, Ruff 0.17.3, SQLite fourni
par Python. Les 55 dépendances résolues sont figées dans `requirements-lock.txt`.
Une seconde installation non éditable a été réalisée dans un environnement isolé,
puis utilisée depuis un autre dossier pour éviter de tester accidentellement les sources.

## Résultats exécutés

| Vérification | Résultat |
|---|---|
| Suite pytest, environnement de développement | 121 tests réussis |
| Même suite, seconde installation non éditable | 121 tests réussis |
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
| Migration SQLite 1 vers 2 | Données métier et modes conservés |
| Ajout, édition et sélection des commerçants | Persistants après réouverture |
| Formulaire invalide et annulation | Aucune écriture partielle |
| Commerçant inconnu, désactivé ou non suivi | Aucune collecte ni réservation |
| Catalogue fictif après ajout, renommage ou redémarrage | Identifiants et retrait journalier stables |

La version initiale avait 73 tests. Le deuxième jalon ajoute 48 cas portant sur les
commerçants, la sélection, la migration, les formulaires et le catalogue dynamique.
La version installée et vérifiée pour ce jalon est `0.2.0`.

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

Les essais du deuxième jalon ont été effectués dans une base dédiée : ajout de deux
créneaux, modification conservant l'estimation, validation des chevauchements, nom
vide et fin avant début. L'empreinte complète de la table des commerçants est restée
identique après chaque erreur et après Annuler. La sélection a réduit le contrôle de
quatre à deux commerces, sans trace pour les exclus. Rechargement et réactivation
ont conservé les réglages. Tableau de bord et dialogue contrôlés à 390 pixels sans
débordement. Zéro erreur JavaScript et aucune requête externe observée.

La migration de la base de démonstration principale a conservé exactement ses
3 commerçants, 18 observations, 4 tentatives et sa politique globale. Les preuves de
sauvegarde et de migration restent dans le dossier privé extérieur au dépôt.

## Ce qui reste hors de cette validation

Aucune connexion à une plateforme ou Telegram, réservation réelle ou annulation réelle
n'a été testée. L'application n'est pas déployée sur Internet.
La surveillance planifiée en arrière-plan et la couverture statistique des contrôles
appartiennent aux prochains jalons. Les audits et sauvegardes privés ne font pas partie
de la démonstration publique.
