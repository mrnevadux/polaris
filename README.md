# POLARIS — assistant vocal IA pour Windows 11

Dis « Hey Polaris » : il t'écoute (détection locale), réfléchit avec Gemini, agit sur ton PC et te répond à voix haute.

## Obtenir Polaris.exe

La compilation est automatique avec GitHub Actions : chaque push sur `main` lance **Build Polaris Windows (Polaris.exe)**.

1. Ouvre l'onglet **Actions** du dépôt et sélectionne **Build Polaris Windows (Polaris.exe)**.
2. Ouvre la dernière exécution terminée avec succès.
3. En bas de la page, télécharge l'artifact **Polaris-Windows** et dézippe-le.
4. Lance `Polaris/Polaris.exe`.

L'archive contient l'application portable et le modèle vocal français. Windows SmartScreen peut avertir car l'exe n'est pas signé : vérifie que l'archive vient bien de ce dépôt avant de choisir « Exécuter quand même ». Ne désactive pas Defender.

## Première utilisation

1. Ouvre **Réglages** et colle une clé API Gemini obtenue sur https://aistudio.google.com/apikey.
2. Enregistre, puis écris une commande ou active le micro et dis « Hey Polaris, ouvre le Bloc-notes ».
3. Le bouton **ARRÊT MICRO** coupe immédiatement le micro.

La clé API est chiffrée avec Windows DPAPI. Les données sont stockées dans `data` à côté de l'exe si le dossier est inscriptible ; sinon, elles sont placées dans `%LOCALAPPDATA%/Polaris/data` pour éviter que les réglages échouent dans un dossier protégé.

## Fonctions

Ouvrir des logiciels et des sites, rechercher des fichiers dans les dossiers utilisateur, lire et résumer des documents, renommer/déplacer des fichiers avec confirmation, gérer des fenêtres, répondre aux questions et rédiger. Le mode économie ralentit les animations et mesures.

## Sécurité et limites

- Le mot de réveil est détecté localement (Vosk) ; aucun son n'est enregistré ni envoyé. Seul le texte de la commande part vers Gemini.
- Gemini n'a accès qu'aux outils contrôlés de `polaris/tools.py` : pas de commande libre et aucune suppression de fichier.
- Confirmation avant les actions sensibles. Aucun démarrage automatique ni modification du registre.
- Sans internet, seules certaines commandes locales de base fonctionnent.
