"""Fleet model (Task 2R component 2): a synthetic 10-vessel Bharat-Line-style
fleet, its candidate routes, vessel-fuel compatibility, and decision-variable
option menus. Consumes `nexfleet.compliance.scope_gating`'s types directly
rather than redefining them — see `model.py`.
"""

from nexfleet.fleet.baseline import (
    BaselineAssignment,
    BaselineResult,
    baseline_to_genome,
    build_default_baseline_assignments,
    compute_cii_rating,
    evaluate_baseline_plan,
)
from nexfleet.fleet.loader import load_fleet, load_prices
from nexfleet.fleet.model import OptionMenu, option_menu_for, speed_bands_knots, vessel_spec

__all__ = [
    "BaselineAssignment",
    "BaselineResult",
    "OptionMenu",
    "baseline_to_genome",
    "build_default_baseline_assignments",
    "compute_cii_rating",
    "evaluate_baseline_plan",
    "load_fleet",
    "load_prices",
    "option_menu_for",
    "speed_bands_knots",
    "vessel_spec",
]
