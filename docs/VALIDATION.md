# Validation de Roro 3.0 — 30 octobre 2026

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
| Suite pytest, environnement de développement | 202 tests réussis |
| Même suite, seconde installation non éditable | 202 tests réussis |
| Cohérence des dépendances, deux environnements | Aucun conflit |
| Contrôle Ruff et formatage | Réussis |
| GitHub Actions, code de la version 0.4.0 | [202 tests et Ruff réussis](https://github.com/Laetitia-Bara/Roro3/actions/runs/41075792963) |
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
| Planification avant démarrage explicite ou après redémarrage | Aucun contrôle |
| Cadence, fenêtres et recouvrements manuels/estimés | Admissions bornées et dédupliquées |
| Deux services concurrents, bail expiré et reprise | Une seule session admise |
| Observation planifiée malgré les modes manuels de réservation | Aucun appel de notification ou réservation |
| Arrêt global ou Observation désactivée puis réactivée | Pas de reprise automatique |
| Résultat d'un propriétaire remplacé pendant le contrôle | Aucun relevé tardif enregistré |
| Filtres de dates locales et changements d'heure | Bornes inclusives respectées |
| Pagination, tri temporel et analyse de toute la sélection | Résultats cohérents |
| Migration 3 vers 4 et séparation famille/simulation | Lignes existantes conservées, mélange refusé |
| Base familiale avec politique de réservation forcée | Aucune collecte, notification ou tentative |
| Sessions familiales, origines étrangères et codes erronés | Accès refusés et essais limités |

La version initiale avait 73 tests. Le deuxième jalon ajoute 48 cas portant sur les
commerçants, la sélection, la migration, les formulaires et le catalogue dynamique.
Le troisième ajoute 43 cas sur la planification et son chemin d'observation seule.
Le quatrième ajoute l'historique filtrable et le carnet familial protégé ; la suite
actuelle compte 202 tests. La version des sources est `0.4.0`.

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

Pour le troisième jalon, une base de contrôle séparée a validé les passages
automatiques dans les créneaux, le respect de la cadence avec deux onglets, la mise
à jour des relevés et la conservation des formulaires ouverts. Les arrêts empêchent
les nouveaux contrôles et la reprise globale n'active pas le planificateur. Les
contrôles continuent quand le navigateur est fermé et le serveur reste actif.
La politique manuelle autorisait volontairement notification et réservation : les
passages planifiés n'en ont produit aucune. Voir [les preuves d'interface](JALON_03_PLANIFICATION.md).

Pour le quatrième jalon, Edge au format iPhone de 390 pixels a vérifié la connexion par
code, deux commerces, deux horaires, la saisie zéro puis disponible, l'arrêt, la reprise,
les filtres et la persistance au rechargement. Aucun débordement horizontal, appel externe
ou erreur JavaScript observé. Un second parcours sur 28 relevés de test a vérifié les
deux pages, le seuil de trois journées distinctes et une sélection vide. La navigation
et le cycle manuel de la démonstration fictive fonctionnent également.

Une comparaison des lignes de toutes les tables préexistantes de la base principale
avant et après migration 3 vers 4 confirme leur conservation. Les sauvegardes SQLite
ont été restaurées et vérifiées dans un dossier privé hors du dépôt.
Le lancement familial par défaut utilise une nouvelle base vide ; aucune donnée réelle
n'a été publiée. Voir [le parcours familial et ses limites](JALON_04_FAMILLE.md).

## Ce qui reste hors de cette validation

Aucune connexion à une plateforme ou Telegram, réservation réelle ou annulation réelle
n'a été testée. L'application n'est pas déployée sur Internet.
La couverture statistique des contrôles, les notifications planifiées et tout connecteur
réel restent hors de cette validation. Les audits et sauvegardes privés ne font pas
partie de la démonstration publique.
Safari sur un iPhone physique et le passage du pare-feu depuis un autre appareil du
foyer restent à confirmer ; les essais du navigateur ont utilisé l'IPv4 privée du PC.
