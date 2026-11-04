"""Liste FERMÉE des actions contrôlées par Gemini.

Le but n'est pas de donner un shell libre : nous exposons uniquement des outils
précis, autorisés et vérifiables. Les actions grasses comme le clavier/souris
peuvent demander une confirmation explicite avant exécution.
"""
import ctypes
import os
import shutil
import subprocess
import unicodedata
import webbrowser
from datetime import datetime
from pathlib import Path
from urllib.parse import quote_plus

from . import config

try:
    import pyautogui
except Exception:  # pragma: no cover - dépendance Windows uniquement
    pyautogui = None

HOME = Path.home()
DEFAULT_FOLDERS = {
    "desktop": HOME / "Desktop",
    "bureau": HOME / "Desktop",
    "documents": HOME / "Documents",
    "downloads": HOME / "Downloads",
    "telechargements": HOME / "Downloads",
    "images": HOME / "Pictures",
    "photos": HOME / "Pictures",
    "musique": HOME / "Music",
    "videos": HOME / "Videos",
}
TEXT_EXT = {
    ".txt", ".md", ".csv", ".json", ".xml", ".html", ".py", ".js", ".ts", ".java", ".c",
    ".cpp", ".h", ".log", ".ini", ".yml", ".yaml", ".sql", ".css", ".kt", ".bat"
}
BUILTIN_APPS = {
    "bloc notes": "notepad.exe",
    "notepad": "notepad.exe",
    "calculatrice": "calc.exe",
    "explorateur": "explorer.exe",
    "explorateur de fichiers": "explorer.exe",
    "parametres": "ms-settings:",
    "gestionnaire des taches": "taskmgr.exe",
    "paint": "mspaint.exe",
    "outil capture": "snippingtool.exe",
}


def norm(s: str) -> str:
    s = unicodedata.normalize("NFD", s.lower())
    return "".join(c for c in s if not unicodedata.combining(c)).replace("-", " ").replace("_", " ").strip()


def _allowed_roots() -> list[Path]:
    roots = {p.resolve() for p in DEFAULT_FOLDERS.values() if p.exists()}
    for extra in config.get("extra_folders", []):
        p = Path(extra)
        if p.exists():
            roots.add(p.resolve())
    return list(roots)


def _check_path(path: str) -> Path | None:
    try:
        p = Path(path).resolve()
    except Exception:
        return None
    if p.is_file() and any(p == r or r in p.parents for r in _allowed_roots()):
        return p
    return None


def _fn(fname, desc, /, **params):
    d = {"name": fname, "description": desc}
    if params:
        d["parameters"] = {
            "type": "object",
            "properties": {k: {"type": v[0], "description": v[1]} for k, v in params.items()},
            "required": [k for k, v in params.items() if v[2]],
        }
    return d


DECLARATIONS = [
    _fn("open_app", "Ouvre un logiciel installé d'après son nom (Bloc-notes, Calculatrice, Chrome, Word, Spotify, Paramètres…).",
        name=("string", "Nom du logiciel", True)),
    _fn("list_windows", "Liste les fenêtres ouvertes."),
    _fn("window_action", "Agit sur une fenêtre ouverte.",
        title=("string", "Partie du titre de la fenêtre", True),
        action=("string", "minimize, maximize, restore, focus ou close (close demande confirmation)", True)),
    _fn("open_url", "Ouvre un site web (http/https) dans le navigateur.", url=("string", "Adresse", True)),
    _fn("web_search", "Lance une recherche Google dans le navigateur.", query=("string", "Termes", True)),
    _fn("find_files", "Cherche des fichiers dans Bureau, Documents, Téléchargements, Images, Musique, Vidéos.",
        query=("string", "Mots du nom du fichier", False),
        extension=("string", "Extension sans point (pdf, jpg, py…)", False),
        folder=("string", "desktop, documents, downloads, images, musique, videos ou vide pour tout", False),
        content=("string", "Mot à chercher dans le contenu (texte et PDF)", False)),
    _fn("open_file", "Ouvre un fichier trouvé avec find_files.", path=("string", "Chemin complet", True)),
    _fn("read_file", "Lit le début d'un fichier texte ou PDF pour le résumer ou l'expliquer.", path=("string", "Chemin complet", True)),
    _fn("rename_file", "Renomme un fichier (confirmation demandée, n'écrase jamais).",
        path=("string", "Chemin complet", True), new_name=("string", "Nouveau nom avec extension", True)),
    _fn("move_file", "Déplace un fichier dans un dossier autorisé (confirmation demandée, n'écrase jamais).",
        path=("string", "Chemin complet", True), folder=("string", "desktop, documents, downloads, images, musique ou videos", True)),
    _fn("get_time", "Donne la date et l'heure actuelles."),
    _fn("mouse_move", "Déplace la souris vers une position absolue en pixels.",
        x=("integer", "Coordonnée X", True), y=("integer", "Coordonnée Y", True), duration=("number", "Durée de l'animation en secondes", False)),
    _fn("mouse_click", "Clique sur la position actuelle ou sur une coordonnée donnée.",
        x=("integer", "Coordonnée X", False), y=("integer", "Coordonnée Y", False), button=("string", "left, right ou middle", False)),
    _fn("mouse_double_click", "Double-clic sur la position actuelle ou sur une coordonnée donnée.",
        x=("integer", "Coordonnée X", False), y=("integer", "Coordonnée Y", False)),
    _fn("mouse_scroll", "Fait défiler la page active.", amount=("integer", "Nombre de pas de scroll", True)),
    _fn("keyboard_write", "Écrit du texte dans l'application active.", text=("string", "Texte à taper", True)),
    _fn("keyboard_hotkey", "Envoie une combinaison de touches.", keys=("string", "Exemple: ctrl,alt,t ou ctrl,shift,esc", True)),
    _fn("get_screen_size", "Renvoie la résolution de l'écran."),
    _fn("capture_screen", "Prend une capture d'écran et la sauve dans le dossier Downloads.",
        name=("string", "Nom du fichier sans extension", False)),
    _fn("list_devices", "Tente de détecter les périphériques et clients réseau compatibles présents sur le PC ou le réseau local."),
]


def execute(name: str, a: dict, confirm) -> str:
    """confirm(question) -> bool, bloquant, demande oui/non à l'utilisateur."""
    try:
        if name == "open_app":
            return open_app(a["name"])
        if name == "list_windows":
            return list_windows()
        if name == "window_action":
            return window_action(a["title"], a["action"], confirm)
        if name == "open_url":
            return open_url(a["url"])
        if name == "web_search":
            return open_url("https://www.google.com/search?q=" + quote_plus(a["query"]))
        if name == "find_files":
            return find_files(a.get("query", ""), a.get("extension", ""), a.get("folder", ""), a.get("content", ""))
        if name == "open_file":
            return open_file(a["path"])
        if name == "read_file":
            return read_file(a["path"])
        if name == "rename_file":
            return rename_file(a["path"], a["new_name"], confirm)
        if name == "move_file":
            return move_file(a["path"], a["folder"], confirm)
        if name == "get_time":
            return datetime.now().strftime("%A %d %B %Y, %H:%M")
        if name == "mouse_move":
            return mouse_move(int(a["x"]), int(a["y"]), float(a.get("duration", 0.2)))
        if name == "mouse_click":
            return mouse_click(a.get("x"), a.get("y"), a.get("button", "left"), confirm)
        if name == "mouse_double_click":
            return mouse_double_click(a.get("x"), a.get("y"), confirm)
        if name == "mouse_scroll":
            return mouse_scroll(int(a["amount"]))
        if name == "keyboard_write":
            return keyboard_write(a["text"], confirm)
        if name == "keyboard_hotkey":
            return keyboard_hotkey(a["keys"], confirm)
        if name == "get_screen_size":
            return get_screen_size()
        if name == "capture_screen":
            return capture_screen(a.get("name", "polaris_capture"), confirm)
        if name == "list_devices":
            return list_devices()
        return f"Outil inconnu : {name} (refusé)."
    except KeyError as e:
        return f"Paramètre manquant : {e}"
    except Exception as e:
        return f"Échec : {e}"


def open_app(wanted: str) -> str:
    q = norm(wanted)
    if q in BUILTIN_APPS:
        target = BUILTIN_APPS[q]
        if target.endswith(":"):
            os.startfile(target)
        else:
            subprocess.Popen([target])
        return f"« {wanted} » lancé."
    roots = [
        Path(os.environ.get("ProgramData", "")) / "Microsoft/Windows/Start Menu/Programs",
        Path(os.environ.get("APPDATA", "")) / "Microsoft/Windows/Start Menu/Programs",
    ]
    best, best_score = None, 0
    for r in roots:
        if not r.exists():
            continue
        for lnk in r.rglob("*.lnk"):
            n = norm(lnk.stem)
            score = 3 if n == q else 2 if n.startswith(q) or q.startswith(n) else 1 if q in n or n in q else 0
            if score > best_score:
                best, best_score = lnk, score
    if best is None:
        return f"Aucun logiciel « {wanted} » trouvé dans le menu Démarrer."
    os.startfile(str(best))
    return f"« {best.stem} » lancé (vérifie avec list_windows)."


def open_url(raw: str) -> str:
    url = raw if raw.startswith(("http://", "https://")) else "https://" + raw
    webbrowser.open(url)
    return f"Navigateur ouvert sur {url}."


# --- souris / clavier / écran ---
def _require_pyautogui():
    if pyautogui is None:
        raise RuntimeError("Le module pyautogui n'est pas installé. Ajoute-le dans requirements.txt.")
    return pyautogui


def mouse_move(x: int, y: int, duration: float = 0.2) -> str:
    pg = _require_pyautogui()
    pg.moveTo(x, y, duration=max(0.0, float(duration)))
    return f"Souris déplacée vers ({x}, {y})."


def mouse_click(x: int | None, y: int | None, button: str = "left", confirm=None) -> str:
    if x is not None and y is not None:
        if confirm is not None and not confirm(f"Cliquer à ({x}, {y}) avec le bouton {button} ?"):
            return "Refusé par l'utilisateur."
        pg = _require_pyautogui(); pg.click(x=x, y=y, button=button)
        return f"Clic {button} envoyé à ({x}, {y})."
    if confirm is not None and not confirm(f"Cliquer avec le bouton {button} sur la position actuelle ?"):
        return "Refusé par l'utilisateur."
    pg = _require_pyautogui(); pg.click(button=button)
    return f"Clic {button} sur la position actuelle."


def mouse_double_click(x: int | None, y: int | None, confirm=None) -> str:
    if x is not None and y is not None:
        if confirm is not None and not confirm(f"Double-clic à ({x}, {y}) ?"):
            return "Refusé par l'utilisateur."
        pg = _require_pyautogui(); pg.doubleClick(x=x, y=y)
        return f"Double-clic envoyé à ({x}, {y})."
    if confirm is not None and not confirm("Double-clic sur la position actuelle ?"):
        return "Refusé par l'utilisateur."
    pg = _require_pyautogui(); pg.doubleClick()
    return "Double-clic sur la position actuelle."


def mouse_scroll(amount: int) -> str:
    pg = _require_pyautogui(); pg.scroll(int(amount))
    return f"Scroll de {amount} pas envoyé."


def keyboard_write(text: str, confirm=None) -> str:
    if confirm is not None and not confirm(f"Taper le texte suivant dans l'application active ?\n\n{text[:200]}"):
        return "Refusé par l'utilisateur."
    pg = _require_pyautogui(); pg.write(text)
    return "Texte tapé dans l'application active."


def keyboard_hotkey(keys: str, confirm=None) -> str:
    if confirm is not None and not confirm(f"Appuyer la combinaison {keys} ?"):
        return "Refusé par l'utilisateur."
    pg = _require_pyautogui(); pg.hotkey(*[part.strip() for part in keys.split(",") if part.strip()])
    return f"Combinaison {keys} envoyée."


def get_screen_size() -> str:
    pg = _require_pyautogui(); w, h = pg.size(); return f"Résolution écran : {w}x{h}."


def capture_screen(name: str = "polaris_capture", confirm=None) -> str:
    if confirm is not None and not confirm("Prendre une capture d'écran du bureau ?"):
        return "Refusé par l'utilisateur."
    pg = _require_pyautogui();
    target_dir = DEFAULT_FOLDERS.get("downloads", HOME / "Downloads")
    target_dir.mkdir(parents=True, exist_ok=True)
    safe_name = (name or "polaris_capture").strip() or "polaris_capture"
    file_path = target_dir / f"{safe_name}_{datetime.now():%Y%m%d_%H%M%S}.png"
    pg.screenshot(str(file_path))
    return f"Capture enregistrée : {file_path}."


def list_devices() -> str:
    # Version réaliste et prudente : on ne prétend pas contrôler des appareils sans interface compatible.
    info = [
        "Bluetooth = détection passive si un adaptateur bluetooth est présent.",
        "Wi‑Fi / réseau local = détection des hôtes visibles après autorisation réseau.",
        "Chromecast / DLNA / UPnP = exposition possible uniquement si le service est activé dans le réseau local.",
        "Miracast = disponible seulement si le système d'exploitation et le périphérique le supportent.",
        "Aucun appareil n'est affirmé comme contrôlé sans interface de commande compatible.",
    ]
    return "\n".join(info)


# --- fenêtres (ctypes, sans dépendance) ---
def _windows():
    user32 = ctypes.windll.user32
    found = []

    @ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)
    def cb(hwnd, _):
        if user32.IsWindowVisible(hwnd):
            n = user32.GetWindowTextLengthW(hwnd)
            if n > 0:
                buf = ctypes.create_unicode_buffer(n + 1)
                user32.GetWindowTextW(hwnd, buf, n + 1)
                text = buf.value.strip()
                if text not in ("Program Manager", "Settings") and text:
                    found.append((hwnd, text))
        return True

    user32.EnumWindows(cb, 0)
    return found


def list_windows() -> str:
    w = _windows()
    return "\n".join(t for _, t in w) if w else "Aucune fenêtre visible."


def window_action(title: str, action: str, confirm) -> str:
    user32 = ctypes.windll.user32
    matches = [(h, t) for h, t in _windows() if norm(title) in norm(t) and "polaris" not in norm(t)]
    if not matches:
        return f"Aucune fenêtre « {title} »."
    hwnd, full = matches[0]
    action = action.lower()
    if action == "close":
        if not confirm(f"Je vais fermer la fenêtre « {full} ». Les modifications non enregistrées peuvent être perdues. Tu confirmes ?"):
            return "Refusé par l'utilisateur : rien n'a été fermé."
        user32.PostMessageW(hwnd, 0x0010, 0, 0)
        return f"Demande de fermeture envoyée à « {full} »."
    codes = {"minimize": 6, "maximize": 3, "restore": 9, "focus": 9}
    if action not in codes:
        return "Action inconnue."
    user32.ShowWindow(hwnd, codes[action])
    user32.SetForegroundWindow(hwnd)
    return f"« {full} » : {action} effectué."


# --- fichiers ---
def find_files(query: str, ext: str, folder: str, content: str) -> str:
    folder_key = norm(folder)
    roots = [DEFAULT_FOLDERS[folder_key]] if folder_key in DEFAULT_FOLDERS else _allowed_roots()
    words = [w for w in norm(query).split() if w]
    ext = ext.lower().strip(".")
    content = content.lower()
    if not (words or ext or content):
        return "Précise un nom, une extension ou un mot du contenu."
    found, visited = [], 0
    for root in roots:
        for dirpath, dirnames, files in os.walk(root):
            dirnames[:] = [d for d in dirnames if not d.startswith((".", "$")) and d.lower() not in ("node_modules", "appdata")]
            for f in files:
                visited += 1
                if visited > 80_000 or len(found) >= 150:
                    break
                p = Path(dirpath) / f
                n = norm(f)
                if any(w not in n for w in words):
                    continue
                if ext and p.suffix.lower().strip(".") != ext:
                    continue
                if content and content not in _text_of(p, 600_000).lower():
                    continue
                found.append(p)
    if not found:
        return "Aucun fichier trouvé."
    found.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return "\n".join(f"{p} ({datetime.fromtimestamp(p.stat().st_mtime):%d/%m/%Y}, {p.stat().st_size // 1024} Ko)" for p in found[:15])


def _text_of(p: Path, limit: int) -> str:
    try:
        s = p.suffix.lower()
        if s in TEXT_EXT and p.stat().st_size <= 2_000_000:
            return p.read_text(encoding="utf-8", errors="ignore")[:limit]
        if s == ".pdf" and p.stat().st_size <= 30_000_000:
            from pypdf import PdfReader
            r = PdfReader(str(p))
            return "\n".join((pg.extract_text() or "") for pg in r.pages[:15])[:limit]
    except Exception:
        pass
    return ""


def open_file(path: str) -> str:
    p = _check_path(path)
    if not p:
        return "Fichier introuvable ou hors des dossiers autorisés."
    os.startfile(str(p))
    return f"« {p.name} » ouvert."


def read_file(path: str) -> str:
    p = _check_path(path)
    if not p:
        return "Fichier introuvable ou hors des dossiers autorisés."
    t = _text_of(p, 15_000)
    return t if t.strip() else "Je ne sais lire que les fichiers texte et les PDF contenant du texte (pas les images/scans)."


def rename_file(path: str, new_name: str, confirm) -> str:
    p = _check_path(path)
    if not p:
        return "Fichier introuvable ou hors des dossiers autorisés."
    if any(c in new_name for c in '\\/:*?\"<>|'):
        return "Nom invalide."
    dest = p.with_name(new_name)
    if dest.exists():
        return "Un fichier porte déjà ce nom : rien n'a été fait."
    if not confirm(f"Renommer « {p.name} » en « {new_name} » ?"):
        return "Refusé par l'utilisateur."
    p.rename(dest)
    return f"Renommé en « {new_name} »."


def move_file(path: str, folder: str, confirm) -> str:
    p = _check_path(path)
    target = DEFAULT_FOLDERS.get(norm(folder))
    if not p or not target:
        return "Fichier ou dossier invalide."
    dest = target / p.name
    if dest.exists():
        return "Un fichier du même nom existe déjà là-bas : rien n'a été fait."
    if not confirm(f"Déplacer « {p.name} » vers {target.name} ?"):
        return "Refusé par l'utilisateur."
    shutil.move(str(p), str(dest))
    return f"Déplacé vers {target.name}."
