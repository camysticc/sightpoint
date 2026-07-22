#!/usr/bin/env python3
"""
╔══════════════════════════════════════════════════════════════════╗
║     SightPoint AI  v1.0  —  Visual Geolocation Intelligence      ║
║  Fully self-contained — all maps render inside the tkinter UI    ║
║  No browser opened. No local server. No external windows.        ║
╚══════════════════════════════════════════════════════════════════╝
Install:  pip install pillow requests
"""

# ─────────────────────────────────────────────────────────────────
#  CONFIG  — API key is stored in ~/.sightpoint/config.json
#  Never hard-code your key here. Run the app and use the
#  Settings dialog to enter it on first launch.
# ─────────────────────────────────────────────────────────────────
import os as _os
import json as _json
from pathlib import Path as _Path

_CONFIG_DIR  = _Path.home() / ".sightpoint"
_CONFIG_FILE = _CONFIG_DIR / "config.json"

def _load_config() -> dict:
    try:
        with open(_CONFIG_FILE, "r", encoding="utf-8") as _f:
            return _json.load(_f)
    except Exception:
        return {}

def _save_config(data: dict):
    _CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    with open(_CONFIG_FILE, "w", encoding="utf-8") as _f:
        _json.dump(data, _f, indent=2)

_config = _load_config()
GEMINI_API_KEY = _config.get("gemini_api_key", "")
# ─────────────────────────────────────────────────────────────────

import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import threading
import base64
import json
import math
import time
import datetime
import io
import re
import csv
import urllib.request
from pathlib import Path
from collections import deque

try:
    from PIL import (Image, ImageTk, ImageDraw,
                     ImageFilter, ImageEnhance, ExifTags)
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False

try:
    import requests
    REQUESTS_AVAILABLE = True
except ImportError:
    REQUESTS_AVAILABLE = False


# ═════════════════════════════════════════════════════════════════
#  THEME
# ═════════════════════════════════════════════════════════════════
BG_DARK      = "#02060d"
BG_PANEL     = "#050a14"
BG_CARD      = "#080e1c"
BG_INPUT     = "#0a1222"
BG_TERM      = "#010408"
BORDER       = "#14243a"
BORDER_LIT   = "#1e3d60"
CYAN         = "#00d8ff"
CYAN_BRIGHT  = "#50eaff"
CYAN_DIM     = "#083040"
TEXT_BRIGHT  = "#f4f9ff"
TEXT_MID     = "#c0d4ec"
TEXT_DIM     = "#5c7fa0"
TEXT_FAINT   = "#223040"
GREEN        = "#00ff99"
YELLOW       = "#ffd000"
RED_COL      = "#ff2244"
PURPLE       = "#bb55ff"
WHITE        = "#ffffff"

FONT_MONO    = ("Courier New", 10)
FONT_MONO_SM = ("Courier New", 8)
FONT_MONO_XS = ("Courier New", 7)

COUNTRIES = [
    "Afghanistan","Albania","Algeria","Argentina","Armenia","Australia","Austria",
    "Azerbaijan","Bangladesh","Belarus","Belgium","Bolivia","Bosnia and Herzegovina",
    "Brazil","Bulgaria","Cambodia","Cameroon","Canada","Chile","China","Colombia",
    "Croatia","Cuba","Czech Republic","Denmark","Dominican Republic","Ecuador",
    "Egypt","Estonia","Ethiopia","Finland","France","Georgia","Germany","Ghana",
    "Greece","Guatemala","Honduras","Hungary","India","Indonesia","Iran","Iraq",
    "Ireland","Israel","Italy","Japan","Jordan","Kazakhstan","Kenya","Kosovo",
    "Latvia","Lebanon","Libya","Lithuania","Luxembourg","Malaysia","Mexico",
    "Mongolia","Morocco","Netherlands","New Zealand","Nigeria","North Korea",
    "Norway","Pakistan","Palestine","Panama","Peru","Philippines","Poland",
    "Portugal","Romania","Russia","Saudi Arabia","Serbia","Singapore","Slovakia",
    "South Africa","South Korea","Spain","Sri Lanka","Sweden","Switzerland",
    "Syria","Taiwan","Thailand","Tunisia","Turkey","Ukraine",
    "United Arab Emirates","United Kingdom","United States","Uruguay",
    "Uzbekistan","Venezuela","Vietnam","Zimbabwe",
]

ANALYSIS_PHASES = [
    "EXTRACTING EXIF METADATA...",
    "FORENSIC VISION SCAN...",
    "IDENTIFYING OSINT INDICATORS...",
    "DECODING LICENSE PLATE FORMATS...",
    "ANALYZING LANGUAGE & SIGNAGE...",
    "ESTIMATING SUN / SHADOW ANGLES...",
    "CROSS-REFERENCING GEO DATABASE...",
    "TRIANGULATING COORDINATES...",
    "COMPUTING CONFIDENCE MATRIX...",
    "FINALIZING HYPOTHESIS...",
]


# ═════════════════════════════════════════════════════════════════
#  TILE ENGINE  — fetches OpenStreetMap / satellite tiles
# ═════════════════════════════════════════════════════════════════
TILE_PX = 256

# Public tile servers (no key required for OSM; Google satellite is public)
TILE_SOURCES = {
    "ROAD":      "https://tile.openstreetmap.org/{z}/{x}/{y}.png",
    "SATELLITE": "https://mt.google.com/vt/lyrs=s&x={x}&y={y}&z={z}",
    "HYBRID":    "https://mt.google.com/vt/lyrs=y&x={x}&y={y}&z={z}",
    "TERRAIN":   "https://tile.opentopomap.org/{z}/{x}/{y}.png",
}

_tile_cache: dict = {}          # (x,y,z,src) → PIL.Image
_tile_lock  = threading.Lock()


def _fallback_tile() -> "Image.Image":
    img = Image.new("RGB", (TILE_PX, TILE_PX), (8, 14, 28))
    d = ImageDraw.Draw(img)
    for i in range(0, TILE_PX, 32):
        d.line([(i, 0), (i, TILE_PX)], fill=(20, 36, 58))
        d.line([(0, i), (TILE_PX, i)], fill=(20, 36, 58))
    return img


def _darken_road(img: "Image.Image") -> "Image.Image":
    """Apply dark-mode tint so OSM tiles match our theme."""
    img = ImageEnhance.Brightness(img).enhance(0.42)
    img = ImageEnhance.Color(img).enhance(0.55)
    r, g, b = img.split()
    r = r.point(lambda v: int(v * 0.68))
    g = g.point(lambda v: int(v * 0.80))
    b = b.point(lambda v: min(255, int(v * 1.30 + 20)))
    return Image.merge("RGB", (r, g, b))


def fetch_tile(x: int, y: int, z: int, source: str,
               done_cb, root: "tk.Tk"):
    """Async tile fetch. Calls done_cb(x,y,z,img) on the main thread."""
    key = (x, y, z, source)
    with _tile_lock:
        if key in _tile_cache:
            img = _tile_cache[key]
            root.after(0, lambda: done_cb(x, y, z, img))
            return

    def _fetch():
        url = TILE_SOURCES.get(source, TILE_SOURCES["ROAD"])
        url = url.replace("{x}", str(x)).replace("{y}", str(y)).replace("{z}", str(z))
        try:
            req = urllib.request.Request(
                url, headers={"User-Agent": "SightPointAI/1.0 OSINT-tool"})
            with urllib.request.urlopen(req, timeout=8) as resp:
                data = resp.read()
            img = Image.open(io.BytesIO(data)).convert("RGB")
            if source in ("ROAD", "TERRAIN"):
                img = _darken_road(img)
        except Exception:
            img = _fallback_tile()

        with _tile_lock:
            # Limit cache size
            if len(_tile_cache) > 600:
                for old in list(_tile_cache.keys())[:200]:
                    del _tile_cache[old]
            _tile_cache[key] = img

        root.after(0, lambda: done_cb(x, y, z, img))

    threading.Thread(target=_fetch, daemon=True).start()


# ═════════════════════════════════════════════════════════════════
#  TILE MATH  — lat/lng ↔ pixel/tile conversions
# ═════════════════════════════════════════════════════════════════
def ll_to_px(lat: float, lng: float, zoom: int):
    """Lat/lng → global pixel (x, y)."""
    n  = 2 ** zoom
    px = (lng + 180.0) / 360.0 * n * TILE_PX
    lr = math.radians(lat)
    py = (1.0 - math.log(math.tan(lr) + 1.0 / math.cos(lr)) / math.pi) \
         / 2.0 * n * TILE_PX
    return px, py


def px_to_ll(px: float, py: float, zoom: int):
    """Global pixel (x, y) → lat/lng."""
    n   = 2 ** zoom
    lng = px / (n * TILE_PX) * 360.0 - 180.0
    lat = math.degrees(
        math.atan(math.sinh(math.pi * (1.0 - 2.0 * py / (n * TILE_PX)))))
    return lat, lng


def haversine_km(la1, lo1, la2, lo2) -> float:
    R = 6371.0
    dla = math.radians(la2 - la1)
    dlo = math.radians(lo2 - lo1)
    a   = (math.sin(dla / 2) ** 2
           + math.cos(math.radians(la1)) * math.cos(math.radians(la2))
           * math.sin(dlo / 2) ** 2)
    return R * 2 * math.asin(math.sqrt(a))


# ═════════════════════════════════════════════════════════════════
#  EMBEDDED MAP WIDGET
# ═════════════════════════════════════════════════════════════════
class MapWidget(tk.Frame):
    """
    Interactive slippy map rendered entirely inside tkinter using PIL tiles.
    Features: pan · zoom · pin · heatmap overlay · ruler · layer toggle
    """
    ZOOM_MIN = 2
    ZOOM_MAX = 18

    def __init__(self, parent, root_ref: "tk.Tk", log_fn=None, **kw):
        kw.setdefault("bg", BG_DARK)
        super().__init__(parent, **kw)
        self._root   = root_ref
        self._log    = log_fn or (lambda m, l="SYS": None)

        # Map state
        self._zoom    = 3
        self._clat    = 20.0       # centre lat
        self._clng    = 0.0        # centre lng
        self._source  = "ROAD"

        # Overlays
        self._pin          = None        # (lat, lng)
        self._pin_label    = ""
        self._heatmap_pts  = []          # [(lat, lng, weight), ...]
        self._ruler_on     = False
        self._ruler_pts    = []          # [(lat, lng), ...]

        # Interaction
        self._drag_anchor  = None        # canvas xy at drag start
        self._drag_cpx     = None        # centre px at drag start
        self._drag_cpy     = None

        # Rendering
        self._photo_refs   = []          # keep PhotoImage alive
        self._tile_photos  = {}          # (x,y,z) → PhotoImage

        self._build()

    # ── Build ──────────────────────────────────────────────────
    def _build(self):
        # Toolbar
        tb = tk.Frame(self, bg=BG_PANEL)
        tb.pack(fill="x")
        tk.Frame(tb, bg=BORDER_LIT, height=1).place(relx=0, rely=1,
                                                     relwidth=1, anchor="sw")

        def tbtn(text, cmd, w=None):
            kw = dict(text=text, command=cmd, bg=BG_PANEL, fg=CYAN,
                      font=FONT_MONO_XS, relief="flat", cursor="hand2",
                      padx=9, pady=5,
                      activebackground=BORDER_LIT,
                      activeforeground=CYAN_BRIGHT)
            if w:
                kw["width"] = w
            b = tk.Button(tb, **kw)
            b.pack(side="left")
            return b

        # Layer buttons
        self._lbtn = {}
        for src in ("ROAD", "SATELLITE", "HYBRID", "TERRAIN"):
            icons = {"ROAD": "◈", "SATELLITE": "⬡",
                     "HYBRID": "⬢", "TERRAIN": "◆"}
            b = tbtn("{} {}".format(icons[src], src),
                     lambda s=src: self._set_source(s))
            self._lbtn[src] = b

        tk.Frame(tb, bg=BORDER, width=1).pack(
            side="left", fill="y", padx=5, pady=4)

        self._ruler_btn = tbtn("⬟ RULER",   self._toggle_ruler)
        tbtn("✕ RULER",  self._clear_ruler)
        tbtn("⊕ +",      lambda: self._zoom_delta(1))
        tbtn("⊖ −",      lambda: self._zoom_delta(-1))

        self._ruler_lbl = tk.Label(
            tb, text="", bg=BG_PANEL, fg=GREEN, font=FONT_MONO_XS)
        self._ruler_lbl.pack(side="right", padx=6)

        self._coord_lbl = tk.Label(
            tb, text="", bg=BG_PANEL, fg=TEXT_DIM, font=FONT_MONO_XS)
        self._coord_lbl.pack(side="right", padx=4)

        # Canvas
        self._cv = tk.Canvas(self, bg=BG_DARK,
                              highlightthickness=0, cursor="crosshair")
        self._cv.pack(fill="both", expand=True)

        self._cv.bind("<Configure>",        self._on_resize)
        self._cv.bind("<ButtonPress-1>",    self._on_press)
        self._cv.bind("<B1-Motion>",        self._on_drag)
        self._cv.bind("<ButtonRelease-1>",  self._on_release)
        self._cv.bind("<MouseWheel>",       self._on_scroll)
        self._cv.bind("<Button-4>",         self._on_scroll)
        self._cv.bind("<Button-5>",         self._on_scroll)
        self._cv.bind("<Motion>",           self._on_motion)

        self._refresh_layer_btns()

    # ── Public API ─────────────────────────────────────────────
    def go_to(self, lat: float, lng: float, zoom: int = 12):
        self._clat  = lat
        self._clng  = lng
        self._zoom  = max(self.ZOOM_MIN, min(self.ZOOM_MAX, zoom))
        self._flush_tiles()
        self._redraw()
        self._log("Map → {:.4f}, {:.4f}  z{}".format(lat, lng, zoom))

    def drop_pin(self, lat: float, lng: float, label: str = ""):
        self._pin       = (lat, lng)
        self._pin_label = label[:40]
        self._redraw()

    def clear_pin(self):
        self._pin = None
        self._redraw()

    def set_heatmap(self, pts: list):
        """pts = [(lat, lng, weight 0‒1), ...]"""
        self._heatmap_pts = pts
        self._redraw()

    def clear_heatmap(self):
        self._heatmap_pts.clear()
        self._redraw()

    # ── Internal helpers ───────────────────────────────────────
    def _flush_tiles(self):
        self._tile_photos.clear()
        # Don't clear _photo_refs entirely — GC safety;
        # trim to last 100 instead
        self._photo_refs = self._photo_refs[-100:]

    def _cv_size(self):
        self._cv.update_idletasks()
        w = self._cv.winfo_width()  or 600
        h = self._cv.winfo_height() or 400
        return w, h

    def _centre_px(self):
        return ll_to_px(self._clat, self._clng, self._zoom)

    def _cv_to_ll(self, cx: float, cy: float):
        cw, ch = self._cv_size()
        cpx, cpy = self._centre_px()
        return px_to_ll(cpx + cx - cw / 2,
                        cpy + cy - ch / 2, self._zoom)

    def _ll_to_cv(self, lat: float, lng: float):
        cw, ch   = self._cv_size()
        cpx, cpy = self._centre_px()
        px, py   = ll_to_px(lat, lng, self._zoom)
        return cw / 2 + px - cpx, ch / 2 + py - cpy

    # ── Redraw ─────────────────────────────────────────────────
    def _redraw(self):
        self._cv.delete("all")
        self._draw_tiles()
        if self._heatmap_pts:
            self._draw_heatmap()
        self._draw_ruler()
        if self._pin:
            self._draw_pin()
        self._draw_crosshair()
        self._update_coord_lbl()

    def _draw_tiles(self):
        cw, ch = self._cv_size()
        if cw < 2 or ch < 2:
            return
        cpx, cpy = self._centre_px()
        n  = 2 ** self._zoom
        x0 = cpx - cw / 2
        y0 = cpy - ch / 2
        tx0 = int(x0 / TILE_PX)
        ty0 = int(y0 / TILE_PX)
        tx1 = int((x0 + cw) / TILE_PX) + 1
        ty1 = int((y0 + ch) / TILE_PX) + 1

        for ty in range(ty0, ty1 + 1):
            for tx in range(tx0, tx1 + 1):
                # Clamp y, wrap x
                if ty < 0 or ty >= n:
                    continue
                wtx = tx % n
                if wtx < 0:
                    wtx += n

                # Canvas position of tile top-left
                cvx = int(tx * TILE_PX - x0)
                cvy = int(ty * TILE_PX - y0)

                key = (wtx, ty, self._zoom)
                if key in self._tile_photos:
                    self._cv.create_image(cvx, cvy, anchor="nw",
                                          image=self._tile_photos[key])
                else:
                    # Placeholder grid square
                    self._cv.create_rectangle(
                        cvx, cvy, cvx + TILE_PX, cvy + TILE_PX,
                        fill=BG_DARK, outline=BORDER)
                    fetch_tile(wtx, ty, self._zoom, self._source,
                               done_cb=self._tile_arrived, root=self._root)

    def _tile_arrived(self, x: int, y: int, z: int, img: "Image.Image"):
        if z != self._zoom:
            return   # stale — zoom changed while fetching
        tk_img = ImageTk.PhotoImage(img)
        self._tile_photos[(x, y, z)] = tk_img
        self._photo_refs.append(tk_img)
        if len(self._photo_refs) > 400:
            self._photo_refs = self._photo_refs[-300:]
        # Place tile directly on canvas without a full redraw — prevents flashing
        cw, ch = self._cv_size()
        cpx, cpy = self._centre_px()
        x0 = cpx - cw / 2
        y0 = cpy - ch / 2
        n  = 2 ** self._zoom
        # Check all wrapped positions this tile could appear at on screen
        for tx in range(x - n, x + 2 * n, n):
            cvx = int(tx * TILE_PX - x0)
            cvy = int(y  * TILE_PX - y0)
            if -TILE_PX < cvx < cw + TILE_PX and -TILE_PX < cvy < ch + TILE_PX:
                self._cv.create_image(cvx, cvy, anchor="nw",
                                      image=tk_img, tags="tile")
        # Bring overlays to front after placing tile
        for tag in ("heatmap", "ruler", "pin", "crosshair"):
            self._cv.tag_raise(tag)

    def _draw_heatmap(self):
        cw, ch = self._cv_size()
        if not PIL_AVAILABLE or cw < 2 or ch < 2:
            return
        heat = Image.new("RGBA", (cw, ch), (0, 0, 0, 0))
        d    = ImageDraw.Draw(heat)
        for lat, lng, w in self._heatmap_pts:
            cx, cy = self._ll_to_cv(lat, lng)
            r   = max(4, int(80 * w))
            alp = int(200 * w)
            for ring in range(r, 0, -3):
                a = int(alp * (ring / r) ** 1.6)
                d.ellipse([cx - ring, cy - ring, cx + ring, cy + ring],
                          fill=(0, 200, 255, a))
        heat = heat.filter(ImageFilter.GaussianBlur(radius=16))
        ref  = ImageTk.PhotoImage(heat)
        self._photo_refs.append(ref)
        self._cv.create_image(0, 0, anchor="nw", image=ref, tags="heatmap")

    def _draw_ruler(self):
        if not self._ruler_pts:
            return
        pts = [self._ll_to_cv(la, lo) for la, lo in self._ruler_pts]
        for i, (cx, cy) in enumerate(pts):
            if i > 0:
                px, py = pts[i - 1]
                self._cv.create_line(px, py, cx, cy,
                                     fill=GREEN, width=2, dash=(8, 4),
                                     tags="ruler")
            self._cv.create_oval(cx - 5, cy - 5, cx + 5, cy + 5,
                                  fill=GREEN, outline=WHITE, width=1,
                                  tags="ruler")
        if len(self._ruler_pts) >= 2:
            km = sum(
                haversine_km(self._ruler_pts[i-1][0], self._ruler_pts[i-1][1],
                             self._ruler_pts[i][0],   self._ruler_pts[i][1])
                for i in range(1, len(self._ruler_pts)))
            self._ruler_lbl.configure(
                text="  {:.2f} km  /  {:.2f} mi  ".format(km, km * 0.621371))

    def _draw_pin(self):
        lat, lng = self._pin
        cx, cy   = self._ll_to_cv(lat, lng)
        # Glow rings
        for r, col, w in [(24, CYAN_DIM, 1), (16, CYAN, 1), (10, CYAN, 2)]:
            self._cv.create_oval(cx-r, cy-r, cx+r, cy+r,
                                  outline=col, width=w, fill="", tags="pin")
        # Filled circle
        self._cv.create_oval(cx-8, cy-8, cx+8, cy+8,
                              fill=CYAN, outline=WHITE, width=2, tags="pin")
        self._cv.create_oval(cx-3, cy-3, cx+3, cy+3,
                              fill=BG_DARK, outline="", tags="pin")
        # Label bubble
        if self._pin_label:
            txt = self._pin_label
            tw  = len(txt) * 5 + 14
            bx1, by1 = int(cx) - 6, int(cy) - 38
            bx2, by2 = bx1 + tw,    by1 + 18
            self._cv.create_rectangle(bx1, by1, bx2, by2,
                                       fill=BG_CARD, outline=CYAN, width=1,
                                       tags="pin")
            self._cv.create_text(bx1 + 7, by1 + 3, anchor="nw",
                                  text=txt, fill=CYAN_BRIGHT,
                                  font=FONT_MONO_XS, tags="pin")

    def _draw_crosshair(self):
        cw, ch = self._cv_size()
        cx, cy = cw // 2, ch // 2
        self._cv.create_line(cx-12, cy, cx+12, cy,
                              fill=TEXT_FAINT, tags="crosshair")
        self._cv.create_line(cx, cy-12, cx, cy+12,
                              fill=TEXT_FAINT, tags="crosshair")
        self._cv.create_oval(cx-3, cy-3, cx+3, cy+3,
                              outline=TEXT_FAINT, fill="", tags="crosshair")

    def _update_coord_lbl(self):
        self._coord_lbl.configure(
            text="  {:.4f}°  {:.4f}°  z{}  ".format(
                self._clat, self._clng, self._zoom))

    # ── Source / ruler ─────────────────────────────────────────
    def _set_source(self, src: str):
        self._source = src
        self._flush_tiles()
        self._refresh_layer_btns()
        self._redraw()
        self._log("Layer → {}".format(src))

    def _refresh_layer_btns(self):
        for src, btn in self._lbtn.items():
            if src == self._source:
                btn.configure(bg=CYAN, fg=BG_DARK)
            else:
                btn.configure(bg=BG_PANEL, fg=CYAN)

    def _toggle_ruler(self):
        self._ruler_on = not self._ruler_on
        self._ruler_btn.configure(
            bg=CYAN if self._ruler_on else BG_PANEL,
            fg=BG_DARK if self._ruler_on else CYAN)

    def _clear_ruler(self):
        self._ruler_on  = False
        self._ruler_pts = []
        self._ruler_btn.configure(bg=BG_PANEL, fg=CYAN)
        self._ruler_lbl.configure(text="")
        self._redraw()

    # ── Events ─────────────────────────────────────────────────
    def _on_resize(self, _e):
        # Debounce resize redraws — only redraw 150ms after last resize event
        if hasattr(self, "_resize_after") and self._resize_after:
            self._root.after_cancel(self._resize_after)
        self._resize_after = self._root.after(150, self._do_resize)

    def _do_resize(self):
        self._resize_after = None
        # The canvas may have been destroyed in the meantime (e.g. a
        # live theme reload rebuilt the whole UI while this debounced
        # callback was still pending) — no-op instead of crashing.
        if not self._cv.winfo_exists():
            return
        self._flush_tiles()
        self._redraw()

    def _on_press(self, e):
        if self._ruler_on:
            lat, lng = self._cv_to_ll(e.x, e.y)
            self._ruler_pts.append((lat, lng))
            self._redraw()
        else:
            self._drag_anchor = (e.x, e.y)
            self._drag_cpx, self._drag_cpy = self._centre_px()

    def _on_drag(self, e):
        if self._drag_anchor and not self._ruler_on:
            dx = e.x - self._drag_anchor[0]
            dy = e.y - self._drag_anchor[1]
            new_lat, new_lng = px_to_ll(
                self._drag_cpx - dx,
                self._drag_cpy - dy, self._zoom)
            # Clamp to valid lat/lng to prevent crashes
            new_lat = max(-85.0, min(85.0, new_lat))
            new_lng = max(-180.0, min(180.0, new_lng))
            self._clat = new_lat
            self._clng = new_lng
            # Move all canvas items instead of full redraw — smooth, no flash
            move_dx = dx - getattr(self, "_last_drag_dx", 0)
            move_dy = dy - getattr(self, "_last_drag_dy", 0)
            self._cv.move("all", move_dx, move_dy)
            self._last_drag_dx = dx
            self._last_drag_dy = dy

    def _on_release(self, _e):
        if self._drag_anchor and not self._ruler_on:
            # Full redraw on release to fetch any newly visible tiles
            self._last_drag_dx = 0
            self._last_drag_dy = 0
            self._redraw()
        self._drag_anchor = None
        self._drag_cpx    = None
        self._drag_cpy    = None

    def _on_scroll(self, e):
        delta = getattr(e, "delta", 0)
        if e.num == 4:   delta =  120
        elif e.num == 5: delta = -120
        self._zoom_delta(1 if delta > 0 else -1)

    def _zoom_delta(self, d: int):
        nz = max(self.ZOOM_MIN, min(self.ZOOM_MAX, self._zoom + d))
        if nz == self._zoom:
            return
        self._zoom = nz
        self._flush_tiles()
        self._redraw()

    def _on_motion(self, e):
        lat, lng = self._cv_to_ll(e.x, e.y)
        self._coord_lbl.configure(
            text="  {:.4f}°  {:.4f}°  z{}  ".format(
                lat, lng, self._zoom))


# ═════════════════════════════════════════════════════════════════
#  EXIF EXTRACTION
# ═════════════════════════════════════════════════════════════════
def extract_exif(path: str) -> dict:
    out = {"has_exif": False, "gps": None, "camera": {}, "raw": {}}
    if not PIL_AVAILABLE:
        return out
    try:
        img  = Image.open(path)
        raw  = img._getexif() if hasattr(img, "_getexif") else None
        if not raw:
            return out
        out["has_exif"] = True
        named = {ExifTags.TAGS.get(k, str(k)): v for k, v in raw.items()}
        keep  = ("Make","Model","DateTime","Software","Orientation",
                 "Flash","FocalLength","ExposureTime","FNumber","ISOSpeedRatings")
        out["raw"] = {k: str(v)[:100] for k, v in named.items() if k in keep}
        for f in ("Make","Model","DateTime"):
            if f in named:
                out["camera"][f.lower()] = str(named[f])
        gps = named.get("GPSInfo")
        if gps and isinstance(gps, dict):
            gt = {ExifTags.GPSTAGS.get(k, k): v for k, v in gps.items()}
            def deg(vals):
                return float(vals[0]) + float(vals[1])/60 + float(vals[2])/3600
            lv = gt.get("GPSLatitude"); lr = gt.get("GPSLatitudeRef","N")
            ov = gt.get("GPSLongitude"); or_ = gt.get("GPSLongitudeRef","E")
            if lv and ov:
                out["gps"] = {
                    "latitude":  round(deg(lv) * (-1 if lr == "S" else 1), 6),
                    "longitude": round(deg(ov) * (-1 if or_ == "W" else 1), 6),
                }
    except Exception as exc:
        out["error"] = str(exc)
    return out


# ═════════════════════════════════════════════════════════════════
#  GEMINI ANALYSIS
# ═════════════════════════════════════════════════════════════════
def gemini_geolocate(image_path: str, country: str,
                     exif_data: dict = None, log_cb=None) -> dict:
    def _log(msg, lvl="INFO"):
        if log_cb:
            try: log_cb(msg, lvl)
            except Exception: pass

    _log("Reading image…")
    with open(image_path, "rb") as f:
        raw = f.read()
    b64  = base64.b64encode(raw).decode()
    ext  = Path(image_path).suffix.lower()
    mime = {".jpg":"image/jpeg",".jpeg":"image/jpeg",".png":"image/png",
            ".gif":"image/gif",".webp":"image/webp"}.get(ext,"image/jpeg")

    scope = (
        "CRITICAL: restrict ALL hypotheses to inside {} ONLY.".format(country)
        if country != "Global" else "Scope: worldwide."
    )
    exif_hint = ""
    if exif_data:
        if exif_data.get("gps"):
            g = exif_data["gps"]
            exif_hint = "\nEXIF GPS embedded: lat={}, lng={}. Treat as strong evidence.".format(
                g["latitude"], g["longitude"])
        elif exif_data.get("camera"):
            exif_hint = "\nEXIF camera: {}.".format(exif_data["camera"])

    prompt = (
        "You are a world-class OSINT geolocation analyst.\n\n"
        "{scope}{exif_hint}\n\n"
        "PHASE 1 — FORENSIC VISION\n"
        "Examine every visual element:\n"
        "• Architecture: style, era, materials, window/door/roof shapes\n"
        "• Infrastructure: road surface, guardrails, utility poles, lane markings\n"
        "• Natural: vegetation species, terrain, soil colour, water, sky/clouds\n"
        "• Cultural: flags, shop fronts, clothing styles, vehicle makes/models\n\n"
        "PHASE 2 — TARGETED OSINT INDICATORS\n"
        "• LICENSE PLATES [68]: Format, colour, country prefix/suffix, region codes.\n"
        "• RAILWAY GAUGES [70]: Gauge from sleeper spacing. Standard=1435mm, narrow=1000mm.\n"
        "• AVIATION TAIL NUMBERS [69]: Reg prefix (G-=UK, N=USA, F-=France, D-=Germany).\n"
        "• LANGUAGE/DIALECT [63]: All text, translate it, identify script, dialect markers.\n"
        "• DRIVING SIDE [61]: LHT or RHT from lane markings, vehicle positions.\n\n"
        "PHASE 3 — FORENSIC ESTIMATION\n"
        "• OCR: Transcribe every visible word/number/partial text.\n"
        "• SUN/SHADOW: Estimate azimuth, hemisphere, time of day, season.\n\n"
        "PHASE 4 — TRIANGULATION\n"
        "Synthesise all evidence. Provide 3 weighted candidate locations for heatmap.\n\n"
        "Return ONLY a raw JSON object — no markdown, no fences, no text outside JSON:\n"
        '{{\n'
        '  "latitude": <float>,\n'
        '  "longitude": <float>,\n'
        '  "location_name": "<City, Country>",\n'
        '  "confidence": <0-100>,\n'
        '  "clues": ["<clue1>","<clue2>","<clue3>","<clue4>","<clue5>"],\n'
        '  "reasoning": "<3-4 sentence chain-of-evidence>",\n'
        '  "country": "<country>",\n'
        '  "city": "<city or region>",\n'
        '  "osint": {{\n'
        '    "license_plate": "<format & country or not visible>",\n'
        '    "railway_gauge": "<gauge estimate or not visible>",\n'
        '    "aviation": "<tail prefix/livery or not visible>",\n'
        '    "language": "<language(s) and script type>",\n'
        '    "driving_side": "<left or right or indeterminate>",\n'
        '    "ocr_text": "<all visible text>",\n'
        '    "sun_azimuth": "<direction or indeterminate>",\n'
        '    "hemisphere": "<north or south or indeterminate>"\n'
        '  }},\n'
        '  "heatmap_candidates": [\n'
        '    {{"lat":<float>,"lng":<float>,"weight":<0.3-1.0>}},\n'
        '    {{"lat":<float>,"lng":<float>,"weight":<0.1-0.5>}},\n'
        '    {{"lat":<float>,"lng":<float>,"weight":<0.05-0.3>}}\n'
        '  ]\n'
        '}}'
    ).format(scope=scope, exif_hint=exif_hint)

    _log("Sending to Gemini 2.0 Flash…")
    url = ("https://generativelanguage.googleapis.com/v1beta/"
           "models/gemini-2.5-flash-lite:generateContent?key={}").format(GEMINI_API_KEY)
    payload = {
        "contents": [{"parts": [
            {"inline_data": {"mime_type": mime, "data": b64}},
            {"text": prompt}
        ]}],
        "generationConfig": {"temperature": 0.05, "maxOutputTokens": 2048}
    }

    try:
        resp = requests.post(url, json=payload, timeout=120)
        resp.raise_for_status()
    except requests.exceptions.Timeout:
        raise RuntimeError("Timed out (120 s). Try a smaller image.")
    except requests.exceptions.HTTPError as exc:
        code = (exc.response.status_code if exc.response else "?")
        msg  = {400: "Bad request / unsupported format.",
                403: "Invalid API key or quota exceeded."}.get(code, str(exc))
        raise RuntimeError("HTTP {}: {}".format(code, msg))
    except requests.exceptions.RequestException as exc:
        raise RuntimeError("Network error: {}".format(exc))

    data = resp.json()
    _log("Parsing response…")
    try:
        text = data["candidates"][0]["content"]["parts"][0]["text"]
    except (KeyError, IndexError, TypeError):
        blocked = data.get("promptFeedback", {}).get("blockReason", "")
        if blocked:
            raise RuntimeError("Blocked by safety filter: {}".format(blocked))
        raise RuntimeError("Unexpected response: {}".format(str(data)[:200]))

    # Robust JSON extraction
    text = re.sub(r"```[a-zA-Z]*\s*", "", text)
    text = re.sub(r"```", "", text).strip().strip("`").strip()
    m = re.search(r"\{[\s\S]*\}", text)
    if not m:
        raise RuntimeError("No JSON object in response:\n{}".format(text[:400]))
    js = m.group()
    try:
        result = json.loads(js)
    except json.JSONDecodeError:
        js2 = re.sub(r",\s*([}\]])", r"\1", js)
        try:
            result = json.loads(js2)
        except json.JSONDecodeError as e:
            raise RuntimeError("JSON parse failed: {}\n{}".format(e, js[:300]))

    _log("{} — {}% confidence".format(
        result.get("location_name", "?"), result.get("confidence", "?")), "OK")
    return result


# ═════════════════════════════════════════════════════════════════
#  REUSABLE WIDGETS
# ═════════════════════════════════════════════════════════════════
class ProgressBar(tk.Frame):
    """Frame-based bar — no Canvas kwarg conflicts on Python 3.14."""
    def __init__(self, parent, bar_height=4, **kw):
        kw.setdefault("bg", BG_DARK)
        kw["height"] = bar_height
        super().__init__(parent, **kw)
        self._track = tk.Frame(self, bg=TEXT_FAINT)
        self._track.place(relx=0, rely=0, relwidth=1, relheight=1)
        self._fill  = tk.Frame(self, bg=CYAN)
        self._fill.place(relx=0, rely=0, relwidth=0, relheight=1)
        self.configure(height=bar_height)

    def set_value(self, v, color=None):
        v = max(0.0, min(100.0, float(v)))
        if color:
            self._fill.configure(bg=color)
        self._fill.place(relx=0, rely=0, relwidth=v / 100.0, relheight=1)


class TerminalConsole(tk.Frame):
    COLORS = {"INFO": CYAN, "OK": GREEN, "WARN": YELLOW,
              "ERROR": RED_COL, "DATA": PURPLE, "SYS": TEXT_DIM}

    def __init__(self, parent, **kw):
        kw.setdefault("bg", BG_TERM)
        super().__init__(parent, **kw)
        self._t = tk.Text(
            self, bg=BG_TERM, fg=CYAN, font=FONT_MONO_SM,
            relief="flat", state="disabled", wrap="word",
            selectbackground=CYAN_DIM, padx=8, pady=5)
        sb = ttk.Scrollbar(self, orient="vertical", command=self._t.yview)
        self._t.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        self._t.pack(side="left", fill="both", expand=True)
        for tag, col in self.COLORS.items():
            self._t.tag_configure(tag, foreground=col)
        self._t.tag_configure("TS",  foreground=TEXT_FAINT)
        self._t.tag_configure("MSG", foreground=TEXT_MID)

    def log(self, msg: str, level: str = "INFO"):
        ts = datetime.datetime.now().strftime("%H:%M:%S")
        self._t.configure(state="normal")
        self._t.insert("end", "[{}] ".format(ts), "TS")
        lvl = level if level in self.COLORS else "INFO"
        self._t.insert("end", "[{:5s}] ".format(level), lvl)
        self._t.insert("end", msg + "\n", "MSG")
        self._t.see("end")
        self._t.configure(state="disabled")

    def clear(self):
        self._t.configure(state="normal")
        self._t.delete("1.0", "end")
        self._t.configure(state="disabled")


class HUD(tk.Frame):
    def __init__(self, parent, **kw):
        kw.setdefault("bg", BG_CARD)
        super().__init__(parent, **kw)
        self._start = time.time()
        self._count = 0
        self._lbl   = {}
        inner = tk.Frame(self, bg=BG_CARD)
        inner.pack(fill="x", padx=6, pady=4)
        for i, (k, v) in enumerate([("UPTIME","00:00:00"),
                                     ("ANALYSES","0"),
                                     ("STATUS","IDLE")]):
            col = tk.Frame(inner, bg=BG_CARD)
            col.pack(side="left", fill="x", expand=True)
            tk.Label(col, text=k, bg=BG_CARD, fg=TEXT_FAINT,
                     font=FONT_MONO_XS).pack()
            lbl = tk.Label(col, text=v, bg=BG_CARD,
                            fg=CYAN, font=FONT_MONO_SM)
            lbl.pack()
            self._lbl[k] = lbl
            if i < 2:
                tk.Frame(inner, bg=BORDER, width=1).pack(
                    side="left", fill="y", padx=3)
        self._tick()

    def set_status(self, s: str, c: str = CYAN):
        self._lbl["STATUS"].configure(text=s, fg=c)

    def increment(self):
        self._count += 1
        self._lbl["ANALYSES"].configure(text=str(self._count))

    def _tick(self):
        # This recurs forever every second — guard against firing
        # after a live theme reload has destroyed this HUD instance.
        if not self.winfo_exists():
            return
        e    = int(time.time() - self._start)
        h, r = divmod(e, 3600)
        m, s = divmod(r, 60)
        self._lbl["UPTIME"].configure(
            text="{:02d}:{:02d}:{:02d}".format(h, m, s))
        self.after(1000, self._tick)


class HistorySidebar(tk.Frame):
    def __init__(self, parent, on_select=None, **kw):
        kw.setdefault("bg", BG_PANEL)
        kw["width"] = 152
        super().__init__(parent, **kw)
        self.pack_propagate(False)
        self._on_select = on_select
        self._sessions  = []
        hdr = tk.Frame(self, bg=BG_PANEL)
        hdr.pack(fill="x", padx=5, pady=(6,3))
        tk.Label(hdr, text="HISTORY", bg=BG_PANEL,
                 fg=TEXT_DIM, font=FONT_MONO_XS).pack(side="left")
        tk.Button(hdr, text="✕", bg=BG_PANEL, fg=TEXT_FAINT,
                  font=FONT_MONO_XS, relief="flat", cursor="hand2",
                  command=self._clear).pack(side="right")
        self._lb = tk.Listbox(
            self, bg=BG_INPUT, fg=TEXT_MID, font=FONT_MONO_XS,
            relief="flat", selectbackground=CYAN_DIM,
            selectforeground=CYAN_BRIGHT,
            activestyle="none", highlightthickness=0)
        sb = ttk.Scrollbar(self, orient="vertical", command=self._lb.yview)
        self._lb.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        self._lb.pack(fill="both", expand=True, padx=3, pady=(0,5))
        self._lb.bind("<<ListboxSelect>>", self._click)

    def add(self, result: dict, image_path: str):
        ts   = datetime.datetime.now().strftime("%H:%M")
        city = (result.get("city") or
                result.get("location_name","?"))[:14]
        conf = result.get("confidence", 0)
        self._sessions.append({"result": result, "image_path": image_path})
        self._lb.insert(0, " {} {}\n {}%".format(ts, city, conf))
        c = GREEN if conf >= 70 else YELLOW if conf >= 40 else RED_COL
        self._lb.itemconfig(0, fg=c)

    def _click(self, _e):
        sel = self._lb.curselection()
        if sel and self._on_select:
            self._on_select(self._sessions[-(sel[0]+1)])

    def _clear(self):
        self._lb.delete(0, "end")
        self._sessions.clear()


class ZoomCanvas(tk.Frame):
    """Pan/zoom viewer for the uploaded target image."""
    def __init__(self, parent, **kw):
        kw.setdefault("bg", BG_CARD)
        super().__init__(parent, **kw)
        self._c   = tk.Canvas(self, bg=BG_CARD,
                               highlightthickness=0, cursor="fleur")
        self._c.pack(fill="both", expand=True)
        self._pil = None
        self._ref = None
        self._scale = 1.0
        self._ox = 0.0
        self._oy = 0.0
        self._drag = None
        self._cid  = None
        self._c.bind("<MouseWheel>",    self._scroll)
        self._c.bind("<Button-4>",      self._scroll)
        self._c.bind("<Button-5>",      self._scroll)
        self._c.bind("<ButtonPress-1>", self._drag_start)
        self._c.bind("<B1-Motion>",     self._drag_move)
        self._c.bind("<Configure>",     self._on_resize)

    def load(self, path: str):
        if not PIL_AVAILABLE:
            return
        try:
            img = Image.open(path)
            img.thumbnail((1600, 1600), Image.LANCZOS)
            self._pil   = img
            self._scale = 1.0
            self._fit()
        except Exception:
            pass

    def placeholder(self):
        self._c.delete("all")
        self._c.update_idletasks()
        w  = self._c.winfo_width()  or 380
        h  = self._c.winfo_height() or 220
        cx, cy = w//2, h//2
        for r, col in [(48,BORDER_LIT),(32,BORDER),(16,TEXT_FAINT)]:
            self._c.create_oval(cx-r, cy-r, cx+r, cy+r, outline=col)
        self._c.create_line(cx-62, cy, cx+62, cy, fill=BORDER)
        self._c.create_line(cx, cy-62, cx, cy+62, fill=BORDER)
        self._c.create_oval(cx-4, cy-4, cx+4, cy+4, fill=CYAN, outline="")
        self._c.create_text(cx, cy+66,
                             text="CLICK TO BROWSE  ·  DRAG & DROP",
                             fill=TEXT_DIM, font=FONT_MONO_XS)
        self._c.create_text(cx, cy+80,
                             text="SCROLL = ZOOM  ·  DRAG = PAN",
                             fill=TEXT_FAINT, font=FONT_MONO_XS)

    def _fit(self):
        if not self._pil:
            return
        self._c.update_idletasks()
        cw = self._c.winfo_width()  or 380
        ch = self._c.winfo_height() or 220
        iw, ih = self._pil.size
        s = min(cw/iw, ch/ih, 1.0)
        self._scale = s
        self._ox    = (cw - iw*s)/2
        self._oy    = (ch - ih*s)/2
        self._render()

    def _render(self):
        if not self._pil:
            return
        iw, ih = self._pil.size
        nw = max(1, int(iw * self._scale))
        nh = max(1, int(ih * self._scale))
        resized   = self._pil.resize((nw, nh), Image.LANCZOS)
        self._ref = ImageTk.PhotoImage(resized)
        self._c.delete("all")
        self._cid = self._c.create_image(
            int(self._ox), int(self._oy), anchor="nw", image=self._ref)
        self._c.create_text(6, 6, anchor="nw",
                             text=" {}% ".format(int(self._scale*100)),
                             fill=CYAN, font=FONT_MONO_XS)

    def _scroll(self, e):
        if not self._pil:
            return
        d = getattr(e, "delta", 0)
        if e.num == 4: d = 120
        elif e.num == 5: d = -120
        f  = 1.15 if d > 0 else 0.87
        ns = max(0.05, min(10.0, self._scale * f))
        self._ox = e.x - (e.x - self._ox) * (ns / self._scale)
        self._oy = e.y - (e.y - self._oy) * (ns / self._scale)
        self._scale = ns
        self._render()

    def _drag_start(self, e):
        self._drag = (e.x, e.y)

    def _drag_move(self, e):
        if self._drag and self._cid:
            dx = e.x - self._drag[0]
            dy = e.y - self._drag[1]
            self._ox  += dx
            self._oy  += dy
            self._drag = (e.x, e.y)
            self._c.move(self._cid, dx, dy)

    def _on_resize(self, _e):
        if self._pil:
            self._fit()
        else:
            self.placeholder()


# ═════════════════════════════════════════════════════════════════
#  HISTORY LOGGER  — CSV + in-app log
# ═════════════════════════════════════════════════════════════════
CSV_FIELDS = [
    "timestamp", "image_filename", "image_path",
    "location_name", "city", "country",
    "latitude", "longitude", "confidence",
    "reasoning", "ocr_text", "language",
    "driving_side", "license_plate", "sun_azimuth", "hemisphere",
    "exif_gps_lat", "exif_gps_lng", "exif_camera",
]

class HistoryLogger:
    """Writes every analysis result to a CSV file and keeps an in-memory list."""
    def __init__(self, csv_path: str = None):
        if csv_path is None:
            home = Path.home()
            csv_path = str(home / "sightpoint_history.csv")
        self.csv_path = csv_path
        self._records: list = []
        self._ensure_header()

    def _ensure_header(self):
        p = Path(self.csv_path)
        if not p.exists() or p.stat().st_size == 0:
            try:
                with open(self.csv_path, "w", newline="", encoding="utf-8") as f:
                    csv.DictWriter(f, fieldnames=CSV_FIELDS).writeheader()
            except Exception:
                pass

    def record(self, result: dict, image_path: str, exif_data: dict = None):
        ts   = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        osint = result.get("osint", {})
        exif_gps_lat = exif_gps_lng = exif_camera = ""
        if exif_data:
            gps = exif_data.get("gps")
            if gps:
                exif_gps_lat = gps.get("latitude", "")
                exif_gps_lng = gps.get("longitude", "")
            cam = exif_data.get("camera", {})
            if cam:
                exif_camera = "{} {}".format(
                    cam.get("make",""), cam.get("model","")).strip()

        row = {
            "timestamp":       ts,
            "image_filename":  Path(image_path).name if image_path else "",
            "image_path":      image_path or "",
            "location_name":   result.get("location_name",""),
            "city":            result.get("city",""),
            "country":         result.get("country",""),
            "latitude":        result.get("latitude",""),
            "longitude":       result.get("longitude",""),
            "confidence":      result.get("confidence",""),
            "reasoning":       result.get("reasoning",""),
            "ocr_text":        osint.get("ocr_text",""),
            "language":        osint.get("language",""),
            "driving_side":    osint.get("driving_side",""),
            "license_plate":   osint.get("license_plate",""),
            "sun_azimuth":     osint.get("sun_azimuth",""),
            "hemisphere":      osint.get("hemisphere",""),
            "exif_gps_lat":    exif_gps_lat,
            "exif_gps_lng":    exif_gps_lng,
            "exif_camera":     exif_camera,
        }
        self._records.append(row)
        try:
            with open(self.csv_path, "a", newline="", encoding="utf-8") as f:
                csv.DictWriter(f, fieldnames=CSV_FIELDS).writerow(row)
        except Exception:
            pass
        return row

    def get_all(self) -> list:
        return list(reversed(self._records))


# ═════════════════════════════════════════════════════════════════
#  MAIN APPLICATION
# ═════════════════════════════════════════════════════════════════
class SightPointApp:
    def __init__(self, root: tk.Tk):
        self.root = root

        # Apply the saved theme (colours + fonts) to this module's
        # globals BEFORE any widget is built, so the very first frame
        # painted already reflects the user's last choice.
        import customise.customise_engine as _themes
        _themes.apply_theme_to_module()

        self.root.title(
            "SightPoint AI  v1.0  —  Geolocation Intelligence")
        self.root.configure(bg=BG_DARK)
        self.root.geometry("1520x920")
        self.root.minsize(1100, 700)

        self.image_path   = None
        self.result       = None
        self.exif_data    = {}
        self.country_var  = tk.StringVar(value="Global")
        self.search_mode  = tk.StringVar(value="global")
        self._phase_idx   = 0
        self._phase_after = None
        self._history_log = HistoryLogger()

        # Set by main.py after cogs are first loaded, so a live theme
        # reload can re-attach cog tabs after the UI is rebuilt.
        self.reload_cogs_callback = None

        self._build_ui()
        self.root.after(400, self._post_init)

    # ── Post-init ─────────────────────────────────────────────
    def _post_init(self):
        self._term.log("SightPoint AI v1.0 ready.", "SYS")
        if GEMINI_API_KEY:
            self._term.log("API key: loaded from config ({}).".format(str(_CONFIG_FILE)), "SYS")
        else:
            self._term.log("API key: NOT SET — open Settings to configure.", "WARN")
            self.root.after(600, self._prompt_api_key)
        self._term.log("History CSV: {}".format(self._history_log.csv_path), "SYS")
        self._zoom_c.placeholder()
        self._map.go_to(20.0, 0.0, zoom=3)

    # ═══════════════════════════════════════════════════════════
    #  UI BUILD
    # ═══════════════════════════════════════════════════════════
    def _build_ui(self):
        # Header ─────────────────────────────────────────────
        hdr = tk.Frame(self.root, bg=BG_PANEL, height=56)
        hdr.pack(fill="x")
        hdr.pack_propagate(False)
        self._draw_header(hdr)
        sep = tk.Frame(self.root, bg=BORDER_LIT, height=1)
        sep.pack(fill="x")

        # Body ───────────────────────────────────────────────
        body = tk.Frame(self.root, bg=BG_DARK)
        body.pack(fill="both", expand=True)

        # Track exactly the widgets _build_ui created directly under
        # root, so a theme reload can destroy *only* these — never any
        # Toplevel dialogs (Options/Theme/API Key) that might be open
        # at the same time.
        self._root_level_widgets = [hdr, sep, body]

        # Settings sidebar (replaces the old history sidebar)
        from options.sidebar import SettingsSidebar
        self._sidebar = SettingsSidebar(body)
        self._sidebar.pack(side="left", fill="y")
        tk.Frame(body, bg=BORDER, width=1).pack(side="left", fill="y")

        # Left controls
        lc = tk.Frame(body, bg=BG_DARK, width=390)
        lc.pack(side="left", fill="y", padx=(8,6), pady=10)
        lc.pack_propagate(False)
        tk.Frame(body, bg=BORDER, width=1).pack(side="left", fill="y", pady=10)

        # Right area
        self._rc = tk.Frame(body, bg=BG_DARK)
        self._rc.pack(side="left", fill="both", expand=True,
                       padx=(6,8), pady=10)

        self._build_controls(lc)
        self._build_right()

    def _draw_header(self, parent):
        c = tk.Canvas(parent, bg=BG_PANEL, highlightthickness=0, height=56)
        c.pack(fill="x")
        c.create_rectangle(14, 12, 40, 44, outline=CYAN, width=2)
        c.create_polygon(19, 40, 36, 40, 27, 15, fill=CYAN)
        c.create_text(50, 19, text="SIGHTPOINT AI  v1.0",
                      anchor="w", fill=WHITE,
                      font=("Courier New", 14, "bold"))
        c.create_text(50, 37,
                      text="TILE MAP  ·  FORENSIC VISION  ·  OSINT  ·  EXIF  ·  HEATMAP  ·  RULER  ·  CONFIG KEY",
                      anchor="w", fill=TEXT_DIM, font=FONT_MONO_XS)
        for i, t in enumerate(reversed(
                ["TILES","HEATMAP","RULER","PLATES","SHADOW","OCR","EXIF"])):
            c.create_text(1500 - i*95, 28, text=t, anchor="e",
                          fill=TEXT_FAINT, font=FONT_MONO_XS)

        # Settings button in header — opens a dropdown menu
        settings_btn = tk.Button(
            parent, text="⬡ SETTINGS ▾",
            bg=BG_PANEL, fg=TEXT_DIM,
            font=FONT_MONO_XS, relief="flat", cursor="hand2",
            padx=10, pady=0,
            activebackground=BORDER_LIT, activeforeground=CYAN,
            command=self._open_settings_menu
        )
        settings_btn.place(relx=1.0, rely=0.5, anchor="e", x=-10)
        self._settings_btn = settings_btn

    def _build_controls(self, parent):
        # ── Image ───────────────────────────────────────────
        self._slbl(parent, "TARGET IMAGE  (scroll=zoom · drag=pan)")
        zf = tk.Frame(parent, bg=BG_CARD,
                       highlightbackground=BORDER_LIT, highlightthickness=1,
                       height=185)
        zf.pack(fill="x", pady=(2,3))
        zf.pack_propagate(False)
        self._zoom_c = ZoomCanvas(zf)
        self._zoom_c.pack(fill="both", expand=True)
        # NOTE: Do NOT bind click on the canvas - ZoomCanvas needs its own
        # drag binding. Use explicit Browse button instead.

        # Browse / Clear row
        img_row = tk.Frame(parent, bg=BG_DARK)
        img_row.pack(fill="x", pady=(2, 2))
        self._browse_btn = tk.Button(
            img_row, text="◈ BROWSE IMAGE",
            bg=CYAN, fg=BG_DARK,
            font=("Courier New", 8, "bold"),
            relief="flat", cursor="hand2", pady=6,
            activebackground=CYAN_BRIGHT, activeforeground=BG_DARK,
            command=self._browse)
        self._browse_btn.pack(side="left", fill="x", expand=True, padx=(0, 4))
        self._clear_img_btn = tk.Button(
            img_row, text="✕ CLEAR",
            bg=BG_INPUT, fg=TEXT_DIM,
            font=("Courier New", 8, "bold"),
            relief="flat", cursor="hand2", pady=6,
            activebackground=RED_COL, activeforeground=WHITE,
            state="disabled", command=self._clear_image)
        self._clear_img_btn.pack(side="left")

        self._fname_lbl = tk.Label(parent, text="No image loaded",
                                    bg=BG_DARK, fg=TEXT_FAINT,
                                    font=FONT_MONO_XS, anchor="w")
        self._fname_lbl.pack(fill="x", pady=(2,2))

        self._exif_lbl = tk.Label(parent, text="", bg=BG_CARD,
                                   fg=GREEN, font=FONT_MONO_XS,
                                   anchor="w", wraplength=370, justify="left")

        # ── Scope ────────────────────────────────────────────
        self._slbl(parent, "SEARCH SCOPE")
        sf = tk.Frame(parent, bg=BG_CARD,
                      highlightbackground=BORDER_LIT, highlightthickness=1)
        sf.pack(fill="x", pady=(2,8))
        mr = tk.Frame(sf, bg=BG_CARD)
        mr.pack(fill="x", padx=8, pady=8)
        self._gbtn = tk.Button(
            mr, text="◎  GLOBAL", bg=CYAN, fg=BG_DARK,
            font=("Courier New",9,"bold"), relief="flat",
            cursor="hand2", pady=9,
            activebackground=CYAN_BRIGHT, activeforeground=BG_DARK,
            command=self._mode_global)
        self._gbtn.pack(side="left", fill="x", expand=True, padx=(0,5))
        self._cbtn = tk.Button(
            mr, text="◈  BY COUNTRY", bg=BG_INPUT, fg=TEXT_DIM,
            font=("Courier New",9,"bold"), relief="flat",
            cursor="hand2", pady=9,
            activebackground=BORDER_LIT, activeforeground=TEXT_BRIGHT,
            command=self._mode_country)
        self._cbtn.pack(side="left", fill="x", expand=True)
        self._cpicker = tk.Frame(sf, bg=BG_CARD)
        tk.Label(self._cpicker, text="COUNTRY:", bg=BG_CARD,
                 fg=TEXT_DIM, font=FONT_MONO_XS).pack(side="left",padx=(8,5))
        self._combo = ttk.Combobox(
            self._cpicker, values=COUNTRIES,
            textvariable=self.country_var,
            font=FONT_MONO_SM, width=22, state="readonly")
        self._combo.pack(side="left", padx=(0,8))
        self._style_combo()

        # ── Analyze button ───────────────────────────────────
        self.go_btn = tk.Button(
            parent, text="⬡  INITIATE ANALYSIS",
            bg=BG_CARD, fg=TEXT_DIM,
            font=("Courier New",10,"bold"),
            relief="flat", pady=14, cursor="hand2", state="disabled",
            highlightbackground=BORDER_LIT, highlightthickness=1,
            command=self._start)
        self.go_btn.pack(fill="x", pady=(0,4))

        self._phase_lbl = tk.Label(parent, text="", bg=BG_DARK,
                                    fg=CYAN, font=FONT_MONO_XS)
        self._phase_lbl.pack(anchor="w", pady=(1,1))
        self._pbar = ProgressBar(parent, bar_height=4)
        self._pbar.pack(fill="x", pady=(0,8))

        # ── HUD ─────────────────────────────────────────────
        self._slbl(parent, "SYSTEM HEALTH")
        self._hud = HUD(parent, highlightbackground=BORDER,
                         highlightthickness=1)
        self._hud.pack(fill="x", pady=(2,0))

    def _build_right(self):
        # Style the notebook
        style = ttk.Style()
        try: style.theme_use("clam")
        except Exception: pass
        style.configure("Dark.TNotebook",
                         background=BG_DARK, borderwidth=0)
        style.configure("Dark.TNotebook.Tab",
                         background=BG_PANEL, foreground=TEXT_DIM,
                         font=FONT_MONO_XS, padding=(14, 6),
                         borderwidth=0)
        style.map("Dark.TNotebook.Tab",
                  background=[("selected", BG_CARD)],
                  foreground=[("selected", CYAN)])

        nb = ttk.Notebook(self._rc, style="Dark.TNotebook")
        nb.pack(fill="both", expand=True)

        # ── Tab 1: MAP ───────────────────────────────────────
        map_tab = tk.Frame(nb, bg=BG_DARK)
        nb.add(map_tab, text="  ◈ MAP  ")

        pw = tk.PanedWindow(map_tab, orient="vertical",
                             bg=BG_DARK, sashwidth=6,
                             sashrelief="flat", sashpad=2)
        pw.pack(fill="both", expand=True)

        map_host = tk.Frame(pw, bg=BG_DARK,
                             highlightbackground=BORDER_LIT,
                             highlightthickness=1)
        pw.add(map_host, minsize=300)
        self._map = MapWidget(
            map_host, root_ref=self.root,
            log_fn=lambda m, l="SYS":
                self.root.after(0, lambda msg=m, lvl=l:
                    self._term.log(msg, lvl)))
        self._map.pack(fill="both", expand=True)

        bottom = tk.Frame(pw, bg=BG_DARK)
        pw.add(bottom, minsize=180)

        self._res_host = tk.Frame(bottom, bg=BG_DARK)
        self._res_host.pack(fill="both", expand=True)
        self._show_idle_placeholder()

        tk.Frame(bottom, bg=BORDER, height=1).pack(fill="x", pady=(3,0))
        th = tk.Frame(bottom, bg=BG_PANEL)
        th.pack(fill="x")
        tk.Label(th, text="  TERMINAL", bg=BG_PANEL,
                 fg=TEXT_DIM, font=FONT_MONO_XS).pack(side="left")
        self._mkbtn(th, "CLEAR", lambda: self._term.clear(),
                    fg=TEXT_FAINT, bg=BG_PANEL).pack(side="right", padx=4)
        tf = tk.Frame(bottom, bg=BG_TERM,
                      highlightbackground=BORDER, highlightthickness=1,
                      height=110)
        tf.pack(fill="x")
        tf.pack_propagate(False)
        self._term = TerminalConsole(tf)
        self._term.pack(fill="both", expand=True)

        # ── Tab 2: HISTORY LOG ───────────────────────────────
        hist_tab = tk.Frame(nb, bg=BG_DARK)
        nb.add(hist_tab, text="  ▣ HISTORY LOG  ")
        self._build_history_tab(hist_tab)

        self._nb = nb

    def _build_history_tab(self, parent):
        # Header row
        hdr = tk.Frame(parent, bg=BG_PANEL)
        hdr.pack(fill="x")
        tk.Label(hdr, text="  ANALYSIS HISTORY LOG",
                 bg=BG_PANEL, fg=TEXT_DIM, font=FONT_MONO_XS).pack(side="left", pady=6)

        self._csv_path_lbl = tk.Label(
            hdr, text="", bg=BG_PANEL, fg=TEXT_FAINT, font=FONT_MONO_XS)
        self._csv_path_lbl.pack(side="left", padx=8)

        tk.Button(hdr, text="↻ REFRESH", bg=BG_PANEL, fg=CYAN,
                  font=FONT_MONO_XS, relief="flat", cursor="hand2",
                  command=self._refresh_history_tab).pack(side="right", padx=6, pady=4)
        tk.Frame(parent, bg=BORDER_LIT, height=1).pack(fill="x")

        # Treeview table
        cols = ("TIME", "FILE", "LOCATION", "CONF%", "COUNTRY", "LAT", "LNG", "LANGUAGE", "DRIVE")
        style = ttk.Style()
        style.configure("History.Treeview",
                         background=BG_INPUT, foreground=TEXT_MID,
                         fieldbackground=BG_INPUT, font=FONT_MONO_XS,
                         rowheight=22, borderwidth=0)
        style.configure("History.Treeview.Heading",
                         background=BG_PANEL, foreground=CYAN,
                         font=FONT_MONO_XS, relief="flat")
        style.map("History.Treeview",
                  background=[("selected", CYAN_DIM)],
                  foreground=[("selected", CYAN_BRIGHT)])

        frame = tk.Frame(parent, bg=BG_DARK)
        frame.pack(fill="both", expand=True, padx=4, pady=4)

        vsb = ttk.Scrollbar(frame, orient="vertical")
        hsb = ttk.Scrollbar(frame, orient="horizontal")
        self._hist_tree = ttk.Treeview(
            frame, columns=cols, show="headings",
            style="History.Treeview",
            yscrollcommand=vsb.set, xscrollcommand=hsb.set)
        vsb.configure(command=self._hist_tree.yview)
        hsb.configure(command=self._hist_tree.xview)

        col_widths = {"TIME":120,"FILE":160,"LOCATION":180,"CONF%":60,
                      "COUNTRY":110,"LAT":90,"LNG":90,"LANGUAGE":130,"DRIVE":80}
        for c in cols:
            self._hist_tree.heading(c, text=c)
            self._hist_tree.column(c, width=col_widths.get(c,100),
                                    minwidth=50, anchor="w")

        vsb.pack(side="right", fill="y")
        hsb.pack(side="bottom", fill="x")
        self._hist_tree.pack(fill="both", expand=True)

        self._hist_tree.bind("<<TreeviewSelect>>", self._hist_row_click)

        # Detail panel below table
        tk.Frame(parent, bg=BORDER, height=1).pack(fill="x")
        self._hist_detail = tk.Text(
            parent, bg=BG_TERM, fg=TEXT_MID, font=FONT_MONO_SM,
            relief="flat", height=6, wrap="word",
            state="disabled", padx=8, pady=6)
        self._hist_detail.pack(fill="x")

        # Update csv path label
        self._csv_path_lbl.configure(
            text="CSV: {}".format(self._history_log.csv_path))

    def _refresh_history_tab(self):
        """Reload history table from in-memory records."""
        for item in self._hist_tree.get_children():
            self._hist_tree.delete(item)
        for row in self._history_log.get_all():
            conf = str(row.get("confidence",""))
            tag  = "hi" if int(conf or 0) >= 70 else "med" if int(conf or 0) >= 40 else "lo"
            self._hist_tree.insert("", "end", values=(
                row.get("timestamp",""),
                row.get("image_filename",""),
                row.get("location_name",""),
                conf,
                row.get("country",""),
                row.get("latitude",""),
                row.get("longitude",""),
                row.get("language","")[:30],
                row.get("driving_side",""),
            ), tags=(tag,))
        self._hist_tree.tag_configure("hi",  foreground=GREEN)
        self._hist_tree.tag_configure("med", foreground=YELLOW)
        self._hist_tree.tag_configure("lo",  foreground=RED_COL)

    def _hist_row_click(self, _e):
        sel = self._hist_tree.selection()
        if not sel:
            return
        idx = self._hist_tree.index(sel[0])
        records = self._history_log.get_all()
        if idx >= len(records):
            return
        row = records[idx]
        detail = (
            "LOCATION:  {location_name}\n"
            "COORDS:    {latitude}, {longitude}  |  CONFIDENCE: {confidence}%\n"
            "REASONING: {reasoning}\n"
            "OCR TEXT:  {ocr_text}\n"
            "LANGUAGE:  {language}  |  DRIVING: {driving_side}  |  "
            "PLATES: {license_plate}\n"
            "SUN AZ:    {sun_azimuth}  |  HEMISPHERE: {hemisphere}\n"
            "EXIF GPS:  {exif_gps_lat}, {exif_gps_lng}  |  CAMERA: {exif_camera}"
        ).format(**{k: row.get(k,"—") or "—" for k in CSV_FIELDS})
        self._hist_detail.configure(state="normal")
        self._hist_detail.delete("1.0","end")
        self._hist_detail.insert("1.0", detail)
        self._hist_detail.configure(state="disabled")
        # Also jump map to that location
        try:
            lat = float(row.get("latitude", 0))
            lng = float(row.get("longitude", 0))
            self._map.go_to(lat, lng, zoom=12)
            self._map.drop_pin(lat, lng, row.get("location_name",""))
        except Exception:
            pass

    # ── Placeholder ───────────────────────────────────────────
    def _show_idle_placeholder(self):
        for w in self._res_host.winfo_children():
            try: w.destroy()
            except Exception: pass
        tk.Label(self._res_host,
                 text="Load an image and press Initiate Analysis",
                 bg=BG_DARK, fg=TEXT_FAINT, font=FONT_MONO_SM).pack(
                     expand=True, pady=20)

    # ── Settings dropdown menu ────────────────────────────────
    def _open_settings_menu(self):
        """Show a dropdown with Options / API Key / Theme under the
        SETTINGS button in the header."""
        menu = tk.Menu(
            self.root, tearoff=0,
            bg=BG_CARD, fg=TEXT_MID,
            activebackground=CYAN, activeforeground=BG_DARK,
            font=FONT_MONO_XS, relief="flat", bd=0)
        menu.add_command(label="⚙  Options", command=self._open_options_dialog)
        menu.add_command(label="🔑  API Key", command=self._prompt_api_key)
        menu.add_command(label="🎨  Theme", command=self._open_theme_dialog)

        btn = self._settings_btn
        x = btn.winfo_rootx()
        y = btn.winfo_rooty() + btn.winfo_height()
        try:
            menu.tk_popup(x, y)
        finally:
            menu.grab_release()

    def _open_options_dialog(self):
        """
        Open the full settings/options panel as a standalone dialog
        (same footprint as the API Key dialog). This reuses the exact
        same SettingsSidebar widget that's docked on the left — no
        duplicated code, so both stay in sync automatically.
        """
        from options.sidebar import SettingsSidebar

        win = tk.Toplevel(self.root)
        win.title("SightPoint AI — Options")
        win.configure(bg=BG_DARK)
        win.geometry("520x480")
        win.minsize(420, 320)
        win.transient(self.root)
        win.grab_set()

        hdr = tk.Frame(win, bg=BG_PANEL, height=40)
        hdr.pack(fill="x")
        hdr.pack_propagate(False)
        tk.Label(hdr, text="  ⚙  OPTIONS", bg=BG_PANEL, fg=CYAN,
                 font=(FONT_MONO[0], 10, "bold")).pack(side="left", pady=10)
        tk.Frame(win, bg=BORDER_LIT, height=1).pack(fill="x")

        body = tk.Frame(win, bg=BG_DARK)
        body.pack(fill="both", expand=True)

        panel = SettingsSidebar(body, fixed_width=False)
        panel.pack(fill="both", expand=True)

        tk.Frame(win, bg=BORDER_LIT, height=1).pack(fill="x")
        tk.Button(
            win, text="✕  CLOSE", bg=BG_INPUT, fg=TEXT_DIM,
            font=("Courier New", 9, "bold"),
            relief="flat", cursor="hand2", pady=8,
            activebackground=BORDER_LIT, activeforeground=WHITE,
            command=win.destroy
        ).pack(fill="x", padx=14, pady=10)

        win.bind("<Escape>", lambda _e: win.destroy())

    def _open_theme_dialog(self):
        from customise.theme_dialog import ThemeDialog
        ThemeDialog(self.root, on_apply=self.reload_theme_live)

    def reload_theme_live(self):
        """
        Attempt to refresh the whole running app with the newly saved
        theme, without requiring a restart. Rebuilds the header/body
        (and re-attaches any cog tabs) while leaving any other open
        Toplevel windows — such as the Theme dialog that just called
        this — completely untouched.

        The actual rebuild is deferred one tick via `after_idle` so it
        never runs while the caller (e.g. ThemeDialog._apply) is still
        mid-execution and about to touch its own widgets afterwards.

        Raises immediately if nothing can be scheduled, so the caller
        can fall back to a "restart to see it fully applied" message.
        """
        import customise.customise_engine as _themes
        _themes.apply_theme_to_module()
        self.root.after_idle(self._rebuild_ui_after_theme_change)

    def _rebuild_ui_after_theme_change(self):
        # Destroy only the widgets _build_ui created directly under
        # root (header/separator/body) — never touch other Toplevels
        # (Options dialog, Theme dialog, API Key dialog, etc.) that
        # might currently be open.
        for w in getattr(self, "_root_level_widgets", []):
            try:
                w.destroy()
            except Exception:
                pass

        try:
            self.root.configure(bg=BG_DARK)
            self._build_ui()
        except Exception as exc:
            print("[ERROR] Theme rebuild failed: {}".format(exc))
            return

        # Re-attach cog tabs (Video, Enhance, ...) if main.py gave us
        # a way to do that.
        if callable(self.reload_cogs_callback):
            try:
                self.reload_cogs_callback()
            except Exception as exc:
                print("[WARN] Could not re-attach cogs after theme reload: {}"
                      .format(exc))

        try:
            self._term.log("Theme applied live.", "SYS")
        except Exception:
            pass

    # ── API Key Settings dialog ───────────────────────────────
    def _prompt_api_key(self):
        """Show a modal dialog to enter / update the Gemini API key."""
        global GEMINI_API_KEY

        win = tk.Toplevel(self.root)
        win.title("SightPoint AI — Settings")
        win.configure(bg=BG_DARK)
        win.geometry("520x280")
        win.resizable(False, False)
        win.transient(self.root)
        win.grab_set()

        # Header strip
        hdr = tk.Frame(win, bg=BG_PANEL, height=40)
        hdr.pack(fill="x")
        hdr.pack_propagate(False)
        tk.Label(hdr, text="  ⬡  API KEY CONFIGURATION",
                 bg=BG_PANEL, fg=CYAN,
                 font=("Courier New", 10, "bold")).pack(side="left", pady=10)
        tk.Frame(win, bg=BORDER_LIT, height=1).pack(fill="x")

        body = tk.Frame(win, bg=BG_DARK)
        body.pack(fill="both", expand=True, padx=20, pady=16)

        tk.Label(body,
                 text="Enter your Google Gemini API key below.\n"
                      "Get a free key at: aistudio.google.com/apikey\n"
                      "Your key is stored locally in: {}".format(_CONFIG_FILE),
                 bg=BG_DARK, fg=TEXT_MID,
                 font=FONT_MONO_XS, justify="left").pack(anchor="w", pady=(0, 12))

        tk.Label(body, text="GEMINI API KEY:", bg=BG_DARK,
                 fg=TEXT_DIM, font=FONT_MONO_XS).pack(anchor="w")

        entry_var = tk.StringVar(value=GEMINI_API_KEY)
        entry = tk.Entry(
            body, textvariable=entry_var,
            bg=BG_INPUT, fg=CYAN_BRIGHT,
            font=("Courier New", 10),
            relief="flat", show="•",
            highlightbackground=BORDER_LIT, highlightthickness=1,
            insertbackground=CYAN)
        entry.pack(fill="x", ipady=6, pady=(4, 4))

        # Show / hide toggle
        show_var = tk.BooleanVar(value=False)
        def _toggle_show():
            entry.configure(show="" if show_var.get() else "•")
        tk.Checkbutton(
            body, text="Show key", variable=show_var,
            command=_toggle_show,
            bg=BG_DARK, fg=TEXT_DIM,
            font=FONT_MONO_XS,
            selectcolor=BG_INPUT,
            activebackground=BG_DARK,
            activeforeground=CYAN,
            relief="flat", cursor="hand2"
        ).pack(anchor="w")

        status_lbl = tk.Label(body, text="", bg=BG_DARK,
                               font=FONT_MONO_XS)
        status_lbl.pack(anchor="w", pady=(4, 0))

        def _save():
            global GEMINI_API_KEY
            key = entry_var.get().strip()
            if not key:
                status_lbl.configure(text="✗  Key cannot be empty.", fg=RED_COL)
                return
            GEMINI_API_KEY = key
            cfg = _load_config()
            cfg["gemini_api_key"] = key
            try:
                _save_config(cfg)
                status_lbl.configure(text="✓  Saved to {}".format(_CONFIG_FILE),
                                     fg=GREEN)
                self._term.log("API key saved to config.", "SYS")
                self.root.after(1200, win.destroy)
            except Exception as exc:
                status_lbl.configure(
                    text="✗  Save failed: {}".format(exc), fg=RED_COL)

        btn_row = tk.Frame(body, bg=BG_DARK)
        btn_row.pack(fill="x", pady=(10, 0))
        tk.Button(btn_row, text="✓  SAVE KEY",
                  bg=CYAN, fg=BG_DARK,
                  font=("Courier New", 9, "bold"),
                  relief="flat", cursor="hand2", pady=8,
                  activebackground=CYAN_BRIGHT, activeforeground=BG_DARK,
                  command=_save).pack(side="left", fill="x", expand=True, padx=(0, 6))
        tk.Button(btn_row, text="✕  CANCEL",
                  bg=BG_INPUT, fg=TEXT_DIM,
                  font=("Courier New", 9, "bold"),
                  relief="flat", cursor="hand2", pady=8,
                  activebackground=BORDER_LIT, activeforeground=WHITE,
                  command=win.destroy).pack(side="left")

        entry.focus_set()
        win.bind("<Return>", lambda _e: _save())
        win.bind("<Escape>", lambda _e: win.destroy())

    # ── Image loading / clearing ──────────────────────────────
    def _browse(self):
        path = filedialog.askopenfilename(
            title="Select Target Image",
            filetypes=[("Images","*.jpg *.jpeg *.png *.webp *.gif *.bmp"),
                       ("All","*.*")])
        if path:
            self._load_image(path)

    def _clear_image(self):
        self.image_path = None
        self.exif_data  = {}
        self._zoom_c._pil = None
        self._zoom_c._ref = None
        self._zoom_c._cid = None
        self._zoom_c.placeholder()
        self._fname_lbl.configure(text="No image loaded", fg=TEXT_FAINT)
        self._exif_lbl.pack_forget()
        self._clear_img_btn.configure(state="disabled")
        self.go_btn.configure(state="disabled", fg=TEXT_DIM, bg=BG_CARD,
                               text="⬡  INITIATE ANALYSIS")
        self.go_btn.unbind("<Enter>")
        self.go_btn.unbind("<Leave>")
        self._phase_lbl.configure(text="")
        self._pbar.set_value(0, CYAN)
        self._show_idle_placeholder()
        self._map.clear_pin()
        self._map.clear_heatmap()
        self._term.log("Image cleared.", "SYS")

    def _load_image(self, path: str):
        self.image_path = path
        self._zoom_c.load(path)
        name = Path(path).name
        self._fname_lbl.configure(text="  " + name, fg=CYAN_BRIGHT)
        self._clear_img_btn.configure(state="normal")
        self._term.log("Image loaded: {}".format(name), "INFO")

        self.exif_data = extract_exif(path)
        if self.exif_data.get("gps"):
            g = self.exif_data["gps"]
            self._exif_lbl.configure(
                text="  EXIF GPS: {}, {}".format(
                    g["latitude"], g["longitude"]), fg=GREEN)
            self._exif_lbl.pack(fill="x", pady=(0,4))
            self._term.log("EXIF GPS: {}, {}".format(
                g["latitude"], g["longitude"]), "DATA")
            self._map.go_to(g["latitude"], g["longitude"], zoom=13)
        elif self.exif_data.get("camera"):
            cam = self.exif_data["camera"]
            txt = "  EXIF: {} {} {}".format(
                cam.get("make",""), cam.get("model",""),
                cam.get("datetime","")).strip()
            self._exif_lbl.configure(text=txt, fg=CYAN)
            self._exif_lbl.pack(fill="x", pady=(0,4))
            self._term.log(txt, "DATA")
        else:
            self._exif_lbl.pack_forget()

        self.go_btn.configure(state="normal", fg=CYAN, bg=BG_CARD,
                               text="⬡  INITIATE ANALYSIS")
        self.go_btn.bind("<Enter>",
                          lambda _: self.go_btn.configure(bg=CYAN, fg=BG_DARK))
        self.go_btn.bind("<Leave>",
                          lambda _: self.go_btn.configure(bg=BG_CARD, fg=CYAN))

    # ── Scope toggles ─────────────────────────────────────────
    def _mode_global(self):
        self.search_mode.set("global")
        self.country_var.set("Global")
        self._gbtn.configure(bg=CYAN, fg=BG_DARK)
        self._cbtn.configure(bg=BG_INPUT, fg=TEXT_DIM)
        self._cpicker.pack_forget()

    def _mode_country(self):
        self.search_mode.set("country")
        self._cbtn.configure(bg=CYAN, fg=BG_DARK)
        self._gbtn.configure(bg=BG_INPUT, fg=TEXT_DIM)
        self._cpicker.pack(fill="x", pady=(0,8))
        if self.country_var.get() == "Global":
            self.country_var.set("United States")

    # ── Analysis ──────────────────────────────────────────────
    def _start(self):
        if not self.image_path:
            messagebox.showwarning("No Image", "Load an image first.")
            return
        if not REQUESTS_AVAILABLE:
            messagebox.showerror("Missing", "pip install requests")
            return
        if not GEMINI_API_KEY:
            messagebox.showerror(
                "API Key Not Set",
                "No Gemini API key configured.\n\n"
                "Go to Settings → Set API Key to enter your key.\n"
                "Get a free key at: aistudio.google.com/apikey")
            self._prompt_api_key()
            return

        country = (self.country_var.get()
                   if self.search_mode.get() == "country" else "Global")
        self._term.log("Analysis started — scope={}".format(country), "INFO")
        self._hud.set_status("SCANNING", YELLOW)
        self.go_btn.configure(state="disabled", fg=TEXT_DIM, bg=BG_CARD,
                               text="◎  ANALYZING…")
        self._show_idle_placeholder()
        self._phase_lbl.configure(text="", fg=CYAN)
        self._pbar.set_value(0, CYAN)
        self._phase_idx = 0
        self._tick_phase()

        threading.Thread(
            target=self._worker,
            args=(self.image_path, country, self.exif_data.copy()),
            daemon=True).start()

    def _tick_phase(self):
        if self._phase_idx < len(ANALYSIS_PHASES):
            self._phase_lbl.configure(text=ANALYSIS_PHASES[self._phase_idx])
            self._pbar.set_value(
                int(self._phase_idx / len(ANALYSIS_PHASES) * 88), CYAN)
            self._phase_idx += 1
            self._phase_after = self.root.after(640, self._tick_phase)

    def _worker(self, path, country, exif):
        def log_safe(msg, lvl="INFO"):
            self.root.after(0, lambda m=msg, l=lvl: self._term.log(m, l))
        try:
            result = gemini_geolocate(
                path, country, exif_data=exif, log_cb=log_safe)
            self.root.after(0, self._on_success, result)
        except Exception as exc:
            self.root.after(0, self._on_fail, str(exc))

    def _on_success(self, result: dict):
        if self._phase_after:
            self.root.after_cancel(self._phase_after)
            self._phase_after = None
        self._pbar.set_value(100, GREEN)
        self._phase_lbl.configure(text="✓  COMPLETE", fg=GREEN)
        self._hud.set_status("COMPLETE", GREEN)
        self._hud.increment()
        self.result = result
        self.go_btn.configure(state="normal", text="⬡  RE-ANALYZE",
                               fg=CYAN, bg=BG_CARD)

        for k, v in result.get("osint", {}).items():
            vs = str(v).lower()
            if vs not in ("not visible","indeterminate","n/a","—",""):
                self._term.log("OSINT [{}]: {}".format(k, v), "DATA")

        # Update embedded map — no browser
        try:
            lat  = float(result.get("latitude",  0))
            lng  = float(result.get("longitude", 0))
            name = result.get("location_name", "")
            raw  = result.get("heatmap_candidates", [])
            hpts = [(p.get("lat", lat), p.get("lng", lng), p.get("weight", 0.5))
                    for p in raw if isinstance(p, dict)]
            if not hpts:
                hpts = [(lat, lng, 1.0)]
            self._map.set_heatmap(hpts)
            self._map.go_to(lat, lng, zoom=12)
            self._map.drop_pin(lat, lng, name)
        except Exception as exc:
            self._term.log("Map error: {}".format(exc), "WARN")

        self._render_results(result)
        if self.image_path:
            # NOTE: sidebar is now SettingsSidebar (no .add() method) —
            # session history is tracked via HistoryLogger below and,
            # if enabled, via the options-system history CSV (see
            # options.append_history in the cogs that extract signal).
            # Log to CSV and refresh history tab
            self._history_log.record(result, self.image_path, self.exif_data)
            self._refresh_history_tab()
            self._term.log("Saved to: {}".format(self._history_log.csv_path), "SYS")

        # ── Deep Analysis (image_engine/) — optional, async ──────
        # Fires only if enabled in Options. Never blocks the UI: the
        # main geolocation result above is already fully displayed by
        # this point, deep analysis just adds corroborating evidence
        # on top of it as each module trickles in.
        try:
            import options
            if options.get_option("deep_analysis_enabled") and self.image_path:
                self._term.log(
                    "Deep analysis enabled. Starting image_engine…", "INFO")
                threading.Thread(
                    target=self._run_deep_analysis,
                    args=(self.image_path, result),
                    daemon=True).start()
        except Exception as exc:
            self._term.log("Deep analysis could not start: {}".format(exc), "WARN")

    def _run_deep_analysis(self, image_path: str, geolocation_result: dict):
        """Background-thread entry point for image_engine. All UI
        updates are marshalled back via root.after()."""
        try:
            import options
            import image_engine

            timeout = options.get_option("deep_analysis_timeout_seconds", 60)

            def on_result(module_name, module_result):
                votes = module_result.get("region_votes", {}) if isinstance(
                    module_result, dict) else {}
                if votes:
                    top = max(votes.items(), key=lambda kv: kv[1])
                    msg = "[{}] {} ({}%)".format(
                        module_name, top[0], int(top[1] * 100))
                else:
                    msg = "[{}] no signal".format(module_name)
                self.root.after(0, lambda m=msg: self._term.log(m, "DATA"))

            def on_complete(full_results):
                consensus = full_results.get("consensus", {})
                modules_run = consensus.get("modules_run", 0)
                contributing = len(consensus.get("modules_contributing", []))
                top_region = consensus.get("top_region")
                summary = (
                    "Image-engine complete. {}/{} modules contributed evidence."
                    .format(contributing, modules_run)
                )
                self.root.after(0, lambda s=summary: self._term.log(s, "OK"))
                if top_region:
                    detail = "Consensus top region: {} (score {:.2f})".format(
                        top_region, consensus.get("top_score", 0.0))
                    self.root.after(0, lambda d=detail: self._term.log(d, "OK"))

            image_engine.run_deep_analysis(
                image_path, geolocation_result,
                on_result_cb=on_result,
                on_complete_cb=on_complete,
                timeout=timeout)
        except Exception as exc:
            self.root.after(0, lambda e=exc:
                self._term.log("Deep analysis error: {}".format(e), "ERROR"))

    def _on_fail(self, err: str):
        if self._phase_after:
            self.root.after_cancel(self._phase_after)
            self._phase_after = None
        self._pbar.set_value(0, RED_COL)
        self._phase_lbl.configure(text="✗  FAILED", fg=RED_COL)
        self._hud.set_status("ERROR", RED_COL)
        self.go_btn.configure(state="normal", text="⬡  RETRY",
                               fg=RED_COL, bg=BG_CARD)
        self._term.log(err, "ERROR")
        self._show_error(err)

    # ── Session reload ────────────────────────────────────────
    def _reload_session(self, session: dict):
        result     = session["result"]
        image_path = session["image_path"]
        if image_path and Path(image_path).exists():
            self.image_path = image_path
            self._zoom_c.load(image_path)
            self._fname_lbl.configure(
                text="  {} [HISTORY]".format(Path(image_path).name),
                fg=YELLOW)
        try:
            lat  = float(result.get("latitude",  0))
            lng  = float(result.get("longitude", 0))
            name = result.get("location_name", "")
            self._map.go_to(lat, lng, zoom=12)
            self._map.drop_pin(lat, lng, name)
        except Exception:
            pass
        self._render_results(result)
        self._term.log("Session reloaded: {}".format(
            result.get("location_name","?")), "SYS")

    # ── Results area helpers ──────────────────────────────────
    def _clear_results(self):
        for w in self._res_host.winfo_children():
            try: w.destroy()
            except Exception: pass

    def _show_error(self, msg: str):
        self._clear_results()
        f = tk.Frame(self._res_host, bg=BG_CARD,
                     highlightbackground=RED_COL, highlightthickness=1)
        f.pack(fill="both", expand=True, pady=4)
        tk.Label(f, text="✗  FAILED", bg=BG_CARD, fg=RED_COL,
                 font=("Courier New",11,"bold")).pack(pady=(16,8))
        tk.Label(f, text=msg, bg=BG_CARD, fg=TEXT_MID,
                 font=FONT_MONO_SM, wraplength=500,
                 justify="center").pack(padx=20)

    def _render_results(self, r: dict):
        self._clear_results()
        outer = tk.Frame(self._res_host, bg=BG_DARK)
        outer.pack(fill="both", expand=True)

        cv = tk.Canvas(outer, bg=BG_DARK, highlightthickness=0)
        sb = ttk.Scrollbar(outer, orient="vertical", command=cv.yview)
        cv.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        cv.pack(side="left", fill="both", expand=True)
        inner = tk.Frame(cv, bg=BG_DARK)
        wid   = cv.create_window((0,0), window=inner, anchor="nw")
        inner.bind("<Configure>",
                   lambda _e: cv.configure(scrollregion=cv.bbox("all")))
        cv.bind("<Configure>",
                lambda e: cv.itemconfig(wid, width=e.width))
        def _sc(e):
            cv.yview_scroll(
                -1*(e.delta//120 if e.delta else
                    (-1 if e.num==5 else 1)), "units")
        for seq in ("<MouseWheel>","<Button-4>","<Button-5>"):
            cv.bind(seq, _sc)

        # ── Location card ──────────────────────────────────
        lc = tk.Frame(inner, bg=BG_CARD,
                      highlightbackground=CYAN, highlightthickness=2)
        lc.pack(fill="x", padx=4, pady=(4,6))
        tk.Frame(lc, bg=CYAN, width=5).pack(side="left", fill="y")
        bd = tk.Frame(lc, bg=BG_CARD)
        bd.pack(side="left", fill="both", expand=True, padx=12, pady=10)

        tk.Label(bd, text="IDENTIFIED LOCATION", bg=BG_CARD,
                 fg=TEXT_DIM, font=FONT_MONO_XS).pack(anchor="w")
        city = r.get("city") or r.get("location_name","?").split(",")[0]
        tk.Label(bd, text=city, bg=BG_CARD, fg=WHITE,
                 font=("Courier New",16,"bold")).pack(anchor="w")
        tk.Label(bd, text=r.get("country") or r.get("location_name",""),
                 bg=BG_CARD, fg=TEXT_MID,
                 font=("Courier New",10)).pack(anchor="w", pady=(1,8))

        cr = tk.Frame(bd, bg=BG_CARD)
        cr.pack(anchor="w", pady=(0,8))
        lat = float(r.get("latitude",  0))
        lng = float(r.get("longitude", 0))
        for lbl, val in [("LAT",lat),("LNG",lng)]:
            bx = tk.Frame(cr, bg=BG_INPUT,
                          highlightbackground=BORDER_LIT, highlightthickness=1)
            bx.pack(side="left", padx=(0,8), ipadx=10, ipady=4)
            tk.Label(bx, text=lbl, bg=BG_INPUT, fg=TEXT_DIM,
                     font=FONT_MONO_XS).pack()
            tk.Label(bx, text="{:.4f}°".format(val),
                     bg=BG_INPUT, fg=CYAN_BRIGHT,
                     font=("Courier New",10,"bold")).pack()

        conf  = int(r.get("confidence", 0))
        cc    = GREEN if conf>=70 else YELLOW if conf>=40 else RED_COL
        cword = "HIGH" if conf>=70 else "MEDIUM" if conf>=40 else "LOW"
        tk.Label(bd, text="CONFIDENCE", bg=BG_CARD, fg=TEXT_DIM,
                 font=FONT_MONO_XS).pack(anchor="w")
        crow = tk.Frame(bd, bg=BG_CARD)
        crow.pack(fill="x")
        tk.Label(crow, text=cword, bg=BG_CARD, fg=cc,
                 font=("Courier New",9,"bold")).pack(side="left")
        tk.Label(crow, text="  {}%".format(conf), bg=BG_CARD, fg=cc,
                 font=("Courier New",13,"bold")).pack(side="right")
        pb = ProgressBar(bd, bar_height=5)
        pb.pack(fill="x", pady=(3,0))
        self.root.after(200, lambda: pb.set_value(conf, cc))

        # ── Reasoning ──────────────────────────────────────
        self._rcard(inner, "DEDUCTION REASONING", r.get("reasoning","—"))

        # ── Visual clues ───────────────────────────────────
        clues = r.get("clues", [])
        if clues:
            cf = tk.Frame(inner, bg=BG_CARD,
                          highlightbackground=BORDER_LIT, highlightthickness=1)
            cf.pack(fill="x", padx=4, pady=(0,6))
            tk.Label(cf, text="VISUAL MARKERS", bg=BG_CARD, fg=TEXT_DIM,
                     font=FONT_MONO_XS).pack(anchor="w", padx=12, pady=(8,4))
            icons = ["⬡","◈","⬢","◆","⬟","◇","⬣","◉","▣","◐"]
            for i, clue in enumerate(clues):
                row = tk.Frame(cf, bg=BG_INPUT,
                               highlightbackground=BORDER, highlightthickness=1)
                row.pack(fill="x", padx=12, pady=(0,4))
                tk.Label(row, text=icons[i % len(icons)],
                         bg=BG_INPUT, fg=CYAN,
                         font=FONT_MONO_SM).pack(side="left", padx=(7,5), pady=6)
                tk.Label(row, text=clue, bg=BG_INPUT, fg=TEXT_MID,
                         font=FONT_MONO_SM, wraplength=460,
                         justify="left").pack(side="left", pady=6, padx=(0,7))
            tk.Frame(cf, height=6, bg=BG_CARD).pack()

        # ── OSINT panel ────────────────────────────────────
        osint = r.get("osint", {})
        if osint:
            oc = tk.Frame(inner, bg=BG_CARD,
                          highlightbackground=PURPLE, highlightthickness=1)
            oc.pack(fill="x", padx=4, pady=(0,6))
            tk.Label(oc, text="OSINT INDICATORS", bg=BG_CARD, fg=PURPLE,
                     font=FONT_MONO_XS).pack(anchor="w", padx=12, pady=(8,4))
            fields = [
                ("license_plate","⬡ PLATES"),
                ("railway_gauge","⬢ RAILWAY"),
                ("aviation",     "◈ AVIATION"),
                ("language",     "◆ LANGUAGE"),
                ("driving_side", "⬟ DRIVE SIDE"),
                ("ocr_text",     "◉ OCR TEXT"),
                ("sun_azimuth",  "◇ SUN AZ."),
                ("hemisphere",   "▣ HEMISPHERE"),
            ]
            for fk, flbl in fields:
                val = str(osint.get(fk, "—")).strip()
                if not val or val.lower() in ("","n/a"):
                    val = "—"
                row = tk.Frame(oc, bg=BG_DARK)
                row.pack(fill="x", padx=12, pady=(0,3))
                tk.Label(row, text="{}:".format(flbl), bg=BG_DARK, fg=PURPLE,
                         font=FONT_MONO_XS, width=14,
                         anchor="w").pack(side="left")
                tk.Label(row, text=val, bg=BG_DARK, fg=TEXT_MID,
                         font=FONT_MONO_SM, wraplength=430,
                         justify="left").pack(side="left", padx=(4,0))
            tk.Frame(oc, height=6, bg=BG_CARD).pack()

        # ── EXIF card ──────────────────────────────────────
        exif = self.exif_data.get("raw", {})
        if exif:
            self._rcard(inner, "EXIF METADATA",
                        "\n".join("{}: {}".format(k,v)
                                  for k,v in exif.items()))

        # ── Copy coords button ─────────────────────────────
        bf = tk.Frame(inner, bg=BG_DARK)
        bf.pack(fill="x", padx=4, pady=(0,8))

        def copy_coords():
            self.root.clipboard_clear()
            self.root.clipboard_append("{:.6f}, {:.6f}".format(lat, lng))
            cpbtn.configure(text="✓  COPIED!", fg=GREEN)
            self.root.after(2500, lambda: cpbtn.configure(
                text="⬡  COPY COORDINATES", fg=TEXT_DIM))

        cpbtn = tk.Button(
            bf, text="⬡  COPY COORDINATES",
            bg=BG_CARD, fg=TEXT_DIM,
            font=("Courier New",9,"bold"),
            relief="flat", pady=11, cursor="hand2",
            highlightbackground=BORDER, highlightthickness=1,
            activebackground=BORDER_LIT, activeforeground=WHITE,
            command=copy_coords)
        cpbtn.pack(fill="x")

    # ── Small helpers ─────────────────────────────────────────
    def _rcard(self, parent, title: str, text: str):
        f = tk.Frame(parent, bg=BG_CARD,
                     highlightbackground=BORDER_LIT, highlightthickness=1)
        f.pack(fill="x", padx=4, pady=(0,6))
        tk.Label(f, text=title, bg=BG_CARD, fg=TEXT_DIM,
                 font=FONT_MONO_XS).pack(anchor="w", padx=12, pady=(8,4))
        tk.Label(f, text=text, bg=BG_CARD, fg=TEXT_MID,
                 font=FONT_MONO_SM, wraplength=500,
                 justify="left").pack(anchor="w", padx=12, pady=(0,10))

    def _slbl(self, parent, text: str):
        tk.Label(parent, text=text, bg=BG_DARK, fg=TEXT_DIM,
                 font=FONT_MONO_XS).pack(anchor="w")

    def _mkbtn(self, parent, text: str, cmd, fg=CYAN, bg=BG_CARD):
        return tk.Button(
            parent, text=text, command=cmd, bg=bg, fg=fg,
            font=FONT_MONO_XS, relief="flat", cursor="hand2",
            activebackground=BORDER_LIT, activeforeground=WHITE)

    def _style_combo(self):
        s = ttk.Style()
        try: s.theme_use("clam")
        except Exception: pass
        s.configure("TCombobox",
                     fieldbackground=BG_INPUT, background=BG_INPUT,
                     foreground=CYAN_BRIGHT, arrowcolor=CYAN,
                     bordercolor=BORDER_LIT, lightcolor=BORDER_LIT,
                     darkcolor=BORDER_LIT, selectbackground=CYAN_DIM,
                     selectforeground=CYAN_BRIGHT)


# ═════════════════════════════════════════════════════════════════
#  ENTRY POINT
# ═════════════════════════════════════════════════════════════════
def main():
    root = tk.Tk()
    root.configure(bg=BG_DARK)

    missing = []
    if not REQUESTS_AVAILABLE:
        missing.append("requests  →  pip install requests")
    if not PIL_AVAILABLE:
        missing.append("Pillow    →  pip install pillow")
    if missing:
        messagebox.showwarning("Missing Packages",
                               "Install:\n\n" + "\n".join(missing))

    app = SightPointApp(root)
    root.protocol("WM_DELETE_WINDOW", root.destroy)
    root.mainloop()


if __name__ == "__main__":
    main()