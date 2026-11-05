"""Cerveau de Polaris : Gemini (API REST) + boucle d'outils contrôlés."""
import json
import re
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime

from . import config, tools, web

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
        return f"Modèle Gemini introuvable ou indisponible pour cette clé : {detail}"
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
        with urllib.request.urlopen(req, timeout=60) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        raise GeminiError(_friendly(exc.code, exc.read().decode("utf-8", "ignore")))
    except (urllib.error.URLError, TimeoutError, OSError):
        raise GeminiError("Pas de connexion à Gemini. Les commandes locales et la recherche Web restent possibles.")


def _list_generate_content_models(api_key: str) -> list[str]:
    """Return models actually enabled for this API key and supporting generateContent."""
    models = []
    page_token = ""
    while True:
        url = "https://generativelanguage.googleapis.com/v1beta/models"
        if page_token:
            url += "?pageToken=" + urllib.parse.quote(page_token, safe="")
        request = urllib.request.Request(url, headers={"x-goog-api-key": api_key})
        try:
            with urllib.request.urlopen(request, timeout=20) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, OSError, ValueError):
            return []
        for item in payload.get("models", []):
            name = item.get("name", "")
            if name.startswith("models/"):
                name = name[len("models/"):]
            if name and "generateContent" in item.get("supportedGenerationMethods", item.get("supportedMethods", [])):
                models.append(name)
        page_token = payload.get("nextPageToken", "")
        if not page_token:
            break
    # Prefer a stable Flash model; otherwise use any compatible model returned for this key.
    preferred = ("gemini-2.5-flash", "gemini-2.0-flash", "gemini-1.5-flash")
    ordered = [name for name in preferred if name in models]
    ordered.extend(sorted(name for name in models if name not in ordered and "gemini" in name and "preview" not in name))
    ordered.extend(sorted(name for name in models if name not in ordered))
    return ordered


def _system() -> str:
    now = datetime.now().strftime("%A %d %B %Y, %H:%M")
    return f"""Tu es POLARIS, un assistant informatique personnel sur Windows. Nous sommes le {now}.
Tu parles français, de façon claire, et tu ne prétends jamais qu'une action a réussi sans résultat vérifiable.
Pour le Web public, tu peux réellement rechercher puis lire des pages avec web_search et read_webpage. Pour une question d'actualité ou une demande de recherche, utilise les résultats et cite les URL consultées. Si une page bloque l'accès, explique-le honnêtement.
Les outils Web ne se connectent pas à des comptes, ne soumettent pas de formulaires et ne réalisent pas d'achats. N'affirme pas avoir effectué ces actions.
Tu peux agir sur le PC UNIQUEMENT avec les outils fournis. Les actions risquées demandent confirmation. Pas de commande shell libre et pas de suppression de fichiers.
Pour résumer un document local : find_files, puis read_file, puis résume."""


class Agent:
    def __init__(self, confirm, on_action, on_status):
        self.confirm = confirm
        self.on_action = on_action
        self.on_status = on_status
        self.history: list[dict] = []

    def _offline(self, text: str) -> str:
        """Quelques commandes locales et de recherche publique sans Gemini."""
        t = text.lower().strip().rstrip(".!?")
        web_match = re.match(r"^(?:cherche|recherche|trouve)\s+(.+?)\s+(?:sur internet|sur le web|en ligne)$", t)
        if web_match:
            query = web_match.group(1).strip()
            config.log_action(f"offline web_search {query}")
            return web.execute("web_search", {"query": query})
        if t.startswith(("cherche sur internet ", "recherche sur internet ", "cherche sur le web ", "recherche sur le web ")):
            query = re.sub(r"^(?:cherche|recherche)\s+sur\s+(?:internet|le web)\s+", "", t).strip()
            return web.execute("web_search", {"query": query})
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
            local = self._offline(text)
            return local or "Il me faut ta clé API Gemini pour l'assistant IA. La recherche Web simple fonctionne aussi avec « cherche … sur internet »."
        model = config.get("model", config.DEFAULT_MODEL)
        contents = list(self.history) + [{"role": "user", "parts": [{"text": text}]}]
        declarations = tools.DECLARATIONS + web.DECLARATIONS
        for _ in range(MAX_STEPS):
            body = {
                "systemInstruction": {"parts": [{"text": _system()}]},
                "contents": contents,
                "tools": [{"functionDeclarations": declarations}],
                "generationConfig": {"temperature": 0.4},
            }
            try:
                try:
                    response = _call(key, model, body)
                except GeminiError as exc:
                    # If the saved/default model is unavailable for this key, discover
                    # eligible model IDs from Google's API and retry once per candidate.
                    if "Modèle Gemini introuvable" not in str(exc):
                        raise
                    available = [candidate for candidate in _list_generate_content_models(key) if candidate != model]
                    if not available:
                        raise
                    last_error = exc
                    response = None
                    for candidate in available:
                        try:
                            response = _call(key, candidate, body)
                            model = candidate
                            config.put("model", model)
                            self.on_action(f"Modèle Gemini sélectionné automatiquement : {model}")
                            break
                        except GeminiError as retry_error:
                            last_error = retry_error
                    if response is None:
                        raise last_error
            except GeminiError as exc:
                self.on_status(False, "erreur")
                local = self._offline(text)
                return f"{exc} {local}" if local else str(exc)
            self.on_status(True, "connecté")
            candidates = response.get("candidates") or []
            content = candidates[0].get("content") if candidates else None
            parts = (content or {}).get("parts")
            if not parts:
                return "Gemini n'a pas pu répondre à cette demande."
            calls = [part["functionCall"] for part in parts if "functionCall" in part]
            if not calls:
                answer = "".join(part.get("text", "") for part in parts if not part.get("thought")).strip() or "Je n'ai rien à ajouter."
                self.history += [{"role": "user", "parts": [{"text": text}]}, {"role": "model", "parts": [{"text": answer}]}]
                self.history = self.history[-16:]
                return answer
            contents.append(content)
            results = []
            for call in calls:
                name, args = call["name"], call.get("args", {})
                self.on_action(f"→ {name} {json.dumps(args, ensure_ascii=False)[:120]}")
                config.log_action(f"{name} {json.dumps(args, ensure_ascii=False)}")
                try:
                    result = web.execute(name, args) if name in web.TOOL_NAMES else tools.execute(name, args, self.confirm)
                except Exception as exc:
                    result = f"Échec : {exc}"
                result = result[:12000]
                config.log_action("   = " + result[:200].replace("\n", " "))
                results.append({"functionResponse": {"name": name, "response": {"result": result}}})
            contents.append({"role": "user", "parts": results})
        return "J'ai atteint ma limite d'étapes pour cette demande. Dis-moi si je dois continuer."
