"""Business-As-Usual (BAU) fleet baseline evaluation engine.

Implements the status-quo, un-optimized operations evaluator for NexFleet:
- Calculates status-quo fuel consumption, fuel expenditure, OPEX, and charter time.
- Evaluates standalone regulatory liabilities across all four regimes (CII, EU ETS, NZF, FuelEU).
- Enforces strict standalone FuelEU penalty accounting without fleet pooling or banking.
- Determines official IMO CII letter ratings ('A' through 'E') per IMO MEPC.336(76)-339(76).
- Establishes the authoritative benchmark against which candidate Pareto plans are compared.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any

from nexfleet.fleet.model import option_menu_for
from nexfleet.optimization.compliance_cost import (
    FuelEuYearInput,
    compute_fueleu_ledger,
)
from nexfleet.optimization.constraints import demand_shortfall_penalty
from nexfleet.optimization.costs import CostBreakdown
from nexfleet.optimization.fuel_model import FuelModel
from nexfleet.optimization.genome import Genome, VesselYearGene
from nexfleet.optimization.objective import (
    _DEFAULT_FUEL_MODEL,
    ObjectiveResult,
    _combine,
    _slot_local,
    vessel_year_facts,
)

#: Standard IMO Tank-to-Wake (TtW) carbon emission factors CF (tCO2 / tFuel)
#: per IMO Resolutions MEPC.245(66) and MEPC.308(73).
_IMO_CF_FACTORS: dict[str, float] = {
    "hfo_scrubber": 3.114,
    "vlsfo": 3.151,
    "mgo": 3.206,
    "lng": 2.750,
    "b30_blend": 2.206,   # 70% VLSFO + 30% zero-rated biofuel component
    "methanol": 1.375,
}

#: IMO MEPC.337(76) Reference Line parameters: CII_ref = a * Capacity^(-c)
#: For Band A (Containership), Band B (Bulk Carrier), Band C (General Cargo).
_CII_REF_PARAMS: dict[str, tuple[float, float]] = {
    "A": (1984.0, 0.489),     # Containership: a=1984, c=0.489
    "B": (4745.0, 0.622),     # Bulk Carrier: a=4745, c=0.622
    "C": (31948.0, 0.742),    # General Cargo: a=31948, c=0.742
}

#: IMO MEPC.339(76) Rating Boundaries (A, B, C, D, E) as ratio of Attained / Required CII.
#: Boundary thresholds: d1 (superior 'A'), d2 ('B'), d3 ('C'), d4 ('D'), above d4 ('E').
_CII_BOUNDARY_RATIOS: dict[str, tuple[float, float, float, float]] = {
    "A": (0.82, 0.93, 1.08, 1.19),  # Containership
    "B": (0.86, 0.94, 1.06, 1.18),  # Bulk Carrier
    "C": (0.83, 0.94, 1.06, 1.19),  # General Cargo / Feeder
}


@dataclass(frozen=True)
class BaselineAssignment:
    """Status-quo operational assignment for one vessel in one year."""

    vessel_id: str
    year: int
    route_id: str
    speed_knots: float
    fuel_id: str
    shore_power: bool = False


@dataclass(frozen=True)
class BaselineResult:
    """Comprehensive evaluation of the fleet's status-quo baseline plan."""

    objective: ObjectiveResult
    total_fuel_tonnes: float
    total_ghg_tco2e: float
    cii_ratings: dict[tuple[str, int], str]  # (vessel_id, year) -> rating ("A".."E" or "EXEMPT")
    vessel_breakdown: list[dict[str, Any]] = field(default_factory=list)


def build_default_baseline_assignments(fleet: dict[str, Any]) -> list[BaselineAssignment]:
    """Construct standard Business-As-Usual (BAU) operational assignments.

    Status quo assumptions for un-optimized fleet operations:
    - Route: Vessel's fixed default route (`vessel["default_route"]`).
    - Speed: Design speed of the vessel's band (`design_speed_knots`).
    - Fuel: Primary conventional fossil bunker from engine compatibility matrix
      ('hfo_scrubber' for scrubber-fitted, 'vlsfo' for dual-fuel/others).
    - Shore Power: Disabled (cold-ironing is an elective abatement in BAU).
    """
    assignments: list[BaselineAssignment] = []
    horizon_years = fleet.get("horizon_years", [2026, 2027, 2028, 2029, 2030])
    vessels = fleet.get("vessels", [])
    class_defaults = fleet.get("vessel_class_defaults", {})
    compat_matrix = fleet.get("engine_fuel_compatibility", {}).get("matrix", {})

    for vessel in vessels:
        vessel_id = vessel["vessel_id"]
        band = vessel["band"]
        engine_type = vessel.get("engine_type", "conventional_hfo_scrubber")
        default_route = vessel["default_route"]
        design_speed = class_defaults[band]["design_speed_knots"]

        compatible_fuels = compat_matrix.get(engine_type, ["vlsfo"])
        status_quo_fuel = compatible_fuels[0]

        for year in horizon_years:
            assignments.append(
                BaselineAssignment(
                    vessel_id=vessel_id,
                    year=year,
                    route_id=default_route,
                    speed_knots=design_speed,
                    fuel_id=status_quo_fuel,
                    shore_power=False,
                )
            )

    return assignments


def compute_cii_rating(
    vessel_band: str,
    dwt_tonnes: float,
    distance_nm: float,
    fuel_tonnes: float,
    fuel_id: str,
    year: int,
    regulations: dict[str, Any],
    is_international: bool = True,
    gross_tonnage: float | None = None,
) -> str:
    """Calculate the official IMO CII letter rating ('A', 'B', 'C', 'D', 'E', or 'EXEMPT').

    Computes:
    1. Attained Annual Operational CII (AER in gCO2 / (dwt * nm)).
    2. Reference Line CII_ref per IMO MEPC.337(76).
    3. Required CII per IMO MEPC.338(76) reduction factors (Z-factors).
    4. Rating boundaries per IMO MEPC.339(76).
    """
    gt_threshold = regulations.get("regimes", {}).get("cii", {}).get("gt_threshold", 5000)
    if gross_tonnage is not None and gross_tonnage < gt_threshold:
        return "EXEMPT"
    if not is_international:
        return "EXEMPT"
    if dwt_tonnes <= 0 or distance_nm <= 0 or fuel_tonnes <= 0:
        return "EXEMPT"

    # Attained CII (AER) in gCO2 / (dwt * nm)
    cf = _IMO_CF_FACTORS.get(fuel_id, 3.151)
    co2_tonnes = fuel_tonnes * cf
    co2_grams = co2_tonnes * 1_000_000.0
    transport_work = dwt_tonnes * distance_nm
    attained_cii = co2_grams / transport_work

    # Reference Line CII_ref
    a, c = _CII_REF_PARAMS.get(vessel_band, (1984.0, 0.489))
    cii_ref = a * (dwt_tonnes ** (-c))

    # Required CII for the given year
    z_factors = regulations.get("regimes", {}).get("cii", {}).get("z_factors_percent", {})
    z_percent = float(z_factors.get(str(year), 11.0))
    cii_required = cii_ref * (1.0 - z_percent / 100.0)

    if cii_required <= 0:
        return "C"

    # Boundary comparison
    ratio = attained_cii / cii_required
    b_a, b_b, b_c, b_d = _CII_BOUNDARY_RATIOS.get(vessel_band, (0.83, 0.94, 1.06, 1.19))

    if ratio <= b_a:
        return "A"
    elif ratio <= b_b:
        return "B"
    elif ratio <= b_c:
        return "C"
    elif ratio <= b_d:
        return "D"
    else:
        return "E"


def baseline_to_genome(fleet: dict[str, Any], assignments: list[BaselineAssignment]) -> Genome:
    """Convert a list of BaselineAssignments into a solver-compatible Genome.

    Finds the nearest discrete speed band index matching each assignment's speed_knots.
    Ensures borrow_election=False and pool_opt_in=False for status-quo baseline behavior.
    """
    vessels_by_id = {v["vessel_id"]: v for v in fleet["vessels"]}
    genome: list[VesselYearGene] = []

    for item in assignments:
        vessel = vessels_by_id[item.vessel_id]
        menu = option_menu_for(vessel, fleet, item.year)
        # Find closest speed band index
        closest_idx = min(
            range(len(menu.speed_bands_knots)),
            key=lambda idx: abs(menu.speed_bands_knots[idx] - item.speed_knots),
        )
        genome.append(
            VesselYearGene(
                vessel_id=item.vessel_id,
                year=item.year,
                route_id=item.route_id,
                speed_band_index=closest_idx,
                fuel_id=item.fuel_id,
                shore_power=item.shore_power,
                borrow_election=False,
                pool_opt_in=False,
            )
        )

    return genome


def evaluate_baseline_plan(
    fleet: dict[str, Any],
    baseline_assignments: list[BaselineAssignment],
    regulations: dict[str, Any],
    prices: dict[str, Any],
    fuel_model: FuelModel | None = None,
    fouling_age_days: float | None = None,
    sea_state_index: float | None = None,
) -> BaselineResult:
    """Evaluate the Business-As-Usual (status quo) fleet operational plan.

    Computes:
    - Bunker fuel consumption (tonnes) and fuel purchase cost (USD).
    - Fixed vessel OPEX and voyage charter time cost (USD).
    - EU ETS carbon compliance cost (USD).
    - Standalone FuelEU Maritime penalties (USD) with zero pooling and zero borrowing.
    - IMO CII annual ratings ('A' through 'E' or 'EXEMPT').
    - Route transport capacity demand shortfall penalties (USD).
    """
    fuel_model = fuel_model or _DEFAULT_FUEL_MODEL
    vessels_by_id = {v["vessel_id"]: v for v in fleet["vessels"]}
    horizon_years = fleet.get("horizon_years", [2026, 2027, 2028, 2029, 2030])

    # Group assignments by vessel and sort chronologically
    assignments_by_vessel: dict[str, list[BaselineAssignment]] = defaultdict(list)
    for assignment in baseline_assignments:
        assignments_by_vessel[assignment.vessel_id].append(assignment)
    for a_list in assignments_by_vessel.values():
        a_list.sort(key=lambda a: a.year)

    fuel_costs: list[CostBreakdown] = []
    opex_costs: list[CostBreakdown] = []
    time_costs: list[CostBreakdown] = []
    cii_costs: list[CostBreakdown] = []
    eu_ets_costs: list[CostBreakdown] = []
    nzf_costs: list[CostBreakdown] = []

    context: dict[tuple[str, int], dict[str, Any]] = {}
    dwt_by_route_year: dict[tuple[str, int], float] = defaultdict(float)
    cii_ratings: dict[tuple[str, int], str] = {}
    vessel_breakdown: list[dict[str, Any]] = []

    total_fuel_tonnes = 0.0
    total_ghg_tco2e = 0.0

    # First Pass: Slot-local physical, economic, and single-year regulatory figures
    for vessel_id, assignments in assignments_by_vessel.items():
        vessel = vessels_by_id[vessel_id]
        band = vessel["band"]
        band_defaults = fleet["vessel_class_defaults"][band]
        gross_tonnage = band_defaults["gross_tonnage"]
        dwt_tonnes = band_defaults["dwt_tonnes"]

        for item in assignments:
            local = _slot_local(
                item,
                vessel,
                fleet,
                regulations,
                prices,
                fuel_model,
                fouling_age_days=fouling_age_days,
                sea_state_index=sea_state_index,
            )
            facts = vessel_year_facts(
                item,
                vessel,
                fleet,
                regulations,
                fuel_model,
                fouling_age_days=fouling_age_days,
                sea_state_index=sea_state_index,
            )

            fuel_costs.append(local.fuel)
            opex_costs.append(local.opex)
            time_costs.append(local.time)
            cii_costs.append(local.cii)
            eu_ets_costs.append(local.eu_ets)
            nzf_costs.append(local.nzf)

            # Route distance and international status for CII
            route = fleet["routes"][item.route_id]
            distance_nm = route["distance_nm"]
            is_international = route.get("voyage_pattern", {}).get("is_international", True)

            rating = compute_cii_rating(
                vessel_band=band,
                dwt_tonnes=dwt_tonnes,
                distance_nm=distance_nm,
                fuel_tonnes=facts.tonnes,
                fuel_id=item.fuel_id,
                year=item.year,
                regulations=regulations,
                is_international=is_international,
                gross_tonnage=gross_tonnage,
            )
            cii_ratings[(vessel_id, item.year)] = rating

            # GHG emissions in tCO2e (energy_mj * intensity_gco2e_per_mj / 1e6)
            ghg_tco2e = (facts.energy_mj * facts.actual_ghg_intensity_gco2e_per_mj) / 1_000_000.0
            total_fuel_tonnes += facts.tonnes
            total_ghg_tco2e += ghg_tco2e

            context[(vessel_id, item.year)] = {
                "assignment": item,
                "facts": facts,
                "local": local,
                "ghg_tco2e": ghg_tco2e,
                "cii_rating": rating,
            }
            dwt_by_route_year[(item.route_id, item.year)] += local.dwt_tonnes

    # Second Pass: Standalone FuelEU Maritime Ledger (NO pooling, NO borrowing)
    fuel_eu_costs: list[CostBreakdown] = []
    fueleu_penalty_by_slot: dict[tuple[str, int], float] = {}
    eur_to_usd_rate = prices["carbon_allowances"]["eu_ets_eua"]["eur_to_usd_rate"]

    for vessel_id, assignments in assignments_by_vessel.items():
        year_inputs = [
            FuelEuYearInput(
                year=item.year,
                actual_ghg_intensity_gco2e_per_mj=context[(vessel_id, item.year)]["facts"].actual_ghg_intensity_gco2e_per_mj,
                energy_used_mj=context[(vessel_id, item.year)]["facts"].regulated_energy_mj,
                borrow_election=False,  # Status quo: no borrowing
                pooled=False,           # Status quo: no pooling
            )
            for item in assignments
        ]
        ledger_results = compute_fueleu_ledger(regulations["regimes"]["fuel_eu"], year_inputs, eur_to_usd_rate)
        for res in ledger_results:
            key = (vessel_id, res.year)
            fuel_eu_costs.append(res.cost)
            fueleu_penalty_by_slot[key] = res.cost.amount_usd

    # Route Demand Shortfall Penalties
    demand_costs = [
        demand_shortfall_penalty(fleet, route_id, dwt_by_route_year.get((route_id, year), 0.0))
        for year in horizon_years
        for route_id in fleet["routes"]
    ]

    # Aggregate All Costs
    compliance_costs = {
        "cii": _combine(cii_costs, "cii"),
        "eu_ets": _combine(eu_ets_costs, "eu_ets"),
        "nzf": _combine(nzf_costs, "nzf"),
        "fuel_eu": _combine(fuel_eu_costs, "fuel_eu"),
    }
    fuel_agg = _combine(fuel_costs, "fuel")
    opex_agg = _combine(opex_costs, "opex")
    time_agg = _combine(time_costs, "time")
    demand_agg = _combine(demand_costs, "demand")

    total_usd = (
        fuel_agg.amount_usd
        + opex_agg.amount_usd
        + time_agg.amount_usd
        + demand_agg.amount_usd
        + sum(c.amount_usd for c in compliance_costs.values())
    )

    objective = ObjectiveResult(
        total_usd=total_usd,
        fuel_cost=fuel_agg,
        opex_cost=opex_agg,
        time_cost=time_agg,
        compliance_costs=compliance_costs,
        demand_penalty=demand_agg,
    )

    # Build detailed per-vessel-year breakdown records
    for vessel_id, assignments in assignments_by_vessel.items():
        vessel = vessels_by_id[vessel_id]
        band = vessel["band"]
        for item in assignments:
            key = (vessel_id, item.year)
            ctx = context[key]
            local = ctx["local"]
            facts = ctx["facts"]
            fueleu_pen = fueleu_penalty_by_slot.get(key, 0.0)

            v_total = (
                local.fuel.amount_usd
                + local.opex.amount_usd
                + local.time.amount_usd
                + local.eu_ets.amount_usd
                + local.nzf.amount_usd
                + fueleu_pen
            )

            vessel_breakdown.append({
                "vessel_id": vessel_id,
                "year": item.year,
                "band": band,
                "route_id": item.route_id,
                "speed_knots": item.speed_knots,
                "fuel_id": item.fuel_id,
                "shore_power": item.shore_power,
                "fuel_tonnes": facts.tonnes,
                "energy_mj": facts.energy_mj,
                "ghg_tco2e": ctx["ghg_tco2e"],
                "fuel_cost_usd": local.fuel.amount_usd,
                "opex_cost_usd": local.opex.amount_usd,
                "time_cost_usd": local.time.amount_usd,
                "eu_ets_cost_usd": local.eu_ets.amount_usd,
                "fueleu_penalty_usd": fueleu_pen,
                "cii_rating": ctx["cii_rating"],
                "total_cost_usd": v_total,
            })

    return BaselineResult(
        objective=objective,
        total_fuel_tonnes=total_fuel_tonnes,
        total_ghg_tco2e=total_ghg_tco2e,
        cii_ratings=cii_ratings,
        vessel_breakdown=vessel_breakdown,
    )
