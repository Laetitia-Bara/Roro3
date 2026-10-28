# Roro 3.0

Un projet Python familial pour étudier les disponibilités de paniers, proposer des
créneaux de suivi et démontrer un parcours de réservation robuste **sur données fictives**.

Cette version livre un cœur modulaire, une démonstration locale configurable et les
invariants de sécurité. Aucun compte réel, token ou accès à une plateforme n'est nécessaire.
Il ne contient ni client Too Good To Go, ni connexion Telegram, ni paiement.

## Utiliser VS Code sur cet ordinateur

L'environnement est déjà installé dans le dossier `.venv`. Dans VS Code, choisir
**Fichier → Ouvrir le dossier**, puis `D:\Roro3`.

- **Lancer l'application** : ouvrir **Exécuter et déboguer** (`Ctrl+Maj+D`), choisir
  **Roro3 : lancer l'application**, puis appuyer sur **F5**. Le navigateur s'ouvre sur
  `http://127.0.0.1:8080`. Le carré rouge ou `Maj+F5` arrête l'application.
- **Tester** : ouvrir le panneau **Tests** (icône éprouvette), puis **Exécuter tous les
  tests**. Une autre possibilité est de sélectionner **Roro3 : tests automatiques**
  dans les configurations de lancement, puis **F5**.

Les extensions Python et Python Debugger sont recommandées par le projet. Si VS Code
demande un interpréteur, choisir `.venv\Scripts\python.exe` dans le dossier Roro3.
Une sélection d'interpréteur déjà mémorisée par VS Code peut devoir être corrigée avec
**Python: Select Interpreter**. Il n'est pas nécessaire de réinstaller l'environnement.

Le lancement utilise le module de l'application, quel que soit le fichier ouvert dans
l'éditeur. Si le port 8080 est déjà occupé par une instance de Roro3, arrêter cette
instance avant de relancer. [Documentation officielle du débogage VS Code](https://code.visualstudio.com/docs/python/debugging),
[panneau de tests Python](https://code.visualstudio.com/docs/python/testing).

## Installation — Windows / PowerShell

Python 3.14.4 a été utilisé pour les vérifications de ce jalon. Le projet déclare Python
3.12 à 3.14 ; les autres versions de cette plage restent à valider.

```powershell
cd D:\Roro3
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev,ui]"
.\.venv\Scripts\python.exe -m roro3 demo
.\.venv\Scripts\python.exe -m roro3 ui
```

L'interface optionnelle s'ouvre sur `http://127.0.0.1:8080`. Elle n'est pas exposée au
réseau local. `Ctrl+C` arrête son serveur. Sans l'option `ui`, le cœur et la CLI restent
utilisables. Voir [le choix d'interface](docs/CHOIX_INTERFACE.md).

Pour reproduire l'environnement vérifié, utiliser `requirements-lock.txt` avant
l'installation du projet :

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-lock.txt
.\.venv\Scripts\python.exe -m pip install --no-deps -e .
```

## Démonstration

Le jeu initial comprend trois commerces inventés, deux paniers disponibles, un historique
fictif de trois mardis et des fenêtres manuelles/estimées. La CLI utilise une horloge fixe au 27 octobre 2026
pour rendre les résultats reproductibles. Aucun contrôle périodique ne démarre tout seul.
L'écran déclenche un cycle fictif uniquement sur demande.

## Commerçants et créneaux

Dans l'interface, **Ajouter un commerçant** ouvre un formulaire avec un nom et autant
de plages jour/début/fin que nécessaire. Un commerçant peut être enregistré sans horaire.
Les plages du même jour ne doivent ni se chevaucher ni traverser minuit. Une erreur
laisse le formulaire ouvert ; **Annuler** ne sauvegarde rien.

**Modifier** permet de renommer le commerçant et d'éditer ses horaires manuels. Les
créneaux estimés restent distincts et ne sont jamais écrasés par le formulaire.
**Recalculer les estimations** actualise ces derniers à partir de l'historique disponible.

**Suivre ce commerçant** sélectionne les commerces inclus dans les prochains contrôles.
**Désactiver** conserve le commerce, ses horaires et tout son historique, mais empêche
son suivi ; **Réactiver** retrouve son choix de suivi précédent. Ces réglages sont
persistants et ne lancent jamais un cycle tout seuls. Un commerce inconnu, désactivé
ou non suivi est également bloqué à la frontière de réservation, indépendamment de l'écran.

Le catalogue fictif prend en compte les ajouts sans redémarrage. Les identifiants et les
créneaux de retrait restent stables pour une même journée, même après un renommage ou
un redémarrage. L'écran suit la date courante ; la CLI conserve son scénario fixe.
[Parcours et limites du deuxième jalon](docs/JALON_02_COMMERCANTS.md).

```powershell
.\.venv\Scripts\python.exe -m roro3 demo --database data\autre-demo.sqlite3
.\.venv\Scripts\python.exe -m roro3 stop
.\.venv\Scripts\python.exe -m roro3 status
.\.venv\Scripts\python.exe -m roro3 resume
```

La politique par défaut observe, sans notification de disponibilité ni réservation,
avec `dry_run=true`. Même en activant la réservation et en désactivant dry-run dans
l'interface, seules des commandes **fictives** peuvent être produites. Un dry-run
n'appelle aucune méthode de réservation ; il peut écrire un aperçu dans l'historique.

Les interrupteurs observation, notification et réservation sont indépendants. Si une
notification ou réservation fictive est activée, les relevés nécessaires enrichissent
également l'historique. Les comptes rendus de tentative restent affichés même si les
notifications de disponibilité sont désactivées. L'arrêt global est conservé dans SQLite
et ne se désactive pas au redémarrage. Il bloque les nouvelles actions admises ; une
action déjà admise ne constitue pas une annulation et reste suivie.

## Configuration et confidentialité

Copier `.env.example` vers `.env` pour personnaliser les variables locales. La CLI charge
ce fichier du dossier courant sans remplacer les variables d'environnement existantes.
La politique d'environnement initialise une **nouvelle base** ; l'état d'une base déjà
créée fait autorité. Les fichiers privés et bases sont exclus de Git.

Ne jamais copier les configurations ou l'historique Git des anciennes applications.
Les sauvegardes vérifiées sont stockées hors de ce dépôt, avec droits Windows privés.
Les anciens projets n'ont pas été modifiés. Voir [la sécurité](docs/SECURITE.md).

## Architecture et tests

Le cœur utilise des modèles typés, SQLite et des contrats simples. L'interface NiceGUI
est un adaptateur optionnel. [Architecture, limites et prochaines étapes](docs/ARCHITECTURE.md).

```powershell
.\.venv\Scripts\python.exe -m pytest
.\.venv\Scripts\python.exe -m ruff check .
```

Les tests couvrent les modes sans action, le dry-run, l'arrêt persistant, les doublons
au redémarrage et en concurrence, les résultats inconnus, l'historique, la migration
SQLite, l'édition des commerçants, leur sélection et la validation des horaires.
Aucun test n'envoie de commande externe. La démonstration se teste avec le réseau bloqué.

## Limites du jalon

La planification calcule des prochaines fenêtres ; elle ne lance pas encore de surveillance
en arrière-plan. Les estimations sont descriptives, sans taux de probabilité : la couverture
complète des jours surveillés reste à modéliser. Une disponibilité observée peut provenir
d'une remise en vente ; elle n'est pas une heure de publication exacte. Les premiers
relevés déjà disponibles ne sont pas utilisés comme transitions pour les estimations.

Le suivi des annulations, expirations et états distants n'est pas implémenté : aucune
plateforme réelle n'est connectée. Les conditions de Too Good To Go interdisent l'extraction
automatisée ; une intégration réelle n'est pas promise et nécessiterait un mécanisme
autorisé. [Conditions officielles, article 7.5](https://www.toogoodtogo.com/fr/legal/terms-and-conditions-using-the-app).

Ce projet est destiné à un usage familial et à une démonstration portfolio Python.
Aucun service commercial ou déploiement public n'est configuré. Le choix de licence
de publication sera arrêté avant diffusion ; aucun code du client tiers n'est recopié.
