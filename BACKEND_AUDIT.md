# BACKEND_AUDIT.md: NexFleet 2.0 Architectural & Model Audit

## 1. Executive Summary

NexFleet 2.0 is a decision-support and fleet optimization engine designed to model green fleet scheduling, fuel selection, speed management, and regulatory compliance under four overlapping decarbonization regimes across a 5-year planning horizon (2026–2030) for a 10-vessel benchmark fleet (Bharat-Line).

The current repository represents a complete research, optimization, and presentation prototype. All mathematical formulations, ML residual predictors, quantum-inspired solvers (QIEA), Matrix Product State (MPS) tensor networks, and regulatory mechanisms are implemented in Python (`src/nexfleet`), tested with 286 test cases, and orchestrated via batch scripts (`scripts/build_demo_data.py`) into static artifacts (`outputs/demo_data.json` / `frontend/public/demo_data.json`). The Next.js frontend is decoupled and strictly data-driven via `AtlasContext.tsx`.

No FastAPI backend exists yet. This audit establishes the exact source-code truth for every model, optimizer, formula, data flow, and frontend contract to prepare for a clean, non-disruptive FastAPI integration.

---

## 2. Existing Architecture

```
                                  [ User / Browser ]
                                          │
                                          ▼
                         [ Next.js 16 + React 19 Frontend ]
                       (App Router: /, /sensitivity, /exposure,
                        /engine, /prediction, /fuels, /fleet-matrix)
                                          │
                                          │ fetches via HTTP GET
                                          ▼
                             [ /public/demo_data.json ]
                             [ /scaling_benchmark.json ]
                             [ /scaling_fairstart_benchmark.json ]
                             [ /phase6_benchmark.json ]
                                          ▲
                                          │ serialized by
                        [ scripts/build_demo_data.py ]
                        [ scripts/benchmark_optimizers.py ]
                        [ scripts/benchmark_fuel_predictor.py ]
                                          │
                  ┌───────────────────────┼───────────────────────┐
                  ▼                       ▼                       ▼
          [ ML & Physics ]       [ Optimization Core ]   [ Regulatory Engine ]
          • PhysicsFuelModel      • GA (DEAP)             • Scope Gating
          • LightGBM Regressor    • QIEA (Qudits)         • Implied Price Converter
          • TT-Residual (SVD)     • Coordinate Descent    • FuelEU Ledger & Banking
          • MLP Regressor         • Born Machine (MPS)    • Compliance Pooling
                  │                       │                       │
                  └───────────────────────┼───────────────────────┘
                                          ▼
                               [ Pure Python Modules ]
                             `src/nexfleet/` package
```

---

## 3. Repository Model Map

### Physics Admiralty Fuel Model
- **Source:** `src/nexfleet/optimization/fuel_model.py`
- **Entry point:** `PhysicsFuelModel` (`daily_energy_mj`, `annual_energy_mj`, `fuel_consumption_tonnes`)
- **Inputs:** vessel dict, fleet dict, `speed_knots: float`, `fuel_id: str`, `route_id: str`, `year: int`
- **Outputs:** Daily energy (MJ), Annual energy (MJ), Fuel mass (tonnes)
- **Formulation:**
  - Admiralty power law: `P ∝ Δ^(2/3) · V^3` (Δ = displacement, V = speed)
  - Daily Energy = Anchor Energy × (V / V_design)^3
  - Sea Days = D / (24 × V)
  - Annual Energy = Daily Energy × Sea Days ∝ V^2
  - Fuel Tonnes = Annual Energy / LCV
- **Dependencies:** Python standard library
- **Runtime:** Deterministic, O(1), microseconds. Safe for synchronous API.

### LightGBM Residual Predictor
- **Source:** `src/nexfleet/optimization/fuel_predictors.py`
- **Entry point:** `LightGbmResidualFuelModel` (`fit`, `fuel_consumption_tonnes`)
- **Inputs:** `train_samples` list, `FeatureEncoder` vector (speed, year, one-hot band/route/fuel)
- **Outputs:** Predicted fuel mass (tonnes)
- **Formulation:**
  - Residual target: δ = (M_actual − M_physics) / M_physics
  - M_pred = M_physics × (1 + GBDT(x))
- **Dependencies:** `lightgbm`, `numpy`
- **Runtime:** Deterministic after fit (200 trees, depth 4). Fit ~0.26s; inference <1ms. Safe for sync API once fit.

### Tensor-Train Residual SVD
- **Source:** `src/nexfleet/optimization/fuel_predictors.py`
- **Entry point:** `TensorTrainResidualFuelModel` (`fit`, `fuel_consumption_tonnes`)
- **Inputs:** Discretized 4D grid (band × route × fuel × speed_bin) of mean residuals
- **Outputs:** Reconstructed dense grid table, predicted tonnes
- **Formulation:** TT-SVD core decomposition with `max_bond=6` truncation; reconstructed table T ≈ Contract(C1, C2, C3, C4)
- **Dependencies:** `numpy`
- **Runtime:** Deterministic SVD. Fit ~0.05s, lookup O(1). Safe for sync API.

### MLP Neural Residual
- **Source:** `src/nexfleet/optimization/fuel_predictors.py`
- **Entry point:** `MlpResidualFuelModel` (`fit`, `fuel_consumption_tonnes`)
- **Inputs:** Standardized feature vector [speed, year, one-hot]
- **Outputs:** Predicted fuel mass (tonnes)
- **Formulation:** δ = MLP(StandardScaler(x)), hidden layers (32, 16), ReLU, Adam
- **Dependencies:** `scikit-learn`, `numpy`
- **Runtime:** Fit ~6s, inference <1ms. High variance across held-out vessels (A3 fold error 13.6%).

### Classical Genetic Algorithm (GA)
- **Source:** `src/nexfleet/optimization/solver.py`
- **Entry point:** `run_ga`
- **Inputs:** fleet, regulations, prices, seed, pop_size, n_gen, seed_genome, reference_genome
- **Outputs:** `SolverResult` (best_genome, best_total_usd, best_breakdown, generations_run)
- **Formulation:** Generational EA, tournament selection (k=3), 1-point crossover, menu-valid mutation, HallOfFame, coordinate-descent polish & cost-tied canonicalization
- **Dependencies:** `deap`, `random.Random`
- **Runtime:** Stochastic (deterministic given fixed seeded `random.Random`). ~0.5s–2s per single solve. Moderately expensive.

### Quantum-Inspired EA (QIEA)
- **Source:** `src/nexfleet/optimization/qiea_solver.py`
- **Entry point:** `run_qiea`
- **Inputs:** fleet, regulations, prices, seed, pop_size, n_gen, mean_field_init, polish
- **Outputs:** `SolverResult` (best_genome, best_total_usd, best_breakdown, generations_run)
- **Formulation:**
  - Qudit probability registers: p⃗ = [p1, …, pk]
  - Mean-field Boltzmann prior: p(ci) ∝ exp(−ΔC / T)
  - Monte Carlo collapse; Q-gate rotation to elite archive with linear rate annealing η ∈ [0.05, 0.45]
  - Quantum catastrophe (2% re-uniform); coordinate-descent polish
- **Dependencies:** `random.Random`, `math` (pure Python lists for fast dispatch)
- **Runtime:** Deterministic given seed. ~1.5s–4s per solve. Moderately expensive.

### Born Machine MPS Exposure
- **Source:** `src/nexfleet/optimization/mps_exposure.py` & `src/nexfleet/optimization/tensor_network.py`
- **Entry point:** `compute_mps_exposure`, `compute_mps_exposure_map`
- **Inputs:** vessel_id, year, baseline_genome, fleet, prices
- **Outputs:** `MPSExposureResult`, mutual_information_bits, Schmidt singular values
- **Formulation:**
  - P(r, d⃗) = (1/K) × exp(−(C(r, d⃗) − C_min) / T) / Σ exp(−…)
  - |ψ⟩ = Σ √P |r, d⃗⟩
  - ρ = |ψ⟩⟨ψ|, ρ_r = Tr_{r̄}(ρ), ρ_d = Tr_{d̄}(ρ)
  - I(r : d) = S(ρ_r) + S(ρ_d) − S(ρ_rd), where S(ρ) = −Σ μᵢ log₂ μᵢ
- **Dependencies:** `numpy` (`linalg.svd`, `linalg.eigvalsh`, `tensordot`, `einsum`)
- **Runtime:** Deterministic. Full fleet map (50 slots × 5 scenarios × 96 combos) ~22.7s with caching. Background/batch or async job.

---

## 4. Prediction Models

### Prediction Flow Architecture

```
Input (vessel, route_id, fuel_id, speed_knots, year)
  ↓
Admiralty Physics Baseline:
  • Sea days: D / (24 * V)
  • Daily Energy: Anchor_E * (V / V_design)^3
  • Annual Energy: Daily_E * Sea_days (Fuel-independent)
  • Base Fuel Mass: Annual_Energy / LCV(fuel_id)
  ↓
Feature Preprocessing:
  • [speed_knots, year] + One-Hot(band, route_id, fuel_id)
  • Standardized via StandardScaler for MLP (unscaled for LightGBM/TT)
  ↓
Residual Predictor:
  • Physics-Only: delta = 0
  • LightGBM: GBDT(x) -> delta
  • MLP: MLP(scaled_x) -> delta
  • Tensor-Train: TableLookup(band, route, fuel, speed_bin) -> delta
  ↓
Prediction:
  • M_predicted = M_base * (1.0 + delta)
  ↓
Post-processing:
  • Energy remains strictly physics-derived (regulatory authority invariant)
  • Only fuel mass is adjusted
  ↓
Evaluation Metrics:
  • MAPE (%): mean(|actual - pred| / actual) * 100
  • R²: 1.0 - (SS_res / SS_tot)
```

### Verification Findings
- LightGBM & Tensor-Train are actively implemented and functional: verified in `src/nexfleet/optimization/fuel_predictors.py`.
- **Model Persistence / Training Lifecycle:** Models are not loaded from pre-saved `.pkl` or `.onnx` disk files at runtime. They are dynamically fitted from synthetic telemetry generated on-the-fly (`synthetic_telemetry.generate_telemetry`) via `FeatureEncoder`. Fitting is fast (LightGBM ~0.26s, TT ~0.05s).
- **LOVO Benchmark Verification:** Leave-One-Vessel-Out cross-validation across 10 folds proves LightGBM achieves 2.436% MAPE and TT achieves 2.470% MAPE against the physics baseline of 3.993% MAPE.

---

## 5. Optimization Engines

### Execution Flow

```
User / Scenario Parameters
  ↓
Decision Variables (50 Vessel-Years):
  • route_id (menu valid)
  • speed_band_index (min speed floor index 2..7)
  • fuel_id (engine-compatible fuels)
  • shore_power (bool)
  • pool_opt_in (bool)
  • borrow_election (bool)
  ↓
Evaluation:
  1. Slot-Local Evaluation (Fuel, OPEX, Time Cost, CII, EU ETS, NZF) -> memoized via ObjectiveCache
  2. FuelEU Cross-Vessel Compliance Pooling (resolve_pool: Σ CB >= 0)
  3. FuelEU Multi-Year Ledger (Banking, Borrowing 2% cap @ 1.1x penalty)
  4. Cargo Demand Penalty ($10,000 / DWT shortfall)
  ↓
Total Objective:
  Min Total Cost = Fuel + OPEX + Charter Premium + Demand Penalty + Σ Compliance Bills
  ↓
Solvers:
  • GA: Tournament(k=3), 1-point crossover, valid mutation, HallOfFame elitism
  • QIEA: Qudit registers, Mean-Field Boltzmann init, Monte Carlo collapse, Q-gate rotation to elite archive
  ↓
Shared Post-Processing:
  • Coordinate-Descent Polish (exhaustive single-field trial across all 50 slots)
  • Cost-Tied Canonicalization (reverts <= 1e-6 USD degenerate flips against reference genome)
  ↓
Final Optimal Fleet Plan
```

### Optimizer Comparison
- **GA:** Faster (35s for full 41-point sweep), robust, deterministic given seed.
- **QIEA:** Explores via quantum qudits and mean-field priors (11.2% raw search gain before polish). After polish, produces identical/narrowly better plans ($369.96M vs $370.33M) but takes ~2.4× longer (83.7s).

---

## 6. Regulatory Engine Audit

### Scope Gating
- **Source:** `src/nexfleet/compliance/scope_gating.py` — `applicable_regimes`
- **Inputs:** VesselSpec (GT), VoyagePattern, year, regulations
- **Outputs:** `dict[str, RegimeApplicability]`
- **Formula:** GT ≥ threshold ∧ year ≥ start_year. Voyage share = (IntraEU + Berth) × 1.0 + ExtraEU × 0.5
- **Units:** Dimensionless shares [0.0, 1.0]
- **Notes:** Dynamic from `regulations.json`. Pure logic.

### IMO CII
- **Source:** `src/nexfleet/optimization/compliance_cost.py` — `cii_cost`
- **Inputs:** RegimeApplicability
- **Outputs:** CostBreakdown
- **Formula:** Cost = $0.00 (Status: `NOT_APPLICABLE_NO_DIRECT_PENALTY`)
- **Units:** USD
- **Notes:** CII has no direct financial levy; enforcement is SEEMP Part III CAP.

### CII Implied Price
- **Source:** `src/nexfleet/regulatory/implied_price.py` — `cii_implied_price`
- **Inputs:** corrective_action_cost_usd, co2e_shortfall_addressed_tonnes, years
- **Outputs:** ImpliedPrice
- **Formula:** Price = (CAP Cost / Years) / Shortfall Tonnes
- **Units:** $/tCO₂e
- **Notes:** Optional proxy converter.

### EU ETS
- **Source:** `src/nexfleet/optimization/compliance_cost.py` — `eu_ets_cost`
- **Inputs:** applicability, ghg_intensity, energy_used_mj, eua_price
- **Outputs:** CostBreakdown
- **Formula:** Allowances = (GHG × E / 10⁶) × VoyageShare × PhaseIn × P_EUA
- **Units:** USD
- **Notes:** Phase-in: 40% (2024), 70% (2025), 100% (2026+). Stacks with FuelEU.

### IMO NZF
- **Source:** `src/nexfleet/optimization/compliance_cost.py` — `nzf_cost`
- **Inputs:** nzf_regime, applicability, year, ghg_intensity, energy_used_mj
- **Outputs:** CostBreakdown
- **Formula:** Cost = (Gap1 × P1 + Gap2 × P2) × (E / 10⁶) − Surplus × P_surplus × (E / 10⁶)
- **Units:** USD
- **Notes:** Starts 2028. Tier 1 ($100/t), Tier 2 ($380/t). Surplus unit floor decoupled.

### FuelEU Balance
- **Source:** `src/nexfleet/regulatory/implied_price.py` — `fueleu_compliance_balance_gco2eq`
- **Inputs:** Target GHG, Actual GHG, Energy MJ
- **Outputs:** Float
- **Formula:** CB = (GHG_target − GHG_actual) × E_used
- **Units:** gCO₂eq
- **Notes:** Target: 89.337 (2025–29), 85.690 (2030–34) gCO₂e/MJ.

### FuelEU Penalty
- **Source:** `src/nexfleet/regulatory/implied_price.py` — `fueleu_penalty_eur`
- **Inputs:** Compliance Balance, Actual GHG, consecutive periods n
- **Outputs:** Float
- **Formula:** Penalty = (|CB| / (GHG_actual × 41,000)) × 2,400 × (1 + (n − 1)/10)
- **Units:** EUR
- **Notes:** Reconstructed from Regulation (EU) 2023/1805 Annex IV Part B secondary summaries.

### FuelEU Ledger
- **Source:** `src/nexfleet/optimization/compliance_cost.py` — `compute_fueleu_ledger`
- **Inputs:** year_inputs, fuel_eu_regime, FX
- **Outputs:** `list[FuelEuYearResult]`
- **Formula:** Sequential state machine: Banked surplus offsets deficit; optional borrow capped at 0.02 × Target × E, repaid next year at 1.1×.
- **Units:** USD / gCO₂eq
- **Notes:** Consecutive borrowing prohibited. Pooled years bypass ledger.

### FuelEU Pooling
- **Source:** `src/nexfleet/optimization/pooling.py` — `resolve_pool`
- **Inputs:** `list[VesselPoolBalance]`
- **Outputs:** PoolResult
- **Formula:** If ΣCBᵢ ≥ 0: accepted. Deficit ships absorbed to 0.0. Surplus ships contribute (Surplusⱼ / ΣSurplus) × ΣDeficit. If sum < 0: rejected.
- **Units:** gCO₂eq
- **Notes:** Exact closed-form pool resolution.

---

## 7. Data Flow

```
[ Static Catalog JSONs ]
  • src/nexfleet/regulatory/regulations.json
  • src/nexfleet/regulatory/scenarios.json
  • src/nexfleet/fleet/fleet.json
  • src/nexfleet/fleet/prices.json
              ↓
[ scripts/build_demo_data.py ]
  ├─ 1. Run Carbon Price Sweep (run_sweep):
  │     - 41 price points ($0 to $1,000 in $25 steps)
  │     - Warm-started GA/QIEA solves
  │     - Monotonic envelope verification & re-attempts
  │     - Switching-point extraction
  │     - Baseline counterfactual ($0 frozen plan costed across prices)
  ├─ 2. Run Scenario Stability & Exposure (compute_exposure):
  │     - Solve K=5 scenarios under seeds 0, 1, 2
  │     - Filter Unanimous vs Majority vs Unstable decisions
  │     - Compute Plan Spread & Capex at Risk
  │     - Price marginal per-decision deltas
  ├─ 3. Run Born Machine MPS Cross-Check (compute_mps_crosscheck):
  │     - Build joint probability tensor P(r, d1..d6)
  │     - TT-SVD & Reduced Density Matrix eigendecomposition
  │     - Quantum Mutual Information I(r : decision)
  ├─ 4. Embed Benchmark Summaries:
  │     - load_optimizer_benchmark() (from outputs/optimizer_benchmark.md)
  │     - load_fuel_predictor_benchmark() (from outputs/fuel_predictor_benchmark.md)
  │     - Inject illustrative routes GeoJSON (ROUTES_GEO)
              ↓
[ outputs/demo_data.json & frontend/public/demo_data.json ]
              ↓
[ frontend/lib/AtlasContext.tsx ]
  - React Context provider that fetches /demo_data.json and benchmark JSONs on mount
  - Maintains state for selected price ($/tCO2e) and scenarioId
  - Derives active switching points, plan configs, and demand constraints
              ↓
[ Frontend Next.js Pages ]
  • /             (Overview & Risk Atlas)
  • /sensitivity  (Sensitivity Curve & Switching Points)
  • /exposure     (Quantum Mutual Information & Capex Exposure)
  • /engine       (Optimizer Benchmark & Scaling)
  • /prediction   (Hydrodynamic ML Benchmarks)
  • /fuels        (Bunker Prices & Fuel Mix)
  • /fleet-matrix (Vessel Specifications & Leaflet Corridors)
```

---

## 8. Frontend Data Contracts

Frontend interfaces defined in `frontend/types/demo.ts`:

| Page Route | Expected Data Structures & Keys | Required Identifiers / Types |
|---|---|---|
| `/` (Overview) | metadata, sweep.grid_points, exposure.summary, exposure.plan_spread, exposure.capex_exposure, routes_geo, fleet.vessels | price_usd_per_tco2e, total_usd, compliance_usd, configuration: VesselYearGene[] |
| `/sensitivity` | sweep.grid_points, sweep.switching_points, sweep.scenario_ticks, sweep.baseline_counterfactual | price_low_usd_per_tco2e, price_high_usd_per_tco2e, decision, from_value, to_value, scenario_id |
| `/exposure` | exposure.per_decision_deltas, exposure.unstable_decisions, exposure.majority_band, exposure.mps_crosscheck, exposure.plan_spread | vessel_id, year, decision, mutual_information_bits, classical_status: 'exposed'\|'unstable'\|'not_exposed' |
| `/engine` | optimizer_benchmark, scaling_benchmark, phase6_benchmark | optimizer: 'ga'\|'qiea', search_attribution, AblationArm, ScalingBenchmark |
| `/prediction` | fuel_predictor_benchmark | arms: Record<'physics'\|'lightgbm'\|'mlp'\|'tensor_train', FuelPredictorArmResult>, fold_vessel_ids, per_fold_mape_percent |
| `/fuels` | prices.fuels, fleet.fuel_properties, fleet.engine_fuel_compatibility | lcv_mj_per_tonne, ghg_intensity_gco2e_per_mj, price_usd_per_tonne, status |
| `/fleet-matrix` | fleet.vessels, fleet.vessel_class_defaults, fleet.routes, routes_geo | vessel_id, band: 'A'\|'B'\|'C', engine_type, waypoints: [lat, lon][] |

---

## 9. Existing Dependencies

### Python (`pyproject.toml`)
- `python >= 3.11`
- `jsonschema >= 4.21` (Schema validation)
- `deap >= 1.4` (Evolutionary computation framework)
- `numpy >= 1.26` (Linear algebra, SVD, tensor math)
- `lightgbm >= 4.0` (Gradient-boosted decision trees)
- `scikit-learn >= 1.4` (MLP, Scalers, Metrics)
- `pytest >= 8.0` (Test runner)
- `ruff >= 0.4` (Linter)

*(Note: `fastapi`, `uvicorn`, `pydantic` are NOT yet in `pyproject.toml`)*

### Frontend (`frontend/package.json`)
- `next: 16.3.3` (App Router)
- `react: 19.2.8`, `react-dom: 19.2.8`
- `leaflet: ^1.9.4`, `react-leaflet: ^5.0.0`
- `@phosphor-icons/react: ^2.1.10`
- `tailwindcss: ^4.3.3`, `@tailwindcss/postcss: ^4.3.3`, `postcss: ^8.5.26`
- `typescript: ^5`

---

## 10. Computational Cost / Runtime Classification

### Category A: Safe for Synchronous API Execution (< 50 ms)
- Single-point regulatory scope gating: `applicable_regimes(vessel, voyage, year)`
- Single-point emission & compliance calculations: `eu_ets_cost()`, `nzf_cost()`, `fueleu_compliance_balance_gco2eq()`, `fueleu_penalty_eur()`
- Single-vessel FuelEU ledger: `compute_fueleu_ledger()`
- Exact pool evaluation: `resolve_pool()`
- Admiralty physics & ML residual inference: `fuel_consumption_tonnes()`
- Single fleet plan evaluation: `evaluate(genome)` (approx. 0.31 ms with cache)
- Static catalog reads: `fleet.json`, `regulations.json`, `prices.json`, `scenarios.json`
- Precomputed demo data queries from `demo_data.json`

### Category B: Potentially Expensive (100 ms – 5 s)
- Single scenario cold optimization solve: `solve_scenario()` (GA ~0.5s–1.5s, QIEA ~1.5s–3.5s)
- Single-slot Born Machine tensor & mutual information: `compute_mps_exposure()` (~0.4s–0.7s)
- Synthetic telemetry generation + LightGBM/TT model training: `generate_telemetry()` + `model.fit()` (~0.3s)
- Short carbon price slice solve (3–5 grid points)

### Category C: Batch / Offline Only (> 10 s)
- Full 41-point carbon-price sweep: `run_sweep()` (~35s–90s)
- Full multi-seed scenario stability & exposure solve: `compute_exposure()` (3 seeds × 5 scenarios = 15 solves, ~45s–180s)
- Full-fleet 50-slot Born Machine MPS Exposure Map: `compute_mps_exposure_map()` (~25s–40s)
- Full 10-fold LOVO ML predictor benchmark: `benchmark_fuel_predictor.py` (~15s)
- Scaled optimizer benchmarking & ablation runs: `benchmark_optimizers.py` (~5–15 mins)

---

## 11. Proposed FastAPI Boundary

The FastAPI service should serve as a high-performance, non-intrusive abstraction layer over the existing Python modules without altering any mathematical logic or forcing the frontend to rewrite its components.

```
                    ┌────────────────────────┐
                    │ Next.js Presentation   │
                    └───────────┬────────────┘
                                │ HTTP REST (JSON)
                                ▼
                    ┌────────────────────────┐
                    │     FastAPI Layer      │
                    │  (Pydantic v2 Schemas) │
                    └───────────┬────────────┘
                                │
        ┌───────────────────────┼───────────────────────┐
        ▼                       ▼                       ▼
┌──────────────┐        ┌──────────────┐        ┌──────────────┐
│  Sync Route  │        │  Sync Route  │        │ Async / Job  │
│  Compliance  │        │  Prediction  │        │ Optimization │
│  & Scope     │        │  & Telemetry │        │ & Exposure   │
└───────┬──────┘        └───────┬──────┘        └───────┬──────┘
        │                       │                       │
        └───────────────────────┼───────────────────────┘
                                ▼
              ┌──────────────────────────────────┐
              │  Existing Pure Python Core       │
              │  (`src/nexfleet/`)               │
              │  - compliance/scope_gating.py    │
              │  - optimization/fuel_model.py    │
              │  - optimization/solver.py        │
              │  - optimization/qiea_solver.py   │
              │  - optimization/mps_exposure.py  │
              │  - regulatory/loader.py          │
              └──────────────────────────────────┘
```

---

## 12. Recommended Backend Modules (For Future Implementation)

When approved, the backend can be organized cleanly under a dedicated package (e.g. `src/nexfleet/api/` or top-level `api/`):

- `api/routers/fleet.py`: Endpoints for fleet catalogs, routes, vessel specs, and bunker fuel prices.
- `api/routers/compliance.py`: Instant calculations for Scope Gating, FuelEU penalties, EU ETS allowances, and NZF tier gaps.
- `api/routers/prediction.py`: Fuel prediction endpoints comparing Admiralty Physics vs LightGBM vs Tensor-Train for any user-configured operating point.
- `api/routers/optimize.py`: Endpoints to evaluate custom fleet plans, run single-scenario solves (GA/QIEA), and fetch pre-computed sweeps/recommendations.
- `api/routers/exposure.py`: Endpoints returning MPS Quantum Mutual Information and Capital-at-Risk exposure metrics.

---

## 13. Risks / Ambiguities

- **FuelEU Penalty Annex IV Secondary Source:** `implied_price.py` explicitly documents that the Annex IV Part B penalty formula was reconstructed from secondary summaries rather than direct primary-source EUR-Lex extraction.
- **Deterministic Seed Dependency:** Solvers use explicit seeded `random.Random` instances. If API callers do not pass a seed, runs are non-deterministic; passing a fixed default seed (e.g., 0) ensures exact reproducibility.
- **Frontend Hybrid Mode:** Currently, the frontend loads everything on initial mount from `/demo_data.json`. Transitioning to live FastAPI endpoints should support progressive enhancement (fallback to `/demo_data.json` if API is offline or during static presentation mode).

---

## 14. Questions Requiring Your Decision

1. **FastAPI Location:** Should the FastAPI application code reside inside the existing package (e.g. `src/nexfleet/api/`) or in a separate top-level directory (e.g. `backend/` or `api/`)?
2. **Dependency Management:** Are you ready for us to add `fastapi`, `uvicorn`, and `pydantic` to `pyproject.toml` when starting Module 1?
3. **Execution Strategy for Expensive Solvers:** For endpoints that trigger GA/QIEA solves or price sweeps, should we:
   - Provide lightweight/fast execution modes (smaller population/generations) for interactive response?
   - Support asynchronous job IDs / background tasks?
   - Or serve pre-computed results by default with on-demand solve options?
4. **Frontend Integration Style:** Should the Next.js frontend fetch live from FastAPI endpoints with automatic fallback to static `demo_data.json`, or switch entirely to FastAPI?

---

## 15. Files That Must NOT Be Modified

To preserve research integrity and verification contracts, the following files must NOT have their core mathematical logic modified:

- `src/nexfleet/compliance/scope_gating.py`
- `src/nexfleet/regulatory/implied_price.py`
- `src/nexfleet/regulatory/scenario_resolution.py`
- `src/nexfleet/optimization/fuel_model.py`
- `src/nexfleet/optimization/fuel_predictors.py`
- `src/nexfleet/optimization/tensor_network.py`
- `src/nexfleet/optimization/mps_exposure.py`
- `src/nexfleet/optimization/pooling.py`
- `src/nexfleet/optimization/compliance_cost.py`
- `src/nexfleet/optimization/objective.py`
- `src/nexfleet/optimization/solver.py`
- `src/nexfleet/optimization/qiea_solver.py`
- `src/nexfleet/optimization/sweep.py`
- `src/nexfleet/optimization/exposure.py`
- `src/nexfleet/regulatory/regulations.json`
- `src/nexfleet/regulatory/scenarios.json`
- `src/nexfleet/fleet/fleet.json`
- `src/nexfleet/fleet/prices.json`