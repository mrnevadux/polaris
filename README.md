# POLARIS — assistant vocal IA pour Windows 11

Dis « Hey Polaris » : il t'écoute (détection locale), réfléchit avec Gemini, agit sur ton PC et te répond à voix haute.

## Obtenir Polaris.exe (compilation sur GitHub, rien à installer sur ton PC)

1. Crée un dépôt GitHub privé et envoie-y tout le contenu de ce dossier (y compris le dossier caché `.github`).
2. Onglet **Actions** > **Build Polaris Windows (Polaris.exe)** > **Run workflow**.
3. Après ~6 à 10 minutes : en bas de l'exécution, **Artifacts** > télécharge `Polaris-Windows`.
4. Dézippe où tu veux (Bureau, clé USB…) et lance `Polaris\Polaris.exe`.

Application portable : tout (réglages, journal) est dans le dossier `data` à côté de l'exe. Supprimer le dossier supprime tout.
Aucun registre modifié, aucun démarrage automatique, Windows Defender intact.

Windows SmartScreen peut afficher « Windows a protégé votre PC » car l'exe n'est pas signé : « Informations complémentaires » > « Exécuter quand même ».
Si Defender signale un faux positif (courant avec PyInstaller), restaure le fichier ; ne désactive jamais Defender.

## Première utilisation
1. Réglages : colle ta clé API Gemini (https://aistudio.google.com/apikey). Elle est chiffrée avec ta session Windows (DPAPI).
2. « Activer le micro » (ou clique l'orbe), puis dis « Hey Polaris, ouvre le Bloc-notes ».
3. Bouton rouge **ARRÊT IMMÉDIAT DU MICRO** : coupe et libère le micro tout de suite.

## Ce qu'il sait faire
Ouvrir des logiciels (Bloc-notes, Calculatrice, Explorateur, Paramètres, tout ce qui est dans le menu Démarrer), lister/réduire/agrandir/fermer des fenêtres,
ouvrir des sites, chercher sur Google, chercher des fichiers (nom, extension, contenu texte et PDF) dans Bureau/Documents/Téléchargements/Images/Musique/Vidéos,
ouvrir, lire et résumer des documents, renommer/déplacer des fichiers, répondre à tes questions, rédiger, aider à programmer.

## Sécurité
- Mot de réveil détecté localement (Vosk) ; aucun son enregistré ni envoyé. Seul le texte de ta commande part vers Gemini.
- Gemini ne peut appeler QUE les outils de `polaris/tools.py` : pas de commande libre, **aucune suppression de fichier**.
- Confirmation « oui / non » (voix ou bouton) avant fermer une fenêtre, renommer ou déplacer. Jamais d'écrasement.
- Accès limité aux dossiers utilisateur listés ; aucun envoi de fichier sans que tu le demandes.
- Journal : `data/actions.log`. Indicateur RAM/CPU en bas, mode économie dans les réglages.

## Limites honnêtes
- Je n'ai pas pu compiler ni tester ce programme là où je l'ai écrit (pas de Windows ici) : si GitHub affiche une erreur, copie le message à Claude pour correction.
- Le modèle vocal français « small » comprend parfois mal « Polaris » : parle clairement, ou écris ta commande.
- Pas de contrôle de la souris/clavier dans les logiciels (seulement lancer, gérer les fenêtres, fichiers, web). Cela demanderait une couche supplémentaire.
- Les applis du Microsoft Store absentes du menu Démarrer classique peuvent ne pas être trouvées.
- Sans Internet, seules deux commandes locales simples marchent (« ouvre … », « cherche … » pour un fichier) ; tout le reste demande Gemini.
- Mesure RAM/CPU affichée en direct ; je ne promets pas zéro consommation : le micro actif et le modèle vocal utilisent un peu de CPU.
