"""Configuration portable : tout est dans le dossier « data » à côté de Polaris.exe.
Supprimer le dossier de Polaris supprime tout (aucun registre, aucun démarrage automatique)."""
import base64
import ctypes
import json
import sys
from ctypes import wintypes
from datetime import datetime
from pathlib import Path


def base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent.parent


def resource_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(getattr(sys, "_MEIPASS", base_dir()))
    return base_dir()


DATA = base_dir() / "data"
DATA.mkdir(exist_ok=True)
CFG = DATA / "config.json"
LOG = DATA / "actions.log"
DEFAULT_MODEL = "gemini-2.5-flash"


def load() -> dict:
    try:
        return json.loads(CFG.read_text(encoding="utf-8"))
    except Exception:
        return {}


def save(cfg: dict) -> None:
    CFG.write_text(json.dumps(cfg, indent=2), encoding="utf-8")


def get(key: str, default=None):
    return load().get(key, default)


def put(key: str, value) -> None:
    cfg = load()
    cfg[key] = value
    save(cfg)


# ---- Clé API chiffrée avec Windows DPAPI (liée à ta session Windows, illisible ailleurs) ----
class _BLOB(ctypes.Structure):
    _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_char))]


def _blob(data: bytes):
    buf = ctypes.create_string_buffer(data, len(data))
    return _BLOB(len(data), ctypes.cast(buf, ctypes.POINTER(ctypes.c_char))), buf


def _protect(data: bytes, decrypt: bool) -> bytes:
    crypt32, kernel32 = ctypes.windll.crypt32, ctypes.windll.kernel32
    inb, _keep = _blob(data)
    out = _BLOB()
    fn = crypt32.CryptUnprotectData if decrypt else crypt32.CryptProtectData
    ok = fn(ctypes.byref(inb), None, None, None, None, 0, ctypes.byref(out))
    if not ok:
        raise ctypes.WinError()
    try:
        return ctypes.string_at(out.pbData, out.cbData)
    finally:
        kernel32.LocalFree(out.pbData)


def get_api_key() -> str:
    enc = get("api_key_enc", "")
    if not enc:
        return ""
    try:
        return _protect(base64.b64decode(enc), True).decode("utf-8")
    except Exception:
        return ""


def set_api_key(key: str) -> None:
    key = key.strip()
    put("api_key_enc", base64.b64encode(_protect(key.encode("utf-8"), False)).decode() if key else "")


def log_action(text: str) -> None:
    """Journal des actions effectuées (tronqué automatiquement)."""
    try:
        if LOG.exists() and LOG.stat().st_size > 500_000:
            LOG.unlink()
        with LOG.open("a", encoding="utf-8") as f:
            f.write(f"{datetime.now():%Y-%m-%d %H:%M:%S}  {text}\n")
    except Exception:
        pass
