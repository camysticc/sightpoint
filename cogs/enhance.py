"""
cogs/enhance.py — SightPoint AI · Image Enhancement Cog
════════════════════════════════════════════════════════
Adds a 🔬 ENHANCE tab to the SightPointApp notebook.

How it works
────────────
1.  Load any image (from the main app's current image, or browse a new one).
2.  Click ANALYSE — Gemini looks at the image and decides what PIL operations
    would most improve it for geolocation analysis (sharpening, contrast,
    denoising, brightness correction, etc.).
    There is NO preset filter — Gemini picks the combination and parameters
    each time based on what the image actually needs.
3.  The chosen operations are applied with PIL and a preview is shown.
4.  Click USE ENHANCED — the enhanced image replaces the current image in
    the main app and is ready for standard or deep analysis.

Works on any image, including extracted video frames.

API key requirements
────────────────────
Uses the same Gemini API key as the rest of the app — no extra permissions
needed.  Enhancement is done entirely with PIL on your machine; Gemini only
provides the recommendation, not image generation.
"""

import threading
import os
import io
import tempfile
import datetime
import base64
import json
import re
import traceback
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from pathlib import Path

import sightpoint as sp

PIL_AVAILABLE = sp.PIL_AVAILABLE
if PIL_AVAILABLE:
    from PIL import Image, ImageTk, ImageFilter, ImageEnhance as PILEnhance

# ─────────────────────────────────────────────────────────────────
#  AVAILABLE ENHANCEMENT OPERATIONS
#  Gemini picks from this palette.  Every entry maps a JSON key to
#  a callable that takes (img, **params) and returns a PIL Image.
# ─────────────────────────────────────────────────────────────────
def _op_sharpen(img, factor=2.0, **_):
    return PILEnhance.Sharpness(img).enhance(float(factor))

def _op_contrast(img, factor=1.4, **_):
    return PILEnhance.Contrast(img).enhance(float(factor))

def _op_brightness(img, factor=1.1, **_):
    return PILEnhance.Brightness(img).enhance(float(factor))

def _op_color(img, factor=1.2, **_):
    return PILEnhance.Color(img).enhance(float(factor))

def _op_unsharp_mask(img, radius=2.0, percent=150, threshold=3, **_):
    return img.filter(ImageFilter.UnsharpMask(
        radius=float(radius),
        percent=int(percent),
        threshold=int(threshold)))

def _op_edge_enhance(img, **_):
    return img.filter(ImageFilter.EDGE_ENHANCE)

def _op_detail(img, **_):
    return img.filter(ImageFilter.DETAIL)

def _op_median(img, size=3, **_):
    """Noise reduction — useful before sharpening."""
    s = int(size)
    s = max(1, min(s, 9))    # clamp to 1–9
    if s % 2 == 0:
        s += 1   # MedianFilter requires odd size
    return img.filter(ImageFilter.MedianFilter(size=s))

def _op_gaussian_blur(img, radius=0.8, **_):
    """Light blur to reduce noise before edge enhancement."""
    return img.filter(ImageFilter.GaussianBlur(radius=float(radius)))

def _op_autolevels(img, **_):
    """Stretch each channel to full range (basic auto-levels)."""
    import numpy as np
    arr = np.array(img, dtype=np.float32)
    for c in range(arr.shape[2]):
        lo, hi = arr[:, :, c].min(), arr[:, :, c].max()
        if hi > lo:
            arr[:, :, c] = (arr[:, :, c] - lo) / (hi - lo) * 255
    return Image.fromarray(arr.clip(0, 255).astype(np.uint8))

ENHANCEMENT_OPS = {
    "sharpen":       _op_sharpen,
    "contrast":      _op_contrast,
    "brightness":    _op_brightness,
    "color":         _op_color,
    "unsharp_mask":  _op_unsharp_mask,
    "edge_enhance":  _op_edge_enhance,
    "detail":        _op_detail,
    "median":        _op_median,
    "gaussian_blur": _op_gaussian_blur,
    "autolevels":    _op_autolevels,
}

OP_DESCRIPTIONS = {
    "sharpen":       "Sharpness boost",
    "contrast":      "Contrast boost",
    "brightness":    "Brightness correction",
    "color":         "Colour saturation boost",
    "unsharp_mask":  "Unsharp mask (edge recovery)",
    "edge_enhance":  "Edge enhancement",
    "detail":        "Detail filter",
    "median":        "Median noise reduction",
    "gaussian_blur": "Light gaussian denoise",
    "autolevels":    "Auto-levels (channel stretch)",
}

# ─────────────────────────────────────────────────────────────────
#  GEMINI QUALITY ASSESSMENT
# ─────────────────────────────────────────────────────────────────
def _gemini_assess_and_plan(image_path: str, api_key: str,
                             log_cb=None) -> dict:
    """
    Send the image to Gemini and ask it to:
      1. Assess what's visually wrong with it
      2. Choose the best sequence of PIL operations from our palette
      3. Return JSON with the plan

    Returns dict:
        {
          "assessment": "...",
          "quality_score": 1-10,
          "operations": [
              {"op": "gaussian_blur", "radius": 0.5},
              {"op": "unsharp_mask", "radius": 2, "percent": 150, "threshold": 3},
              ...
          ],
          "reasoning": "..."
        }
    """
    import requests as _req

    def _log(msg, lvl="INFO"):
        if log_cb:
            try: log_cb(msg, lvl)
            except Exception: pass

    ext  = Path(image_path).suffix.lower()
    mime = {".jpg":"image/jpeg", ".jpeg":"image/jpeg",
            ".png":"image/png", ".webp":"image/webp"}.get(ext, "image/jpeg")
    with open(image_path, "rb") as f:
        b64 = base64.b64encode(f.read()).decode()

    ops_list = "\n".join(
        '  • "{}" — {}'.format(k, v) for k, v in OP_DESCRIPTIONS.items())

    prompt = (
        "You are an expert image quality analyst.\n\n"
        "Analyse the quality of this image specifically for the purpose of "
        "geolocation and OSINT analysis — i.e. identifying text, landmarks, "
        "signage, vehicle plates, and fine detail.\n\n"
        "Identify any/all of these issues:\n"
        "  • Motion blur (camera or subject movement)\n"
        "  • Defocus blur (out of focus)\n"
        "  • Low contrast (flat, washed out)\n"
        "  • Noise / grain (especially in dark areas)\n"
        "  • Underexposure (too dark)\n"
        "  • Overexposure (blown highlights)\n"
        "  • Colour cast (unusual tint)\n"
        "  • Compression artefacts (JPEG blockiness)\n\n"
        "Then choose a sequence of operations from ONLY this list to correct "
        "the issues and maximise clarity for geolocation analysis:\n"
        "{}\n\n"
        "RULES:\n"
        "  • Use at most 4 operations — more is not always better\n"
        "  • Order matters — e.g. denoise before sharpen\n"
        "  • If the image is already good quality, use 1 light sharpen at most\n"
        "  • Only include operations that will genuinely help\n"
        "  • Choose parameter values carefully for each operation\n\n"
        "Return ONLY raw JSON starting immediately with {{ — "
        "no preamble, no explanation, no markdown, no fences:\n"
        '{{\n'
        '  "assessment": "<what is wrong with this image>",\n'
        '  "quality_score": <1-10 where 10 is perfect>,\n'
        '  "issues": ["<issue1>","<issue2>"],\n'
        '  "operations": [\n'
        '    {{"op": "<op_name>", "<param1>": <value>, "<param2>": <value>}},\n'
        '    ...\n'
        '  ],\n'
        '  "reasoning": "<why these operations in this order>"\n'
        '}}'
    ).format(ops_list)

    _log("Sending image to Gemini for quality assessment…")

    models  = ["gemini-2.5-flash", "gemini-2.5-flash-lite", "gemini-2.5-pro"]
    base    = ("https://generativelanguage.googleapis.com/v1beta/"
               "models/{}:generateContent")
    headers = {"Content-Type": "application/json",
               "x-goog-api-key": api_key}
    payload = {
        "contents": [{"parts": [
            {"inline_data": {"mime_type": mime, "data": b64}},
            {"text": prompt},
        ]}],
        "generationConfig": {"temperature": 0.1, "maxOutputTokens": 2048},
    }

    resp = None
    for model in models:
        try:
            r = _req.post(base.format(model), json=payload,
                          headers=headers, timeout=60)
            if r.status_code == 200:
                resp = r
                _log("Assessment model: {}".format(model))
                break
            elif r.status_code == 404:
                continue
            r.raise_for_status()
        except _req.exceptions.Timeout:
            raise RuntimeError("Timed out waiting for Gemini assessment.")
        except _req.exceptions.HTTPError as exc:
            code = exc.response.status_code if exc.response else "?"
            if code == 404:
                continue
            msg = {403: "Invalid API key.", 429: "Rate limit."}.get(code, str(exc))
            raise RuntimeError("HTTP {}: {}".format(code, msg))
        except _req.exceptions.RequestException as exc:
            raise RuntimeError("Network error: {}".format(exc))

    if resp is None:
        raise RuntimeError("No Gemini model available for enhancement assessment.")

    try:
        raw = resp.json()["candidates"][0]["content"]["parts"][0]["text"]
    except (KeyError, IndexError, TypeError) as exc:
        raise RuntimeError("Unexpected Gemini response: {}".format(exc))

    raw = re.sub(r"```[a-zA-Z]*\s*", "", raw)
    raw = re.sub(r"```", "", raw).strip().strip("`").strip()

    # Try all of: full {…} match, find first { and extract from there,
    # or attempt direct parse in case the entire response is JSON.
    plan = None
    candidates = []

    m = re.search(r"\{[\s\S]*\}", raw)
    if m:
        candidates.append(m.group())

    # Also try from the first { to end of string (handles partial-wrap)
    brace = raw.find("{")
    if brace != -1:
        candidates.append(raw[brace:])

    # And try the whole raw string
    candidates.append(raw)

    for js in candidates:
        # Try as-is
        try:
            plan = json.loads(js)
            break
        except json.JSONDecodeError:
            pass
        # Try trailing-comma fix
        try:
            plan = json.loads(re.sub(r",\s*([}\]])", r"\1", js))
            break
        except json.JSONDecodeError:
            pass
        # Try closing unclosed brackets — also close unclosed strings
        try:
            repaired = js.rstrip().rstrip(",")
            repaired = re.sub(r',\s*"[^"]*$', "", repaired).rstrip(",")
            # If an odd number of quotes, close the open string
            if repaired.count('"') % 2 != 0:
                repaired += '"'
            opens   = repaired.count("[") - repaired.count("]")
            opens_c = repaired.count("{") - repaired.count("}")
            repaired += "]" * max(0, opens) + "}" * max(0, opens_c)
            plan = json.loads(repaired)
            break
        except json.JSONDecodeError:
            pass

    if plan is None:
        # Last resort: regex-extract the fields we need directly
        # Use [^"]* to match even unclosed strings
        assessment = re.search(r'"assessment"\s*:\s*"([^"]*)', raw)
        quality    = re.search(r'"quality_score"\s*:\s*(\d+)', raw)
        reasoning  = re.search(r'"reasoning"\s*:\s*"([^"]*)', raw)
        ops_match  = re.search(r'"operations"\s*:\s*(\[[\s\S]*?\])', raw)
        try:
            ops = json.loads(ops_match.group(1)) if ops_match else []
        except Exception:
            ops = []
        if assessment:
            plan = {
                "assessment":    assessment.group(1),
                "quality_score": int(quality.group(1)) if quality else 5,
                "issues":        [],
                "operations":    ops,
                "reasoning":     reasoning.group(1) if reasoning else "",
            }
            _log("JSON repaired via regex fallback.", "WARN")
        else:
            # Gemini returned pure text with no JSON structure at all.
            # Treat the raw text as the assessment and apply a safe default.
            _log("No JSON found — using raw text as assessment.", "WARN")
            plan = {
                "assessment":    raw[:300] if raw else "Could not assess image.",
                "quality_score": 5,
                "issues":        [],
                "operations":    [
                    {"op": "unsharp_mask", "radius": 1.5, "percent": 100, "threshold": 3},
                    {"op": "contrast", "factor": 1.2},
                ],
                "reasoning":     "Gemini did not return structured JSON. "
                                 "Applying safe defaults (light sharpen + contrast).",
            }

    _log("Assessment: {} (quality {}/10)".format(
        plan.get("assessment", "?")[:60],
        plan.get("quality_score", "?")), "OK")
    return plan


# ─────────────────────────────────────────────────────────────────
#  APPLY PIL OPERATIONS
# ─────────────────────────────────────────────────────────────────
def apply_enhancement_plan(image_path: str, plan: dict,
                            out_path: str = None) -> str:
    """
    Execute the operations in `plan["operations"]` using PIL.
    Saves the result to `out_path` (auto-generated if None).
    Returns the output path.
    """
    if not PIL_AVAILABLE:
        raise RuntimeError("Pillow not installed.")

    img = Image.open(image_path).convert("RGB")
    applied = []

    for op_def in plan.get("operations", []):
        op_name = op_def.get("op", "").lower()
        fn = ENHANCEMENT_OPS.get(op_name)
        if fn is None:
            continue   # Gemini hallucinated an op name — skip safely
        params = {k: v for k, v in op_def.items() if k != "op"}
        try:
            img = fn(img, **params)
            applied.append(op_name)
        except Exception:
            pass   # bad parameter — skip this op, continue

    if not out_path:
        tmp_dir = os.path.join(tempfile.gettempdir(), "sightpoint_enhanced")
        os.makedirs(tmp_dir, exist_ok=True)
        ts  = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        out_path = os.path.join(tmp_dir, "enhanced_{}.jpg".format(ts))

    img.save(out_path, "JPEG", quality=95)
    return out_path, applied


# ─────────────────────────────────────────────────────────────────
#  THE COG
# ─────────────────────────────────────────────────────────────────
class EnhanceCog:
    """
    Image enhancement cog.  Injected into SightPointApp by setup().

    Adds a  🔬 ENHANCE  tab.  Gemini decides what to apply;
    PIL does the actual pixel work locally.
    """

    def __init__(self, app):
        self.app  = app
        self.root = app.root
        self.term = app._term
        self.hud  = app._hud
        self.nb   = app._nb

        self._source_path   = None   # original image being enhanced
        self._enhanced_path = None   # output after applying plan
        self._plan          = None   # last Gemini plan
        self._before_ref    = None   # PhotoImage GC guard
        self._after_ref     = None

        self._build_tab()
        self.term.log("EnhanceCog loaded — 🔬 ENHANCE tab ready.", "SYS")

    # ── Tab construction ──────────────────────────────────────
    def _build_tab(self):
        tab = tk.Frame(self.nb, bg=sp.BG_DARK)
        self.nb.add(tab, text="  🔬 ENHANCE  ")
        self._populate_tab(tab)

    def _populate_tab(self, parent):
        # Header
        hdr = tk.Frame(parent, bg=sp.BG_PANEL)
        hdr.pack(fill="x")
        tk.Label(hdr,
                  text="  AI-DETERMINED IMAGE ENHANCEMENT",
                  bg=sp.BG_PANEL, fg=sp.TEXT_DIM,
                  font=sp.FONT_MONO_XS).pack(side="left", pady=6)
        tk.Frame(parent, bg=sp.BORDER_LIT, height=1).pack(fill="x")

        # Source row
        src_row = tk.Frame(parent, bg=sp.BG_DARK)
        src_row.pack(fill="x", padx=8, pady=6)
        self._mkbtn(src_row, "◈ USE CURRENT IMAGE",
                    self._use_current_image,
                    bg=sp.CYAN, fg=sp.BG_DARK).pack(side="left", padx=(0, 8))
        self._mkbtn(src_row, "◈ BROWSE IMAGE",
                    self._browse_image).pack(side="left", padx=(0, 12))
        self._src_lbl = tk.Label(src_row,
                                  text="No image selected",
                                  bg=sp.BG_DARK, fg=sp.TEXT_FAINT,
                                  font=sp.FONT_MONO_XS)
        self._src_lbl.pack(side="left")

        # Action row
        act_row = tk.Frame(parent, bg=sp.BG_DARK)
        act_row.pack(fill="x", padx=8, pady=(0, 6))
        self._mkbtn(act_row, "🔬 ANALYSE & ENHANCE",
                    self._run_enhance,
                    bg=sp.CYAN, fg=sp.BG_DARK).pack(side="left", padx=(0, 8))
        self._mkbtn(act_row, "✓ USE ENHANCED FOR ANALYSIS",
                    self._apply_to_main).pack(side="left", padx=(0, 8))
        self._mkbtn(act_row, "✕ RESET",
                    self._reset).pack(side="left")

        # Progress / status
        self._progress_lbl = tk.Label(parent, text="",
                                       bg=sp.BG_DARK, fg=sp.CYAN,
                                       font=sp.FONT_MONO_XS)
        self._progress_lbl.pack(anchor="w", padx=10)

        # Assessment card
        assess_frame = tk.Frame(parent, bg=sp.BG_CARD,
                                  highlightbackground=sp.BORDER,
                                  highlightthickness=1)
        assess_frame.pack(fill="x", padx=8, pady=(0, 6))
        tk.Label(assess_frame, text="GEMINI ASSESSMENT",
                  bg=sp.BG_CARD, fg=sp.TEXT_DIM,
                  font=sp.FONT_MONO_XS).pack(anchor="w", padx=10, pady=(6, 2))
        self._assess_lbl = tk.Label(assess_frame, text="—",
                                     bg=sp.BG_CARD, fg=sp.TEXT_MID,
                                     font=sp.FONT_MONO_SM,
                                     wraplength=800, justify="left")
        self._assess_lbl.pack(anchor="w", padx=10, pady=(0, 4))

        # Operations applied
        tk.Label(assess_frame, text="OPERATIONS APPLIED",
                  bg=sp.BG_CARD, fg=sp.TEXT_DIM,
                  font=sp.FONT_MONO_XS).pack(anchor="w", padx=10, pady=(2, 2))
        self._ops_lbl = tk.Label(assess_frame, text="—",
                                  bg=sp.BG_CARD, fg=sp.CYAN,
                                  font=sp.FONT_MONO_SM)
        self._ops_lbl.pack(anchor="w", padx=10, pady=(0, 8))

        # Before / After panels
        ba_frame = tk.Frame(parent, bg=sp.BG_DARK)
        ba_frame.pack(fill="both", expand=True, padx=8, pady=(0, 8))

        for side, attr, label, colour in [
            ("left",  "_before_canvas", "ORIGINAL",  sp.TEXT_DIM),
            ("right", "_after_canvas",  "ENHANCED",  sp.GREEN),
        ]:
            panel = tk.Frame(ba_frame, bg=sp.BG_CARD,
                              highlightbackground=sp.BORDER, highlightthickness=1)
            panel.pack(side=side, fill="both", expand=True,
                        padx=(0 if side == "right" else 0, 4 if side == "left" else 0))
            tk.Label(panel, text=label,
                      bg=sp.BG_CARD, fg=colour,
                      font=sp.FONT_MONO_XS).pack(pady=(4, 0))
            cv = tk.Canvas(panel, bg=sp.BG_DARK,
                            highlightthickness=0, cursor="crosshair")
            cv.pack(fill="both", expand=True, padx=4, pady=4)
            setattr(self, attr, cv)

    # ── Image selection ───────────────────────────────────────
    def _use_current_image(self):
        path = getattr(self.app, "image_path", None)
        if not path:
            messagebox.showwarning(
                "No Image",
                "Load an image in the main panel first, "
                "then come back to Enhance.")
            return
        self._set_source(path)

    def _browse_image(self):
        path = filedialog.askopenfilename(
            title="Select Image to Enhance",
            filetypes=[("Images", "*.jpg *.jpeg *.png *.webp *.bmp"),
                       ("All files", "*.*")])
        if path:
            self._set_source(path)

    def _set_source(self, path: str):
        self._source_path   = path
        self._enhanced_path = None
        self._plan          = None
        name = Path(path).name
        self._src_lbl.configure(text=name, fg=sp.CYAN_BRIGHT)
        self._set_progress("Image loaded: {}".format(name))
        self._assess_lbl.configure(text="—")
        self._ops_lbl.configure(text="—")
        self._show_image(self._before_canvas, path, "_before_ref")
        # Clear after panel
        self._after_canvas.delete("all")
        self.term.log("Enhance: source set to {}".format(name), "INFO")

    # ── Main enhance pipeline ─────────────────────────────────
    def _run_enhance(self):
        if not self._source_path:
            messagebox.showwarning("No Image", "Select an image first.")
            return
        key = sp.GEMINI_API_KEY
        if not key:
            messagebox.showerror("No API Key",
                                  "Set your Gemini API key in Settings.")
            return

        self._set_progress("Step 1/2 — Gemini analysing image quality…",
                            sp.YELLOW)
        self.hud.set_status("ENHANCING", sp.YELLOW)

        def _do():
            # Step 1: Gemini decides what to do
            try:
                plan = _gemini_assess_and_plan(
                    self._source_path, key,
                    log_cb=lambda m, l="INFO":
                        self.root.after(0, lambda msg=m, lvl=l:
                            self.term.log(msg, lvl)))
            except Exception as exc:
                traceback.print_exc()   # show in terminal
                err = str(exc)
                self.root.after(0, lambda e=err: (
                    self._set_progress("Assessment failed: " + e, sp.RED_COL),
                    self.term.log(e, "ERROR"),
                    self.hud.set_status("ERROR", sp.RED_COL),
                ))
                return

            self.root.after(0, lambda p=plan:
                self._set_progress(
                    "Step 2/2 — Applying {} operations with PIL…".format(
                        len(p.get("operations", []))),
                    sp.YELLOW))

            # Step 2: Apply PIL ops locally
            try:
                out_path, applied = apply_enhancement_plan(
                    self._source_path, plan)
            except Exception as exc:
                traceback.print_exc()   # show in terminal
                err = str(exc)
                self.root.after(0, lambda e=err: (
                    self._set_progress("Enhancement failed: " + e, sp.RED_COL),
                    self.term.log(e, "ERROR"),
                    self.hud.set_status("ERROR", sp.RED_COL),
                ))
                return

            self.root.after(0, lambda p=plan, o=out_path, a=applied:
                self._enhancement_done(p, o, a))

        threading.Thread(target=_do, daemon=True).start()

    def _enhancement_done(self, plan: dict, out_path: str, applied: list):
        self._plan          = plan
        self._enhanced_path = out_path

        # Update assessment card
        assessment = plan.get("assessment", "—")
        quality    = plan.get("quality_score", "?")
        reasoning  = plan.get("reasoning", "")
        self._assess_lbl.configure(
            text="Quality score: {}/10\n{}\n\n{}".format(
                quality, assessment, reasoning))

        # Show ops
        ops_display = []
        for op_def in plan.get("operations", []):
            op_name = op_def.get("op", "?")
            params  = {k: v for k, v in op_def.items() if k != "op"}
            desc    = OP_DESCRIPTIONS.get(op_name, op_name)
            if params:
                param_str = "  ({})".format(
                    ", ".join("{}={}".format(k, v) for k, v in params.items()))
            else:
                param_str = ""
            ops_display.append("◈ {}{}".format(desc, param_str))
        self._ops_lbl.configure(
            text="\n".join(ops_display) if ops_display else "None needed")

        # Show enhanced image in after panel
        self._show_image(self._after_canvas, out_path, "_after_ref")

        self._set_progress(
            "Enhanced with {}  —  click ✓ USE ENHANCED to apply for analysis".format(
                ", ".join(applied) if applied else "no operations"),
            sp.GREEN)
        self.hud.set_status("COMPLETE", sp.GREEN)
        self.term.log("Enhancement complete: {}".format(", ".join(applied)), "OK")

    # ── Apply to main app ─────────────────────────────────────
    def _apply_to_main(self):
        if not self._enhanced_path:
            messagebox.showwarning("Nothing Enhanced",
                                    "Run Analyse & Enhance first.")
            return
        try:
            self.app._load_image(self._enhanced_path)
            # Switch to MAP tab so user can see the analysis panel
            self.nb.select(0)
            self.term.log(
                "Enhanced image loaded into main analysis panel.", "OK")
        except Exception as exc:
            self.term.log("Could not apply enhanced image: {}".format(exc),
                           "ERROR")

    # ── Reset ─────────────────────────────────────────────────
    def _reset(self):
        self._source_path   = None
        self._enhanced_path = None
        self._plan          = None
        self._before_ref    = None
        self._after_ref     = None
        self._src_lbl.configure(text="No image selected", fg=sp.TEXT_FAINT)
        self._assess_lbl.configure(text="—")
        self._ops_lbl.configure(text="—")
        self._before_canvas.delete("all")
        self._after_canvas.delete("all")
        self._set_progress("")
        self.hud.set_status("IDLE", sp.CYAN)

    # ── Canvas image display ──────────────────────────────────
    def _show_image(self, canvas: tk.Canvas, path: str, ref_attr: str):
        """Display an image in a canvas, fit to its current size."""
        if not PIL_AVAILABLE:
            return
        try:
            canvas.update_idletasks()
            w = max(canvas.winfo_width(),  200)
            h = max(canvas.winfo_height(), 150)

            img = Image.open(path).convert("RGB")
            img.thumbnail((w, h), Image.LANCZOS)

            tk_img = ImageTk.PhotoImage(img)
            setattr(self, ref_attr, tk_img)   # GC guard

            canvas.delete("all")
            # Centre the image
            x = (w - img.width)  // 2
            y = (h - img.height) // 2
            canvas.create_image(x, y, anchor="nw", image=tk_img)
        except Exception as exc:
            canvas.delete("all")
            canvas.create_text(10, 10, anchor="nw",
                                text="Cannot display: {}".format(exc),
                                fill=sp.RED_COL, font=sp.FONT_MONO_XS)

    # ── Helpers ───────────────────────────────────────────────
    def _set_progress(self, text: str, colour: str = None):
        try:
            self._progress_lbl.configure(
                text=text, fg=colour or sp.CYAN)
        except Exception:
            pass

    def _mkbtn(self, parent, text: str, cmd,
               fg: str = sp.CYAN, bg: str = sp.BG_CARD):
        return tk.Button(
            parent,
            text=text,
            command=cmd,
            bg=bg, fg=fg,
            font=sp.FONT_MONO_XS,
            relief="flat",
            cursor="hand2",
            padx=10, pady=5,
            activebackground=sp.BORDER_LIT,
            activeforeground=sp.WHITE)


# ─────────────────────────────────────────────────────────────────
#  COG ENTRY POINT
# ─────────────────────────────────────────────────────────────────
def setup(app) -> EnhanceCog:
    """
    Called by main.py after SightPointApp is created.
    Injects the 🔬 ENHANCE tab into the notebook.
    """
    return EnhanceCog(app)
