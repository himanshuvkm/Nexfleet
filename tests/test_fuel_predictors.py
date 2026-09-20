"""Tests for the fuel-consumption residual predictors (Objective 1 /
experiment B1)."""

from __future__ import annotations

import pytest

from nexfleet.fleet.loader import load_fleet
from nexfleet.optimization.fuel_model import PhysicsFuelModel
from nexfleet.optimization.fuel_predictors import (
    FeatureEncoder,
    LightGbmResidualFuelModel,
    MlpResidualFuelModel,
    PredictorHub,
    QuantumInspiredNeuralResidualModel,
    TensorTrainResidualFuelModel,
    mape,
    predict_with_intervals,
    r_squared,
    residual_fraction,
)
from nexfleet.optimization.synthetic_telemetry import generate_telemetry, leave_one_vessel_out_folds

_PREDICTOR_CLASSES = (
    LightGbmResidualFuelModel,
    MlpResidualFuelModel,
    TensorTrainResidualFuelModel,
    QuantumInspiredNeuralResidualModel,
)


@pytest.fixture(scope="module")
def fleet():
    return load_fleet()


@pytest.fixture(scope="module")
def table(fleet):
    return generate_telemetry(fleet, samples_per_vessel_year=30, seed=0)


@pytest.fixture(scope="module")
def one_fold(table):
    return leave_one_vessel_out_folds(table)[0]  # (held_out_vessel_id, train, test)


class TestMetrics:
    def test_mape_of_perfect_prediction_is_zero(self):
        actual = [100.0, 200.0, 50.0]
        assert mape(actual, actual) == pytest.approx(0.0)

    def test_mape_hand_computed(self):
        actual = [100.0, 200.0]
        predicted = [110.0, 180.0]  # +10%, -10% -> mean abs pct error 10%
        assert mape(actual, predicted) == pytest.approx(10.0)

    def test_mape_rejects_empty_input(self):
        with pytest.raises(ValueError):
            mape([], [])

    def test_r_squared_of_perfect_prediction_is_one(self):
        actual = [100.0, 200.0, 50.0, 300.0]
        assert r_squared(actual, actual) == pytest.approx(1.0)

    def test_r_squared_of_constant_actual_is_zero_not_nan(self):
        # No variance to explain -- the honest, finite answer is 0.0, not NaN/inf.
        actual = [100.0, 100.0, 100.0]
        predicted = [90.0, 100.0, 110.0]
        assert r_squared(actual, predicted) == 0.0

    def test_residual_fraction_hand_computed(self):
        from nexfleet.optimization.synthetic_telemetry import TelemetrySample

        sample = TelemetrySample(
            vessel_id="X", band="A", year=2026, route_id="r", fuel_id="f",
            speed_knots=10.0, hull_fouling_age_days=0.0, sea_state_index=0.5,
            physics_tonnes=1000.0, actual_tonnes=1100.0,
        )
        assert residual_fraction(sample) == pytest.approx(0.1)


class TestFeatureEncoder:
    def test_vocab_comes_from_fleet_not_from_a_sample(self, fleet):
        encoder = FeatureEncoder(fleet)
        assert set(encoder.bands) == set(fleet["vessel_class_defaults"].keys())
        assert set(encoder.routes) == set(fleet["routes"].keys())
        assert set(encoder.fuels) == set(fleet["fuel_properties"]["fuels"].keys())

    def test_encoded_vector_length_matches_n_features(self, fleet):
        encoder = FeatureEncoder(fleet)
        vector = encoder.encode_one(encoder.bands[0], encoder.routes[0], encoder.fuels[0], 12.0, 2026)
        assert vector.shape == (encoder.n_features,)

    def test_encode_samples_stacks_rows(self, fleet, table):
        encoder = FeatureEncoder(fleet)
        matrix = encoder.encode_samples(table[:5])
        assert matrix.shape == (5, encoder.n_features)


class TestPredictorsAreFuelModelConformant:
    """The invariant `objective.py:105`'s direct `annual_energy_mj` call
    depends on: every residual predictor must delegate energy to physics
    unchanged (see synthetic_telemetry.py's module docstring for why)."""

    @pytest.mark.parametrize("predictor_cls", _PREDICTOR_CLASSES)
    def test_annual_energy_mj_matches_physics_exactly(self, predictor_cls, fleet):
        physics = PhysicsFuelModel()
        vessel = fleet["vessels"][0]
        encoder = FeatureEncoder(fleet)
        model = predictor_cls(encoder)
        expected = physics.annual_energy_mj(vessel, fleet, 15.0, vessel["default_route"])
        assert model.annual_energy_mj(vessel, fleet, 15.0, vessel["default_route"]) == pytest.approx(expected)

    @pytest.mark.parametrize("predictor_cls", _PREDICTOR_CLASSES)
    def test_daily_energy_mj_matches_physics_exactly(self, predictor_cls, fleet):
        physics = PhysicsFuelModel()
        vessel = fleet["vessels"][0]
        encoder = FeatureEncoder(fleet)
        model = predictor_cls(encoder)
        expected = physics.daily_energy_mj(vessel, fleet, 15.0)
        assert model.daily_energy_mj(vessel, fleet, 15.0) == pytest.approx(expected)

    @pytest.mark.parametrize("predictor_cls", _PREDICTOR_CLASSES)
    def test_raises_before_fit(self, predictor_cls, fleet):
        vessel = fleet["vessels"][0]
        encoder = FeatureEncoder(fleet)
        model = predictor_cls(encoder)
        with pytest.raises(RuntimeError):
            model.fuel_consumption_tonnes(vessel, fleet, 2026, 15.0, "vlsfo", vessel["default_route"])


class TestPredictorsLearnTheResidual:
    """Sanity check the residual is actually learnable, not just plumbing
    that runs: each learned arm must beat physics-only MAPE on a real
    held-out vessel fold of the synthetic data it was trained to predict."""

    @pytest.mark.parametrize("predictor_cls", _PREDICTOR_CLASSES)
    def test_beats_physics_only_on_a_held_out_vessel(self, predictor_cls, fleet, one_fold):
        held_out_vessel_id, train, test = one_fold
        vessels_by_id = {v["vessel_id"]: v for v in fleet["vessels"]}
        physics = PhysicsFuelModel()
        encoder = FeatureEncoder(fleet)

        model = predictor_cls(encoder)
        model.fit(train, fleet)

        actual = [s.actual_tonnes for s in test]
        physics_predicted = [
            physics.fuel_consumption_tonnes(vessels_by_id[s.vessel_id], fleet, s.year, s.speed_knots, s.fuel_id, s.route_id)
            for s in test
        ]
        model_predicted = [
            model.fuel_consumption_tonnes(vessels_by_id[s.vessel_id], fleet, s.year, s.speed_knots, s.fuel_id, s.route_id)
            for s in test
        ]

        physics_mape = mape(actual, physics_predicted)
        model_mape = mape(actual, model_predicted)
        assert model_mape < physics_mape, (
            f"{predictor_cls.__name__} MAPE {model_mape:.3f}% did not beat physics-only "
            f"{physics_mape:.3f}% on held-out vessel {held_out_vessel_id}"
        )


class TestTensorTrainResidualFuelModel:
    def test_bond_dimensions_reported_after_fit(self, fleet, one_fold):
        _, train, _ = one_fold
        encoder = FeatureEncoder(fleet)
        model = TensorTrainResidualFuelModel(encoder)
        assert model.bond_dimensions is None
        model.fit(train, fleet)
        assert model.bond_dimensions is not None
        assert len(model.bond_dimensions) == 3  # 4-axis grid -> 3 internal bonds

    def test_empty_grid_cell_falls_back_to_global_mean_not_a_crash(self, fleet):
        # A tiny, deliberately sparse training set -- most (band, route,
        # fuel, speed-bin) cells will have zero observations.
        table = generate_telemetry(fleet, samples_per_vessel_year=2, seed=0)
        encoder = FeatureEncoder(fleet)
        model = TensorTrainResidualFuelModel(encoder)
        model.fit(table, fleet)  # must not raise
        vessel = fleet["vessels"][0]
        result = model.fuel_consumption_tonnes(vessel, fleet, 2026, 15.0, "methanol", vessel["default_route"])
        assert result > 0


class TestConfidenceIntervals:
    @pytest.mark.parametrize("predictor_cls", _PREDICTOR_CLASSES)
    def test_predict_with_intervals_returns_valid_bounds(self, predictor_cls, fleet, one_fold):
        _, train, _ = one_fold
        encoder = FeatureEncoder(fleet)
        model = predictor_cls(encoder)
        model.fit(train, fleet)

        vessel = fleet["vessels"][0]
        pred, lower, upper = model.predict_with_intervals(
            vessel, fleet, 2026, 15.0, "vlsfo", vessel["default_route"]
        )
        assert 0.0 <= lower <= pred <= upper
        assert upper - lower > 0.0

    def test_physics_model_predict_with_intervals(self, fleet):
        physics = PhysicsFuelModel()
        vessel = fleet["vessels"][0]
        pred, lower, upper = physics.predict_with_intervals(
            vessel, fleet, 2026, 15.0, "vlsfo", vessel["default_route"]
        )
        assert 0.0 <= lower <= pred <= upper

    def test_standalone_predict_with_intervals_helper(self, fleet):
        physics = PhysicsFuelModel()
        vessel = fleet["vessels"][0]
        pred, lower, upper = predict_with_intervals(
            physics, vessel, fleet, 2026, 15.0, "vlsfo", vessel["default_route"]
        )
        assert 0.0 <= lower <= pred <= upper


class TestPredictorHub:
    def test_available_models_list(self):
        models = PredictorHub.available_models()
        assert "physics" in models
        assert "lightgbm" in models
        assert "mlp" in models
        assert "tt_svd" in models
        assert "qnn_residual" in models

    def test_get_predictor_physics(self, fleet):
        model = PredictorHub.get_predictor("physics", fleet=fleet)
        assert isinstance(model, PhysicsFuelModel)
        vessel = fleet["vessels"][0]
        tonnes = model.fuel_consumption_tonnes(vessel, fleet, 2026, 15.0, "vlsfo", vessel["default_route"])
        assert tonnes > 0.0

    def test_get_predictor_tt_svd_sub_millisecond_inference(self, fleet, table):
        import time

        PredictorHub.clear_cache()
        model = PredictorHub.get_predictor("tt_svd", train_samples=table, fleet=fleet)
        vessel = fleet["vessels"][0]
        route = vessel["default_route"]

        # Time single inference
        t0 = time.perf_counter()
        for _ in range(100):
            tonnes = model.fuel_consumption_tonnes(vessel, fleet, 2026, 15.0, "vlsfo", route)
        elapsed_ms = (time.perf_counter() - t0) / 100 * 1000.0

        assert tonnes > 0.0
        assert elapsed_ms < 1.0, f"TT-SVD inference time {elapsed_ms:.4f} ms exceeded 1 ms limit"

    def test_get_predictor_qnn_residual(self, fleet, table):
        PredictorHub.clear_cache()
        model = PredictorHub.get_predictor("qnn_residual", train_samples=table, fleet=fleet)
        vessel = fleet["vessels"][0]
        tonnes = model.fuel_consumption_tonnes(vessel, fleet, 2026, 15.0, "vlsfo", vessel["default_route"])
        assert tonnes > 0.0

    def test_caching_behavior(self, fleet, table):
        PredictorHub.clear_cache()
        m1 = PredictorHub.get_predictor("tt_svd", train_samples=table, fleet=fleet)
        m2 = PredictorHub.get_predictor("tt_svd")
        assert m1 is m2

    def test_unknown_model_raises_value_error(self, fleet):
        with pytest.raises(ValueError):
            PredictorHub.get_predictor("nonexistent_model", fleet=fleet)

