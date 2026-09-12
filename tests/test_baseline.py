"""Unit tests for the Business-As-Usual (BAU) baseline evaluation engine (Member 2)."""

import pytest

from nexfleet.fleet.baseline import (
    BaselineResult,
    baseline_to_genome,
    build_default_baseline_assignments,
    compute_cii_rating,
    evaluate_baseline_plan,
)
from nexfleet.fleet.loader import load_fleet, load_prices
from nexfleet.optimization.fuel_model import PhysicsFuelModel
from nexfleet.optimization.objective import evaluate
from nexfleet.regulatory.loader import load_regulations


@pytest.fixture(scope="module")
def fleet():
    return load_fleet()


@pytest.fixture(scope="module")
def regulations():
    return load_regulations()


@pytest.fixture(scope="module")
def prices():
    return load_prices()


@pytest.fixture(scope="module")
def default_assignments(fleet):
    return build_default_baseline_assignments(fleet)


class TestBaselineAssignmentGeneration:
    def test_generates_fifty_assignments_for_ten_vessels(self, fleet, default_assignments):
        assert len(default_assignments) == 50
        vessels = {a.vessel_id for a in default_assignments}
        assert vessels == {v["vessel_id"] for v in fleet["vessels"]}
        years = {a.year for a in default_assignments}
        assert years == set(fleet["horizon_years"])

    def test_default_assignments_use_design_speed_and_default_routes(self, fleet, default_assignments):
        vessels_by_id = {v["vessel_id"]: v for v in fleet["vessels"]}
        for a in default_assignments:
            vessel = vessels_by_id[a.vessel_id]
            expected_speed = fleet["vessel_class_defaults"][vessel["band"]]["design_speed_knots"]
            assert a.speed_knots == expected_speed
            assert a.route_id == vessel["default_route"]
            assert a.shore_power is False

    def test_default_fuel_matches_engine_primary_fuel(self, fleet, default_assignments):
        vessels_by_id = {v["vessel_id"]: v for v in fleet["vessels"]}
        compat_matrix = fleet["engine_fuel_compatibility"]["matrix"]
        for a in default_assignments:
            vessel = vessels_by_id[a.vessel_id]
            primary_fuel = compat_matrix[vessel["engine_type"]][0]
            assert a.fuel_id == primary_fuel


class TestBaselineEvaluationIntegrity:
    def test_baseline_evaluates_without_errors(self, fleet, default_assignments, regulations, prices):
        result = evaluate_baseline_plan(fleet, default_assignments, regulations, prices)
        assert isinstance(result, BaselineResult)
        assert result.total_fuel_tonnes > 0
        assert result.total_ghg_tco2e > 0
        assert len(result.cii_ratings) == 50
        assert len(result.vessel_breakdown) == 50

    def test_cost_sum_matches_total(self, fleet, default_assignments, regulations, prices):
        result = evaluate_baseline_plan(fleet, default_assignments, regulations, prices)
        obj = result.objective
        component_sum = (
            obj.fuel_cost.amount_usd
            + obj.opex_cost.amount_usd
            + obj.time_cost.amount_usd
            + obj.demand_penalty.amount_usd
            + sum(c.amount_usd for c in obj.compliance_costs.values())
        )
        assert obj.total_usd == pytest.approx(component_sum)

    def test_all_compliance_regimes_present(self, fleet, default_assignments, regulations, prices):
        result = evaluate_baseline_plan(fleet, default_assignments, regulations, prices)
        regimes = set(result.objective.compliance_costs.keys())
        assert regimes == {"cii", "eu_ets", "nzf", "fuel_eu"}

    def test_breakdown_records_contain_all_fields(self, fleet, default_assignments, regulations, prices):
        result = evaluate_baseline_plan(fleet, default_assignments, regulations, prices)
        for record in result.vessel_breakdown:
            assert "vessel_id" in record
            assert "year" in record
            assert "fuel_tonnes" in record
            assert "ghg_tco2e" in record
            assert "fuel_cost_usd" in record
            assert "fueleu_penalty_usd" in record
            assert "cii_rating" in record
            assert "total_cost_usd" in record
            assert record["fuel_tonnes"] > 0
            assert record["total_cost_usd"] > 0


class TestCiiRatings:
    def test_coastal_band_c_is_exempt(self, fleet, default_assignments, regulations, prices):
        result = evaluate_baseline_plan(fleet, default_assignments, regulations, prices)
        for (vessel_id, year), rating in result.cii_ratings.items():
            if vessel_id.startswith("C"):
                # Band C is < 5000 GT and domestic routes
                assert rating == "EXEMPT"

    def test_band_a_and_b_receive_valid_letter_ratings(self, fleet, default_assignments, regulations, prices):
        result = evaluate_baseline_plan(fleet, default_assignments, regulations, prices)
        for (vessel_id, year), rating in result.cii_ratings.items():
            if vessel_id.startswith(("A", "B")):
                assert rating in {"A", "B", "C", "D", "E"}

    def test_compute_cii_rating_boundary_logic(self, regulations):
        # High emissions -> 'E'
        bad_rating = compute_cii_rating(
            vessel_band="A",
            dwt_tonnes=72000,
            distance_nm=85000,
            fuel_tonnes=25000,
            fuel_id="hfo_scrubber",
            year=2026,
            regulations=regulations,
            is_international=True,
            gross_tonnage=45000,
        )
        assert bad_rating == "E"

        # Very low emissions -> 'A'
        good_rating = compute_cii_rating(
            vessel_band="A",
            dwt_tonnes=72000,
            distance_nm=85000,
            fuel_tonnes=1000,
            fuel_id="methanol",
            year=2026,
            regulations=regulations,
            is_international=True,
            gross_tonnage=45000,
        )
        assert good_rating == "A"


class TestBaselineConsistencyWithGenomeEvaluate:
    def test_baseline_and_unpooled_genome_evaluation_align(self, fleet, default_assignments, regulations, prices):
        baseline_result = evaluate_baseline_plan(fleet, default_assignments, regulations, prices)
        genome = baseline_to_genome(fleet, default_assignments)
        genome_result = evaluate(genome, fleet, regulations, prices)

        # In baseline, borrow_election=False and pool_opt_in=False
        # Fuel and opex costs should be identical
        assert baseline_result.objective.fuel_cost.amount_usd == pytest.approx(genome_result.fuel_cost.amount_usd)
        assert baseline_result.objective.opex_cost.amount_usd == pytest.approx(genome_result.opex_cost.amount_usd)
        assert baseline_result.objective.time_cost.amount_usd == pytest.approx(genome_result.time_cost.amount_usd)
        assert baseline_result.objective.compliance_costs["eu_ets"].amount_usd == pytest.approx(
            genome_result.compliance_costs["eu_ets"].amount_usd
        )
        assert baseline_result.objective.compliance_costs["fuel_eu"].amount_usd == pytest.approx(
            genome_result.compliance_costs["fuel_eu"].amount_usd
        )
        assert baseline_result.objective.total_usd == pytest.approx(genome_result.total_usd)


class TestPluggableFuelModelAndFactModifiers:
    def test_custom_fuel_model_scales_consumption(self, fleet, default_assignments, regulations, prices):
        class ScaledFuelModel:
            def __init__(self, multiplier: float):
                self.multiplier = multiplier
                self.base = PhysicsFuelModel()

            def annual_energy_mj(self, vessel, fleet, speed_knots, route_id):
                return self.base.annual_energy_mj(vessel, fleet, speed_knots, route_id) * self.multiplier

            def fuel_consumption_tonnes(self, vessel, fleet, year, speed_knots, fuel_id, route_id):
                return self.base.fuel_consumption_tonnes(vessel, fleet, year, speed_knots, fuel_id, route_id) * self.multiplier

        base_res = evaluate_baseline_plan(fleet, default_assignments, regulations, prices)
        scaled_res = evaluate_baseline_plan(fleet, default_assignments, regulations, prices, fuel_model=ScaledFuelModel(1.2))

        assert scaled_res.total_fuel_tonnes == pytest.approx(base_res.total_fuel_tonnes * 1.2, rel=1e-3)
        assert scaled_res.objective.fuel_cost.amount_usd == pytest.approx(base_res.objective.fuel_cost.amount_usd * 1.2, rel=1e-3)

    def test_environmental_modifiers_increase_consumption(self, fleet, default_assignments, regulations, prices):
        clean_res = evaluate_baseline_plan(fleet, default_assignments, regulations, prices)
        degraded_res = evaluate_baseline_plan(
            fleet,
            default_assignments,
            regulations,
            prices,
            fouling_age_days=500.0,
            sea_state_index=0.8,
        )
        assert degraded_res.total_fuel_tonnes > clean_res.total_fuel_tonnes
        assert degraded_res.objective.fuel_cost.amount_usd > clean_res.objective.fuel_cost.amount_usd


class TestBaselineEdgeCases:
    def test_empty_assignments_evaluates_to_zero_fuel_and_demand_penalty(self, fleet, regulations, prices):
        result = evaluate_baseline_plan(fleet, [], regulations, prices)
        assert result.total_fuel_tonnes == 0.0
        assert result.total_ghg_tco2e == 0.0
        assert len(result.vessel_breakdown) == 0
        # With zero vessels, route demand penalty fires for unserved routes
        assert result.objective.demand_penalty.amount_usd > 0.0

    def test_invalid_vessel_id_raises_key_error(self, fleet, regulations, prices):
        from nexfleet.fleet.baseline import BaselineAssignment
        bad_assignment = [
            BaselineAssignment(
                vessel_id="NON_EXISTENT_VESSEL",
                year=2026,
                route_id="india_northeurope",
                speed_knots=20.0,
                fuel_id="vlsfo",
            )
        ]
        with pytest.raises(KeyError):
            evaluate_baseline_plan(fleet, bad_assignment, regulations, prices)

    def test_objective_cache_clear_and_isolation(self, fleet, default_assignments, regulations, prices):
        from nexfleet.optimization.objective import ObjectiveCache
        cache = ObjectiveCache()
        model1 = PhysicsFuelModel()
        model2 = PhysicsFuelModel()

        slots1 = cache.slots_for(fleet, regulations, prices, model1)
        slots1[("key1",)] = "mock1"
        assert len(cache.slots_for(fleet, regulations, prices, model1)) == 1

        # Switching to model2 resets the cache
        slots2 = cache.slots_for(fleet, regulations, prices, model2)
        assert len(slots2) == 0

        # Explicit clear works
        slots2[("key2",)] = "mock2"
        cache.clear()
        assert len(cache.slots_for(fleet, regulations, prices, model2)) == 0
