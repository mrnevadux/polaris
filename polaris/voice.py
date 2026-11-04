"""Micro (détection locale du mot de réveil avec Vosk) et voix (pyttsx3).
Le son n'est jamais enregistré sur disque ni envoyé sur Internet.
"""
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
            for voice in engine.getProperty("voices"):
                blob = (voice.id + " " + str(getattr(voice, "name", ""))).lower()
                if "fr" in blob or "hortense" in blob or "french" in blob or "julie" in blob:
                    engine.setProperty("voice", voice.id)
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
    """Écoute tant qu'elle est activée ; le micro reste ouvert entre les commandes."""

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
        """Met en pause la lecture du micro pendant la réponse vocale."""
        self.paused = value
        if value:
            self._drain()

    def resume_listening(self):
        """Reprend l'écoute après TTS en mode mot de réveil, sans réactiver un micro coupé."""
        if not self.running:
            return False
        # Écarte les derniers buffers capturés pendant la synthèse afin que Polaris
        # ne prenne pas sa propre voix pour une commande utilisateur.
        self.paused = True
        self._drain()
        self.command_until = 0.0
        self.paused = False
        self.on_state("wake")
        return True

    def open_followup(self, seconds: float = 6.0):
        """Fenêtre courte permettant une commande suivante sans répéter le mot de réveil."""
        if not self.running:
            return
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
            recognizer = KaldiRecognizer(self.model, 16000)

            def callback(indata, frames, timing, status):
                if not self.paused:
                    try:
                        self.audio.put_nowait(bytes(indata))
                    except queue.Full:
                        pass

            self.stream = sd.RawInputStream(samplerate=16000, blocksize=8000 if eco else 4000,
                                            dtype="int16", channels=1, callback=callback)
            self.stream.start()
        except Exception as exc:
            self.on_error(f"Micro ou modèle vocal indisponible : {exc}")
            self.stop()
            return
        self.running = True
        self.paused = False
        self.command_until = 0.0
        self.on_state("wake")
        self.thread = threading.Thread(target=self._loop, args=(recognizer,), daemon=True)
        self.thread.start()

    def stop(self):
        """Coupe immédiatement le micro et libère la ressource."""
        self.running = False
        self.paused = True
        self.command_until = 0.0
        stream, self.stream = self.stream, None
        if stream is not None:
            try:
                stream.abort()
                stream.close()
            except Exception:
                pass
        self._drain()
        self.paused = False
        self.on_state("off")

    def _loop(self, recognizer):
        while self.running:
            try:
                data = self.audio.get(timeout=0.3)
            except queue.Empty:
                if self.command_until and time.time() > self.command_until:
                    self.command_until = 0.0
                    self.on_state("wake")
                continue
            if self.paused:
                continue
            try:
                if recognizer.AcceptWaveform(data):
                    text = json.loads(recognizer.Result()).get("text", "")
                    if text.strip():
                        self._utterance(norm(text))
            except Exception as exc:
                self.on_error(f"Erreur de reconnaissance vocale : {exc}")
                time.sleep(0.1)

    def _utterance(self, text: str):
        if not text:
            return
        if self.confirm_pending():
            words = text.split()
            if any(word in NO for word in words):
                self.on_confirm_answer(False)
            elif any(word in YES for word in words):
                self.on_confirm_answer(True)
            return
        if self.is_busy():
            return
        in_command = time.time() < self.command_until
        command = text
        if not in_command:
            hits = [text.index(variant) + len(variant) for variant in WAKE_VARIANTS if variant in text]
            if not hits:
                return
            command = text[min(hits):].strip()
            if len(command) < 3:
                self.open_followup(9.0)
                return
        self.command_until = 0.0
        self.on_state("wake")
        self.on_command(command)
