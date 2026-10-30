# Quatrième jalon — historique et carnet familial mobile

## Ce qui fonctionne

Deux parcours séparés : la démonstration fictive existante et un carnet familial vide,
dans lequel ajouter ses commerces et saisir des relevés manuels. Les horaires et
observations restent dans SQLite après redémarrage. Aucun compte Too Good To Go n'est
connecté : le carnet ne lit pas la plateforme et ne réserve pas de panier.

## Premier lancement dans VS Code

1. Ouvrir le dossier Roro3 et arrêter une éventuelle instance sur le port 8080.
2. Dans Exécuter et déboguer, choisir **Roro3 : test familial sur iPhone** puis **F5**.
3. Le terminal affiche une adresse locale et le chemin du fichier du code familial.
4. Ouvrir `data/family-access.json` dans VS Code. Conserver son contenu en privé.
5. Sur l'iPhone connecté au même réseau domestique, ouvrir l'adresse du terminal dans
   Safari et saisir la valeur `access_code`. Ne pas utiliser `localhost` sur l'iPhone.
6. Ajouter les commerces et leurs horaires. Vérifier les disponibilités dans l'app
   officielle, puis revenir dans Roro pour saisir le nombre de paniers, y compris zéro.

L'heure enregistrée est l'heure actuelle du serveur. Les anciens relevés ne doivent pas
être saisis comme des observations actuelles. Si plusieurs types de paniers sont suivis
dans un même magasin, créer une fiche distincte et clairement nommée pour chaque type ;
le carnet regroupe les saisies par fiche et journée, sans connaître les offres distantes.

Le code familial donne accès à tout le carnet, comme aux autres membres de la famille :
il n'y a pas de rôles individuels. Les données sont conservées sur le PC. Le fichier de
code n'est pas chiffré ; les sauvegardes privées doivent inclure la base et garder le code
hors du dépôt public. La session est valable douze heures. Pour changer le code, arrêter
le serveur, déplacer le fichier privé hors du projet puis relancer ; un nouveau code est
créé et les anciennes sessions ne sont plus reconnues.

Safari peut ajouter un raccourci via **Partager → Sur l'écran d'accueil**. Le serveur
doit rester actif et le PC éveillé. Aucun mode hors ligne, notification iOS ou service
Windows permanent n'est installé. `Maj+F5` arrête le serveur.

## Si l'iPhone ne se connecte pas

- Vérifier que l'adresse est celle du terminal et que le PC et l'iPhone sont sur le
  même réseau. Un Wi-Fi invité peut isoler les appareils.
- Si plusieurs cartes réseau sont présentes, lancer avec `--host` et l'IPv4 privée du
  PC sur ce réseau. La liaison aux adresses publiques ou à toutes les interfaces est refusée.
- Si Windows affiche une demande d'accès, autoriser le réseau **privé** uniquement.
  Ne pas désactiver le pare-feu. Une règle privée limitée au port choisi et au sous-réseau
  local peut être nécessaire selon la configuration Windows.
- HTTP ne chiffre pas les échanges : utiliser seulement un réseau de confiance. Aucun
  port de box, tunnel public ou partage Internet ne doit être ouvert pour ce parcours.

## Lire et analyser les relevés

Ouvrir **Historique et estimations**, choisir un commerce, un événement ou des dates,
puis **Appliquer / actualiser**. Les filtres utilisent les dates locales inclusives.
La pagination affiche vingt relevés ; les comptes portent sur tous les résultats filtrés.
Une saisie de date invalide laisse les résultats précédents affichés avec un message.
**Réinitialiser** retrouve tout l'historique. Aucun filtre ne supprime de données.

Pour un commerce, les groupes horaires comptent les journées distinctes avec un passage
observé de zéro à disponible. Trois dates du même jour de semaine et du même quart d'heure
atteignent le seuil actuel. Un groupe moins documenté porte la mention **Encore peu de
recul**. Les groupes suivent les filtres, sans remplacer les horaires enregistrés.

Un premier relevé déjà disponible peut correspondre à une vente plus ancienne. Une
transition peut aussi provenir d'une remise en vente et ne donne pas son instant exact.
Les interruptions ne sont pas modélisées et aucun taux de probabilité n'est calculé.
Plusieurs semaines sont nécessaires pour documenter un même jour de semaine ; un essai
de quelques jours permet de vérifier la collecte manuelle, pas une fiabilité statistique.

## Vérifications et limites

La suite comprend 202 tests, dont les filtres aux changements d'heure, le tri temporel,
la pagination, les jours distincts, la séparation des bases, les migrations et le refus
de toute réservation familiale. Les contrôles ASGI testent aussi les sessions expirées
ou falsifiées, les origines étrangères et la limitation des tentatives de connexion.

Le parcours mobile a été vérifié dans Edge avec un format iPhone de 390 pixels : accès
par code, deux commerces, deux créneaux, relevés zéro puis disponible, arrêt, reprise,
historique, validation des dates et persistance au rechargement. Aucun appel externe,
erreur JavaScript ou débordement horizontal observé. Safari sur un iPhone physique reste
à confirmer par un essai familial.

[Capture sur données de test](images/family-mobile.png).
[Analyse et pagination de l'historique de test](images/history-analysis.png).

La connexion réelle et la réservation automatisée restent non livrées. L'existence d'un
ancien client tiers ne confirme pas un mécanisme autorisé. Les [conditions officielles,
article 7.5](https://static.apptoogoodtogo.com/general-terms-conditions/fr-fr/index.html)
interdisent l'extraction automatisée. La démonstration du parcours de réservation utilise
le simulateur et ses tests de doublons, dry-run, arrêt et résultat inconnu.
