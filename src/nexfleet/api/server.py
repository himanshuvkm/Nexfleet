"""FastAPI server exposing live GA and QIEA optimization for NexFleet."""

from __future__ import annotations

import copy
import time
from typing import Any, Dict, List, Literal, Optional

from fastapi import FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from nexfleet.fleet.baseline import BaselineAssignment, build_default_baseline_assignments, evaluate_baseline_plan
from nexfleet.fleet.loader import load_fleet, load_prices
from nexfleet.optimization import qiea_solver, solver
from nexfleet.optimization.objective import evaluate
from nexfleet.optimization.qiea_solver import compute_plan_lifecycle_emissions
from nexfleet.optimization.solver import DEGENERATE_COST_TOLERANCE_USD
from nexfleet.optimization.sweep import _nzf_price_override
from nexfleet.regulatory.loader import load_scenarios
from nexfleet.regulatory.scenario_resolution import resolve_regulations_for_scenario

app = FastAPI(
    title="NexFleet Optimizer API",
    description="Live GA and QIEA fleet decarbonization solver API.",
    version="1.0.0",
)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class EstimateRequest(BaseModel):
    carbon_price_usd_per_tco2e: float = Field(default=175.0, ge=0.0)
    cargo_demand_multiplier: float = Field(default=1.0, gt=0.0)
    scenario_id: Optional[str] = Field(default="approved_text")
    vessel_id: Optional[str] = None
    fuel_id: Optional[str] = None


class CompareFuelsRequest(BaseModel):
    vessel_id: str = Field(default="A1")
    carbon_price_usd_per_tco2e: float = Field(default=175.0, ge=0.0)
    cargo_demand_multiplier: float = Field(default=1.0, gt=0.0)
    scenario_id: Optional[str] = Field(default="approved_text")


class OptimizeRequest(BaseModel):
    carbon_price_usd_per_tco2e: float = Field(default=175.0, ge=0.0)
    cargo_demand_multiplier: float = Field(default=1.0, gt=0.0)
    run_both: bool = Field(default=True)
    optimizer: Literal["ga", "qiea", "both"] = Field(default="both")
    population_size: int = Field(default=30, ge=5, le=200)
    generations: int = Field(default=30, ge=1, le=200)
    seed: int = Field(default=0)
    scenario_id: Optional[str] = Field(default="approved_text")
    vessel_id: Optional[str] = None
    fuel_id: Optional[str] = None


def _check_fuel_compatibility(fleet: Dict[str, Any], vessel_id: Optional[str], fuel_id: Optional[str]) -> None:
    """Validate that fuel_id is compatible with vessel_id's engine type."""
    if not vessel_id or not fuel_id:
        return

    vessels = fleet.get("vessels", [])
    matched_vessel = next((v for v in vessels if v.get("vessel_id") == vessel_id), None)
    if not matched_vessel:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Vessel '{vessel_id}' was not found in the fleet catalog.",
        )

    engine_type = matched_vessel.get("engine_type", "")
    matrix = fleet.get("engine_fuel_compatibility", {}).get("matrix", {})
    compatible_fuels = matrix.get(engine_type, [])

    if fuel_id not in compatible_fuels:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="This fuel is not compatible with the selected vessel.",
        )


@app.get("/health")
def health_check() -> Dict[str, str]:
    """Health check endpoint."""
    return {"status": "healthy", "service": "nexfleet-optimizer"}


@app.post("/api/estimate")
def estimate_plan(req: EstimateRequest) -> Dict[str, Any]:
    """Quick preliminary estimate using the fleet baseline model."""
    fleet = load_fleet()
    prices = load_prices()
    scenarios = load_scenarios()

    _check_fuel_compatibility(fleet, req.vessel_id, req.fuel_id)

    scenario_id = req.scenario_id or "approved_text"
    base_reg = resolve_regulations_for_scenario(scenario_id, scenarios=scenarios)
    regulations = _nzf_price_override(base_reg, req.carbon_price_usd_per_tco2e)

    fleet_adj = copy.deepcopy(fleet)
    if req.cargo_demand_multiplier != 1.0:
        for route in fleet_adj.get("routes", {}).values():
            if "min_capacity_dwt_required" in route:
                route["min_capacity_dwt_required"] = float(route["min_capacity_dwt_required"]) * req.cargo_demand_multiplier
            if "annual_cargo_demand_tonne_nm" in route:
                route["annual_cargo_demand_tonne_nm"] = float(route["annual_cargo_demand_tonne_nm"]) * req.cargo_demand_multiplier

    base_assignments = build_default_baseline_assignments(fleet_adj)
    base_eval = evaluate_baseline_plan(fleet_adj, base_assignments, regulations, prices)
    comp_usd = sum(c.amount_usd for c in base_eval.objective.compliance_costs.values())

    return {
        "status": "completed",
        "data_mode": "synthetic_estimate",
        "carbon_price_usd_per_tco2e": req.carbon_price_usd_per_tco2e,
        "cargo_demand_multiplier": req.cargo_demand_multiplier,
        "estimated_total_cost_usd": round(base_eval.objective.total_usd, 2),
        "estimated_fuel_tonnes": round(base_eval.total_fuel_tonnes, 2),
        "estimated_lifecycle_emissions_tco2e": round(base_eval.total_ghg_tco2e, 2),
        "estimated_compliance_cost_usd": round(comp_usd, 2),
        "cargo_fulfillment_percent": 100.0,
        "message": "Instant preliminary estimate computed using baseline status-quo model.",
    }


@app.post("/api/optimize")
def optimize_fleet(req: OptimizeRequest) -> Dict[str, Any]:
    """Run live GA and/or QIEA optimization on the fleet under user parameters."""
    fleet = load_fleet()
    prices = load_prices()
    scenarios = load_scenarios()

    _check_fuel_compatibility(fleet, req.vessel_id, req.fuel_id)

    scenario_id = req.scenario_id or "approved_text"
    base_reg = resolve_regulations_for_scenario(scenario_id, scenarios=scenarios)
    regulations = _nzf_price_override(base_reg, req.carbon_price_usd_per_tco2e)

    fleet_adj = copy.deepcopy(fleet)
    if req.cargo_demand_multiplier != 1.0:
        for route in fleet_adj.get("routes", {}).values():
            if "min_capacity_dwt_required" in route:
                route["min_capacity_dwt_required"] = float(route["min_capacity_dwt_required"]) * req.cargo_demand_multiplier
            if "annual_cargo_demand_tonne_nm" in route:
                route["annual_cargo_demand_tonne_nm"] = float(route["annual_cargo_demand_tonne_nm"]) * req.cargo_demand_multiplier

    # Compute baseline for comparison
    base_assignments = build_default_baseline_assignments(fleet_adj)
    base_eval = evaluate_baseline_plan(fleet_adj, base_assignments, regulations, prices)
    base_comp_usd = sum(c.amount_usd for c in base_eval.objective.compliance_costs.values())

    if req.optimizer in ("ga", "qiea"):
        effective_optimizer = req.optimizer
    else:
        effective_optimizer = "both"

    def _execute_optimizer(solver_name: str) -> Dict[str, Any]:
        t0 = time.perf_counter()
        try:
            if solver_name == "ga":
                res = solver.run_ga(
                    fleet_adj,
                    regulations,
                    prices,
                    seed=req.seed,
                    population_size=req.population_size,
                    n_generations=req.generations,
                )
            else:
                res = qiea_solver.run_qiea(
                    fleet_adj,
                    regulations,
                    prices,
                    seed=req.seed,
                    population_size=req.population_size,
                    n_generations=req.generations,
                )
            runtime = time.perf_counter() - t0
            breakdown = res.best_breakdown
            ghg_tco2e, fuel_tonnes = compute_plan_lifecycle_emissions(res.best_genome, fleet_adj, regulations)
            comp_cost = sum(c.amount_usd for c in breakdown.compliance_costs.values())
            is_feasible = breakdown.demand_penalty.amount_usd <= 1e-6

            # Compute cargo fulfillment %
            cargo_fulfillment = 100.0
            if not is_feasible:
                routes = fleet_adj.get("routes", {})
                horizon = len(fleet_adj.get("horizon_years", [2026, 2027, 2028, 2029, 2030]))
                total_required = sum(r.get("min_capacity_dwt_required", 0) for r in routes.values()) * horizon
                shortfall_dwt = breakdown.demand_penalty.amount_usd / 10000.0
                cargo_fulfillment = max(0.0, round((total_required - shortfall_dwt) / max(1.0, total_required) * 100.0, 1))

            config = [
                {
                    "vessel_id": gene.vessel_id,
                    "year": gene.year,
                    "route_id": gene.route_id,
                    "speed_band_index": gene.speed_band_index,
                    "fuel_id": gene.fuel_id,
                    "shore_power": gene.shore_power,
                    "pool_opt_in": gene.pool_opt_in,
                    "borrow_election": gene.borrow_election,
                }
                for gene in res.best_genome
            ]

            return {
                "available": True,
                "runtime_seconds": round(runtime, 3),
                "total_cost_usd": round(breakdown.total_usd, 2),
                "fuel_tonnes": round(fuel_tonnes, 2),
                "lifecycle_emissions_tco2e": round(ghg_tco2e, 2),
                "compliance_cost_usd": round(comp_cost, 2),
                "cargo_fulfillment_percent": cargo_fulfillment,
                "feasible": is_feasible,
                "generations_run": res.generations_run,
                "configuration": config,
                "error": None,
            }
        except Exception as err:
            runtime = time.perf_counter() - t0
            return {
                "available": False,
                "runtime_seconds": round(runtime, 3),
                "total_cost_usd": 0.0,
                "fuel_tonnes": 0.0,
                "lifecycle_emissions_tco2e": 0.0,
                "compliance_cost_usd": 0.0,
                "cargo_fulfillment_percent": 0.0,
                "feasible": False,
                "generations_run": 0,
                "configuration": [],
                "error": str(err),
            }

    ga_res = _execute_optimizer("ga") if effective_optimizer in ("ga", "both") else {
        "available": False,
        "runtime_seconds": 0.0,
        "total_cost_usd": 0.0,
        "fuel_tonnes": 0.0,
        "lifecycle_emissions_tco2e": 0.0,
        "compliance_cost_usd": 0.0,
        "feasible": False,
        "generations_run": 0,
        "configuration": [],
        "error": "GA was not selected for this run",
    }

    qiea_res = _execute_optimizer("qiea") if effective_optimizer in ("qiea", "both") else {
        "available": False,
        "runtime_seconds": 0.0,
        "total_cost_usd": 0.0,
        "fuel_tonnes": 0.0,
        "lifecycle_emissions_tco2e": 0.0,
        "compliance_cost_usd": 0.0,
        "feasible": False,
        "generations_run": 0,
        "configuration": [],
        "error": "QIEA was not selected for this run",
    }

    # Comparison & winner determination
    cost_diff = 0.0
    cost_diff_pct = 0.0
    emiss_diff = 0.0
    runtime_diff = 0.0
    winner_reason = ""
    best_opt = "equivalent"
    best_plan = None

    if ga_res["available"] and qiea_res["available"]:
        cost_diff = round(ga_res["total_cost_usd"] - qiea_res["total_cost_usd"], 2)
        baseline_ref = max(ga_res["total_cost_usd"], 1.0)
        cost_diff_pct = round((abs(cost_diff) / baseline_ref) * 100.0, 2)
        emiss_diff = round(ga_res["lifecycle_emissions_tco2e"] - qiea_res["lifecycle_emissions_tco2e"], 2)
        runtime_diff = round(ga_res["runtime_seconds"] - qiea_res["runtime_seconds"], 3)

        # Check feasibility and costs
        if ga_res["feasible"] and not qiea_res["feasible"]:
            best_opt = "ga"
            best_plan = ga_res
            winner_reason = "GA found a feasible fleet assignment satisfying all cargo demand constraints, whereas QIEA violated demand bounds."
        elif qiea_res["feasible"] and not ga_res["feasible"]:
            best_opt = "qiea"
            best_plan = qiea_res
            winner_reason = "QIEA found a feasible fleet assignment satisfying all cargo demand constraints, whereas GA violated demand bounds."
        elif abs(cost_diff) <= DEGENERATE_COST_TOLERANCE_USD or cost_diff_pct < 0.01:
            best_opt = "equivalent"
            # Prefer whichever is faster or has lower emissions
            best_plan = ga_res if ga_res["runtime_seconds"] <= qiea_res["runtime_seconds"] else qiea_res
            winner_reason = "Both solvers found economically equivalent solutions within tolerance (<0.01% cost delta)."
        elif ga_res["total_cost_usd"] < qiea_res["total_cost_usd"]:
            best_opt = "ga"
            best_plan = ga_res
            winner_reason = f"GA achieved ${abs(cost_diff):,.2f} lower total operational and compliance expenditure ({cost_diff_pct}% savings)."
        else:
            best_opt = "qiea"
            best_plan = qiea_res
            winner_reason = f"QIEA achieved ${abs(cost_diff):,.2f} lower total operational and compliance expenditure ({cost_diff_pct}% savings)."
    elif ga_res["available"]:
        best_opt = "ga"
        best_plan = ga_res
        winner_reason = "GA ran as the solitary solver."
    elif qiea_res["available"]:
        best_opt = "qiea"
        best_plan = qiea_res
        winner_reason = "QIEA ran as the solitary solver."
    else:
        best_plan = {
            "total_cost_usd": 0.0,
            "fuel_tonnes": 0.0,
            "lifecycle_emissions_tco2e": 0.0,
            "compliance_cost_usd": 0.0,
            "cargo_fulfillment_percent": 0.0,
            "feasible": False,
            "configuration": [],
        }
        winner_reason = "Both solvers failed execution."

    # Baseline "What changed?" breakdown
    base_cost = base_eval.objective.total_usd
    base_ghg = base_eval.total_ghg_tco2e
    base_fuel = base_eval.total_fuel_tonnes

    what_changed = {
        "fuel_changes": 0,
        "speed_changes": 0,
        "route_changes": 0,
        "shore_power_changes": 0,
        "pooling_changes": 0,
        "summary": "No plan changes",
    }

    if best_plan and best_plan["configuration"]:
        base_map = {}
        for a in base_assignments:
            vid = a.vessel_id if hasattr(a, "vessel_id") else a["vessel_id"]
            yr = a.year if hasattr(a, "year") else a["year"]
            base_map[(vid, yr)] = a

        fuel_ch = 0
        speed_ch = 0
        route_ch = 0
        shore_ch = 0
        pool_ch = 0

        for gene in best_plan["configuration"]:
            b = base_map.get((gene["vessel_id"], gene["year"]))
            if b:
                b_fuel = b.fuel_id if hasattr(b, "fuel_id") else b["fuel_id"]
                b_route = b.route_id if hasattr(b, "route_id") else b["route_id"]
                b_shore = b.shore_power if hasattr(b, "shore_power") else b["shore_power"]

                if gene["fuel_id"] != b_fuel:
                    fuel_ch += 1
                if gene["speed_band_index"] != 4:  # Design speed is band 4
                    speed_ch += 1
                if gene["route_id"] != b_route:
                    route_ch += 1
                if gene["shore_power"] != b_shore:
                    shore_ch += 1
                if gene["pool_opt_in"]:
                    pool_ch += 1

        what_changed = {
            "fuel_changes": fuel_ch,
            "speed_changes": speed_ch,
            "route_changes": route_ch,
            "shore_power_changes": shore_ch,
            "pooling_changes": pool_ch,
            "summary": f"Selected plan modified {fuel_ch} fuel choices, {speed_ch} speeds, and {shore_ch} shore power elections vs BAU baseline.",
        }

    validation_messages = []
    if ga_res["available"] and qiea_res["available"]:
        validation_messages.append("Both GA and QIEA evaluated identical input constraints and random seeds.")
    elif ga_res["available"]:
        validation_messages.append("GA completed successfully.")
    elif qiea_res["available"]:
        validation_messages.append("QIEA completed successfully.")
    if ga_res.get("error"):
        validation_messages.append(f"GA Notice: {ga_res['error']}")
    if qiea_res.get("error"):
        validation_messages.append(f"QIEA Notice: {qiea_res['error']}")

    return {
        "status": "completed",
        "data_mode": "synthetic_live_solve",
        "request": req.model_dump(),
        "best_optimizer": best_opt,
        "best_plan": {
            "total_cost_usd": best_plan["total_cost_usd"],
            "fuel_tonnes": best_plan["fuel_tonnes"],
            "lifecycle_emissions_tco2e": best_plan["lifecycle_emissions_tco2e"],
            "compliance_cost_usd": best_plan["compliance_cost_usd"],
            "cargo_fulfillment_percent": best_plan.get("cargo_fulfillment_percent", 100.0),
            "feasible": best_plan["feasible"],
            "configuration": best_plan["configuration"],
        },
        "ga_result": ga_res,
        "qiea_result": qiea_res,
        "comparison": {
            "cost_difference_usd": cost_diff,
            "cost_difference_percent": cost_diff_pct,
            "emissions_difference_tco2e": emiss_diff,
            "runtime_difference_seconds": runtime_diff,
            "winner_reason": winner_reason,
        },
        "baseline_comparison": {
            "baseline_total_cost_usd": round(base_cost, 2),
            "baseline_fuel_tonnes": round(base_fuel, 2),
            "baseline_lifecycle_emissions_tco2e": round(base_ghg, 2),
            "baseline_compliance_cost_usd": round(base_comp_usd, 2),
            "cost_savings_usd": round(base_cost - best_plan["total_cost_usd"], 2),
            "cost_savings_percent": round(max(0.0, (base_cost - best_plan["total_cost_usd"]) / max(1.0, base_cost) * 100.0), 2),
            "emissions_reduction_tco2e": round(base_ghg - best_plan["lifecycle_emissions_tco2e"], 2),
            "what_changed": what_changed,
        },
        "validation_messages": validation_messages,
    }


@app.post("/api/compare-fuels")
def compare_fuels(req: CompareFuelsRequest) -> Dict[str, Any]:
    """Compare all compatible fuels for a chosen vessel under current operational parameters."""
    fleet = load_fleet()
    prices = load_prices()
    scenarios = load_scenarios()

    vessels = fleet.get("vessels", [])
    matched_vessel = next((v for v in vessels if v.get("vessel_id") == req.vessel_id), None)
    if not matched_vessel:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Vessel '{req.vessel_id}' was not found in the fleet catalog.",
        )

    engine_type = matched_vessel.get("engine_type", "conventional_hfo_scrubber")
    matrix = fleet.get("engine_fuel_compatibility", {}).get("matrix", {})
    compatible_fuels = matrix.get(engine_type, ["vlsfo"])

    scenario_id = req.scenario_id or "approved_text"
    base_reg = resolve_regulations_for_scenario(scenario_id, scenarios=scenarios)
    regulations = _nzf_price_override(base_reg, req.carbon_price_usd_per_tco2e)

    fleet_adj = copy.deepcopy(fleet)
    if req.cargo_demand_multiplier != 1.0:
        for route in fleet_adj.get("routes", {}).values():
            if "min_capacity_dwt_required" in route:
                route["min_capacity_dwt_required"] = float(route["min_capacity_dwt_required"]) * req.cargo_demand_multiplier
            if "annual_cargo_demand_tonne_nm" in route:
                route["annual_cargo_demand_tonne_nm"] = float(route["annual_cargo_demand_tonne_nm"]) * req.cargo_demand_multiplier

    fuel_names_map = {
        "hfo_scrubber": "Heavy Fuel Oil (HFO + Scrubber)",
        "vlsfo": "Very Low Sulphur Fuel Oil (VLSFO)",
        "mgo": "Marine Gas Oil (MGO)",
        "lng": "Liquefied Natural Gas (LNG)",
        "b30_blend": "B30 Biofuel Blend (30% FAME)",
        "methanol": "Green e-Methanol",
        "ammonia": "Green e-Ammonia",
        "hydrogen": "Green Liquid Hydrogen",
    }

    raw_evals: Dict[str, Dict[str, Any]] = {}
    horizon_years = fleet_adj.get("horizon_years", [2026, 2027, 2028, 2029, 2030])
    class_defaults = fleet_adj.get("vessel_class_defaults", {})
    compat_matrix = fleet_adj.get("engine_fuel_compatibility", {}).get("matrix", {})

    for f_id in compatible_fuels:
        assignments: List[BaselineAssignment] = []
        for v in fleet_adj.get("vessels", []):
            v_id = v["vessel_id"]
            v_band = v["band"]
            v_engine = v.get("engine_type", "conventional_hfo_scrubber")
            v_default_route = v["default_route"]
            v_speed = class_defaults[v_band]["design_speed_knots"]
            v_compat = compat_matrix.get(v_engine, ["vlsfo"])
            v_fuel = f_id if v_id == req.vessel_id else v_compat[0]

            for yr in horizon_years:
                assignments.append(
                    BaselineAssignment(
                        vessel_id=v_id,
                        year=yr,
                        route_id=v_default_route,
                        speed_knots=v_speed,
                        fuel_id=v_fuel,
                        shore_power=False,
                    )
                )

        eval_res = evaluate_baseline_plan(fleet_adj, assignments, regulations, prices)
        v_ghg = sum(x["ghg_tco2e"] for x in eval_res.vessel_breakdown if x["vessel_id"] == req.vessel_id)
        v_fuel_tonnes = sum(x["fuel_tonnes"] for x in eval_res.vessel_breakdown if x["vessel_id"] == req.vessel_id)
        v_cost = sum(x["total_cost_usd"] for x in eval_res.vessel_breakdown if x["vessel_id"] == req.vessel_id)
        v_fueleu = sum(x["fueleu_penalty_usd"] for x in eval_res.vessel_breakdown if x["vessel_id"] == req.vessel_id)

        raw_evals[f_id] = {
            "eval_res": eval_res,
            "v_ghg": v_ghg,
            "v_fuel_tonnes": v_fuel_tonnes,
            "v_cost": v_cost,
            "v_fueleu": v_fueleu,
        }

    baseline_fuel_id = compatible_fuels[0]
    base_v_ghg = raw_evals[baseline_fuel_id]["v_ghg"]
    base_v_cost = raw_evals[baseline_fuel_id]["v_cost"]

    fuel_comparisons = []
    for f_id in compatible_fuels:
        item = raw_evals[f_id]
        eval_res = item["eval_res"]
        v_ghg = item["v_ghg"]
        v_cost = item["v_cost"]
        v_fueleu = item["v_fueleu"]
        v_fuel_tonnes = item["v_fuel_tonnes"]

        ghg_saved = round(base_v_ghg - v_ghg, 2)
        ghg_saved_pct = round((ghg_saved / max(1.0, base_v_ghg)) * 100.0, 1)
        cost_delta = round(v_cost - base_v_cost, 2)

        if ghg_saved > 0.1:
            mac = round(cost_delta / ghg_saved, 1)
        else:
            mac = 0.0

        if ghg_saved > 1.0:
            break_even_carbon = max(0.0, round(req.carbon_price_usd_per_tco2e + (cost_delta / ghg_saved), 1))
        else:
            break_even_carbon = None

        is_base = (f_id == baseline_fuel_id)
        if is_base:
            tag = "Status Quo Baseline"
        elif ghg_saved_pct >= 20.0 and cost_delta <= 0:
            tag = "Immediate Win (Lower Cost & Cleaner)"
        elif ghg_saved_pct >= 25.0:
            tag = "Highest Decarbonization"
        elif cost_delta < 0:
            tag = "Cheapest Option"
        elif ghg_saved_pct > 15.0:
            tag = "Balanced Transition"
        else:
            tag = "Alternative Option"

        fuel_comparisons.append({
            "fuel_id": f_id,
            "fuel_name": fuel_names_map.get(f_id, f_id.replace("_", " ").title()),
            "is_baseline": is_base,
            "tag": tag,
            "vessel_5yr_ghg_tco2e": round(v_ghg, 1),
            "vessel_5yr_fuel_tonnes": round(v_fuel_tonnes, 1),
            "vessel_5yr_cost_usd": round(v_cost, 2),
            "vessel_5yr_fueleu_penalty_usd": round(v_fueleu, 2),
            "ghg_reduction_tco2e": ghg_saved,
            "ghg_reduction_percent": ghg_saved_pct,
            "cost_delta_usd": cost_delta,
            "abatement_cost_usd_per_tco2e": mac,
            "break_even_carbon_price_usd": break_even_carbon,
            "fleet_total_cost_usd": round(eval_res.objective.total_usd, 2),
            "fleet_lifecycle_emissions_tco2e": round(eval_res.total_ghg_tco2e, 1),
        })

    return {
        "status": "completed",
        "vessel_id": req.vessel_id,
        "engine_type": engine_type,
        "carbon_price_usd_per_tco2e": req.carbon_price_usd_per_tco2e,
        "cargo_demand_multiplier": req.cargo_demand_multiplier,
        "baseline_fuel_id": baseline_fuel_id,
        "fuels": fuel_comparisons,
    }

