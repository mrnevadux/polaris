# POLARIS — assistant IA pour Windows

POLARIS est un assistant informatique personnel pour Windows. Chaque push sur `main` déclenche le build Windows ; le téléchargement de l'artifact reste manuel dans l'onglet Actions.

## Voix

Active le micro une fois. Tant que le micro reste activé, POLARIS reprend automatiquement l'écoute du mot de réveil « Hey Polaris » après chaque réponse vocale. Pour préserver la confidentialité, l'écoute ne démarre pas seule après le lancement de l'application et ne redémarre pas si tu as utilisé Arrêt micro.

## Recherche Web

POLARIS peut chercher sur le Web public, lire le texte des pages accessibles et en faire une synthèse avec Gemini. Les pages qui nécessitent JavaScript ou une connexion, les formulaires, messages et achats ne sont pas automatisés.

## Fonctionnalités et limites

- Ouvrir applications, URL et fenêtres ; rechercher des fichiers dans les dossiers autorisés ; lire des fichiers texte/PDF.
- Contrôle souris/clavier et captures d'écran avec confirmation pour les actions sensibles.
- Aucun shell libre, aucune suppression directe et aucune promesse de contrôle d'appareils sans intégration compatible.

## Obtenir l'EXE

Après un push sur `main`, ouvre la dernière exécution réussie dans Actions et télécharge `Polaris-Windows`. Il faut ensuite dézipper l'archive et lancer `Polaris/Polaris.exe`. La clé Gemini est requise pour les réponses IA ; la recherche Web simple est disponible avec la formulation « cherche … sur internet ».
