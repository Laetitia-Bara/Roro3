# Sécurité et confidentialité

## Périmètre de la démonstration

La version publique de Roro3 fonctionne uniquement sur des données fictives. Aucun
client Too Good To Go ou Telegram, compte réel, token ni paiement n'est nécessaire.
Le connecteur disponible est un simulateur ; une configuration demandant un connecteur
réel est refusée. Les tests métier bloquent le réseau sortant.

## Fichiers privés

Le `.gitignore` exclut les configurations locales, sessions, identifiants, bases SQLite
et leurs fichiers annexes, journaux, captures réseau, clés privées, certificats sensibles,
archives, sauvegardes et environnements virtuels. `.env.example` contient seulement des
réglages génériques sans secret. Les captures d'écran du dépôt montrent des données fictives.

Ne jamais ajouter de clés ou de données personnelles pour présenter le portfolio.
Les sauvegardes et rapports d'audit privés doivent rester hors de ce dépôt. Vérifier
les fichiers réellement suivis et l'historique avant tout envoi : ajouter un nom au
`.gitignore` ne retire pas un secret déjà enregistré dans un commit.

## Journalisation

Le journal applicatif ne reçoit pas les exceptions externes brutes. Un filtre masque
en plus les formes courantes d'adresses et de tokens. Ce filtre ne garantit pas
l'anonymisation de données arbitraires : ne jamais journaliser les identifiants.

## Interface locale

L'interface écoute uniquement sur `127.0.0.1`, sans partage distant ni rechargement
automatique. Elle ne comporte pas d'authentification multi-utilisateur et n'est pas
conçue pour être exposée au réseau ou à Internet. Un lancement de l'écran ne démarre
aucune surveillance en arrière-plan.

## Prévenir les actions involontaires

Les modes sans réservation et le dry-run ne peuvent pas appeler la méthode de réservation.
L'arrêt global, la sélection des commerçants et les tentatives sont persistants. La
réservation vérifie à nouveau la politique et la sélection dans une transaction SQLite.
Un résultat incertain reste bloquant ; aucune tentative n'est répétée aveuglément.

## En cas de fuite

Ne pas transmettre une clé dans une issue publique. Révoquer ou renouveler la clé auprès
de son fournisseur, puis traiter les copies et l'historique concernés : retirer seulement
la valeur du dernier fichier ne suffit pas. Ne pas tester la validité d'un secret exposé
en le réutilisant contre un service.
