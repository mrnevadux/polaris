# POLARIS — assistant IA pour Windows

POLARIS est un assistant informatique autonome, pensé comme un agent du système, pas comme un simple chatbot.

## Ce que la version actuelle comprend

- Assistant vocal local (détection du mot de réveil avec Vosk)
- Interface graphique futuriste personnelle
- Gestion de fichiers locale dans les dossiers autorisés
- Ouverture d'applications et d'URL
- Recherche de fichiers et lecture de PDF / texte
- Contrôle minimal de fenêtres Windows
- Messages de confirmation avant les actions sensibles
- Prise de capture d'écran
- Contrôle souris / clavier / scroll via `pyautogui`
- Résolution écran et détection des dispositifs réseau compatibles

## Limites honnêtes

Les protocoles de télécommande avancée tels que Chromecast, Miracast, DLNA, TV connectées, imprimantes, domotique, NAS et appareils IoT demandent des intégrations spécifiques, des pilotes ou des appareils compatibles. POLARIS peut détecter et préparer cette utilisation, mais il ne peut pas affirmer un contrôle complet sans interface de commande compatible sur l'appareil.

## Sécurité

- Aucune suppression directe non confirmée.
- Aucun outil de shell libre.
- Les actions à risque demandent une confirmation explicite.
- Les clés API sont protégées et stockées localement.

## Build EXE

Le workflow GitHub Actions compile l'application en `Polaris.exe` avec PyInstaller. Le dossier `data` est créé à côté de l'exe, ou dans `%LOCALAPPDATA%/Polaris/data` si le dossier d'exécution est protégé.
