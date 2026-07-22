"""
image_engine — Deep Analysis Powerhouse
════════════════════════════════════════
Optional subsystem for SightPoint AI. Completely separate from cogs/ —
this is a deeper, slower, opt-in forensic layer that only runs when
"Deep Analysis" is switched on in Options.

Activates when:
    options.get_option("deep_analysis_enabled") is True

Runs a parallel set of specialised forensic analysers, each looking
for a different category of visible evidence (signage, infrastructure,
vegetation, retail chains, etc.) and voting on which region/country the
evidence points to. Results are combined with the main Gemini
geolocation call into a single weighted consensus.

Note on scope
─────────────
Three modules described in early planning were deliberately left out
or narrowed before this was built:

  • school_uniforms — NOT built. A uniform→specific-school lookup is
    a child-location tool regardless of framing, so it doesn't exist
    here at all.
  • sensor_analysis — narrowed to EXIF camera make/model reading only
    (which the core app already surfaces). No sensor-noise / PRNU
    fingerprint matching is implemented — that's a real technique for
    deanonymising photographers across supposedly unrelated photos,
    and this project doesn't build that.
  • graffiti_analysis — narrowed to "which cities/regions commonly
    show this tagging style", with no lookup that resolves a tag to a
    specific named artist. Most graffiti artists are anonymous by
    necessity (legal exposure), and a name-matching tool would be a
    deanonymisation capability aimed at that anonymity.

Everything else runs as originally scoped: reading visible public
signage, infrastructure, and environmental evidence for broad regional
narrowing — the same category of analysis the main Gemini prompt
already does, just with dedicated modules and lookup tables per topic.

Usage
─────
    import image_engine

    image_engine.run_deep_analysis(
        image_path, geolocation_result,
        on_result_cb=lambda name, result: ...,
        on_complete_cb=lambda all_results: ...,
    )
"""

from .core import run_deep_analysis, MODULE_NAMES

__all__ = ["run_deep_analysis", "MODULE_NAMES"]
