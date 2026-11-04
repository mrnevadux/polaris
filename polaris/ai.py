"""Cerveau de Polaris : Gemini (API REST) + boucle d'outils contrôlés."""
import json
import re
import urllib.error
import urllib.request
from datetime import datetime

from . import config, tools

MAX_STEPS = 8


class GeminiError(Exception):
    pass


def _friendly(code: int, body: str) -> str:
    try:
        detail = json.loads(body)["error"]["message"]
    except Exception:
        detail = body[:200]
    if code == 429:
        return "Limite d'utilisation Gemini atteinte (quota ou crédits). Réessaie plus tard."
    if code in (401, 403) or "API key" in detail:
        return "Clé API Gemini refusée. Vérifie-la dans les réglages."
    if code == 404:
        return "Modèle Gemini introuvable. Change le nom du modèle dans les réglages."
    if code >= 500:
        return "Gemini est temporairement indisponible. Réessaie dans un instant."
    return f"Erreur Gemini ({code}) : {detail}"


def _call(api_key: str, model: str, body: dict) -> dict:
    req = urllib.request.Request(
        f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json", "x-goog-api-key": api_key},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        raise GeminiError(_friendly(e.code, e.read().decode("utf-8", "ignore")))
    except (urllib.error.URLError, TimeoutError, OSError):
        raise GeminiError("Pas de connexion à Gemini. Les commandes locales (ouvrir une appli, chercher un fichier) restent possibles.")


def _system() -> str:
    now = datetime.now().strftime("%A %d %B %Y, %H:%M")
    return f"""Tu es POLARIS, un assistant vocal personnel inspiré de JARVIS, sur le PC Windows 11 de l'utilisateur. Nous sommes le {now}.
Tu parles français, de façon brève et naturelle. Tes réponses sont lues à voix haute : pas de markdown, pas de listes, pas d'URL longues.
Tu peux agir sur le PC UNIQUEMENT avec les outils fournis. Règles strictes :
- N'affirme JAMAIS qu'une action a réussi si le résultat de l'outil dit le contraire ou si tu ne peux pas le vérifier. Dis honnêtement ce qui a échoué.
- Les actions risquées (fermer une fenêtre, renommer, déplacer) demandent une confirmation gérée par les outils. Tu ne peux rien supprimer.
- Pour la culture générale, les explications, la rédaction, la programmation : réponds directement sans outil.
- Pour résumer un document : find_files, puis read_file, puis résume."""


class Agent:
    def __init__(self, confirm, on_action, on_status):
        self.confirm = confirm          # confirm(question) -> bool
        self.on_action = on_action      # on_action(texte) pour l'interface
        self.on_status = on_status      # on_status(True/False, message)
        self.history: list[dict] = []

    def _offline(self, text: str) -> str:
        """Commandes locales de base quand Gemini est injoignable (« ouvre … », « cherche … sur internet »)."""
        t = text.lower().strip().rstrip(".!?")
        m = re.match(r"^(?:ouvre|ouvrir|lance|lancer)\s+(?:le |la |l'|les |l’)?(.+)$", t)
        if m:
            config.log_action(f"offline open_app {m.group(1)}")
            return "Commande locale : " + tools.execute("open_app", {"name": m.group(1)}, self.confirm)
        m = re.match(r"^(?:cherche|recherche|trouve)\s+(?:mon |ma |mes |le |la |les )?(?:fichier |fichiers )?(.+)$", t)
        if m:
            config.log_action(f"offline find_files {m.group(1)}")
            return "Commande locale : " + tools.execute("find_files", {"query": m.group(1)}, self.confirm)
        return ""

    def handle(self, text: str) -> str:
        key = config.get_api_key()
        if not key:
            self.on_status(False, "clé manquante")
            return "Il me faut ta clé API Gemini. Ouvre les réglages de Polaris pour l'ajouter."
        model = config.get("model", config.DEFAULT_MODEL)
        contents = list(self.history) + [{"role": "user", "parts": [{"text": text}]}]
        for _ in range(MAX_STEPS):
            body = {
                "systemInstruction": {"parts": [{"text": _system()}]},
                "contents": contents,
                "tools": [{"functionDeclarations": tools.DECLARATIONS}],
                "generationConfig": {"temperature": 0.4},
            }
            try:
                resp = _call(key, model, body)
            except GeminiError as e:
                self.on_status(False, "erreur")
                local = self._offline(text)
                return f"{e} {local}" if local else str(e)
            self.on_status(True, "connecté")
            cands = resp.get("candidates") or []
            content = cands[0].get("content") if cands else None
            parts = (content or {}).get("parts")
            if not parts:
                return "Gemini n'a pas pu répondre à cette demande."
            calls = [p["functionCall"] for p in parts if "functionCall" in p]
            if not calls:
                answer = "".join(p.get("text", "") for p in parts if not p.get("thought")).strip() or "Je n'ai rien à ajouter."
                self.history += [{"role": "user", "parts": [{"text": text}]}, {"role": "model", "parts": [{"text": answer}]}]
                self.history = self.history[-16:]
                return answer
            contents.append(content)
            results = []
            for c in calls:
                name, args = c["name"], c.get("args", {})
                self.on_action(f"→ {name} {json.dumps(args, ensure_ascii=False)[:120]}")
                config.log_action(f"{name} {json.dumps(args, ensure_ascii=False)}")
                try:
                    res = tools.execute(name, args, self.confirm)
                except Exception as e:
                    res = f"Échec : {e}"
                res = res[:6000]
                config.log_action("   = " + res[:200].replace("\n", " "))
                results.append({"functionResponse": {"name": name, "response": {"result": res}}})
            contents.append({"role": "user", "parts": results})
        return "J'ai atteint ma limite d'étapes pour cette demande. Dis-moi si je dois continuer."
