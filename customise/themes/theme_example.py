"""
theme_example.py — TEMPLATE for making your own SightPoint AI theme.
════════════════════════════════════════════════════════════════════
Copy this file to a new name inside customise/themes/, e.g.:

    customise/themes/my_theme.py

Then:
  1. Change NAME below to whatever you want it to show up as in the
     Theme dialog's preset list.
  2. Edit any of the colours/fonts in THEME. You don't have to fill in
     every single key — anything you leave out automatically falls
     back to the Cyber Dark default, so you can start small (just
     change BG_DARK and CYAN, say) and grow it from there.
  3. Save the file. Open the Theme dialog (⬡ SETTINGS ▾ → Theme) and
     your theme appears in the preset list immediately — no restart,
     no registration, nothing else to edit anywhere.

Colour values are standard hex strings, e.g. "#ff8800".
Font sizes are plain integers (point size).

What each key controls
───────────────────────
    BG_DARK        Main window background
    BG_PANEL       Header bar / section header backgrounds
    BG_CARD        Card/panel backgrounds (result cards, dialogs)
    BG_INPUT       Text entry / input field backgrounds
    BORDER         Normal (dim) border colour
    BORDER_LIT     Highlighted / hover border colour
    CYAN           Primary accent colour (buttons, active states)
    CYAN_BRIGHT    Brighter accent, used for hover states
    CYAN_DIM       Dim accent, used for selection highlights
    TEXT_BRIGHT    Brightest text (headings)
    TEXT_MID       Normal body text
    TEXT_DIM       Dimmer text (labels, captions)
    TEXT_FAINT     Faintest text (placeholders, disabled state)
    GREEN          Success / confirmation colour
    YELLOW         Warning colour
    RED_COL        Error colour
    PURPLE         Secondary highlight colour
    WHITE          Pure white text, used sparingly
    FONT_FAMILY    Font family name, e.g. "Courier New", "Consolas"
    FONT_SIZE_NORMAL   Base UI font size (point size, integer)
    FONT_SIZE_SMALL    Secondary text size
    FONT_SIZE_XS       Smallest label size

This example uses a deliberately loud neon green/pink combination so
it's obviously a demo — replace every value below with your own.
"""

NAME = "Example (copy me!)"

THEME = {
    "BG_DARK":      "#0a0014",
    "BG_PANEL":     "#12001e",
    "BG_CARD":      "#180028",
    "BG_INPUT":     "#160020",
    "BORDER":       "#3a0a4a",
    "BORDER_LIT":   "#6a1a80",
    "CYAN":         "#39ff14",
    "CYAN_BRIGHT":  "#8cff6b",
    "CYAN_DIM":     "#0f3a0a",
    "TEXT_BRIGHT":  "#ffffff",
    "TEXT_MID":     "#e0b0ff",
    "TEXT_DIM":     "#a070c0",
    "TEXT_FAINT":   "#4a2a5a",
    "GREEN":        "#39ff14",
    "YELLOW":       "#ffe600",
    "RED_COL":      "#ff2079",
    "PURPLE":       "#ff2079",
    "WHITE":        "#ffffff",
    "FONT_FAMILY":       "Courier New",
    "FONT_SIZE_NORMAL":  10,
    "FONT_SIZE_SMALL":   8,
    "FONT_SIZE_XS":      7,
}
