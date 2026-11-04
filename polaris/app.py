"""Interface Polaris (CustomTkinter) : orbe animée, chat, micro, réglages, RAM/CPU."""
import math
import os
import queue
import threading
import time

import customtkinter as ctk
import psutil

from . import config
from .ai import Agent
from .voice import TTS, Voice

CYAN, BLUE, BG, PANEL, DIM, RED = "#00E5FF", "#2979FF", "#05080F", "#0B1220", "#7C8BA3", "#FF6E6E"


class Confirmation:
    def __init__(self, question: str):
        self.question = question
        self.event = threading.Event()
        self.result = False


class PolarisApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        ctk.set_appearance_mode("dark")
        self.title("POLARIS")
        self.geometry("760x720")
        self.minsize(520, 560)
        self.configure(fg_color=BG)

        self.ui_q: queue.Queue = queue.Queue()
        self.busy_lock = threading.Lock()
        self.pending: Confirmation | None = None
        self.dialog = None
        self.mic_state = "off"
        self.activity = "idle"
        self.error = ""
        self.proc = psutil.Process()
        self.proc.cpu_percent(None)

        self.tts = TTS()
        self.agent = Agent(self.ask_confirm, lambda t: self.post("action", t), lambda ok, m: self.post("gemini", (ok, m)))
        self.voice = Voice(
            config.resource_dir() / "model-fr",
            on_command=self.run_command,
            on_confirm_answer=self.answer_confirm,
            is_busy=self.busy_lock.locked,
            confirm_pending=lambda: self.pending is not None,
            on_state=lambda s: self.post("mic", s),
            on_error=lambda e: self.post("error", e),
        )

        self._build()
        self.protocol("WM_DELETE_WINDOW", self.on_close)
        self.after(100, self.poll)
        self.after(50, self.animate)
        self.after(1000, self.update_resources)
        if not config.get_api_key():
            self.after(600, self.open_settings)

    # ---------- construction ----------
    def _build(self):
        top = ctk.CTkFrame(self, fg_color="transparent")
        top.pack(fill="x", padx=16, pady=(14, 0))
        ctk.CTkLabel(top, text="P O L A R I S", font=("Segoe UI", 24, "bold"), text_color=CYAN).pack(side="left")
        ctk.CTkButton(top, text="Réglages", width=90, fg_color=PANEL, hover_color="#14213a", command=self.open_settings).pack(side="right")

        self.canvas = ctk.CTkCanvas(self, width=170, height=170, bg=BG, highlightthickness=0)
        self.canvas.pack(pady=6)
        self.canvas.bind("<Button-1>", lambda e: self.toggle_mic())

        self.status = ctk.CTkLabel(self, text="", text_color=DIM)
        self.status.pack()

        bar = ctk.CTkFrame(self, fg_color="transparent")
        bar.pack(pady=6)
        self.mic_btn = ctk.CTkButton(bar, text="Activer le micro", width=150, fg_color=BLUE, command=self.toggle_mic)
        self.mic_btn.pack(side="left", padx=6)
        ctk.CTkButton(bar, text="ARRÊT IMMÉDIAT DU MICRO", width=190, fg_color="#7a1f1f", hover_color="#a02a2a",
                      command=self.voice.stop).pack(side="left", padx=6)

        self.chat = ctk.CTkTextbox(self, fg_color=PANEL, wrap="word", font=("Segoe UI", 14))
        self.chat.pack(fill="both", expand=True, padx=16, pady=8)
        tb = self.chat._textbox
        tb.tag_config("user", foreground="#8fd3ff")
        tb.tag_config("bot", foreground="#E6F1FF")
        tb.tag_config("act", foreground=DIM, font=("Consolas", 10))
        self.chat.configure(state="disabled")
        self.append("act", "Essaie : « Hey Polaris, ouvre le Bloc-notes », « trouve mon PDF sur Apollo 11 »…")

        row = ctk.CTkFrame(self, fg_color="transparent")
        row.pack(fill="x", padx=16)
        self.entry = ctk.CTkEntry(row, placeholder_text="Écris à Polaris…", height=38)
        self.entry.pack(side="left", fill="x", expand=True)
        self.entry.bind("<Return>", lambda e: self.send_text())
        ctk.CTkButton(row, text="Envoyer", width=90, height=38, command=self.send_text).pack(side="left", padx=(8, 0))

        foot = ctk.CTkFrame(self, fg_color="transparent")
        foot.pack(fill="x", padx=16, pady=(8, 10))
        self.gem_lbl = ctk.CTkLabel(foot, text="", text_color=DIM, font=("Segoe UI", 11))
        self.gem_lbl.pack(side="left")
        self.res_lbl = ctk.CTkLabel(foot, text="", text_color=DIM, font=("Consolas", 11))
        self.res_lbl.pack(side="right")
        self.set_gemini(bool(config.get_api_key()), "clé enregistrée" if config.get_api_key() else "clé manquante")
        self.refresh_status()

    # ---------- utilitaires UI ----------
    def post(self, kind, payload):
        self.ui_q.put((kind, payload))

    def append(self, tag, text):
        self.chat.configure(state="normal")
        self.chat._textbox.insert("end", text + "\n\n" if tag != "act" else text + "\n", tag)
        self.chat.configure(state="disabled")
        self.chat._textbox.see("end")

    def set_gemini(self, ok, msg):
        self.gem_lbl.configure(text=f"● Gemini : {msg}", text_color=CYAN if ok else RED)

    def refresh_status(self):
        if self.error:
            text, col = self.error, RED
        elif self.activity == "thinking":
            text, col = "Je réfléchis…", CYAN
        elif self.activity == "speaking":
            text, col = "Je parle…", CYAN
        elif self.mic_state == "command":
            text, col = "Je t'écoute…", CYAN
        elif self.mic_state == "wake":
            text, col = "En veille — dis « Hey Polaris »", DIM
        else:
            text, col = "Micro coupé — touche l'orbe ou écris", DIM
        self.status.configure(text=text, text_color=col)
        self.mic_btn.configure(text="Couper le micro" if self.mic_state != "off" else "Activer le micro")

    def poll(self):
        try:
            while True:
                kind, p = self.ui_q.get_nowait()
                if kind == "msg":
                    self.append("user" if p[0] == "Toi" else "bot", f"{p[0]} : {p[1]}")
                elif kind == "action":
                    self.append("act", p)
                elif kind == "mic":
                    self.mic_state = p
                    if p != "off":
                        self.error = ""
                elif kind == "activity":
                    self.activity = p
                elif kind == "gemini":
                    self.set_gemini(*p)
                elif kind == "error":
                    self.error = p
                    self.append("act", p)
                elif kind == "confirm":
                    self.show_dialog(p)
                elif kind == "confirm_close":
                    self.close_dialog()
                self.refresh_status()
        except queue.Empty:
            pass
        self.after(100 if not config.get("eco", False) else 250, self.poll)

    def animate(self):
        c = self.canvas
        c.delete("all")
        active = self.mic_state != "off" or self.activity != "idle"
        fast = self.activity != "idle" or self.mic_state == "command"
        pulse = (math.sin(time.time() * (7 if fast else 2.2)) + 1) / 2
        col = CYAN if active else DIM
        cx = cy = 85
        r = 78 * (0.86 + 0.14 * pulse) if active else 70
        c.create_oval(cx - r, cy - r, cx + r, cy + r, outline=col, width=2)
        c.create_oval(cx - 52, cy - 52, cx + 52, cy + 52, outline=col, width=1)
        c.create_oval(cx - 34, cy - 34, cx + 34, cy + 34, fill=BLUE if active else "#263042", outline="")
        c.create_oval(cx - 12, cy - 12, cx + 12, cy + 12, fill=col, outline="")
        self.after(150 if config.get("eco", False) else 60, self.animate)

    def update_resources(self):
        try:
            cpu = self.proc.cpu_percent(None) / (psutil.cpu_count() or 1)
            ram = self.proc.memory_info().rss / 1_000_000
            self.res_lbl.configure(text=f"RAM {ram:.0f} Mo · CPU {cpu:.1f} %" + ("  · mode éco" if config.get("eco", False) else ""))
        except Exception:
            pass
        self.after(5000 if config.get("eco", False) else 2000, self.update_resources)

    # ---------- micro ----------
    def toggle_mic(self):
        if self.voice.active:
            self.voice.stop()
            return
        if not (config.resource_dir() / "model-fr").exists():
            self.post("error", "Modèle vocal français absent (voir README).")
            return
        self.post("action", "Chargement du micro et du modèle vocal…")
        threading.Thread(target=lambda: self.voice.start(config.get("eco", False)), daemon=True).start()

    # ---------- commandes ----------
    def send_text(self):
        t = self.entry.get().strip()
        if t:
            self.entry.delete(0, "end")
            self.run_command(t)

    def run_command(self, text: str):
        if not self.busy_lock.acquire(blocking=False):
            self.post("action", "Polaris est déjà occupé, patiente un instant.")
            return
        threading.Thread(target=self._work, args=(text,), daemon=True).start()

    def _work(self, text: str):
        try:
            self.post("msg", ("Toi", text))
            self.post("activity", "thinking")
            try:
                reply = self.agent.handle(text)
            except Exception as e:
                reply = f"Une erreur est survenue : {e}"
            self.post("msg", ("Polaris", reply))
            self.post("activity", "speaking")
            if self.voice.active:
                self.voice.pause(True)
            self.tts.speak(reply)
        finally:
            if self.voice.active:
                self.voice.pause(False)
                self.voice.open_followup()
            self.post("activity", "idle")
            self.busy_lock.release()

    # ---------- confirmations (voix « oui/non » ou boutons) ----------
    def ask_confirm(self, question: str) -> bool:
        c = Confirmation(question)
        self.pending = c
        self.post("confirm", question)
        if self.voice.active:
            self.voice.pause(True)
        self.tts.speak(question)
        if self.voice.active:
            self.voice.pause(False)
        c.event.wait(30)
        result = c.result if c.event.is_set() else False
        self.pending = None
        self.post("confirm_close", None)
        return result

    def answer_confirm(self, value: bool):
        if self.pending:
            self.pending.result = value
            self.pending.event.set()

    def show_dialog(self, question: str):
        self.close_dialog()
        d = ctk.CTkToplevel(self)
        d.title("Confirmation")
        d.geometry("420x170")
        d.configure(fg_color=PANEL)
        d.attributes("-topmost", True)
        d.protocol("WM_DELETE_WINDOW", lambda: self.answer_confirm(False))
        ctk.CTkLabel(d, text=question, wraplength=380, justify="left").pack(padx=16, pady=18)
        row = ctk.CTkFrame(d, fg_color="transparent")
        row.pack()
        ctk.CTkButton(row, text="Oui", width=100, command=lambda: self.answer_confirm(True)).pack(side="left", padx=8)
        ctk.CTkButton(row, text="Non", width=100, fg_color="#7a1f1f", command=lambda: self.answer_confirm(False)).pack(side="left", padx=8)
        self.dialog = d

    def close_dialog(self):
        if self.dialog is not None:
            try:
                self.dialog.destroy()
            except Exception:
                pass
            self.dialog = None

    # ---------- réglages ----------
    def open_settings(self):
        w = ctk.CTkToplevel(self)
        w.title("Réglages Polaris")
        w.geometry("460x420")
        w.configure(fg_color=PANEL)
        w.attributes("-topmost", True)
        ctk.CTkLabel(w, text="Clé API Gemini (chiffrée avec ta session Windows)", text_color=CYAN).pack(anchor="w", padx=16, pady=(16, 4))
        key = ctk.CTkEntry(w, show="•", placeholder_text="Colle ta clé (aistudio.google.com/apikey)")
        key.pack(fill="x", padx=16)
        ctk.CTkLabel(w, text="Modèle Gemini", text_color=CYAN).pack(anchor="w", padx=16, pady=(14, 4))
        model = ctk.CTkEntry(w)
        model.insert(0, config.get("model", config.DEFAULT_MODEL))
        model.pack(fill="x", padx=16)
        eco = ctk.CTkCheckBox(w, text="Mode économie de ressources (animations et mesures ralenties)")
        if config.get("eco", False):
            eco.select()
        eco.pack(anchor="w", padx=16, pady=14)

        def save():
            if key.get().strip():
                config.set_api_key(key.get())
            config.put("model", model.get().strip() or config.DEFAULT_MODEL)
            config.put("eco", bool(eco.get()))
            self.set_gemini(bool(config.get_api_key()), "clé enregistrée" if config.get_api_key() else "clé manquante")
            w.destroy()

        ctk.CTkButton(w, text="Enregistrer", command=save).pack(padx=16, pady=4, anchor="w")
        ctk.CTkButton(w, text="Ouvrir le dossier des données et du journal", fg_color=BG,
                      command=lambda: os.startfile(str(config.DATA))).pack(padx=16, pady=10, anchor="w")
        ctk.CTkLabel(
            w, justify="left", wraplength=420, text_color=DIM,
            text="Polaris n'écoute que si tu actives le micro. Aucun enregistrement, aucun démarrage automatique, "
                 "aucune modification du registre. Les actions sont notées dans actions.log.",
        ).pack(padx=16, pady=6, anchor="w")

    def on_close(self):
        self.voice.stop()
        self.destroy()


def main():
    PolarisApp().mainloop()
