"""
image_engine/modules/__init__.py
═══════════════════════════════════
Imports every analysis module so core.py can do
`getattr(modules, module_name, None)` to dispatch by name from the
options.deep_analysis_modules list.

15 of the original 16 planned modules are implemented here.
`school_uniforms` was not built at all (see image_engine/__init__.py
for why) — referencing it in deep_analysis_modules is harmless, core.py
just skips names it can't find.
"""

from . import electoral_signage
from . import retail_footprint
from . import plate_forensics
from . import grid_analysis
from . import screen_branding
from . import bicycle_analysis
from . import tree_phenology
from . import utility_billing
from . import building_codes
from . import cloud_analysis
from . import sensor_analysis
from . import tower_analysis
from . import graffiti_analysis
from . import phenology_comprehensive
from . import mounting_forensics

__all__ = [
    "electoral_signage", "retail_footprint", "plate_forensics",
    "grid_analysis", "screen_branding", "bicycle_analysis",
    "tree_phenology", "utility_billing", "building_codes",
    "cloud_analysis", "sensor_analysis", "tower_analysis",
    "graffiti_analysis", "phenology_comprehensive", "mounting_forensics",
]
