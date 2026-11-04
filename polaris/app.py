"""Interface Polaris (CustomTkinter) : HUD futuriste, chat, micro et réglages."""
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

CYAN, BLUE, BG, PANEL, DIM, RED = "#55E7FF", "#3978FF", "#060A13", "#0D1422", "#8494AA", "#FF657A"
PANEL_LIGHT, WHITE, GREEN = "#121D2E", "#EAF4FF", "#54E6B3"


class Confirmation:
    def __init__(self, question: str):
        self.question = question
        self.event = threading.Event()
        self.result = False


class PolarisApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")
        self.title("POLARIS  /  ASSISTANT SYSTEM")
        self.geometry("900x820")
        self.minsize(620, 680)
        self.configure(fg_color=BG)

        self.ui_q: queue.Queue = queue.Queue()
        self.busy_lock = threading.Lock()
        self.pending: Confirmation | None = None
        self.dialog = None
        self.settings_window = None
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
            self.after(700, self.open_settings)

    # ---------- construction ----------
    def _build(self):
        shell = ctk.CTkFrame(self, fg_color="transparent")
        shell.pack(fill="both", expand=True, padx=20, pady=18)

        header = ctk.CTkFrame(shell, fg_color=PANEL, corner_radius=18, border_width=1, border_color="#1C2A40")
        header.pack(fill="x", pady=(0, 12))
        identity = ctk.CTkFrame(header, fg_color="transparent")
        identity.pack(side="left", padx=20, pady=14)
        ctk.CTkLabel(identity, text="POLARIS", font=("Segoe UI", 25, "bold"), text_color=CYAN).pack(anchor="w")
        ctk.CTkLabel(identity, text="PERSONAL AI  /  SYSTEM ONLINE", font=("Consolas", 10), text_color=DIM).pack(anchor="w", pady=(2, 0))
        ctk.CTkButton(header, text="⚙  RÉGLAGES", width=130, height=38, corner_radius=10,
                      fg_color=PANEL_LIGHT, hover_color="#1C2D45", command=self.open_settings).pack(side="right", padx=18)

        orb_card = ctk.CTkFrame(shell, fg_color="#0A111E", corner_radius=22, border_width=1, border_color="#18283E")
        orb_card.pack(fill="x", pady=(0, 10))
        ctk.CTkLabel(orb_card, text="NŒUD D'ASSISTANCE", font=("Consolas", 10, "bold"), text_color=DIM).pack(pady=(13, 0))
        self.canvas = ctk.CTkCanvas(orb_card, width=190, height=190, bg="#0A111E", highlightthickness=0)
        self.canvas.pack(pady=(0, 0))
        self.canvas.bind("<Button-1>", lambda _event: self.toggle_mic())
        self.status = ctk.CTkLabel(orb_card, text="", text_color=DIM, font=("Segoe UI", 13))
        self.status.pack(pady=(0, 14))

        controls = ctk.CTkFrame(shell, fg_color="transparent")
        controls.pack(pady=(2, 12))
        self.mic_btn = ctk.CTkButton(controls, text="ACTIVER LE MICRO", width=175, height=42, corner_radius=11,
                                     fg_color=BLUE, hover_color="#285FD0", command=self.toggle_mic)
        self.mic_btn.pack(side="left", padx=6)
        ctk.CTkButton(controls, text="■  ARRÊT MICRO", width=175, height=42, corner_radius=11,
                      fg_color="#702838", hover_color="#913347", command=self.voice.stop).pack(side="left", padx=6)

        chat_card = ctk.CTkFrame(shell, fg_color=PANEL, corner_radius=17, border_width=1, border_color="#1A273A")
        chat_card.pack(fill="both", expand=True, pady=(0, 10))
        ctk.CTkLabel(chat_card, text="  CONVERSATION  /  LIVE", font=("Consolas", 10, "bold"), text_color=DIM).pack(anchor="w", padx=12, pady=(10, 0))
        self.chat = ctk.CTkTextbox(chat_card, fg_color=PANEL, wrap="word", font=("Segoe UI", 14),
                                   border_width=0, corner_radius=12, scrollbar_button_color="#253650")
        self.chat.pack(fill="both", expand=True, padx=10, pady=(3, 10))
        tb = self.chat._textbox
        tb.tag_config("user", foreground="#8EDCFF", font=("Segoe UI", 13, "bold"))
        tb.tag_config("bot", foreground=WHITE)
        tb.tag_config("act", foreground="#8FA6C2", font=("Consolas", 10))
        self.chat.configure(state="disabled")
        self.append("act", "SYSTÈME PRÊT  ·  « Hey Polaris, ouvre le Bloc-notes »  ·  ou écris une commande ci-dessous.")

        row = ctk.CTkFrame(shell, fg_color="transparent")
        row.pack(fill="x")
        self.entry = ctk.CTkEntry(row, placeholder_text="Écris une commande à Polaris…", height=44,
                                  corner_radius=11, border_color="#263951", fg_color="#0D1422", font=("Segoe UI", 13))
        self.entry.pack(side="left", fill="x", expand=True)
        self.entry.bind("<Return>", lambda _event: self.send_text())
        ctk.CTkButton(row, text="ENVOYER  ➤", width=118, height=44, corner_radius=11,
                      fg_color=BLUE, hover_color="#285FD0", command=self.send_text).pack(side="left", padx=(9, 0))

        footer = ctk.CTkFrame(shell, fg_color="transparent")
        footer.pack(fill="x", pady=(11, 0))
        self.gem_lbl = ctk.CTkLabel(footer, text="", text_color=DIM, font=("Segoe UI", 11))
        self.gem_lbl.pack(side="left")
        self.res_lbl = ctk.CTkLabel(footer, text="", text_color=DIM, font=("Consolas", 10))
        self.res_lbl.pack(side="right")
        self.set_gemini(bool(config.get_api_key()), "clé enregistrée" if config.get_api_key() else "clé manquante")
        self.refresh_status()

    # ---------- utilitaires UI ----------
    def post(self, kind, payload):
        self.ui_q.put((kind, payload))

    def append(self, tag, text):
        self.chat.configure(state="normal")
        self.chat._textbox.insert("end", text + ("\n\n" if tag != "act" else "\n"), tag)
        self.chat.configure(state="disabled")
        self.chat._textbox.see("end")

    def set_gemini(self, ok, msg):
        self.gem_lbl.configure(text=f"●  GEMINI  /  {msg.upper()}", text_color=GREEN if ok else RED)

    def refresh_status(self):
        if self.error:
            text, color = self.error, RED
        elif self.activity == "thinking":
            text, color = "Traitement de la demande…", CYAN
        elif self.activity == "speaking":
            text, color = "Réponse vocale en cours…", CYAN
        elif self.mic_state == "command":
            text, color = "ÉCOUTE ACTIVE  ·  parle maintenant", GREEN
        elif self.mic_state == "wake":
            text, color = "EN VEILLE  ·  dis « Hey Polaris »", CYAN
        else:
            text, color = "MICRO DÉSACTIVÉ  ·  clique sur l'orbe ou écris", DIM
        self.status.configure(text=text, text_color=color)
        self.mic_btn.configure(text="COUPER LE MICRO" if self.mic_state != "off" else "ACTIVER LE MICRO")

    def poll(self):
        try:
            while True:
                kind, payload = self.ui_q.get_nowait()
                if kind == "msg":
                    self.append("user" if payload[0] == "Toi" else "bot", f"{payload[0]}  ›  {payload[1]}")
                elif kind == "action":
                    self.append("act", payload)
                elif kind == "mic":
                    self.mic_state = payload
                    if payload != "off":
                        self.error = ""
                elif kind == "activity":
                    self.activity = payload
                elif kind == "gemini":
                    self.set_gemini(*payload)
                elif kind == "error":
                    self.error = payload
                    self.append("act", payload)
                elif kind == "confirm":
                    self.show_dialog(payload)
                elif kind == "confirm_close":
                    self.close_dialog()
                self.refresh_status()
        except queue.Empty:
            pass
        self.after(100 if not config.get("eco", False) else 250, self.poll)

    def animate(self):
        canvas = self.canvas
        canvas.delete("all")
        active = self.mic_state != "off" or self.activity != "idle"
        speed = 6.0 if self.activity != "idle" or self.mic_state == "command" else 2.0
        pulse = (math.sin(time.time() * speed) + 1) / 2
        cx = cy = 95
        color = CYAN if active else "#52647D"
        radius = 72 + 7 * pulse if active else 68
        canvas.create_oval(cx - 88, cy - 88, cx + 88, cy + 88, outline="#17283D", width=1)
        canvas.create_oval(cx - radius, cy - radius, cx + radius, cy + radius,
                           outline=color, width=2 if active else 1)
        canvas.create_oval(cx - 57, cy - 57, cx + 57, cy + 57, outline="#29466A", width=1)
        canvas.create_oval(cx - 43, cy - 43, cx + 43, cy + 43,
                           fill="#12223A" if active else "#111A28", outline=color, width=2)
        core = 12 + 3 * pulse if active else 10
        canvas.create_oval(cx - core, cy - core, cx + core, cy + core,
                           fill=color if active else "#64748B", outline="")
        canvas.create_text(cx, 164, text="LISTENING" if self.mic_state != "off" else "STANDBY",
                           fill=color, font=("Consolas", 8, "bold"))
        self.after(150 if config.get("eco", False) else 60, self.animate)

    def update_resources(self):
        try:
            cpu = self.proc.cpu_percent(None) / (psutil.cpu_count() or 1)
            ram = self.proc.memory_info().rss / 1_000_000
            self.res_lbl.configure(text=f"RAM {ram:.0f} Mo  /  CPU {cpu:.1f}%" + ("  /  ÉCO" if config.get("eco", False) else ""))
        except Exception:
            pass
        self.after(5000 if config.get("eco", False) else 2000, self.update_resources)

    # ---------- micro ----------
    def toggle_mic(self):
        if self.voice.active:
            self.voice.stop()
            return
        if not (config.resource_dir() / "model-fr").exists():
            self.post("error", "Modèle vocal français absent. Télécharge une nouvelle version via le workflow.")
            return
        self.post("action", "Chargement du micro et du modèle vocal…")
        threading.Thread(target=lambda: self.voice.start(config.get("eco", False)), daemon=True).start()

    # ---------- commandes ----------
    def send_text(self):
        text = self.entry.get().strip()
        if text:
            self.entry.delete(0, "end")
            self.run_command(text)

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
            except Exception as exc:
                reply = f"Une erreur est survenue : {exc}"
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

    # ---------- confirmations ----------
    def ask_confirm(self, question: str) -> bool:
        confirmation = Confirmation(question)
        self.pending = confirmation
        self.post("confirm", question)
        if self.voice.active:
            self.voice.pause(True)
        self.tts.speak(question)
        if self.voice.active:
            self.voice.pause(False)
        confirmation.event.wait(30)
        result = confirmation.result if confirmation.event.is_set() else False
        self.pending = None
        self.post("confirm_close", None)
        return result

    def answer_confirm(self, value: bool):
        if self.pending:
            self.pending.result = value
            self.pending.event.set()

    def show_dialog(self, question: str):
        self.close_dialog()
        dialog = ctk.CTkToplevel(self)
        dialog.title("Confirmation requise")
        dialog.geometry("440x190")
        dialog.configure(fg_color=PANEL)
        dialog.attributes("-topmost", True)
        dialog.protocol("WM_DELETE_WINDOW", lambda: self.answer_confirm(False))
        ctk.CTkLabel(dialog, text="ACTION À CONFIRMER", text_color=CYAN,
                     font=("Consolas", 11, "bold")).pack(anchor="w", padx=20, pady=(18, 5))
        ctk.CTkLabel(dialog, text=question, wraplength=400, justify="left", text_color=WHITE).pack(padx=20, pady=10)
        buttons = ctk.CTkFrame(dialog, fg_color="transparent")
        buttons.pack(pady=5)
        ctk.CTkButton(buttons, text="Confirmer", width=120, command=lambda: self.answer_confirm(True)).pack(side="left", padx=6)
        ctk.CTkButton(buttons, text="Annuler", width=120, fg_color="#702838", hover_color="#913347",
                      command=lambda: self.answer_confirm(False)).pack(side="left", padx=6)
        self.dialog = dialog

    def close_dialog(self):
        if self.dialog is not None:
            try:
                self.dialog.destroy()
            except Exception:
                pass
            self.dialog = None

    # ---------- réglages ----------
    def open_settings(self):
        if self.settings_window is not None:
            try:
                if self.settings_window.winfo_exists():
                    self.settings_window.focus_force()
                    return
            except Exception:
                self.settings_window = None

        window = ctk.CTkToplevel(self)
        self.settings_window = window
        window.title("POLARIS  /  RÉGLAGES")
        window.geometry("540x560")
        window.minsize(500, 520)
        window.configure(fg_color=BG)
        window.attributes("-topmost", True)
        window.protocol("WM_DELETE_WINDOW", window.destroy)

        card = ctk.CTkFrame(window, fg_color=PANEL, corner_radius=18, border_width=1, border_color="#1C2A40")
        card.pack(fill="both", expand=True, padx=18, pady=18)
        ctk.CTkLabel(card, text="CONFIGURATION", font=("Consolas", 12, "bold"), text_color=CYAN).pack(anchor="w", padx=20, pady=(20, 2))
        ctk.CTkLabel(card, text="Personnalise la connexion et les performances.", text_color=DIM).pack(anchor="w", padx=20, pady=(0, 18))

        ctk.CTkLabel(card, text="CLÉ API GEMINI", text_color="#B9C9DB", font=("Consolas", 10, "bold")).pack(anchor="w", padx=20, pady=(4, 6))
        key_entry = ctk.CTkEntry(card, height=40, show="•", placeholder_text="Colle une nouvelle clé API…",
                                 border_color="#263951", fg_color="#080E18")
        key_entry.pack(fill="x", padx=20)
        key_state = "Une clé est enregistrée (saisie vide = conservation)." if config.get_api_key() else "Aucune clé enregistrée."
        ctk.CTkLabel(card, text=key_state, text_color=DIM, font=("Segoe UI", 10)).pack(anchor="w", padx=20, pady=(5, 0))
        clear_key = ctk.CTkCheckBox(card, text="Effacer la clé enregistrée", font=("Segoe UI", 11), checkbox_width=18, checkbox_height=18)
        clear_key.pack(anchor="w", padx=20, pady=(12, 4))

        ctk.CTkLabel(card, text="MODÈLE GEMINI", text_color="#B9C9DB", font=("Consolas", 10, "bold")).pack(anchor="w", padx=20, pady=(15, 6))
        model_entry = ctk.CTkEntry(card, height=38, border_color="#263951", fg_color="#080E18")
        model_entry.insert(0, config.get("model", config.DEFAULT_MODEL))
        model_entry.pack(fill="x", padx=20)

        eco = ctk.CTkCheckBox(card, text="Mode économie (animations et mesures ralenties)", font=("Segoe UI", 11), checkbox_width=18, checkbox_height=18)
        if config.get("eco", False):
            eco.select()
        eco.pack(anchor="w", padx=20, pady=(16, 8))

        result = ctk.CTkLabel(card, text="", text_color=RED, wraplength=450, justify="left")
        result.pack(anchor="w", padx=20, pady=(5, 0))

        def save_settings():
            new_key = key_entry.get().strip()
            model_value = model_entry.get().strip() or config.DEFAULT_MODEL
            if not model_value or any(char.isspace() for char in model_value):
                result.configure(text="Le nom du modèle ne doit pas contenir d'espaces.")
                return
            try:
                if clear_key.get():
                    config.set_api_key("")
                elif new_key:
                    config.set_api_key(new_key)
                config.put("model", model_value)
                config.put("eco", bool(eco.get()))
            except Exception as exc:
                result.configure(text=f"Enregistrement impossible : {exc}", text_color=RED)
                return
            has_key = bool(config.get_api_key())
            self.set_gemini(has_key, "clé enregistrée" if has_key else "clé manquante")
            result.configure(text=f"Réglages enregistrés dans : {config.DATA}", text_color=GREEN)
            window.after(900, window.destroy)

        actions = ctk.CTkFrame(card, fg_color="transparent")
        actions.pack(fill="x", padx=20, pady=(12, 8))
        ctk.CTkButton(actions, text="ENREGISTRER", height=40, corner_radius=10,
                      fg_color=BLUE, hover_color="#285FD0", command=save_settings).pack(side="left")
        def open_data_folder():
            try:
                if hasattr(os, "startfile"):
                    os.startfile(str(config.DATA))
                else:
                    result.configure(text=f"Dossier des données : {config.DATA}", text_color=DIM)
            except OSError as exc:
                result.configure(text=f"Impossible d'ouvrir le dossier : {exc}", text_color=RED)
        ctk.CTkButton(actions, text="OUVRIR LE DOSSIER DATA", height=40, corner_radius=10,
                      fg_color=PANEL_LIGHT, hover_color="#1C2D45", command=open_data_folder).pack(side="left", padx=(9, 0))

        ctk.CTkLabel(card, text="Clé chiffrée avec Windows DPAPI. Micro activé uniquement sur demande.\n"
                     "Si le dossier de l'exe est protégé, les données sont placées dans AppData.",
                     text_color=DIM, justify="left", wraplength=470, font=("Segoe UI", 10)).pack(anchor="w", padx=20, pady=(7, 18))

    def on_close(self):
        self.voice.stop()
        self.destroy()


def main():
    PolarisApp().mainloop()
