# POLARIS — assistant IA pour Windows

POLARIS est un assistant informatique personnel pour Windows. Les modifications du dépôt déclenchent automatiquement la compilation Windows via GitHub Actions ; il n'est pas nécessaire de lancer « Run workflow » à chaque changement.

## Recherche Web réellement disponible

POLARIS peut rechercher sur le Web public et lire le texte des pages accessibles, puis demander à Gemini de synthétiser les informations. Exemples : « cherche sur le Web les dernières nouveautés de Python », « compare ces deux pages : … » ou « lis cette page et résume-la : … ». Même sans clé Gemini, les demandes explicites « cherche … sur internet » utilisent la recherche Web locale.

La navigation automatique dans des comptes privés, l'envoi de formulaires/messages, les achats, les pages nécessitant JavaScript ou une connexion, et le contrôle universel de tout site ne sont pas fournis. Ces opérations demandent une intégration navigateur/authentification spécifique et une validation humaine. POLARIS ne prétend pas les avoir effectuées.

## Fonctions

- Assistant vocal local (Vosk), chat et interface graphique
- Ouverture d'applications, sites et fenêtres
- Recherche Web publique et extraction de texte de pages
- Gestion de fichiers dans les dossiers autorisés, lecture de PDF/texte
- Souris, clavier, défilement et captures d'écran avec confirmation pour les actions sensibles

## Sécurité

Pas de shell libre ni de connexion à des comptes par l'agent. Le lecteur Web limite l'accès aux hôtes publics, ports web standards, pages HTML/texte et tailles raisonnables ; il ne soumet aucun formulaire. Les opérations sensibles sur fichiers demandent confirmation.

## Obtenir l'EXE

Après un push sur `main`, ouvre l'exécution la plus récente dans l'onglet Actions, puis télécharge l'artifact `Polaris-Windows`. Le build automatique ne télécharge pas l'EXE sur ton ordinateur : il faut encore récupérer l'artifact. La clé Gemini est nécessaire pour les réponses et recherches effectuées par le modèle, sauf recherche Web simple en mode hors Gemini.
