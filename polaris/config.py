"""Configuration portable et fiable de Polaris (dossier data près de l'exe)."""
import base64
import ctypes
import json
import os
import sys
import tempfile
from ctypes import wintypes
from datetime import datetime
from pathlib import Path


def base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


def resource_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(getattr(sys, "_MEIPASS", base_dir()))
    return base_dir()


def _writable_directory(path: Path) -> bool:
    try:
        path.mkdir(parents=True, exist_ok=True)
        fd, probe = tempfile.mkstemp(prefix=".polaris-write-test-", dir=str(path))
        os.close(fd)
        Path(probe).unlink(missing_ok=True)
        return True
    except OSError:
        return False


def _data_dir() -> Path:
    # Garder le mode portable lorsque le dossier de l'exe est accessible en écriture.
    portable = base_dir() / "data"
    if _writable_directory(portable):
        return portable
    # Un exe placé dans Program Files ou un dossier protégé ne doit pas perdre ses réglages.
    local = Path(os.environ.get("LOCALAPPDATA", Path.home())) / "Polaris" / "data"
    if _writable_directory(local):
        return local
    # Dernier recours pour les environnements où LOCALAPPDATA n'est pas défini.
    fallback = Path.home() / ".polaris" / "data"
    fallback.mkdir(parents=True, exist_ok=True)
    return fallback


DATA = _data_dir()
CFG = DATA / "config.json"
LOG = DATA / "actions.log"
DEFAULT_MODEL = "gemini-2.5-flash"


def load() -> dict:
    try:
        value = json.loads(CFG.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {}
    except (OSError, ValueError, TypeError):
        return {}


def save(cfg: dict) -> None:
    """Écriture atomique : une fermeture pendant l'enregistrement ne corrompt pas la config."""
    DATA.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix="config-", suffix=".tmp", dir=str(DATA))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(cfg, stream, indent=2, ensure_ascii=False)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, CFG)
    except Exception:
        try:
            os.unlink(temporary)
        except OSError:
            pass
        raise


def get(key: str, default=None):
    return load().get(key, default)


def put(key: str, value) -> None:
    cfg = load()
    cfg[key] = value
    save(cfg)


class _BLOB(ctypes.Structure):
    _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_ubyte))]


def _blob(data: bytes):
    buf = ctypes.create_string_buffer(data, len(data))
    blob = _BLOB(len(data), ctypes.cast(buf, ctypes.POINTER(ctypes.c_ubyte)))
    return blob, buf


def _protect(data: bytes, decrypt: bool) -> bytes:
    if sys.platform != "win32":
        raise OSError("Le chiffrement DPAPI est disponible uniquement sous Windows.")
    crypt32 = ctypes.windll.crypt32
    kernel32 = ctypes.windll.kernel32
    crypt32.CryptProtectData.argtypes = [ctypes.POINTER(_BLOB), wintypes.LPCWSTR,
                                         ctypes.POINTER(_BLOB), ctypes.c_void_p,
                                         ctypes.c_void_p, wintypes.DWORD,
                                         ctypes.POINTER(_BLOB)]
    crypt32.CryptProtectData.restype = wintypes.BOOL
    crypt32.CryptUnprotectData.argtypes = [ctypes.POINTER(_BLOB), ctypes.c_void_p,
                                           ctypes.POINTER(_BLOB), ctypes.c_void_p,
                                           ctypes.c_void_p, wintypes.DWORD,
                                           ctypes.POINTER(_BLOB)]
    crypt32.CryptUnprotectData.restype = wintypes.BOOL
    kernel32.LocalFree.argtypes = [ctypes.c_void_p]
    kernel32.LocalFree.restype = ctypes.c_void_p

    in_blob, keepalive = _blob(data)
    out_blob = _BLOB()
    function = crypt32.CryptUnprotectData if decrypt else crypt32.CryptProtectData
    if not function(ctypes.byref(in_blob), None, None, None, None, 0, ctypes.byref(out_blob)):
        raise ctypes.WinError()
    try:
        return ctypes.string_at(out_blob.pbData, out_blob.cbData)
    finally:
        kernel32.LocalFree(ctypes.cast(out_blob.pbData, ctypes.c_void_p))


def get_api_key() -> str:
    encoded = get("api_key_enc", "")
    if not encoded:
        return ""
    try:
        return _protect(base64.b64decode(encoded, validate=True), True).decode("utf-8")
    except Exception:
        return ""


def set_api_key(key: str) -> None:
    key = key.strip()
    encrypted = base64.b64encode(_protect(key.encode("utf-8"), False)).decode("ascii") if key else ""
    put("api_key_enc", encrypted)


def log_action(text: str) -> None:
    """Journal des actions effectuées (tronqué automatiquement)."""
    try:
        if LOG.exists() and LOG.stat().st_size > 500_000:
            LOG.unlink()
        with LOG.open("a", encoding="utf-8") as stream:
            stream.write(f"{datetime.now():%Y-%m-%d %H:%M:%S}  {text}\n")
    except OSError:
        pass
