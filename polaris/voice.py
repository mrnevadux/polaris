"""Micro (détection locale du mot de réveil avec Vosk) et voix (pyttsx3).
Le son n'est jamais enregistré sur disque ni envoyé sur Internet."""
import json
import queue
import re
import threading
import time
import unicodedata

from . import config

WAKE_VARIANTS = ["polaris", "pola ris", "pollaris", "polarisse", "pola riz", "polaire", "polari"]
YES = {"oui", "ouais", "confirme", "confirmer", "ok", "okay", "daccord", "yes", "vasy"}
NO = {"non", "annule", "annuler", "stop", "refuse", "nan", "no"}


def norm(s: str) -> str:
    s = unicodedata.normalize("NFD", s.lower())
    s = "".join(c for c in s if not unicodedata.combining(c)).replace("-", " ").replace("'", "").replace("’", "")
    return re.sub(r"[^a-z0-9 ]", "", s).strip()


class TTS:
    """Un seul thread dédié à la synthèse vocale (pyttsx3 n'aime pas le multi-thread)."""

    def __init__(self):
        self.q: queue.Queue = queue.Queue()
        self.enabled = True
        threading.Thread(target=self._run, daemon=True).start()

    def _run(self):
        try:
            import pyttsx3
            engine = pyttsx3.init()
            for v in engine.getProperty("voices"):
                blob = (v.id + " " + str(getattr(v, "name", ""))).lower()
                if "fr" in blob or "hortense" in blob or "french" in blob or "julie" in blob:
                    engine.setProperty("voice", v.id)
                    break
            engine.setProperty("rate", 185)
        except Exception:
            engine = None
        while True:
            text, done = self.q.get()
            try:
                if engine and self.enabled:
                    engine.say(re.sub(r"[*#`_>|~]|https?://\S+", " ", text)[:3500])
                    engine.runAndWait()
            except Exception:
                pass
            finally:
                done.set()

    def speak(self, text: str):
        """Parle et attend la fin."""
        done = threading.Event()
        self.q.put((text, done))
        done.wait(120)


class Voice:
    """Écoute en continu tant qu'elle est activée. start()/stop() ouvrent/ferment réellement le micro."""

    def __init__(self, model_path, on_command, on_confirm_answer, is_busy, confirm_pending, on_state, on_error):
        self.model_path = str(model_path)
        self.on_command = on_command
        self.on_confirm_answer = on_confirm_answer
        self.is_busy = is_busy
        self.confirm_pending = confirm_pending
        self.on_state = on_state      # "off" | "wake" | "command"
        self.on_error = on_error
        self.model = None
        self.stream = None
        self.audio: queue.Queue = queue.Queue(maxsize=50)
        self.thread = None
        self.running = False
        self.paused = False
        self.command_until = 0.0

    @property
    def active(self) -> bool:
        return self.running

    def pause(self, value: bool):
        self.paused = value
        if value:
            self._drain()

    def open_followup(self, seconds: float = 6.0):
        self.command_until = time.time() + seconds
        self.on_state("command")

    def _drain(self):
        try:
            while True:
                self.audio.get_nowait()
        except queue.Empty:
            pass

    def start(self, eco: bool = False):
        if self.running:
            return
        try:
            import sounddevice as sd
            from vosk import KaldiRecognizer, Model, SetLogLevel
            SetLogLevel(-1)
            if self.model is None:
                self.model = Model(self.model_path)
            rec = KaldiRecognizer(self.model, 16000)

            def cb(indata, frames, t, status):
                if not self.paused:
                    try:
                        self.audio.put_nowait(bytes(indata))
                    except queue.Full:
                        pass

            self.stream = sd.RawInputStream(samplerate=16000, blocksize=8000 if eco else 4000,
                                            dtype="int16", channels=1, callback=cb)
            self.stream.start()
        except Exception as e:
            self.on_error(f"Micro ou modèle vocal indisponible : {e}")
            self.stop()
            return
        self.running = True
        self.command_until = 0.0
        self.on_state("wake")
        self.thread = threading.Thread(target=self._loop, args=(rec,), daemon=True)
        self.thread.start()

    def stop(self):
        """Coupe immédiatement le micro et libère la ressource."""
        self.running = False
        self.command_until = 0.0
        s, self.stream = self.stream, None
        if s is not None:
            try:
                s.abort()
                s.close()
            except Exception:
                pass
        self._drain()
        self.on_state("off")

    def _loop(self, rec):
        while self.running:
            try:
                data = self.audio.get(timeout=0.3)
            except queue.Empty:
                if self.command_until and time.time() > self.command_until:
                    self.command_until = 0.0
                    self.on_state("wake")
                continue
            if rec.AcceptWaveform(data):
                text = json.loads(rec.Result()).get("text", "")
                if text.strip():
                    self._utterance(norm(text))

    def _utterance(self, t: str):
        if self.confirm_pending():
            words = t.split()
            if any(w in NO for w in words):
                self.on_confirm_answer(False)
            elif any(w in YES for w in words):
                self.on_confirm_answer(True)
            return
        if self.is_busy():
            return
        in_command = time.time() < self.command_until
        command = t
        if not in_command:
            hits = [t.index(v) + len(v) for v in WAKE_VARIANTS if v in t]
            if not hits:
                return
            command = t[min(hits):].strip()
            if len(command) < 3:
                self.open_followup(9.0)
                return
        self.command_until = 0.0
        self.on_state("wake")
        self.on_command(command)
