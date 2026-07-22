"""
options/sidebar.py — SightPoint AI · Settings Sidebar
════════════════════════════════════════════════════════
Replaces the old HistorySidebar in the same left-hand position.
Every control here is live-updating: clicking a checkbox, changing a
dropdown, or adjusting a spinbox calls options.set_option() and writes
~/.sightpoint/options.json immediately. There is no separate "Apply"
or "Save" button for these controls — the "Reset to Defaults" button
is the only destructive action, and it asks for confirmation first.

Theme constants (BG_DARK, CYAN, etc.) are pulled from the sightpoint
module at import time. This module is only ever imported from inside
SightPointApp.__init__() (after sightpoint.py has fully finished
loading), so there is no circular-import issue — see main.py / cogs
for the same pattern.
"""

import tkinter as tk
from tkinter import ttk, messagebox

import options
import sightpoint as sp   # theme constants — safe, see module docstring


# ─────────────────────────────────────────────────────────────────
#  COLLAPSIBLE CATEGORY SECTION
# ─────────────────────────────────────────────────────────────────
class _CollapsibleSection(tk.Frame):
    """
    A category header that expands/collapses its body frame on click.
    Used internally by SettingsSidebar — one per category.
    """

    def __init__(self, parent, title: str, expanded: bool = True, **kw):
        kw.setdefault("bg", sp.BG_DARK)
        super().__init__(parent, **kw)

        self._expanded = expanded

        # Header row (click to toggle)
        self._hdr = tk.Frame(self, bg=sp.BG_PANEL, cursor="hand2")
        self._hdr.pack(fill="x")

        self._arrow_lbl = tk.Label(
            self._hdr, text=self._arrow_char(),
            bg=sp.BG_PANEL, fg=sp.CYAN,
            font=sp.FONT_MONO_XS, width=2)
        self._arrow_lbl.pack(side="left", padx=(4, 0), pady=4)

        self._title_lbl = tk.Label(
            self._hdr, text=title,
            bg=sp.BG_PANEL, fg=sp.CYAN_BRIGHT,
            font=("Courier New", 8, "bold"), anchor="w")
        self._title_lbl.pack(side="left", fill="x", expand=True, pady=4)

        for widget in (self._hdr, self._arrow_lbl, self._title_lbl):
            widget.bind("<Button-1>", self._toggle)

        # Body frame — holds the actual controls
        self.body = tk.Frame(self, bg=sp.BG_DARK)
        if self._expanded:
            self.body.pack(fill="x", padx=(6, 2), pady=(2, 6))

    def _arrow_char(self) -> str:
        return "▾" if self._expanded else "▸"

    def _toggle(self, _e=None):
        self._expanded = not self._expanded
        self._arrow_lbl.configure(text=self._arrow_char())
        if self._expanded:
            self.body.pack(fill="x", padx=(6, 2), pady=(2, 6))
        else:
            self.body.pack_forget()


# ─────────────────────────────────────────────────────────────────
#  SETTINGS SIDEBAR
# ─────────────────────────────────────────────────────────────────
class SettingsSidebar(tk.Frame):
    """
    Replaces HistorySidebar in the same position (left side of the
    main app body). Organised into collapsible categories, each full
    of live-updating Checkbuttons (plus one dropdown and one spinbox).

    Usage (inside SightPointApp.__init__, same spot HistorySidebar
    used to occupy):

        from options.sidebar import SettingsSidebar
        self._sidebar = SettingsSidebar(body)
        self._sidebar.pack(side="left", fill="y")
    """

    WIDTH = 250

    def __init__(self, parent, fixed_width: bool = True, **kw):
        """
        fixed_width=True  (default) — behaves exactly as before: a
            250px-wide docked panel with pack_propagate disabled, for
            use in the main app body.
        fixed_width=False — no forced width, no propagate override,
            so it can be packed fill="both", expand=True inside a
            Toplevel (used by the standalone Options dialog).
        """
        kw.setdefault("bg", sp.BG_PANEL)
        if fixed_width:
            kw["width"] = self.WIDTH
        super().__init__(parent, **kw)
        if fixed_width:
            self.pack_propagate(False)

        self._build()

    # ── Build ──────────────────────────────────────────────────
    def _build(self):
        # Header
        hdr = tk.Frame(self, bg=sp.BG_PANEL)
        hdr.pack(fill="x", padx=6, pady=(6, 3))
        tk.Label(hdr, text="⬡ SETTINGS", bg=sp.BG_PANEL,
                  fg=sp.TEXT_DIM, font=sp.FONT_MONO_XS).pack(side="left")

        tk.Frame(self, bg=sp.BORDER_LIT, height=1).pack(fill="x", padx=4)

        # Scrollable body
        outer = tk.Frame(self, bg=sp.BG_DARK)
        outer.pack(fill="both", expand=True)

        cv = tk.Canvas(outer, bg=sp.BG_DARK, highlightthickness=0)
        sb = ttk.Scrollbar(outer, orient="vertical", command=cv.yview)
        cv.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        cv.pack(side="left", fill="both", expand=True)

        self._inner = tk.Frame(cv, bg=sp.BG_DARK)
        win = cv.create_window((0, 0), window=self._inner, anchor="nw")
        self._inner.bind(
            "<Configure>",
            lambda _e: cv.configure(scrollregion=cv.bbox("all")))
        cv.bind("<Configure>",
                lambda e: cv.itemconfig(win, width=e.width))

        def _on_scroll(e):
            cv.yview_scroll(
                -1 * (e.delta // 120 if e.delta else (-1 if e.num == 5 else 1)),
                "units")
        for seq in ("<MouseWheel>", "<Button-4>", "<Button-5>"):
            cv.bind(seq, _on_scroll)

        # Status / feedback label (flashes green on save)
        self._status_lbl = tk.Label(
            self, text="", bg=sp.BG_PANEL, fg=sp.GREEN,
            font=sp.FONT_MONO_XS)
        self._status_lbl.pack(fill="x", padx=6, pady=(2, 0))
        self._status_after_id = None

        # ── Categories ──────────────────────────────────────
        self._build_data_extraction()
        self._build_reverse_search()
        self._build_temporal_analysis()
        self._build_regional_fingerprinting()
        self._build_logging_history()
        self._build_confidence_tracking()
        self._build_reporting()
        self._build_performance()
        self._build_ethical()
        self._build_deep_analysis()

        # ── Footer ──────────────────────────────────────────
        tk.Frame(self, bg=sp.BORDER_LIT, height=1).pack(fill="x", padx=4, pady=(4, 0))

        reset_btn = tk.Button(
            self, text="✕ RESET TO DEFAULTS",
            bg=sp.BG_CARD, fg=sp.RED_COL,
            font=sp.FONT_MONO_XS, relief="flat", cursor="hand2",
            activebackground=sp.BORDER_LIT, activeforeground=sp.RED_COL,
            command=self._on_reset_clicked)
        reset_btn.pack(fill="x", padx=6, pady=(6, 4))

        path_lbl = tk.Label(
            self, text=options.get_options_file_path(),
            bg=sp.BG_PANEL, fg=sp.TEXT_FAINT,
            font=sp.FONT_MONO_XS, wraplength=self.WIDTH - 16,
            justify="left")
        path_lbl.pack(fill="x", padx=6, pady=(0, 6))

    # ── Feedback helper ───────────────────────────────────────
    def _flash_status(self, text: str, colour: str = None):
        """Show a brief confirmation message, then fade it after 1.6s."""
        if self._status_after_id is not None:
            try:
                self.after_cancel(self._status_after_id)
            except Exception:
                pass
        self._status_lbl.configure(text=text, fg=colour or sp.GREEN)
        self._status_after_id = self.after(
            1600, lambda: self._status_lbl.configure(text=""))

    # ── Generic control builders ──────────────────────────────
    def _checkbutton(self, parent, label: str, option_key: str):
        """
        A Checkbutton bound directly to an option key. Reflects the
        current on-disk value immediately and persists on every click.
        """
        var = tk.BooleanVar(value=bool(options.get_option(option_key, False)))

        def _on_toggle():
            options.set_option(option_key, var.get())
            state = "ON" if var.get() else "OFF"
            self._flash_status("✓ {} → {}".format(option_key, state))

        cb = tk.Checkbutton(
            parent, text=label, variable=var,
            command=_on_toggle,
            bg=sp.BG_DARK, fg=sp.TEXT_MID,
            selectcolor=sp.BG_INPUT,
            activebackground=sp.BG_DARK, activeforeground=sp.TEXT_BRIGHT,
            font=sp.FONT_MONO_XS, anchor="w",
            highlightthickness=0, bd=0)
        cb.pack(fill="x", anchor="w", pady=1)
        return var

    def _dropdown(self, parent, label: str, option_key: str, values: list):
        """A labelled ttk.Combobox bound to an option key."""
        row = tk.Frame(parent, bg=sp.BG_DARK)
        row.pack(fill="x", pady=(3, 1))
        tk.Label(row, text=label, bg=sp.BG_DARK, fg=sp.TEXT_MID,
                  font=sp.FONT_MONO_XS).pack(side="left")

        var = tk.StringVar(value=str(options.get_option(option_key, values[0])))
        combo = ttk.Combobox(
            row, textvariable=var, values=values,
            state="readonly", width=8, font=sp.FONT_MONO_XS)
        combo.pack(side="right")

        def _on_change(_e=None):
            options.set_option(option_key, var.get())
            self._flash_status("✓ {} → {}".format(option_key, var.get()))

        combo.bind("<<ComboboxSelected>>", _on_change)
        return var

    def _spinbox(self, parent, label: str, option_key: str,
                 frm: int, to: int, step: int = 1):
        """A labelled Spinbox bound to an integer option key."""
        row = tk.Frame(parent, bg=sp.BG_DARK)
        row.pack(fill="x", pady=(3, 1))
        tk.Label(row, text=label, bg=sp.BG_DARK, fg=sp.TEXT_MID,
                  font=sp.FONT_MONO_XS).pack(side="left")

        var = tk.IntVar(value=int(options.get_option(option_key, frm)))

        def _persist(*_args):
            try:
                value = var.get()
            except (tk.TclError, ValueError):
                return
            options.set_option(option_key, value)
            self._flash_status("✓ {} → {}".format(option_key, value))

        spin = tk.Spinbox(
            row, from_=frm, to=to, increment=step,
            textvariable=var, width=6,
            bg=sp.BG_INPUT, fg=sp.CYAN,
            highlightthickness=0, font=sp.FONT_MONO_XS,
            command=_persist)
        spin.pack(side="right")

        # Also persist typed values (not just arrow clicks)
        spin.bind("<Return>", _persist)
        spin.bind("<FocusOut>", _persist)
        return var

    # ── Categories ──────────────────────────────────────────────
    def _build_data_extraction(self):
        sec = _CollapsibleSection(self._inner, "📊 DATA EXTRACTION")
        sec.pack(fill="x")
        for label, key in [
            ("EXIF metadata",       "extract_exif"),
            ("Text / OCR",          "extract_text_ocr"),
            ("Vehicles",            "extract_vehicles"),
            ("Vegetation",          "extract_vegetation"),
            ("Weather",             "extract_weather"),
            ("Time of day",         "extract_time_of_day"),
            ("Language",            "extract_language"),
            ("Infrastructure",      "extract_infrastructure"),
        ]:
            self._checkbutton(sec.body, label, key)

    def _build_reverse_search(self):
        sec = _CollapsibleSection(self._inner, "🔍 REVERSE SEARCH")
        sec.pack(fill="x")
        self._checkbutton(sec.body, "Enabled", "reverse_search_enabled")
        self._checkbutton(sec.body, "Cache results", "reverse_search_cache")

    def _build_temporal_analysis(self):
        sec = _CollapsibleSection(self._inner, "⏰ TEMPORAL ANALYSIS",
                                   expanded=False)
        sec.pack(fill="x")
        self._checkbutton(sec.body, "Enabled", "temporal_analysis")
        self._checkbutton(sec.body, "Detect tampering", "detect_tampering")
        self._checkbutton(sec.body, "Detect image age", "detect_image_age")

    def _build_regional_fingerprinting(self):
        sec = _CollapsibleSection(self._inner, "🗺️ REGIONAL FINGERPRINTING")
        sec.pack(fill="x")
        self._checkbutton(sec.body, "Vehicle plates", "vehicle_plates_analyzer")
        self._checkbutton(sec.body, "Traffic signs", "traffic_signs_analyzer")
        self._checkbutton(sec.body, "Building architecture",
                           "building_architecture_analyzer")
        self._checkbutton(sec.body, "Utility poles", "utility_poles_analyzer")

    def _build_logging_history(self):
        sec = _CollapsibleSection(self._inner, "💾 LOGGING & HISTORY")
        sec.pack(fill="x")
        self._checkbutton(sec.body, "Auto-save history", "auto_save_history")
        self._checkbutton(sec.body, "Save extracted data", "save_extracted_data")
        self._checkbutton(sec.body, "Save metadata JSON", "save_metadata_json")

    def _build_confidence_tracking(self):
        sec = _CollapsibleSection(self._inner, "📈 CONFIDENCE TRACKING",
                                   expanded=False)
        sec.pack(fill="x")
        self._checkbutton(sec.body, "Track personal accuracy",
                           "track_personal_accuracy")

    def _build_reporting(self):
        sec = _CollapsibleSection(self._inner, "📋 REPORTING", expanded=False)
        sec.pack(fill="x")
        self._checkbutton(sec.body, "Auto-generate reports",
                           "auto_generate_reports")
        self._dropdown(sec.body, "Format:", "report_format", ["pdf", "html"])
        self._checkbutton(sec.body, "Include evidence",
                           "report_include_evidence")
        self._checkbutton(sec.body, "Include contradictions",
                           "report_include_contradictions")

    def _build_performance(self):
        sec = _CollapsibleSection(self._inner, "⚡ PERFORMANCE", expanded=False)
        sec.pack(fill="x")
        self._checkbutton(sec.body, "Cache map tiles", "cache_tiles")
        self._checkbutton(sec.body, "Cache reverse search",
                           "cache_reverse_search")
        self._checkbutton(sec.body, "Cache OCR results", "cache_ocr_results")
        self._spinbox(sec.body, "Max cache (MB):", "max_cache_size_mb",
                       frm=16, to=4096, step=16)

    def _build_ethical(self):
        sec = _CollapsibleSection(self._inner, "🔐 ETHICAL")
        sec.pack(fill="x")
        self._checkbutton(sec.body, "Flag sensitive locations",
                           "flag_sensitive_locations")
        self._checkbutton(sec.body, "Require confirmation on sensitive",
                           "require_confirmation_sensitive")

    def _build_deep_analysis(self):
        sec = _CollapsibleSection(self._inner, "🔬 DEEP ANALYSIS", expanded=False)
        sec.pack(fill="x")

        tk.Label(sec.body,
                 text="Optional forensic powerhouse — 15 specialised\n"
                      "analysers run after normal geolocation completes.\n"
                      "Slower, but adds independent regional evidence.",
                 bg=sp.BG_DARK, fg=sp.TEXT_FAINT, font=sp.FONT_MONO_XS,
                 justify="left", anchor="w").pack(fill="x", pady=(0, 6))

        self._checkbutton(sec.body, "Enable Deep Analysis",
                           "deep_analysis_enabled")
        self._checkbutton(sec.body, "Cache results", "deep_analysis_cache")
        self._spinbox(sec.body, "Timeout (seconds):",
                       "deep_analysis_timeout_seconds",
                       frm=10, to=300, step=10)

    # ── Reset ───────────────────────────────────────────────────
    def _on_reset_clicked(self):
        confirmed = messagebox.askyesno(
            "Reset Settings",
            "Reset ALL settings to their defaults?\n\n"
            "This cannot be undone.",
            parent=self)
        if not confirmed:
            return
        options.reset_to_defaults()
        self._flash_status("✓ All settings reset to defaults", sp.YELLOW)
        # Rebuild the whole panel so every control reflects the reset state
        for child in self._inner.winfo_children():
            child.destroy()
        self._build_data_extraction()
        self._build_reverse_search()
        self._build_temporal_analysis()
        self._build_regional_fingerprinting()
        self._build_logging_history()
        self._build_confidence_tracking()
        self._build_reporting()
        self._build_performance()
        self._build_ethical()
        self._build_deep_analysis()
