"""
customise/theme_dialog.py — SightPoint AI · Theme Picker Dialog
════════════════════════════════════════════════════════════════
A Toplevel window offering:
  • One-click presets — built dynamically from every .py file found
    in customise/themes/ (ships with 5, but any file you add appears
    here too — no code changes needed)
  • ↻ Rescan — re-scans customise/themes/ without closing the dialog,
    so a theme file you just created or edited shows up immediately
  • A scrollable list of every themeable colour role with a live
    swatch — click any swatch to open the system colour picker
  • Font family + size controls
  • Apply (saves + live-reloads the running app where possible)
  • Reset to the Cyber Dark default

All changes are written to ~/.sightpoint/theme.json immediately via
customise_engine.set_theme_value() / set_preset() — there is no
separate save step. "Apply" additionally tries to refresh the
*running* app so you see the result immediately; if that fails for
any reason it falls back to telling you to restart.
"""

import tkinter as tk
from tkinter import ttk, colorchooser, font as tkfont

import customise.customise_engine as themes


class ThemeDialog(tk.Toplevel):
    """
    Usage:
        ThemeDialog(root, on_apply=app.reload_theme_live)

    `on_apply` is called (with no arguments) after a theme change has
    been persisted to disk, so the caller can attempt a live UI
    refresh. If `on_apply` is None or raises, the dialog just tells
    the user to restart to see the change.
    """

    def __init__(self, parent, on_apply=None, **kw):
        # Import here (not at module top level) so this dialog always
        # reflects whatever theme is currently applied to sightpoint.
        import sightpoint as sp
        self._sp = sp

        kw.setdefault("bg", sp.BG_DARK)
        super().__init__(parent, **kw)
        self._on_apply = on_apply
        self._swatch_buttons = {}   # key -> button widget (for live preview)

        self.title("SightPoint AI — Theme")
        self.configure(bg=sp.BG_DARK)
        self.geometry("640x600")
        self.minsize(540, 440)
        self.transient(parent)
        self.grab_set()

        self._working = dict(themes.get_all_theme_values())  # local edit buffer

        self._build()
        self.bind("<Escape>", lambda _e: self.destroy())

    # ── Build ──────────────────────────────────────────────────
    def _build(self):
        sp = self._sp

        hdr = tk.Frame(self, bg=sp.BG_PANEL, height=40)
        hdr.pack(fill="x")
        hdr.pack_propagate(False)
        tk.Label(hdr, text="  🎨  THEME",
                 bg=sp.BG_PANEL, fg=sp.CYAN,
                 font=(sp.FONT_MONO[0], 10, "bold")).pack(side="left", pady=10)
        tk.Frame(self, bg=sp.BORDER_LIT, height=1).pack(fill="x")

        # ── Preset row ──────────────────────────────────────────
        preset_frame = tk.Frame(self, bg=sp.BG_DARK)
        preset_frame.pack(fill="x", padx=14, pady=(10, 6))

        preset_hdr = tk.Frame(preset_frame, bg=sp.BG_DARK)
        preset_hdr.pack(fill="x")
        tk.Label(preset_hdr, text="PRESETS  (from customise/themes/)",
                 bg=sp.BG_DARK, fg=sp.TEXT_DIM,
                 font=sp.FONT_MONO_XS).pack(side="left")
        tk.Button(
            preset_hdr, text="↻ Rescan", bg=sp.BG_DARK, fg=sp.CYAN,
            font=sp.FONT_MONO_XS, relief="flat", cursor="hand2",
            activebackground=sp.BORDER_LIT, activeforeground=sp.CYAN_BRIGHT,
            command=self._rescan_themes
        ).pack(side="right")

        self._preset_btn_row = tk.Frame(preset_frame, bg=sp.BG_DARK)
        self._preset_btn_row.pack(fill="x", pady=(4, 0))
        self._render_preset_buttons()

        current = themes.get_active_preset_name()
        self._active_lbl = tk.Label(
            preset_frame, text="Active: {}".format(current),
            bg=sp.BG_DARK, fg=sp.TEXT_FAINT, font=sp.FONT_MONO_XS)
        self._active_lbl.pack(anchor="w", pady=(4, 0))

        tk.Frame(self, bg=sp.BORDER, height=1).pack(fill="x", padx=14, pady=(8, 0))

        # ── Font controls ────────────────────────────────────────
        font_frame = tk.Frame(self, bg=sp.BG_DARK)
        font_frame.pack(fill="x", padx=14, pady=(10, 6))
        tk.Label(font_frame, text="FONT", bg=sp.BG_DARK,
                 fg=sp.TEXT_DIM, font=sp.FONT_MONO_XS).pack(anchor="w")

        row = tk.Frame(font_frame, bg=sp.BG_DARK)
        row.pack(fill="x", pady=(4, 0))

        tk.Label(row, text="Family:", bg=sp.BG_DARK, fg=sp.TEXT_MID,
                 font=sp.FONT_MONO_XS).pack(side="left")
        try:
            families = sorted(set(tkfont.families(self)))
        except Exception:
            families = ["Courier New", "Consolas", "Segoe UI", "Arial"]
        preferred = ["Courier New", "Consolas", "Segoe UI", "Arial",
                     "Helvetica", "DejaVu Sans Mono", "Menlo", "Monaco"]
        ordered = [f for f in preferred if f in families] + \
                  [f for f in families if f not in preferred]

        self._family_var = tk.StringVar(
            value=self._working.get("FONT_FAMILY", "Courier New"))
        family_combo = ttk.Combobox(
            row, values=ordered, textvariable=self._family_var,
            state="readonly", width=22, font=sp.FONT_MONO_XS)
        family_combo.pack(side="left", padx=(6, 16))
        family_combo.bind("<<ComboboxSelected>>",
                           lambda _e: self._set_working("FONT_FAMILY",
                                                         self._family_var.get()))

        for label, key in [("Normal:", "FONT_SIZE_NORMAL"),
                            ("Small:", "FONT_SIZE_SMALL"),
                            ("XS:", "FONT_SIZE_XS")]:
            tk.Label(row, text=label, bg=sp.BG_DARK, fg=sp.TEXT_MID,
                     font=sp.FONT_MONO_XS).pack(side="left")
            var = tk.IntVar(value=int(self._working.get(key, 10)))
            spin = tk.Spinbox(
                row, from_=6, to=24, width=3, textvariable=var,
                bg=sp.BG_INPUT, fg=sp.CYAN, highlightthickness=0,
                font=sp.FONT_MONO_XS,
                command=lambda k=key, v=var: self._set_working(k, v.get()))
            spin.pack(side="left", padx=(2, 10))
            spin.bind("<Return>",
                      lambda _e, k=key, v=var: self._set_working(k, v.get()))
            spin.bind("<FocusOut>",
                      lambda _e, k=key, v=var: self._set_working(k, v.get()))

        tk.Frame(self, bg=sp.BORDER, height=1).pack(fill="x", padx=14, pady=(8, 0))

        # ── Colour swatches (scrollable) ─────────────────────────
        tk.Label(self, text="COLOURS  (click a swatch to change it)",
                 bg=sp.BG_DARK, fg=sp.TEXT_DIM,
                 font=sp.FONT_MONO_XS).pack(anchor="w", padx=14, pady=(10, 2))

        outer = tk.Frame(self, bg=sp.BG_DARK)
        outer.pack(fill="both", expand=True, padx=14, pady=(0, 6))

        cv = tk.Canvas(outer, bg=sp.BG_DARK, highlightthickness=0)
        sb = ttk.Scrollbar(outer, orient="vertical", command=cv.yview)
        cv.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        cv.pack(side="left", fill="both", expand=True)

        inner = tk.Frame(cv, bg=sp.BG_DARK)
        win = cv.create_window((0, 0), window=inner, anchor="nw")
        inner.bind("<Configure>",
                   lambda _e: cv.configure(scrollregion=cv.bbox("all")))
        cv.bind("<Configure>", lambda e: cv.itemconfig(win, width=e.width))

        def _on_scroll(e):
            cv.yview_scroll(
                -1 * (e.delta // 120 if e.delta else (-1 if e.num == 5 else 1)),
                "units")
        for seq in ("<MouseWheel>", "<Button-4>", "<Button-5>"):
            cv.bind(seq, _on_scroll)

        for key in themes.COLOR_KEYS:
            self._build_swatch_row(inner, key)

        # ── Bottom buttons ────────────────────────────────────────
        tk.Frame(self, bg=sp.BORDER_LIT, height=1).pack(fill="x")
        btns = tk.Frame(self, bg=sp.BG_DARK)
        btns.pack(fill="x", padx=14, pady=10)

        tk.Button(btns, text="↺  RESET TO DEFAULT", bg=sp.BG_INPUT, fg=sp.TEXT_DIM,
                  font=(sp.FONT_MONO_XS[0], sp.FONT_MONO_XS[1], "bold"),
                  relief="flat", cursor="hand2", pady=8,
                  activebackground=sp.BORDER_LIT, activeforeground=sp.WHITE,
                  command=self._reset).pack(side="left")

        tk.Button(btns, text="✓  APPLY", bg=sp.CYAN, fg=sp.BG_DARK,
                  font=(sp.FONT_MONO_XS[0], sp.FONT_MONO_XS[1], "bold"),
                  relief="flat", cursor="hand2", pady=8,
                  activebackground=sp.CYAN_BRIGHT, activeforeground=sp.BG_DARK,
                  command=self._apply).pack(side="right", padx=(6, 0))

        tk.Button(btns, text="✕  CLOSE", bg=sp.BG_INPUT, fg=sp.TEXT_DIM,
                  font=(sp.FONT_MONO_XS[0], sp.FONT_MONO_XS[1], "bold"),
                  relief="flat", cursor="hand2", pady=8,
                  activebackground=sp.BORDER_LIT, activeforeground=sp.WHITE,
                  command=self.destroy).pack(side="right")

        self._status_lbl = tk.Label(self, text="", bg=sp.BG_DARK,
                                     font=sp.FONT_MONO_XS)
        self._status_lbl.pack(anchor="w", padx=14, pady=(0, 8))

    def _render_preset_buttons(self):
        """(Re)build the row of preset buttons from whatever themes
        are currently known (customise_engine.get_available_themes())."""
        sp = self._sp
        for w in self._preset_btn_row.winfo_children():
            w.destroy()

        available = themes.get_available_themes()
        # Sort so the 5 shipped themes appear first in a stable order,
        # any user-added ones after, alphabetically.
        shipped_order = ["Cyber Dark", "Light Mode", "Solarized Dark",
                          "Midnight Purple", "High Contrast"]
        names = [n for n in shipped_order if n in available] + \
                sorted(n for n in available if n not in shipped_order)

        for name in names:
            tk.Button(
                self._preset_btn_row, text=name,
                bg=sp.BG_CARD, fg=sp.CYAN,
                font=sp.FONT_MONO_XS, relief="flat", cursor="hand2",
                padx=8, pady=6,
                activebackground=sp.BORDER_LIT, activeforeground=sp.CYAN_BRIGHT,
                command=lambda n=name: self._load_preset(n)
            ).pack(side="left", padx=(0, 6), pady=(0, 4), fill="x", expand=True)

    def _rescan_themes(self):
        """Re-scan customise/themes/ for new/edited files without
        closing the dialog. Newly added theme files appear as preset
        buttons immediately."""
        themes.discover_themes()  # refresh the module cache indirectly
        # discover_themes() doesn't itself update _AVAILABLE_THEMES —
        # only load_theme() does — so call it explicitly here without
        # disturbing the currently active/working theme.
        fresh = themes.discover_themes()
        # Manually refresh the engine's cache so get_available_themes()
        # reflects the new scan immediately.
        import customise.customise_engine as engine
        engine._AVAILABLE_THEMES = fresh
        self._render_preset_buttons()
        self._status_lbl.configure(
            text="Rescanned customise/themes/ — found {} theme(s).".format(
                len(fresh)),
            fg=self._sp.CYAN)

    def _build_swatch_row(self, parent, key: str):
        sp = self._sp
        row = tk.Frame(parent, bg=sp.BG_DARK)
        row.pack(fill="x", pady=2)

        label = themes.KEY_LABELS.get(key, key)
        tk.Label(row, text=label, bg=sp.BG_DARK, fg=sp.TEXT_MID,
                 font=sp.FONT_MONO_XS, width=28, anchor="w").pack(side="left")

        current_color = self._working.get(key, "#000000")
        swatch = tk.Button(
            row, text="  " + current_color + "  ",
            bg=current_color, fg=self._contrasting_fg(current_color),
            font=sp.FONT_MONO_XS, relief="flat", cursor="hand2",
            bd=1, highlightbackground=sp.BORDER,
            command=lambda k=key: self._pick_color(k))
        swatch.pack(side="left", padx=(6, 0))
        self._swatch_buttons[key] = swatch

    @staticmethod
    def _contrasting_fg(hex_color: str) -> str:
        """Pick black or white text so the hex label is always readable."""
        try:
            hex_color = hex_color.lstrip("#")
            r, g, b = (int(hex_color[i:i+2], 16) for i in (0, 2, 4))
            luminance = (0.299 * r + 0.587 * g + 0.114 * b)
            return "#000000" if luminance > 140 else "#ffffff"
        except Exception:
            return "#ffffff"

    # ── Actions ────────────────────────────────────────────────
    def _set_working(self, key, value):
        self._working[key] = value

    def _pick_color(self, key: str):
        current = self._working.get(key, "#000000")
        result = colorchooser.askcolor(
            color=current, title="Choose colour — {}".format(key),
            parent=self)
        if result and result[1]:
            new_color = result[1]
            self._working[key] = new_color
            btn = self._swatch_buttons.get(key)
            if btn:
                btn.configure(
                    bg=new_color, text="  " + new_color + "  ",
                    fg=self._contrasting_fg(new_color))
            self._active_lbl.configure(text="Active: Custom")

    def _load_preset(self, name: str):
        available = themes.get_available_themes()
        preset = available.get(name)
        if not preset:
            return
        self._working = dict(preset)
        self._family_var.set(self._working.get("FONT_FAMILY", "Courier New"))
        for key, btn in self._swatch_buttons.items():
            color = self._working.get(key, "#000000")
            btn.configure(bg=color, text="  " + color + "  ",
                          fg=self._contrasting_fg(color))
        self._active_lbl.configure(text="Active: {}".format(name))
        self._status_lbl.configure(
            text="Preset '{}' loaded — click APPLY to save & use it.".format(name),
            fg=self._sp.CYAN)

    def _reset(self):
        self._load_preset(themes.DEFAULT_PRESET_NAME)

    def _apply(self):
        sp = self._sp
        # Persist every working value
        for key in themes.THEME_KEYS:
            if key in self._working:
                themes.set_theme_value(key, self._working[key])

        # If the whole buffer matches a known theme exactly, record
        # that name instead of leaving it stamped "Custom".
        available = themes.get_available_themes()
        for name, preset in available.items():
            if all(self._working.get(k) == v for k, v in preset.items()):
                import customise.customise_engine as engine
                engine._ACTIVE_PRESET_NAME = name
                engine.save_theme()
                break

        themes.apply_theme_to_module(self._working)

        reload_ok = False
        reload_err = ""
        if self._on_apply:
            try:
                self._on_apply()
                reload_ok = True
            except Exception as exc:
                reload_err = str(exc)

        if reload_ok:
            self._status_lbl.configure(
                text="✓  Theme saved and applied live.", fg=sp.GREEN)
        else:
            msg = "✓  Theme saved — restart SightPoint AI to see it fully applied."
            if reload_err:
                msg += "  ({})".format(reload_err[:60])
            self._status_lbl.configure(text=msg, fg=sp.YELLOW)
