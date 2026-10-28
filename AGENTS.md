# Consignes de développement de Roro3

- À chaque jalon fonctionnel livré et testé, mettre à jour le README avec l'état réel
  des fonctionnalités, le lancement, les tests effectués et les limites restantes.
  Actualiser aussi les documents de validation concernés. Distinguer ce qui est livré,
  ce qui est prévu et ce qui a effectivement été vérifié ; ne pas annoncer une CI
  réussie avant de consulter son résultat. Un essai manuel isolé ne constitue pas une
  nouvelle version à publier.
- Préserver le lancement par F5 et le panneau Tests dans VS Code. Présenter une courte
  marche à suivre pour vérifier chaque nouvelle fonctionnalité dans l'interface.
- Le dépôt est public : ne jamais ajouter de secrets, fichiers de session, bases réelles,
  journaux privés ou sauvegardes. Garder les données de démonstration fictives.
- Travailler dans Roro3. Ne pas modifier les anciens projets Roro2 ou Roland.
- Garder le cœur Python indépendant de NiceGUI et de tout service externe. La connexion
  réelle à une plateforme reste hors périmètre sans mécanisme autorisé confirmé.
- Exécuter les vérifications adaptées aux changements. Pour une modification purement
  documentaire, contrôler les liens et la cohérence sans relancer inutilement les tests métier.
