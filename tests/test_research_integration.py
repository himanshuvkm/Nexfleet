"""End-to-End Research Integration Tests (Member 4 - Quality & Research Validation).

Verifies the complete un-mocked integration pipeline across all 5 member domains:
1. Fuel Prediction (Member 1: Physics, TT-SVD, LightGBM, MLP)
2. Baseline Evaluation (Member 2: Status-quo BAU, standalone FuelEU penalties, IMO CII ratings)
3. Classical & Quantum Optimization (Member 3: GA vs QIEA, multi-objective ε-constraint Pareto engine)
4. Constraints & Mathematical Consistency: Zero cargo shortfall, valid service days, non-dominated frontier.
"""

from __future__ import annotations

import pytest

from nexfleet.fleet.baseline import BaselineAssignment, BaselineResult, evaluate_baseline_plan
from nexfleet.fleet.loader import load_fleet, load_prices
from nexfleet.fleet.model import option_menu_for
from nexfleet.optimization.fuel_model import PhysicsFuelModel
from nexfleet.optimization.fuel_predictors import (
    FeatureEncoder,
    LightGbmResidualFuelModel,
    TensorTrainResidualFuelModel,
)
from nexfleet.optimization.genome import random_genome
from nexfleet.optimization.objective import evaluate
from nexfleet.optimization.qiea_solver import (
    ParetoAlternative,
    ParetoSetResult,
    generate_pareto_frontier,
    pareto_result_to_dict,
    run_qiea,
)
from nexfleet.optimization.solver import run_ga
from nexfleet.optimization.synthetic_telemetry import generate_telemetry
from nexfleet.regulatory.scenario_resolution import resolve_regulations_for_scenario


@pytest.fixture(scope="module")
def fleet():
    return load_fleet()


@pytest.fixture(scope="module")
def prices():
    return load_prices()


@pytest.fixture(scope="module")
def regulations():
    return resolve_regulations_for_scenario("approved_text")


@pytest.fixture(scope="module")
def fitted_tt_fuel_model(fleet):
    """Fitted Tensor-Train SVD residual model on synthetic telemetry."""
    encoder = FeatureEncoder(fleet)
    tt_model = TensorTrainResidualFuelModel(encoder, max_bond=4)
    telemetry = generate_telemetry(fleet, samples_per_vessel_year=20, seed=42)
    tt_model.fit(telemetry, fleet)
    return tt_model


class TestEndToEndResearchIntegration:
    """Rigorous end-to-end integration test battery."""

    def test_predictor_to_baseline_evaluation_chain(self, fleet, regulations, prices, fitted_tt_fuel_model):
        """Verify baseline evaluation with both standard Physics and TT-SVD models."""
        physics_model = PhysicsFuelModel()

        # Build status quo baseline assignments
        assignments = []
        for vessel in fleet["vessels"]:
            vessel_id = vessel["vessel_id"]
            default_route = "india_gulf"
            default_fuel = "vlsfo"
            for year in fleet["horizon_years"]:
                menu = option_menu_for(vessel, fleet, year)
                default_speed = menu.speed_bands_knots[len(menu.speed_bands_knots) // 2]
                assignments.append(
                    BaselineAssignment(
                        vessel_id=vessel_id,
                        year=year,
                        route_id=default_route,
                        speed_knots=default_speed,
                        fuel_id=default_fuel,
                        shore_power=False,
                    )
                )

        baseline_physics: BaselineResult = evaluate_baseline_plan(
            fleet, assignments, regulations, prices, fuel_model=physics_model
        )
        assert baseline_physics.objective.total_usd > 0
        assert baseline_physics.total_fuel_tonnes > 0
        assert baseline_physics.total_ghg_tco2e > 0
        assert len(baseline_physics.cii_ratings) == len(assignments)

        # Baseline with TT-SVD model
        baseline_tt: BaselineResult = evaluate_baseline_plan(
            fleet, assignments, regulations, prices, fuel_model=fitted_tt_fuel_model
        )
        assert baseline_tt.objective.total_usd > 0
        assert baseline_tt.total_fuel_tonnes > 0
        # Fuel consumption should be in a close physically realistic band (< 15% difference from physics)
        diff_pct = abs(baseline_tt.total_fuel_tonnes - baseline_physics.total_fuel_tonnes) / baseline_physics.total_fuel_tonnes
        assert diff_pct < 0.15

    def test_ga_and_qiea_solvers_with_custom_predictor(self, fleet, regulations, prices, fitted_tt_fuel_model):
        """Verify both Classical GA and Quantum QIEA execute cleanly with custom TT-SVD predictor."""
        # Run Classical GA
        ga_res = run_ga(
            fleet,
            regulations,
            prices,
            fuel_model=fitted_tt_fuel_model,
            seed=42,
            population_size=10,
            n_generations=5,
        )
        assert ga_res.best_total_usd > 0
        assert len(ga_res.best_genome) == len(fleet["vessels"]) * len(fleet["horizon_years"])

        # Check zero cargo shortfall on GA solution
        ga_eval = evaluate(ga_res.best_genome, fleet, regulations, prices, fuel_model=fitted_tt_fuel_model)
        assert ga_eval.demand_penalty.amount_usd == 0.0, "GA solution produced non-zero cargo deficit penalty"

        # Run Quantum QIEA
        qiea_res = run_qiea(
            fleet,
            regulations,
            prices,
            fuel_model=fitted_tt_fuel_model,
            seed=42,
            population_size=10,
            n_generations=5,
            polish=True,
        )
        assert qiea_res.best_total_usd > 0
        assert len(qiea_res.best_genome) == len(fleet["vessels"]) * len(fleet["horizon_years"])

        # Check zero cargo shortfall on QIEA solution
        qiea_eval = evaluate(qiea_res.best_genome, fleet, regulations, prices, fuel_model=fitted_tt_fuel_model)
        assert qiea_eval.demand_penalty.amount_usd == 0.0, "QIEA solution produced non-zero cargo deficit penalty"

    def test_pareto_frontier_generation_and_tradeoff_consistency(self, fleet, regulations, prices):
        """Verify multi-objective Pareto generation produces non-dominated, feasible strategies."""
        pareto_res: ParetoSetResult = generate_pareto_frontier(
            fleet,
            regulations,
            prices,
            steps=3,
            population_size=10,
            n_generations=5,
            seed=42,
        )

        assert pareto_res.cheapest is not None
        assert pareto_res.balanced is not None
        assert pareto_res.greenest is not None
        assert len(pareto_res.alternatives) == 3

        cheapest = pareto_res.cheapest
        balanced = pareto_res.balanced
        greenest = pareto_res.greenest

        # Verify strategy definitions
        assert "Cheapest" in cheapest.definition or "Cost" in cheapest.definition
        assert "Balanced" in balanced.definition
        assert "Lowest Lifecycle Emissions" in greenest.definition or "Greenest" in greenest.definition or "GHG" in greenest.definition

        # Verify cost and emission tradeoffs
        # Greenest must have lower or equal GHG than Cheapest
        assert greenest.lifecycle_ghg_tco2e <= cheapest.lifecycle_ghg_tco2e + 1e-3, (
            f"Greenest GHG ({greenest.lifecycle_ghg_tco2e}) should be <= Cheapest GHG ({cheapest.lifecycle_ghg_tco2e})"
        )

        # Cheapest must have lower or equal cost than Greenest
        assert cheapest.total_cost_usd <= greenest.total_cost_usd + 1e-3, (
            f"Cheapest cost ({cheapest.total_cost_usd}) should be <= Greenest cost ({greenest.total_cost_usd})"
        )

        # Balanced plan GHG should sit between greenest and cheapest
        min_ghg = min(cheapest.lifecycle_ghg_tco2e, greenest.lifecycle_ghg_tco2e)
        max_ghg = max(cheapest.lifecycle_ghg_tco2e, greenest.lifecycle_ghg_tco2e)
        assert min_ghg - 1e-3 <= balanced.lifecycle_ghg_tco2e <= max_ghg + 1e-3

        # Verify constraint compliance for all alternatives
        for alt in [cheapest, balanced, greenest]:
            alt_eval = evaluate(alt.genome, fleet, regulations, prices)
            assert alt_eval.demand_penalty.amount_usd == 0.0, (
                f"Alternative {alt.strategy_id} has cargo shortfall penalty: {alt_eval.demand_penalty.amount_usd}"
            )

    def test_pareto_serializer_schema_compatibility(self, fleet, regulations, prices):
        """Verify pareto_result_to_dict produces the exact schema expected by frontend and build_demo_data."""
        pareto_res = generate_pareto_frontier(
            fleet,
            regulations,
            prices,
            steps=2,
            population_size=8,
            n_generations=4,
            seed=10,
        )
        serialized = pareto_result_to_dict(pareto_res, fleet, regulations, prices)

        assert "alternatives" in serialized
        assert len(serialized["alternatives"]) == 3
        assert "scenario" in serialized
        assert "provenance" in serialized

        for alt_dict in serialized["alternatives"]:
            assert "id" in alt_dict
            assert "definition" in alt_dict
            assert "configuration" in alt_dict
            assert "metrics" in alt_dict
            assert "change_summary" in alt_dict

            metrics = alt_dict["metrics"]
            assert "total_usd" in metrics
            assert "lifecycle_emissions_tco2e" in metrics
            assert "fuel_tonnes" in metrics
            assert "cargo" in metrics
            assert "annual_service" in metrics
            assert isinstance(metrics["cargo"]["passed"], bool)
            assert isinstance(metrics["annual_service"]["passed"], bool)
            assert len(metrics["cargo"]["rows"]) > 0
            assert len(metrics["annual_service"]["rows"]) > 0
