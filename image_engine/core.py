"""
image_engine/core.py — Deep Analysis Orchestrator
════════════════════════════════════════════════════
Runs every enabled module in parallel, feeds results back as each one
completes, and combines everything (including the main Gemini
geolocation result) into a single weighted regional consensus — the
"Conflict Resolver" described in the original design.

school_uniforms is intentionally absent from MODULE_NAMES — see
image_engine/__init__.py for why. If a settings file still lists it in
deep_analysis_modules (e.g. an old config), it's silently skipped here
since it simply won't be found on the `modules` package.
"""

import threading
import time

from . import modules

MODULE_NAMES = [
    "electoral_signage",
    "retail_footprint",
    "plate_forensics",
    "grid_analysis",
    "screen_branding",
    "bicycle_analysis",
    "tree_phenology",
    "utility_billing",
    "building_codes",
    "cloud_analysis",
    "sensor_analysis",
    "tower_analysis",
    "graffiti_analysis",
    "phenology_comprehensive",
    "mounting_forensics",
]


def run_deep_analysis(image_path: str, geolocation_result: dict,
                      on_result_cb=None, on_complete_cb=None,
                      enabled_modules: list = None, timeout: int = 60) -> dict:
    """
    Run every enabled deep-analysis module on `image_path` in parallel.

    Args:
        image_path:         path to the image being analysed
        geolocation_result: the dict returned by the main Gemini
                            geolocation call (used as context by some
                            modules, and combined into the consensus)
        on_result_cb:       called as (module_name, result_dict) each
                            time a module finishes — for live UI updates
        on_complete_cb:     called once as (full_results_dict) when
                            every module has finished or timed out
        enabled_modules:    list of module name strings to run; if None,
                            reads options.get_option("deep_analysis_modules")
        timeout:            per-run join timeout in seconds (not per
                            module — the whole batch gets this budget)

    Returns:
        dict with keys:
            "modules":  { module_name: result_dict, ... }
            "consensus": aggregated region-vote consensus dict
    """
    if enabled_modules is None:
        try:
            import options
            enabled_modules = options.get_option(
                "deep_analysis_modules", MODULE_NAMES)
        except Exception:
            enabled_modules = MODULE_NAMES

    results = {}
    lock = threading.Lock()
    threads = []
    start = time.time()

    def _run_one(name):
        module = getattr(modules, name, None)
        if module is None:
            # Silently skip unknown names (e.g. a legacy
            # "school_uniforms" entry in an old settings file).
            return
        try:
            result = module.analyze(image_path, geolocation_result)
        except Exception as exc:
            result = {"detected": False, "region_votes": {},
                      "confidence": 0.0, "error": str(exc)}
        with lock:
            results[name] = result
        if on_result_cb:
            try:
                on_result_cb(name, result)
            except Exception:
                pass   # a UI callback failing must never kill the run

    for name in enabled_modules:
        t = threading.Thread(target=_run_one, args=(name,), daemon=True)
        threads.append(t)
        t.start()

    # Give the whole batch `timeout` seconds total, not per-thread —
    # join() with a shrinking budget so slow stragglers don't each
    # individually consume the full timeout.
    for t in threads:
        remaining = max(0.0, timeout - (time.time() - start))
        t.join(remaining)

    consensus = resolve_conflicts(geolocation_result, results)
    full = {"modules": results, "consensus": consensus}

    if on_complete_cb:
        try:
            on_complete_cb(full)
        except Exception:
            pass

    return full


def resolve_conflicts(geolocation_result: dict, module_results: dict) -> dict:
    """
    Combine the main Gemini geolocation's country/city with every
    module's region_votes into one weighted consensus dict:

        { region_name: combined_score }

    The main geolocation result is given a strong baseline vote
    (weighted by its own confidence) so 15 weak module signals can't
    outvote a single high-confidence primary analysis; they can only
    reinforce or gently contest it.
    """
    consensus = {}

    # Baseline vote from the primary Gemini analysis
    primary_conf = float(geolocation_result.get("confidence", 50)) / 100.0
    for field in ("country", "city"):
        val = geolocation_result.get(field)
        if val:
            consensus[val] = consensus.get(val, 0.0) + primary_conf

    contributing = []
    for name, result in module_results.items():
        votes = result.get("region_votes", {}) if isinstance(result, dict) else {}
        if votes:
            contributing.append(name)
        for region, score in votes.items():
            try:
                consensus[region] = consensus.get(region, 0.0) + float(score)
            except (TypeError, ValueError):
                continue

    ranked = sorted(consensus.items(), key=lambda kv: kv[1], reverse=True)

    return {
        "ranked_regions": ranked,
        "top_region": ranked[0][0] if ranked else None,
        "top_score": round(ranked[0][1], 2) if ranked else 0.0,
        "modules_contributing": contributing,
        "modules_run": len(module_results),
    }
