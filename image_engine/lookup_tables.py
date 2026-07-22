"""
image_engine/lookup_tables.py — Regional Reference Data
══════════════════════════════════════════════════════════
Centralised lookup tables used by the deep-analysis modules to turn
"Gemini spotted X" into "X is associated with region Y".

IMPORTANT — these are starter/example tables, not exhaustive real
databases
──────────────────────────────────────────────────────────────────
None of these are claimed to be complete or authoritative. They're
small, clearly-labelled seed sets covering common/obvious cases so the
modules are useful out of the box, and are meant to be extended by
whoever deploys this — add entries as you encounter them. Do not treat
any list here as exhaustive or ship it as if it were a verified
official database; several categories below (electoral candidates,
building codes) are genuinely regional and time-sensitive, and the
correct long-term approach is a properly sourced, regularly-updated
dataset rather than what's hardcoded here.

No individual-identifying databases (specific schools, specific
camera-sensor fingerprints, specific graffiti artists) are included
here — see image_engine/__init__.py for why those three module
categories were narrowed or excluded entirely.
"""

# ─────────────────────────────────────────────────────────────────
#  ELECTORAL — political parties by country (campaign posters/signage
#  are public political speech at public elections; this only maps
#  party *names*, not individual private citizens)
# ─────────────────────────────────────────────────────────────────
ELECTORAL_PARTIES_DB = {
    "Conservative Party":      {"regions": ["United Kingdom"]},
    "Labour Party":            {"regions": ["United Kingdom"]},
    "Liberal Democrats":       {"regions": ["United Kingdom"]},
    "Scottish National Party": {"regions": ["Scotland", "United Kingdom"]},
    "Democratic Party":        {"regions": ["United States"]},
    "Republican Party":        {"regions": ["United States"]},
    "Christian Democratic Union": {"regions": ["Germany"]},
    "Social Democratic Party": {"regions": ["Germany"]},
    "Fine Gael":               {"regions": ["Ireland"]},
    "Fianna Fáil":             {"regions": ["Ireland"]},
}

# ─────────────────────────────────────────────────────────────────
#  RETAIL — chains strongly associated with one country/region
# ─────────────────────────────────────────────────────────────────
RETAIL_CHAINS_DB = {
    "Tesco":            {"regions": ["United Kingdom", "Ireland"]},
    "Sainsbury's":      {"regions": ["United Kingdom"]},
    "Aldi":             {"regions": ["Germany", "United Kingdom", "United States"]},
    "Lidl":             {"regions": ["Germany", "United Kingdom", "Europe"]},
    "Target":           {"regions": ["United States"]},
    "Walmart":          {"regions": ["United States"]},
    "Walgreens":        {"regions": ["United States"]},
    "Boots":            {"regions": ["United Kingdom"]},
    "Coles":            {"regions": ["Australia"]},
    "Woolworths":       {"regions": ["Australia"]},
    "Loblaws":          {"regions": ["Canada"]},
    "Carrefour":        {"regions": ["France"]},
    "7-Eleven":         {"regions": ["United States", "Japan", "Thailand"]},
    "Lawson":           {"regions": ["Japan"]},
    "FamilyMart":       {"regions": ["Japan", "Taiwan"]},
}

# ─────────────────────────────────────────────────────────────────
#  UTILITY COMPANIES — visible branding on meters, vans, manhole
#  covers, substations etc. (branding/infrastructure only — never
#  account numbers or billing data)
# ─────────────────────────────────────────────────────────────────
UTILITY_COMPANIES_DB = {
    "National Grid":    {"regions": ["United Kingdom"]},
    "Thames Water":     {"regions": ["United Kingdom", "London"]},
    "Scottish Power":   {"regions": ["Scotland", "United Kingdom"]},
    "E.ON":             {"regions": ["Germany", "United Kingdom"]},
    "EDF Energy":       {"regions": ["France", "United Kingdom"]},
    "Con Edison":       {"regions": ["United States", "New York"]},
    "PG&E":             {"regions": ["United States", "California"]},
    "Hydro One":        {"regions": ["Canada", "Ontario"]},
}

# ─────────────────────────────────────────────────────────────────
#  BUILDING CODE / CONSTRUCTION CONVENTIONS — broad regional signals
#  (roofing pitch, brick bonding pattern, window styles etc.)
# ─────────────────────────────────────────────────────────────────
BUILDING_CONVENTIONS_DB = {
    "steep_slate_roof_terrace":     {"regions": ["United Kingdom", "Ireland"]},
    "clapboard_siding":              {"regions": ["United States", "Canada", "New England"]},
    "stucco_flat_roof":               {"regions": ["Mediterranean", "Southern Europe", "Latin America"]},
    "timber_frame_alpine":            {"regions": ["Switzerland", "Austria", "Bavaria"]},
    "red_brick_victorian_terrace":    {"regions": ["United Kingdom"]},
    "raised_stilt_house":             {"regions": ["Southeast Asia", "Louisiana"]},
    "concrete_block_tropical":        {"regions": ["Caribbean", "Southeast Asia"]},
}

# ─────────────────────────────────────────────────────────────────
#  TREE / VEGETATION — species with a narrow native or common
#  cultivated range, useful for regional (and seasonal) narrowing
# ─────────────────────────────────────────────────────────────────
TREE_SPECIES_DB = {
    "Coast Redwood":       {"regions": ["California", "United States (West Coast)"]},
    "Silver Birch":        {"regions": ["Northern Europe", "United Kingdom", "Scandinavia"]},
    "Baobab":              {"regions": ["Sub-Saharan Africa", "Madagascar"]},
    "Joshua Tree":         {"regions": ["Mojave Desert", "United States (Southwest)"]},
    "Cherry Blossom (Sakura)": {"regions": ["Japan", "Korea"]},
    "Eucalyptus":          {"regions": ["Australia"]},
    "Palmetto":            {"regions": ["Florida", "Southeastern United States"]},
    "Monkey Puzzle Tree":  {"regions": ["Chile", "Argentina"]},
    "Olive Tree":          {"regions": ["Mediterranean", "Southern Europe"]},
}

# ─────────────────────────────────────────────────────────────────
#  TELECOM TOWER / MAST DESIGN — mounting hardware and mast style
#  conventions vary by carrier standard and country
# ─────────────────────────────────────────────────────────────────
TOWER_STANDARDS_DB = {
    "lattice_triangular_uk":   {"regions": ["United Kingdom"]},
    "monopole_us_carrier":     {"regions": ["United States"]},
    "guyed_mast_scandinavia":  {"regions": ["Scandinavia", "Northern Europe"]},
    "concrete_pole_japan":     {"regions": ["Japan"]},
    "camouflaged_tree_pole":   {"regions": ["United States", "United Kingdom"]},
}


def lookup_regions(db: dict, key: str) -> list:
    """Small helper — case-insensitive fuzzy-ish lookup across a DB."""
    if key in db:
        return db[key].get("regions", [])
    key_lower = key.lower()
    for name, entry in db.items():
        if name.lower() == key_lower:
            return entry.get("regions", [])
    return []
