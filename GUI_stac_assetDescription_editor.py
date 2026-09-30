"""
STAC Asset Editor - GUI.

Eingabe der Asset-hrefs (einzeln oder aus TXT-Datei) und der Attribute der
Description. Die eigentliche Arbeit macht processingScripts/stac_asset_editor.py.

Aussehen (Hell/Dunkel, Farben, Schriften) wie GUI_GDWHimport.py.
Läuft ab Python 3.6.

Start: python GUI_stac_assetDescription_editor.py
Fehlende Python-Pakete (requirements/requirements.txt) werden beim Start
automatisch installiert.
"""

import ctypes
import importlib.util
import logging
import logging.handlers
import queue
import subprocess
import sys
import threading
import tkinter as tk
from datetime import datetime
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

# Kernlogik, Konfiguration und utilities liegen in processingScripts/
# (gleicher Aufbau wie GUI_GDWHimport.py)
GUI_DIR = Path(__file__).resolve().parent
PROCESSING_DIR = str(GUI_DIR / "processingScripts")
if PROCESSING_DIR not in sys.path:
    sys.path.insert(0, PROCESSING_DIR)

# Pakete, die beim Start vorhanden sein müssen (Importnamen).
# Neue Einträge in requirements.txt auch hier ergänzen.
REQUIRED_MODULES = ("requests", "urllib3")
REQUIREMENTS_FILE = GUI_DIR / "requirements" / "requirements.txt"


def missing_modules() -> list:
    """Gibt die Namen der Pakete aus REQUIRED_MODULES zurück, die nicht installiert sind."""
    return [name for name in REQUIRED_MODULES if importlib.util.find_spec(name) is None]


def ensure_requirements():
    """
    Installiert fehlende Pakete aus requirements.txt (nötig beim ersten Start).

    Sind alle Pakete vorhanden, passiert nichts: kein pip-Aufruf, keine Wartezeit.
    Schlägt die Installation fehl, erscheint eine Meldung und das Programm endet.
    """
    missing = missing_modules()
    if not missing:
        return

    # Hinweisfenster, weil pip einige Sekunden braucht und das GUI noch nicht steht
    info = tk.Tk()
    info.title("STAC Asset Editor")
    tk.Label(
        info, padx=30, pady=20,
        text=f"Erster Start: fehlende Python-Pakete werden installiert ({', '.join(missing)}).\n"
             "Das kann bis zu einer Minute dauern ..."
    ).pack()
    info.update()

    # Gleiches Python wie das GUI verwenden, damit die Pakete am richtigen Ort landen
    command = [
        sys.executable, "-m", "pip", "install", "--disable-pip-version-check",
        "-r", str(REQUIREMENTS_FILE),
    ]
    try:
        result = subprocess.run(
            command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            universal_newlines=True, errors="replace"
        )
        failed, output = result.returncode != 0, result.stdout
    except OSError as e:
        failed, output = True, str(e)

    info.withdraw()
    importlib.invalidate_caches()
    if failed:
        messagebox.showerror(
            "Installation fehlgeschlagen",
            f"Die Python-Pakete ({', '.join(missing)}) konnten nicht automatisch "
            "installiert werden.\n\n"
            "Internetverbindung / Proxy prüfen und das Programm neu starten, oder in "
            "einer Konsole von Hand installieren:\n\n"
            f"\"{sys.executable}\" -m pip install -r \"{REQUIREMENTS_FILE}\"\n\n"
            f"Meldung von pip:\n{output[-600:]}"
        )
    elif missing_modules():
        # Installiert, aber im laufenden Programm noch nicht sichtbar (z.B. neuer Benutzer-Ordner)
        messagebox.showinfo(
            "Installation abgeschlossen",
            "Die Python-Pakete wurden installiert. Bitte das Programm neu starten."
        )
    info.destroy()
    if failed or missing_modules():
        sys.exit(1)


ensure_requirements()

from configuration import (
    ACQUISITION_TIME_FIELD,
    DEFAULT_ENVIRONMENT,
    DESCRIPTION_FIELDS,
    DESCRIPTION_SEPARATOR,
    FIELD_DEFAULTS,
    STAC_HOSTNAMES,
)
from stac_asset_editor import (
    ACQUISITION_TIME_PLACEHOLDER,
    PROJECT_DIR,
    acquisition_time_from_item,
    build_description,
    parse_asset_href,
    read_hrefs,
    update_asset_descriptions,
)

logger = logging.getLogger(__name__)

# ── Themes (identisch zu GUI_GDWHimport.py) ──────────────────────────────────
LIGHT = {
    "root":      "#f0f0f0",
    "panel":     "#f5f5f5",
    "input":     "#ffffff",
    "fg":        "#1a1a1a",
    "fg_dim":    "#666666",
    "accent":    "#0063b1",
    "scroll":    "#9098a8",   # Grau mit leichtem Blaustich für Scrollbar
    "hdr_bg":    "#1a3a5c",
    "hdr_fg":    "#ffffff",
    "btn":       "#e1e1e1",
    "btn_hover": "#c8c8c8",
    "list":      "#ffffff",
    "log_bg":    "#1e1e1e",
    "log_fg":    "#d4d4d4",
    "sep":       "#c0c0c0",
    "sel_bg":    "#0078d4",
    "sel_fg":    "#ffffff",
    "ok":        "#2e7d32",
    "err":       "#c62828",
    "hint":      "#8a6f2e",   # Gedämpftes Amber für Info-Hinweise
}

DARK = {
    "root":      "#1e1e1e",   # Photoshop: tiefstes Dunkelgrau
    "panel":     "#252526",   # Section-Hintergrund
    "input":     "#3c3c3c",   # Eingabefelder
    "fg":        "#cccccc",   # Haupttext
    "fg_dim":    "#7a7a7a",   # Gedimmter Hinweistext
    "accent":    "#4fc3f7",   # Hellblau für Hervorhebungen
    "scroll":    "#6a6f7d",   # Grau mit leichtem Blaustich für Scrollbar
    "hdr_bg":    "#1a1a1a",   # Header-Balken
    "hdr_fg":    "#cccccc",   # Header-Text
    "btn":       "#3c3c3c",   # Button-Hintergrund
    "btn_hover": "#505050",   # Button hover
    "list":      "#2d2d30",   # Listbox-Hintergrund
    "log_bg":    "#1e1e1e",   # Log-Bereich
    "log_fg":    "#d4d4d4",
    "sep":       "#3c3c3c",   # Trennlinien / Rahmen
    "sel_bg":    "#094771",   # Selektion blau
    "sel_fg":    "#cccccc",
    "ok":        "#66bb6a",
    "err":       "#ef5350",
    "hint":      "#c9a84c",   # Gedämpftes Amber für Info-Hinweise
}

# Der Log-Bereich ist in beiden Themes dunkel, darum immer die hellen Farben
LOG_COLORS = {"SUCCESS": DARK["ok"], "WARNING": DARK["hint"], "ERROR": DARK["err"]}


class AssetEditorApp(tk.Tk):
    """Hauptfenster des STAC Asset Editors."""

    def __init__(self):
        super().__init__()
        self.title("STAC Asset Editor")
        win_h = min(940, self.winfo_screenheight() - 80)
        self.geometry(f"860x{win_h}")
        self.minsize(720, min(700, win_h))
        self.resizable(True, True)

        self._running     = False
        self._dark        = False
        self._dim_labels  = []   # Labels mit fg_dim (grau)
        self._comboboxes  = []
        self.log_queue    = queue.Queue()
        self.environment  = tk.StringVar(value=DEFAULT_ENVIRONMENT)
        self.overwrite    = tk.BooleanVar(value=False)
        # Acquisition time hat kein Eingabefeld, sie kommt pro Asset aus der Item-ID
        self.field_vars   = {name: tk.StringVar(value=FIELD_DEFAULTS.get(name, ""))
                             for name, _ in DESCRIPTION_FIELDS
                             if name != ACQUISITION_TIME_FIELD}
        self.event_var    = tk.StringVar()

        self._build_ui()
        self._update_preview()
        self._apply_theme(True)    # Dark Mode als Standard
        self.after(120, self._poll_queue)

    # ── UI Aufbau ─────────────────────────────────────────────────────────────
    def _build_ui(self):
        # Mausrad soll Combobox-Auswahl nicht versehentlich verstellen
        self.bind_class("TCombobox", "<MouseWheel>", lambda _e: "break")

        # Header (tk.Frame für direkte Farb-Kontrolle)
        self._hdr = tk.Frame(self, height=52)
        self._hdr.pack(fill="x")
        self._hdr.pack_propagate(False)

        self._hdr_lbl = tk.Label(self._hdr, text="STAC Asset Editor",
                                 font=("Segoe UI", 16, "bold"))
        self._hdr_lbl.pack(side="left", padx=16, pady=12)

        self._theme_btn = tk.Button(self._hdr, text="Dark",
                                    command=self._toggle_theme,
                                    relief="flat", borderwidth=0,
                                    font=("", 9), cursor="hand2", padx=10, pady=4)
        self._theme_btn.pack(side="right", padx=12)

        # Umgebung
        env_frame = ttk.LabelFrame(self, text="Umgebung", padding=8, style="Section.TLabelframe")
        env_frame.pack(fill="x", padx=12, pady=(8, 0))
        for col, (env, host) in enumerate(STAC_HOSTNAMES.items()):
            ttk.Radiobutton(env_frame, text=env, variable=self.environment, value=env
                            ).grid(row=0, column=col, padx=10, pady=(4, 0), sticky="nw")
            # Hostname als Kommentar (grau, kursiv) darunter, Klick wählt die Umgebung
            host_lbl = ttk.Label(env_frame, text=host, font=("Segoe UI", 8, "italic"),
                                 cursor="hand2")
            host_lbl.grid(row=1, column=col, padx=(22, 10), pady=(0, 4), sticky="nw")
            host_lbl.bind("<Button-1>", lambda _e, v=env: self.environment.set(v))
            self._dim_labels.append(host_lbl)

        # Asset-hrefs
        href_frame = ttk.LabelFrame(self, text="Asset-hrefs", padding=8, style="Section.TLabelframe")
        href_frame.pack(fill="x", padx=12, pady=(8, 0))
        href_hint = ttk.Label(
            href_frame, font=("Segoe UI", 8, "italic"),
            text="Eine URL pro Zeile - alle aufgeführten Assets erhalten dieselbe Description")
        href_hint.pack(fill="x", pady=(0, 3))
        self._dim_labels.append(href_hint)
        hf = ttk.Frame(href_frame)
        hf.pack(fill="x")
        hf.columnconfigure(0, weight=1)
        vsb = ttk.Scrollbar(hf, orient="vertical")
        hsb = ttk.Scrollbar(hf, orient="horizontal")
        self.href_text = tk.Text(hf, height=4, wrap="none", font=("Courier New", 9),
                                 relief="flat", borderwidth=1, highlightthickness=1,
                                 yscrollcommand=vsb.set, xscrollcommand=hsb.set)
        vsb.config(command=self.href_text.yview)
        hsb.config(command=self.href_text.xview)
        self.href_text.grid(row=0, column=0, sticky="ew")
        vsb.grid(row=0, column=1, sticky="ns")
        hsb.grid(row=1, column=0, sticky="ew")
        ttk.Button(href_frame, text="Aus TXT-Datei laden…",
                   command=self._load_href_file).pack(anchor="w", pady=(6, 0))

        # Attribute der Description
        sec = ttk.LabelFrame(self, text="Attribute der Description", padding=10,
                             style="Section.TLabelframe")
        sec.pack(fill="x", padx=12, pady=(8, 0))
        sec.columnconfigure(1, weight=1)
        row = 0
        for name, suggestions in DESCRIPTION_FIELDS:
            if name == "Commentary":
                # RapidMapping Event wird im Commentary vor die Auswahl gesetzt (siehe _values)
                row = self._add_field_row(sec, row, "RapidMapping Event",
                                          ttk.Entry(sec, textvariable=self.event_var),
                                          "wird dem Commentary vorangestellt, z.B. "
                                          "RapidMapping Trockenheit Wallis 2026")
                self.event_var.trace_add("write", self._update_preview)
            if name == ACQUISITION_TIME_FIELD:
                widget = ttk.Label(sec, font=("Segoe UI", 8, "italic"),
                                   text="wird pro Asset aus der Item-ID gelesen (UTC), z.B. "
                                        "ram-2022-07-16t10080000 → 2022-07-16T10:08:00.00")
                self._dim_labels.append(widget)
            elif name == "Commentary":
                # Nur Auswahl aus der Liste; leerer Eintrag zuoberst zum Abwählen
                widget = ttk.Combobox(sec, textvariable=self.field_vars[name],
                                      values=[""] + suggestions, state="readonly")
                self._comboboxes.append(widget)
            elif suggestions:
                widget = ttk.Combobox(sec, textvariable=self.field_vars[name], values=suggestions)
                self._comboboxes.append(widget)
            else:
                widget = ttk.Entry(sec, textvariable=self.field_vars[name])
            hint = ""
            if name == "LineID":
                hint = "mehrere LineIDs mit Komma und Leerzeichen trennen, z.B. 12345, 12346"
            row = self._add_field_row(sec, row, name, widget, hint)
            if name in self.field_vars:
                self.field_vars[name].trace_add("write", self._update_preview)
        field_hint = ttk.Label(sec, text="leere Felder erscheinen nicht in der Description",
                               font=("", 8))
        field_hint.grid(row=row, column=1, sticky="w", padx=(8, 0))
        self._dim_labels.append(field_hint)

        # Vorschau
        preview_frame = ttk.LabelFrame(self, text="Vorschau der Description (erstes Asset)",
                                       padding=8,
                                       style="Section.TLabelframe")
        preview_frame.pack(fill="x", padx=12, pady=(8, 0))
        self.preview_text = tk.Text(preview_frame, height=3, wrap="word", state="disabled",
                                    font=("Segoe UI", 9), relief="flat", borderwidth=1,
                                    highlightthickness=1)
        self.preview_text.pack(fill="x")

        # Buttons (vor dem Log gepackt, damit sie bei kleinem Fenster sichtbar bleiben)
        self._btn_row = ttk.Frame(self)
        self._btn_row.pack(side="bottom", fill="x", padx=12, pady=(0, 10))
        # tk.Button (statt ttk.Button) für direkte Textfarben-Kontrolle:
        # amber solange hrefs oder Description fehlen, grün sobald schreibbereit
        # (siehe _update_button_state).
        self.write_btn = tk.Button(self._btn_row, text="▶   DESCRIPTION SCHREIBEN",
                                   font=("Segoe UI", 10, "bold"),
                                   relief="flat", cursor="hand2",
                                   padx=22, pady=7,
                                   command=lambda: self._start(dry_run=False))
        self.write_btn.pack(side="right")
        self.check_btn = ttk.Button(self._btn_row, text="Prüfen (nichts schreiben)",
                                    command=lambda: self._start(dry_run=True))
        self.check_btn.pack(side="right", padx=(0, 10))
        ttk.Button(self._btn_row, text="Log löschen",
                   command=self._clear_log).pack(side="right", padx=(0, 10))
        ttk.Checkbutton(self._btn_row, text="Bestehende Description überschreiben",
                        variable=self.overwrite).pack(side="left")

        # Log
        self._log_frame = ttk.LabelFrame(self, text="Log-Ausgabe", padding=4,
                                         style="Section.TLabelframe")
        self._log_frame.pack(fill="both", expand=True, padx=12, pady=(8, 8))
        log_sb = ttk.Scrollbar(self._log_frame, orient="vertical")
        self.log_box = tk.Text(
            self._log_frame, height=8, wrap="word", state="disabled",
            font=("Courier New", 9), relief="flat", yscrollcommand=log_sb.set)
        log_sb.config(command=self.log_box.yview)
        log_sb.pack(side="right", fill="y")
        self.log_box.pack(side="left", fill="both", expand=True)
        for tag, color in LOG_COLORS.items():
            self.log_box.tag_configure(tag, foreground=color)

    def _add_field_row(self, sec, row, name, widget, hint=""):
        """Setzt Beschriftung, Eingabe und optionalen Hinweis (grau) ins Raster.
        Gibt die nächste freie Zeile zurück."""
        ttk.Label(sec, text=name + ":", font=("Segoe UI", 9, "bold")
                  ).grid(row=row, column=0, sticky="w", pady=3)
        widget.grid(row=row, column=1, sticky="ew", padx=(8, 0), pady=3)
        row += 1
        if hint:
            hint_lbl = ttk.Label(sec, text=hint, font=("", 8))
            hint_lbl.grid(row=row, column=1, sticky="w", padx=(8, 0), pady=(0, 3))
            self._dim_labels.append(hint_lbl)
            row += 1
        return row

    # ── Windows Titelleiste Dark Mode ─────────────────────────────────────────
    def _set_titlebar_dark(self, dark):
        # Fenster muss sichtbar sein bevor DWM reagiert – sonst erneut versuchen
        if not self.winfo_ismapped():
            self.after(50, lambda: self._set_titlebar_dark(dark))
            return
        try:
            # wm_frame() liefert den echten Top-Level-HWND mit Titelleiste
            hwnd  = int(self.wm_frame(), 16)
            value = ctypes.c_int(1 if dark else 0)
            for attr in (20, 19):   # 20 = Windows 11 / Win10 2004+; 19 = ältere Builds
                if ctypes.windll.dwmapi.DwmSetWindowAttribute(
                        hwnd, attr, ctypes.byref(value), ctypes.sizeof(value)) == 0:
                    break
            # Frame-Neuzeichnung erzwingen
            ctypes.windll.user32.SetWindowPos(hwnd, 0, 0, 0, 0, 0, 0x0027)
        except Exception:
            pass

    # ── Theme ─────────────────────────────────────────────────────────────────
    def _toggle_theme(self):
        self._apply_theme(not self._dark)

    def _apply_theme(self, dark):
        self._dark = dark
        T = DARK if dark else LIGHT

        # ttk Style (clam-Theme – unterstützt vollständige Farbanpassung)
        s = ttk.Style(self)
        s.theme_use("clam")
        s.configure(".",
            background=T["panel"], foreground=T["fg"],
            fieldbackground=T["input"],
            selectbackground=T["sel_bg"], selectforeground=T["sel_fg"],
            bordercolor=T["sep"], lightcolor=T["panel"], darkcolor=T["sep"],
            insertcolor=T["fg"], troughcolor=T["root"],
        )
        s.configure("TFrame",      background=T["panel"])
        s.configure("TLabelframe", background=T["panel"], bordercolor=T["sep"])
        s.configure("TLabelframe.Label", background=T["panel"], foreground=T["fg"],
                    font=("Segoe UI", 9, "bold"))
        s.configure("Section.TLabelframe", background=T["panel"], bordercolor=T["sep"])
        s.configure("Section.TLabelframe.Label", background=T["panel"], foreground=T["accent"],
                    font=("Segoe UI", 10, "bold"))
        s.configure("TLabel",      background=T["panel"], foreground=T["fg"])
        s.configure("TButton",
            background=T["btn"], foreground=T["fg"],
            bordercolor=T["sep"], relief="flat",
            padding=(8, 4), focuscolor=T["panel"],
        )
        s.map("TButton",
            background=[("active", T["btn_hover"]), ("pressed", T["sep"])],
            foreground=[("active", T["fg"]), ("disabled", T["fg_dim"])],
            relief=[("pressed", "flat")],
        )
        s.configure("TRadiobutton",
            background=T["panel"], foreground=T["fg"], focuscolor=T["panel"])
        s.map("TRadiobutton",
            background=[("active", T["panel"])], foreground=[("active", T["fg"])])
        s.configure("TCheckbutton",
            background=T["panel"], foreground=T["fg"], focuscolor=T["panel"])
        s.map("TCheckbutton",
            background=[("active", T["panel"])], foreground=[("active", T["fg"])])
        s.configure("TCombobox",
            fieldbackground=T["input"], background=T["btn"],
            foreground=T["fg"], arrowcolor=T["fg"],
            selectbackground=T["sel_bg"], selectforeground=T["sel_fg"],
            bordercolor=T["sep"], insertcolor=T["fg"],
        )
        s.map("TCombobox",
            fieldbackground=[("readonly", T["input"]), ("disabled", T["panel"])],
            foreground=[("readonly", T["fg"]), ("disabled", T["fg_dim"])],
            background=[("active", T["btn_hover"])],
        )
        s.configure("TEntry",
            fieldbackground=T["input"], foreground=T["fg"],
            bordercolor=T["sep"], insertcolor=T["fg"],
            selectbackground=T["sel_bg"], selectforeground=T["sel_fg"],
        )
        for scrollbar in ("Vertical.TScrollbar", "Horizontal.TScrollbar"):
            s.configure(scrollbar,
                background=T["scroll"], troughcolor=T["root"],
                bordercolor=T["sep"], arrowcolor=T["fg"],
            )
            s.map(scrollbar,
                background=[("active", T["scroll"]), ("pressed", T["scroll"])],
            )

        # Combobox-Dropdown Farben: direkt an der Liste setzen, damit auch ein
        # bereits geöffnetes Dropdown beim Umschalten Hell/Dunkel mitwechselt
        for cb in self._comboboxes:
            try:
                popdown = self.tk.call("ttk::combobox::PopdownWindow", cb)
                self.tk.call(f"{popdown}.f.l", "configure",
                             "-background", T["list"], "-foreground", T["fg"],
                             "-selectbackground", T["sel_bg"],
                             "-selectforeground", T["sel_fg"])
            except tk.TclError:
                pass

        # Root
        self.configure(bg=T["root"])

        # Header (tk.Frame – direkte Farbkontrolle)
        self._hdr.configure(bg=T["hdr_bg"])
        self._hdr_lbl.configure(bg=T["hdr_bg"], fg=T["hdr_fg"])
        self._theme_btn.configure(
            bg=T["hdr_bg"], fg=T["hdr_fg"],
            activebackground=T["btn"], activeforeground=T["fg"],
            text="Hell" if dark else "Dark",
        )

        # Textfelder (rohe tk-Widgets, vom ttk-Style nicht erfasst)
        for widget in (self.href_text, self.preview_text):
            widget.configure(
                bg=T["input"], fg=T["fg"], insertbackground=T["fg"],
                selectbackground=T["sel_bg"], selectforeground=T["sel_fg"],
                highlightbackground=T["sep"], highlightcolor=T["sep"],
            )

        # Log-Bereich
        self.log_box.configure(bg=T["log_bg"], fg=T["log_fg"],
                               insertbackground=T["log_fg"])

        # Spezifisch gefärbte Labels
        for lbl in self._dim_labels:
            lbl.configure(foreground=T["fg_dim"])

        # "DESCRIPTION SCHREIBEN"-Button: Textfarbe (amber/grün) neu bewerten
        self._update_button_state()

        self._set_titlebar_dark(dark)

    # ── Eingaben ──────────────────────────────────────────────────────────────
    def _values(self):
        """Attribute aus den Eingabefeldern (ohne Acquisition time).
        Ein RapidMapping Event wird dem Commentary vorangestellt:
        "<Event>, <Commentary-Auswahl>"."""
        values = {name: var.get() for name, var in self.field_vars.items()}
        parts = [self.event_var.get().strip(), values["Commentary"].strip()]
        values["Commentary"] = DESCRIPTION_SEPARATOR.join(p for p in parts if p)
        return values

    def _preview_description(self):
        """Description, wie sie das erste Asset erhält (Acquisition time aus dessen Item-ID)."""
        values = self._values()
        try:
            href = read_hrefs(self.href_text.get("1.0", "end"))[0]
            _, item, _ = parse_asset_href(href, self.environment.get())
            values[ACQUISITION_TIME_FIELD] = acquisition_time_from_item(item)
        except (IndexError, ValueError):
            values[ACQUISITION_TIME_FIELD] = ACQUISITION_TIME_PLACEHOLDER
        return build_description(values)

    def _update_preview(self, *_):
        # Wird auch aus dem Poll-Zyklus aufgerufen (hrefs, Umgebung): nur bei Änderung neu setzen
        text = self._preview_description()
        if text == self.preview_text.get("1.0", "end-1c"):
            return
        self.preview_text.configure(state="normal")
        self.preview_text.delete("1.0", "end")
        self.preview_text.insert("1.0", text)
        self.preview_text.configure(state="disabled")

    def _load_href_file(self):
        path = filedialog.askopenfilename(
            title="TXT-Datei mit Asset-hrefs wählen",
            filetypes=[("Textdatei", "*.txt"), ("Alle Dateien", "*.*")],
        )
        if not path:
            return
        try:
            with open(path, "r", encoding="utf-8-sig") as f:
                content = f.read()
        except (OSError, UnicodeDecodeError) as e:
            messagebox.showerror(
                "Datei nicht lesbar",
                f"Die Datei konnte nicht gelesen werden:\n{path}\n\n{e}\n\n"
                "Bitte eine Textdatei (UTF-8) mit einer URL pro Zeile wählen.",
            )
            return
        self.href_text.delete("1.0", "end")
        self.href_text.insert("1.0", content)

    def _update_button_state(self):
        """Sperrt beide Buttons während eines Laufs und färbt DESCRIPTION
        SCHREIBEN amber (hrefs oder Description fehlen) bzw. grün (bereit).
        Wird laufend über den Log-Poll-Zyklus neu ausgewertet - deckt damit
        alle Eingabewege ab (Tippen, Dropdown, TXT-Datei) ohne Einzel-Traces."""
        T = DARK if self._dark else LIGHT
        ready = (bool(read_hrefs(self.href_text.get("1.0", "end")))
                 and bool(build_description(self._values())))
        color = T["ok"] if ready else T["hint"]
        state = "disabled" if self._running else "normal"
        self.write_btn.config(
            state=state, fg=color, disabledforeground=T["fg_dim"],
            bg=T["btn"], activebackground=T["btn_hover"], activeforeground=color,
        )
        self.check_btn.config(state=state)

    # ── Ablauf ────────────────────────────────────────────────────────────────
    def _start(self, dry_run):
        hrefs = read_hrefs(self.href_text.get("1.0", "end"))
        values = self._values()
        environment = self.environment.get()

        if not hrefs:
            messagebox.showwarning("Eingabe fehlt", "Bitte mindestens einen Asset-href angeben.")
            return
        if not build_description(values):
            messagebox.showwarning("Eingabe fehlt", "Bitte mindestens ein Attribut der Description ausfüllen.")
            return

        overwrite = self.overwrite.get()
        if not dry_run:
            question = (
                f"{len(hrefs)} Asset(s) in {environment} ({STAC_HOSTNAMES[environment]}) "
                f"erhalten diese Description (Beispiel erstes Asset):\n\n"
                f"{self._preview_description()}\n\n"
                "Die Acquisition time wird pro Asset aus der Item-ID gelesen.\n\n"
            )
            if overwrite:
                question += "ACHTUNG: Bestehende Descriptions werden überschrieben.\n\n"
            question += "Jetzt schreiben?"
            if not messagebox.askyesno("Description schreiben", question, icon="warning"):
                return

        self._running = True
        self._update_button_state()
        threading.Thread(
            target=self._worker,
            args=(hrefs, values, environment, overwrite, dry_run),
            daemon=True,
        ).start()

    def _worker(self, hrefs, values, environment, overwrite, dry_run):
        """Läuft im Hintergrund-Thread, damit das Fenster bedienbar bleibt."""
        try:
            update_asset_descriptions(hrefs, values, environment, overwrite, dry_run)
        except Exception as e:
            logger.error(f"ABBRUCH: {e}")
        finally:
            self.log_queue.put(None)  # Signal: Lauf beendet

    # ── Log ───────────────────────────────────────────────────────────────────
    def _poll_queue(self):
        """Holt Log-Meldungen des Hintergrund-Threads ins Fenster."""
        while True:
            try:
                record = self.log_queue.get_nowait()
            except queue.Empty:
                break
            if record is None:
                self._running = False
            else:
                self._log(record)
        self._update_button_state()
        self._update_preview()   # hrefs und Umgebung haben keinen Trace
        self.after(120, self._poll_queue)

    def _log(self, record):
        text = record.getMessage()
        if record.levelname in ("WARNING", "ERROR"):
            tag = record.levelname
        elif "] SUCCESS:" in text:   # Asset-Zeile, nicht die Zusammenfassung
            tag = "SUCCESS"
        else:
            tag = ""
        self.log_box.config(state="normal")
        self.log_box.insert("end", text + "\n", tag)
        self.log_box.see("end")
        self.log_box.config(state="disabled")

    def _clear_log(self):
        self.log_box.config(state="normal")
        self.log_box.delete("1.0", "end")
        self.log_box.config(state="disabled")


def main():
    app = AssetEditorApp()

    queue_handler = logging.handlers.QueueHandler(app.log_queue)
    queue_handler.setFormatter(logging.Formatter("%(message)s"))
    handlers = [queue_handler]
    # Logdatei als Nachweis, welches Asset wann welche Description erhalten hat
    try:
        log_dir = PROJECT_DIR / "logs"
        log_dir.mkdir(exist_ok=True)
        file_handler = logging.FileHandler(
            str(log_dir / f"stac_asset_editor_{datetime.now():%Y-%m-%d}.log"), encoding="utf-8"
        )
        file_handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)-7s %(message)s"))
        handlers.append(file_handler)
    except OSError as e:
        messagebox.showwarning(
            "Keine Logdatei", f"Die Logdatei konnte nicht angelegt werden:\n{e}\n\n"
            "Das Protokoll erscheint nur im Fenster."
        )
    logging.basicConfig(level=logging.INFO, handlers=handlers)

    app.mainloop()


if __name__ == "__main__":
    main()
