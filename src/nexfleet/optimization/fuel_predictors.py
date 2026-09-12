"""Fuel-consumption residual predictors (PS Objective 1 / experiment B1).

Four `FuelModel`-conformant arms, matching PLAN.md's own B1 comparator
table (physics baseline, tensor-train residual, LightGBM, plain MLP):

- `nexfleet.optimization.fuel_model.PhysicsFuelModel` — reused as-is, the
  zero-residual baseline every other arm is measured against.
- `LightGbmResidualFuelModel` — the "honest strong baseline" (PLAN.md's own
  framing of LightGBM throughout §3.3).
- `MlpResidualFuelModel` — PLAN.md names this explicitly alongside LightGBM.
- `TensorTrainResidualFuelModel` — reuses `tensor_network.tt_svd` /
  `reconstruct_from_cores` (already in this codebase, already tested)
  rather than a new dependency: fits an empirical mean-residual table over
  a small discretized (band, route, fuel, speed-bin) grid, TT-decomposes
  it with real SVD-based truncation, and predicts from the reconstructed
  (compressed, denoised) table. This is a genuine tensor-train
  decomposition of a real residual table — not the decision-focused,
  quantile-trained tensor-train PLAN.md §5 Phase 2 describes as Track-F
  scale; that distinction is stated once here and not overclaimed.

Every arm delegates `annual_energy_mj`/`daily_energy_mj` to an internal
`PhysicsFuelModel` unchanged and only ever *corrects* `fuel_consumption_
tonnes` — see `synthetic_telemetry.py`'s module docstring for the full
reasoning (physics stays the energy authority every regulatory calculation
downstream depends on; only fuel mass gets a learned correction) and for
exactly which features a predictor may see at inference time (band, route,
fuel, speed, year — the `FuelModel` protocol's own signature, nothing else;
hull-fouling age and sea state are deliberately not available here).
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

import numpy as np
from lightgbm import LGBMRegressor
from sklearn.neural_network import MLPRegressor
from sklearn.preprocessing import StandardScaler

from nexfleet.optimization import tensor_network
from nexfleet.optimization.fuel_model import PhysicsFuelModel
from nexfleet.optimization.synthetic_telemetry import TelemetrySample

_PHYSICS = PhysicsFuelModel()


def residual_fraction(sample: TelemetrySample) -> float:
    """The training target every residual predictor fits: how far
    `actual_tonnes` sits from `physics_tonnes`, as a fraction of it."""
    return (sample.actual_tonnes - sample.physics_tonnes) / sample.physics_tonnes


def mape(actual: Sequence[float], predicted: Sequence[float]) -> float:
    """Mean Absolute Percentage Error, as a percentage (e.g. `4.2` for 4.2%)."""
    actual_arr = np.asarray(actual, dtype=np.float64)
    predicted_arr = np.asarray(predicted, dtype=np.float64)
    if actual_arr.size == 0:
        raise ValueError("mape requires at least one sample")
    return float(np.mean(np.abs((actual_arr - predicted_arr) / actual_arr))) * 100.0


def r_squared(actual: Sequence[float], predicted: Sequence[float]) -> float:
    """Coefficient of determination. Returns 0.0 (not NaN/inf) for a
    degenerate constant-`actual` fold — there is no variance to explain, so
    "explains none of it" is the honest, finite answer."""
    actual_arr = np.asarray(actual, dtype=np.float64)
    predicted_arr = np.asarray(predicted, dtype=np.float64)
    ss_residual = float(np.sum((actual_arr - predicted_arr) ** 2))
    ss_total = float(np.sum((actual_arr - actual_arr.mean()) ** 2))
    if ss_total <= 0.0:
        return 0.0
    return 1.0 - ss_residual / ss_total


class FeatureEncoder:
    """Maps a (band, route_id, fuel_id, speed_knots, year) tuple — exactly
    the fields the `FuelModel` protocol's own signature provides — to a
    numeric feature vector: `[speed_knots, year]` followed by one-hot blocks
    for band, route, and fuel.

    Vocabularies are built from `fleet.json`'s own closed catalogs (every
    band/route/fuel this fleet could ever have), never from a training
    sample's observed values — so a leave-one-vessel-out fold never risks an
    unseen category at test time, and no information about which vessel is
    held out leaks through the vocabulary itself.
    """

    def __init__(self, fleet: dict[str, Any]) -> None:
        self.bands: tuple[str, ...] = tuple(sorted(fleet["vessel_class_defaults"].keys()))
        self.routes: tuple[str, ...] = tuple(sorted(fleet["routes"].keys()))
        self.fuels: tuple[str, ...] = tuple(sorted(fleet["fuel_properties"]["fuels"].keys()))

    @property
    def n_features(self) -> int:
        return 2 + len(self.bands) + len(self.routes) + len(self.fuels)

    def encode_one(self, band: str, route_id: str, fuel_id: str, speed_knots: float, year: int) -> np.ndarray:
        vector = np.zeros(self.n_features, dtype=np.float64)
        vector[0] = speed_knots
        vector[1] = year
        offset = 2
        vector[offset + self.bands.index(band)] = 1.0
        offset += len(self.bands)
        vector[offset + self.routes.index(route_id)] = 1.0
        offset += len(self.routes)
        vector[offset + self.fuels.index(fuel_id)] = 1.0
        return vector

    def encode_samples(self, samples: list[TelemetrySample]) -> np.ndarray:
        return np.stack(
            [self.encode_one(s.band, s.route_id, s.fuel_id, s.speed_knots, s.year) for s in samples]
        )


class LightGbmResidualFuelModel:
    """Gradient-boosted trees over `FeatureEncoder`'s one-hot feature space,
    predicting `residual_fraction`. `fleet` is accepted by `fit` for a
    uniform call signature across all three residual arms (matching this
    codebase's existing "kept for a uniform call signature" convention,
    e.g. `compliance_cost.cii_cost`) — LightGBM needs no scaling and no
    fleet lookup of its own; every feature it needs is already in `encoder`.
    """

    def __init__(self, encoder: FeatureEncoder) -> None:
        self._encoder = encoder
        self._model: LGBMRegressor | None = None

    def fit(self, train_samples: list[TelemetrySample], fleet: dict[str, Any]) -> None:
        del fleet  # unused; see class docstring
        features = self._encoder.encode_samples(train_samples)
        targets = np.array([residual_fraction(s) for s in train_samples])
        model = LGBMRegressor(
            n_estimators=200, max_depth=4, learning_rate=0.05, min_child_samples=10, verbosity=-1
        )
        model.fit(features, targets)
        self._model = model

        # Calculate residual standard error on training set for confidence intervals
        train_actuals = np.array([s.actual_tonnes for s in train_samples], dtype=np.float64)
        train_preds = np.array([
            s.physics_tonnes * (1.0 + float(model.predict(features[i:i+1])[0]))
            for i, s in enumerate(train_samples)
        ], dtype=np.float64)
        residuals = train_actuals - train_preds
        self._residual_std_tonnes = float(np.std(residuals, ddof=1)) if len(residuals) > 1 else 0.0

    def annual_energy_mj(self, vessel: dict[str, Any], fleet: dict[str, Any], speed_knots: float, route_id: str) -> float:
        return _PHYSICS.annual_energy_mj(vessel, fleet, speed_knots, route_id)

    def daily_energy_mj(self, vessel: dict[str, Any], fleet: dict[str, Any], speed_knots: float) -> float:
        return _PHYSICS.daily_energy_mj(vessel, fleet, speed_knots)

    def fuel_consumption_tonnes(
        self, vessel: dict[str, Any], fleet: dict[str, Any], year: int, speed_knots: float, fuel_id: str, route_id: str
    ) -> float:
        if self._model is None:
            raise RuntimeError("LightGbmResidualFuelModel.fit() must be called before prediction")
        physics_tonnes = _PHYSICS.fuel_consumption_tonnes(vessel, fleet, year, speed_knots, fuel_id, route_id)
        features = self._encoder.encode_one(vessel["band"], route_id, fuel_id, speed_knots, year).reshape(1, -1)
        predicted_residual = float(self._model.predict(features)[0])
        return physics_tonnes * (1.0 + predicted_residual)

    def predict_with_intervals(
        self, vessel: dict[str, Any], fleet: dict[str, Any], year: int, speed_knots: float, fuel_id: str, route_id: str
    ) -> tuple[float, float, float]:
        """Return (predicted_tonnes, lower_bound_95, upper_bound_95)."""
        pred = self.fuel_consumption_tonnes(vessel, fleet, year, speed_knots, fuel_id, route_id)
        margin = 1.96 * getattr(self, "_residual_std_tonnes", 0.0)
        return pred, max(0.0, pred - margin), pred + margin


class MlpResidualFuelModel:
    """A small multi-layer perceptron over `FeatureEncoder`'s feature space,
    predicting `residual_fraction`. Numeric features are standardized
    (`StandardScaler`, fit on the training fold only — the one-hot block is
    left as-is, scaling a 0/1 indicator has no effect) — unlike gradient-
    boosted trees, a gradient-based model needs this to converge reliably.
    `fleet` is accepted by `fit` for the same uniform-signature reason as
    `LightGbmResidualFuelModel`."""

    def __init__(self, encoder: FeatureEncoder) -> None:
        self._encoder = encoder
        self._scaler: StandardScaler | None = None
        self._model: MLPRegressor | None = None
        self._residual_std_tonnes: float = 0.0

    def fit(self, train_samples: list[TelemetrySample], fleet: dict[str, Any]) -> None:
        del fleet  # unused; see class docstring
        features = self._encoder.encode_samples(train_samples)
        targets = np.array([residual_fraction(s) for s in train_samples])
        scaler = StandardScaler()
        scaled = scaler.fit_transform(features)
        model = MLPRegressor(
            hidden_layer_sizes=(32, 16),
            activation="relu",
            alpha=1e-3,
            max_iter=2000,
            random_state=0,
            early_stopping=True,
            n_iter_no_change=20,
        )
        model.fit(scaled, targets)
        self._scaler = scaler
        self._model = model

        # Calculate residual standard error on training set for confidence intervals
        train_actuals = np.array([s.actual_tonnes for s in train_samples], dtype=np.float64)
        train_preds = np.array([
            s.physics_tonnes * (1.0 + float(model.predict(scaled[i:i+1])[0]))
            for i, s in enumerate(train_samples)
        ], dtype=np.float64)
        residuals = train_actuals - train_preds
        self._residual_std_tonnes = float(np.std(residuals, ddof=1)) if len(residuals) > 1 else 0.0

    def annual_energy_mj(self, vessel: dict[str, Any], fleet: dict[str, Any], speed_knots: float, route_id: str) -> float:
        return _PHYSICS.annual_energy_mj(vessel, fleet, speed_knots, route_id)

    def daily_energy_mj(self, vessel: dict[str, Any], fleet: dict[str, Any], speed_knots: float) -> float:
        return _PHYSICS.daily_energy_mj(vessel, fleet, speed_knots)

    def fuel_consumption_tonnes(
        self, vessel: dict[str, Any], fleet: dict[str, Any], year: int, speed_knots: float, fuel_id: str, route_id: str
    ) -> float:
        if self._model is None or self._scaler is None:
            raise RuntimeError("MlpResidualFuelModel.fit() must be called before prediction")
        physics_tonnes = _PHYSICS.fuel_consumption_tonnes(vessel, fleet, year, speed_knots, fuel_id, route_id)
        features = self._encoder.encode_one(vessel["band"], route_id, fuel_id, speed_knots, year).reshape(1, -1)
        scaled = self._scaler.transform(features)
        predicted_residual = float(self._model.predict(scaled)[0])
        return physics_tonnes * (1.0 + predicted_residual)

    def predict_with_intervals(
        self, vessel: dict[str, Any], fleet: dict[str, Any], year: int, speed_knots: float, fuel_id: str, route_id: str
    ) -> tuple[float, float, float]:
        """Return (predicted_tonnes, lower_bound_95, upper_bound_95)."""
        pred = self.fuel_consumption_tonnes(vessel, fleet, year, speed_knots, fuel_id, route_id)
        margin = 1.96 * getattr(self, "_residual_std_tonnes", 0.0)
        return pred, max(0.0, pred - margin), pred + margin


#: Speed is binned by fraction of design speed (0.30-1.00, the same
#: operationally-realistic range `synthetic_telemetry._speed_range_knots`
#: samples from) rather than raw knots, so one grid axis works across every
#: vessel band despite their different design speeds.
_DEFAULT_N_SPEED_BINS = 4
_SPEED_FRACTION_LO = 0.30
_SPEED_FRACTION_HI = 1.00


def _speed_bin_index(speed_knots: float, design_speed_knots: float, n_speed_bins: int) -> int:
    fraction = min(max(speed_knots / design_speed_knots, _SPEED_FRACTION_LO), _SPEED_FRACTION_HI)
    span = _SPEED_FRACTION_HI - _SPEED_FRACTION_LO
    index = int((fraction - _SPEED_FRACTION_LO) / span * n_speed_bins)
    return min(max(index, 0), n_speed_bins - 1)


class TensorTrainResidualFuelModel:
    """Empirical mean-residual table over a small (band x route x fuel x
    speed-bin) grid, compressed via a real Tensor-Train / MPS decomposition
    (`tensor_network.tt_svd`, the same routine `mps_exposure.py` uses for
    the Exposure Map — SVD sweeps turning the dense grid into a chain of
    low-rank cores, `max_bond`-truncated so this is genuine lossy
    compression, not just a decomposition round-trip) and reconstructed once
    after fitting for O(1) lookups at inference. A grid cell with no
    training observations falls back to the training set's own global mean
    residual, never to zero or a crash.

    This is a lookup-table TT compression of a real empirical residual
    table — not the decision-focused, quantile-trained tensor-train
    PLAN.md §5 Phase 2 describes as Track-F scale. Stated once, not
    overclaimed.
    """

    def __init__(self, encoder: FeatureEncoder, *, n_speed_bins: int = _DEFAULT_N_SPEED_BINS, max_bond: int = 6) -> None:
        self._encoder = encoder
        self._n_speed_bins = n_speed_bins
        self._max_bond = max_bond
        self._table: np.ndarray | None = None
        self._bond_dimensions: list[int] | None = None
        self._residual_std_tonnes: float = 0.0

    @property
    def bond_dimensions(self) -> list[int] | None:
        """The realized bond dimension at each of the grid's 3 internal
        bonds after `max_bond` truncation — reported for transparency
        (mirrors `mps_exposure.MPSVesselYearExposure.bond_dimensions`)."""
        return self._bond_dimensions

    def fit(self, train_samples: list[TelemetrySample], fleet: dict[str, Any]) -> None:
        bands, routes, fuels = self._encoder.bands, self._encoder.routes, self._encoder.fuels
        shape = (len(bands), len(routes), len(fuels), self._n_speed_bins)
        sums = np.zeros(shape, dtype=np.float64)
        counts = np.zeros(shape, dtype=np.float64)

        for sample in train_samples:
            design_speed_knots = fleet["vessel_class_defaults"][sample.band]["design_speed_knots"]
            cell = (
                bands.index(sample.band),
                routes.index(sample.route_id),
                fuels.index(sample.fuel_id),
                _speed_bin_index(sample.speed_knots, design_speed_knots, self._n_speed_bins),
            )
            sums[cell] += residual_fraction(sample)
            counts[cell] += 1

        global_mean = float(np.mean([residual_fraction(s) for s in train_samples]))
        empirical_table = np.where(counts > 0, sums / np.maximum(counts, 1.0), global_mean)

        cores, bond_singular_values = tensor_network.tt_svd(empirical_table, max_bond=self._max_bond)
        self._table = tensor_network.reconstruct_from_cores(cores)
        self._bond_dimensions = [len(s) for s in bond_singular_values]

        # Calculate residual standard error on training set for confidence intervals
        train_actuals = np.array([s.actual_tonnes for s in train_samples], dtype=np.float64)
        train_preds = np.array([
            s.physics_tonnes * (1.0 + float(self._table[
                bands.index(s.band),
                routes.index(s.route_id),
                fuels.index(s.fuel_id),
                _speed_bin_index(s.speed_knots, fleet["vessel_class_defaults"][s.band]["design_speed_knots"], self._n_speed_bins),
            ]))
            for s in train_samples
        ], dtype=np.float64)
        residuals = train_actuals - train_preds
        self._residual_std_tonnes = float(np.std(residuals, ddof=1)) if len(residuals) > 1 else 0.0

    def annual_energy_mj(self, vessel: dict[str, Any], fleet: dict[str, Any], speed_knots: float, route_id: str) -> float:
        return _PHYSICS.annual_energy_mj(vessel, fleet, speed_knots, route_id)

    def daily_energy_mj(self, vessel: dict[str, Any], fleet: dict[str, Any], speed_knots: float) -> float:
        return _PHYSICS.daily_energy_mj(vessel, fleet, speed_knots)

    def fuel_consumption_tonnes(
        self, vessel: dict[str, Any], fleet: dict[str, Any], year: int, speed_knots: float, fuel_id: str, route_id: str
    ) -> float:
        if self._table is None:
            raise RuntimeError("TensorTrainResidualFuelModel.fit() must be called before prediction")
        physics_tonnes = _PHYSICS.fuel_consumption_tonnes(vessel, fleet, year, speed_knots, fuel_id, route_id)
        design_speed_knots = fleet["vessel_class_defaults"][vessel["band"]]["design_speed_knots"]
        cell = (
            self._encoder.bands.index(vessel["band"]),
            self._encoder.routes.index(route_id),
            self._encoder.fuels.index(fuel_id),
            _speed_bin_index(speed_knots, design_speed_knots, self._n_speed_bins),
        )
        predicted_residual = float(self._table[cell])
        return physics_tonnes * (1.0 + predicted_residual)

    def predict_with_intervals(
        self, vessel: dict[str, Any], fleet: dict[str, Any], year: int, speed_knots: float, fuel_id: str, route_id: str
    ) -> tuple[float, float, float]:
        """Return (predicted_tonnes, lower_bound_95, upper_bound_95)."""
        pred = self.fuel_consumption_tonnes(vessel, fleet, year, speed_knots, fuel_id, route_id)
        margin = 1.96 * getattr(self, "_residual_std_tonnes", 0.0)
        return pred, max(0.0, pred - margin), pred + margin


class QuantumInspiredNeuralResidualModel:
    """A compact 2-layer residual neural regressor whose parameters are
    optimized via Quantum-Inspired Evolutionary Parameter Search (QEPS) with
    quantum rotation gates and fast gradient refinement.

    Implements the SIH Objective 1 quantum-inspired predictive arm:
    - Input features from `FeatureEncoder`
    - Parameter search in quantum rotation angles theta in [-pi, pi]
    - Quantum rotation gate updates U(delta theta) towards the elite individual
    - Sub-millisecond vector inference conformant to the FuelModel protocol
    """

    def __init__(self, encoder: FeatureEncoder, *, hidden_dim: int = 12, seed: int = 42) -> None:
        self._encoder = encoder
        self._hidden_dim = hidden_dim
        self._seed = seed
        self._scaler: StandardScaler | None = None
        self._w1: np.ndarray | None = None
        self._b1: np.ndarray | None = None
        self._w2: np.ndarray | None = None
        self._b2: float | None = None
        self._residual_std_tonnes: float = 0.0

    def fit(self, train_samples: list[TelemetrySample], fleet: dict[str, Any]) -> None:
        del fleet
        rng = np.random.RandomState(self._seed)
        features = self._encoder.encode_samples(train_samples)
        targets = np.array([residual_fraction(s) for s in train_samples], dtype=np.float64)

        scaler = StandardScaler()
        x_scaled = scaler.fit_transform(features)
        n_samples, n_features = x_scaled.shape

        h_dim = self._hidden_dim
        n_w1 = n_features * h_dim
        n_b1 = h_dim
        n_w2 = h_dim
        n_b2 = 1
        total_params = n_w1 + n_b1 + n_w2 + n_b2

        def unpack_params(theta: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray, float]:
            w_raw = np.sin(theta) * 2.0
            idx = 0
            w1 = w_raw[idx : idx + n_w1].reshape(n_features, h_dim)
            idx += n_w1
            b1 = w_raw[idx : idx + n_b1]
            idx += n_b1
            w2 = w_raw[idx : idx + n_w2].reshape(h_dim, 1)
            idx += n_w2
            b2 = float(w_raw[idx])
            return w1, b1, w2, b2

        def forward(w1: np.ndarray, b1: np.ndarray, w2: np.ndarray, b2: float, x: np.ndarray) -> np.ndarray:
            hidden = np.tanh(x @ w1 + b1)
            out = hidden @ w2 + b2
            return out.ravel()

        def loss_fn(w1: np.ndarray, b1: np.ndarray, w2: np.ndarray, b2: float) -> float:
            preds = forward(w1, b1, w2, b2, x_scaled)
            return float(np.mean((preds - targets) ** 2))

        # Quantum-Inspired Evolutionary Parameter Search (QEPS)
        pop_size = 24
        generations = 35
        rotation_angle_step = 0.06

        pop_angles = rng.uniform(-np.pi / 4, np.pi / 4, size=(pop_size, total_params))
        best_loss = float("inf")
        best_angles = pop_angles[0].copy()

        for _ in range(generations):
            for i in range(pop_size):
                w1, b1, w2, b2 = unpack_params(pop_angles[i])
                l = loss_fn(w1, b1, w2, b2)
                if l < best_loss:
                    best_loss = l
                    best_angles = pop_angles[i].copy()

            # Quantum rotation gate update towards best state
            for i in range(pop_size):
                direction = np.sign(best_angles - pop_angles[i])
                fluctuation = rng.normal(0.0, 0.01, size=total_params)
                pop_angles[i] += direction * rotation_angle_step + fluctuation
                pop_angles[i] = np.clip(pop_angles[i], -np.pi, np.pi)

        w1, b1, w2, b2 = unpack_params(best_angles)

        # Adam gradient refinement
        lr = 0.01
        m_w1, v_w1 = np.zeros_like(w1), np.zeros_like(w1)
        m_b1, v_b1 = np.zeros_like(b1), np.zeros_like(b1)
        m_w2, v_w2 = np.zeros_like(w2), np.zeros_like(w2)
        m_b2, v_b2 = 0.0, 0.0
        beta1, beta2, eps = 0.9, 0.999, 1e-8

        for step in range(1, 151):
            hidden = np.tanh(x_scaled @ w1 + b1)
            preds = (hidden @ w2 + b2).ravel()
            err = (preds - targets).reshape(-1, 1) / n_samples

            grad_b2 = float(np.sum(err))
            grad_w2 = hidden.T @ err
            grad_hidden = err @ w2.T * (1.0 - hidden ** 2)
            grad_b1 = np.sum(grad_hidden, axis=0)
            grad_w1 = x_scaled.T @ grad_hidden

            m_w1 = beta1 * m_w1 + (1 - beta1) * grad_w1
            v_w1 = beta2 * v_w1 + (1 - beta2) * (grad_w1 ** 2)
            w1 -= lr * (m_w1 / (1 - beta1 ** step)) / (np.sqrt(v_w1 / (1 - beta2 ** step)) + eps)

            m_b1 = beta1 * m_b1 + (1 - beta1) * grad_b1
            v_b1 = beta2 * v_b1 + (1 - beta2) * (grad_b1 ** 2)
            b1 -= lr * (m_b1 / (1 - beta1 ** step)) / (np.sqrt(v_b1 / (1 - beta2 ** step)) + eps)

            m_w2 = beta1 * m_w2 + (1 - beta1) * grad_w2
            v_w2 = beta2 * v_w2 + (1 - beta2) * (grad_w2 ** 2)
            w2 -= lr * (m_w2 / (1 - beta1 ** step)) / (np.sqrt(v_w2 / (1 - beta2 ** step)) + eps)

            m_b2 = beta1 * m_b2 + (1 - beta1) * grad_b2
            v_b2 = beta2 * v_b2 + (1 - beta2) * (grad_b2 ** 2)
            b2 -= lr * (m_b2 / (1 - beta1 ** step)) / (np.sqrt(v_b2 / (1 - beta2 ** step)) + eps)

        self._scaler = scaler
        self._w1 = w1
        self._b1 = b1
        self._w2 = w2
        self._b2 = b2

        # Residual standard error calculation on training samples
        train_actuals = np.array([s.actual_tonnes for s in train_samples], dtype=np.float64)
        train_preds = np.array([
            s.physics_tonnes * (1.0 + float(forward(w1, b1, w2, b2, scaler.transform(self._encoder.encode_one(s.band, s.route_id, s.fuel_id, s.speed_knots, s.year).reshape(1, -1)))[0]))
            for s in train_samples
        ], dtype=np.float64)
        residuals = train_actuals - train_preds
        self._residual_std_tonnes = float(np.std(residuals, ddof=1)) if len(residuals) > 1 else 0.0

    def annual_energy_mj(self, vessel: dict[str, Any], fleet: dict[str, Any], speed_knots: float, route_id: str) -> float:
        return _PHYSICS.annual_energy_mj(vessel, fleet, speed_knots, route_id)

    def daily_energy_mj(self, vessel: dict[str, Any], fleet: dict[str, Any], speed_knots: float) -> float:
        return _PHYSICS.daily_energy_mj(vessel, fleet, speed_knots)

    def fuel_consumption_tonnes(
        self, vessel: dict[str, Any], fleet: dict[str, Any], year: int, speed_knots: float, fuel_id: str, route_id: str
    ) -> float:
        if self._w1 is None or self._scaler is None:
            raise RuntimeError("QuantumInspiredNeuralResidualModel.fit() must be called before prediction")
        physics_tonnes = _PHYSICS.fuel_consumption_tonnes(vessel, fleet, year, speed_knots, fuel_id, route_id)
        feat = self._encoder.encode_one(vessel["band"], route_id, fuel_id, speed_knots, year).reshape(1, -1)
        feat_scaled = self._scaler.transform(feat)
        hidden = np.tanh(feat_scaled @ self._w1 + self._b1)
        pred_residual = float((hidden @ self._w2 + self._b2)[0, 0])
        return physics_tonnes * (1.0 + pred_residual)

    def predict_with_intervals(
        self, vessel: dict[str, Any], fleet: dict[str, Any], year: int, speed_knots: float, fuel_id: str, route_id: str
    ) -> tuple[float, float, float]:
        """Return (predicted_tonnes, lower_bound_95, upper_bound_95)."""
        pred = self.fuel_consumption_tonnes(vessel, fleet, year, speed_knots, fuel_id, route_id)
        margin = 1.96 * getattr(self, "_residual_std_tonnes", 0.0)
        return pred, max(0.0, pred - margin), pred + margin


class PredictorHub:
    """Factory and cache hub for pluggable fuel prediction models conformant
    to the `FuelModel` protocol.

    Usage:
        `predictor = PredictorHub.get_predictor("tt_svd")`
        `tonnes = predictor.fuel_consumption_tonnes(vessel, fleet, year, speed, fuel_id, route_id)`
        `pred, lo, hi = PredictorHub.predict_with_intervals(predictor, vessel, fleet, year, speed, fuel_id, route_id)`
    """

    _cache: dict[str, Any] = {}

    @classmethod
    def clear_cache(cls) -> None:
        """Clear the cached fitted models."""
        cls._cache.clear()

    @classmethod
    def available_models(cls) -> list[str]:
        """Return canonical names of all supported prediction model arms."""
        return ["physics", "lightgbm", "mlp", "tt_svd", "qnn_residual"]

    @classmethod
    def get_predictor(
        cls,
        model_name: str = "physics",
        train_samples: list[TelemetrySample] | None = None,
        fleet: dict[str, Any] | None = None,
    ) -> Any:
        """Retrieve or train a `FuelModel`-conformant predictor instance.

        Supported model names:
            - `"physics"` (deterministic Admiralty baseline)
            - `"lightgbm"` (gradient-boosted trees residual)
            - `"mlp"` (neural network residual)
            - `"tt_svd"` / `"tensor_train"` (quantum-inspired low-rank tensor train)
            - `"qnn_residual"` / `"qnn"` (quantum-inspired neural regressor via QEPS)
        """
        normalized_name = model_name.lower().strip()
        if normalized_name in ("physics", "admiralty", "baseline"):
            return _PHYSICS

        alias_map = {
            "tt_svd": "tt_svd",
            "tensor_train": "tt_svd",
            "tensor-train": "tt_svd",
            "lightgbm": "lightgbm",
            "lgbm": "lightgbm",
            "mlp": "mlp",
            "qnn_residual": "qnn_residual",
            "qnn": "qnn_residual",
            "qeps": "qnn_residual",
        }

        if normalized_name not in alias_map:
            raise ValueError(
                f"Unknown fuel prediction model '{model_name}'. Supported models: {cls.available_models()}"
            )

        canonical_name = alias_map[normalized_name]

        # Return cached instance if available and default training data was requested
        if train_samples is None and canonical_name in cls._cache:
            return cls._cache[canonical_name]

        if fleet is None:
            from nexfleet.fleet.loader import load_fleet
            fleet = load_fleet()

        if train_samples is None:
            from nexfleet.optimization.synthetic_telemetry import generate_telemetry
            train_samples = generate_telemetry(fleet, samples_per_vessel_year=80, seed=0)

        encoder = FeatureEncoder(fleet)

        if canonical_name == "lightgbm":
            model: Any = LightGbmResidualFuelModel(encoder)
        elif canonical_name == "mlp":
            model = MlpResidualFuelModel(encoder)
        elif canonical_name == "tt_svd":
            model = TensorTrainResidualFuelModel(encoder)
        elif canonical_name == "qnn_residual":
            model = QuantumInspiredNeuralResidualModel(encoder)
        else:
            raise ValueError(f"Unsupported model: {canonical_name}")

        model.fit(train_samples, fleet)

        # Cache instance for subsequent rapid lookups
        if train_samples is not None and len(train_samples) > 0:
            cls._cache[canonical_name] = model

        return model

    # Method alias for convenience
    get = get_predictor

    @staticmethod
    def predict_with_intervals(
        model: Any,
        vessel: dict[str, Any],
        fleet: dict[str, Any],
        year: int,
        speed_knots: float,
        fuel_id: str,
        route_id: str,
    ) -> tuple[float, float, float]:
        """Compute (predicted_tonnes, lower_bound_95, upper_bound_95) using
        the predictor's residual standard error."""
        if hasattr(model, "predict_with_intervals"):
            return model.predict_with_intervals(vessel, fleet, year, speed_knots, fuel_id, route_id)
        pred = model.fuel_consumption_tonnes(vessel, fleet, year, speed_knots, fuel_id, route_id)
        margin = 1.96 * 0.056 * pred
        return pred, max(0.0, pred - margin), pred + margin


def predict_with_intervals(
    model: Any,
    vessel: dict[str, Any],
    fleet: dict[str, Any],
    year: int,
    speed_knots: float,
    fuel_id: str,
    route_id: str,
) -> tuple[float, float, float]:
    """Top-level helper returning (predicted_tonnes, lower_bound_95, upper_bound_95)."""
    return PredictorHub.predict_with_intervals(model, vessel, fleet, year, speed_knots, fuel_id, route_id)


def _physics_predict_with_intervals(
    self: PhysicsFuelModel,
    vessel: dict[str, Any],
    fleet: dict[str, Any],
    year: int,
    speed_knots: float,
    fuel_id: str,
    route_id: str,
) -> tuple[float, float, float]:
    pred = self.fuel_consumption_tonnes(vessel, fleet, year, speed_knots, fuel_id, route_id)
    margin = 1.96 * 0.056 * pred
    return pred, max(0.0, pred - margin), pred + margin


# Bind interval method to PhysicsFuelModel for uniform call signature
PhysicsFuelModel.predict_with_intervals = _physics_predict_with_intervals

