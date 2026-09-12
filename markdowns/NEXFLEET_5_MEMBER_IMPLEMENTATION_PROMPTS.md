# NEXFLEET 2.0: 5-MEMBER IMPLEMENTATION PROMPTS
## Copy-Paste Ready Standalone Agent Directives for Parallel Execution

**Document Status:** Approved Operational Execution Directives (Single Source of Truth)  
**Parent Plan:** [`NEXFLEET_REMAINING_WORK_5_MEMBER_EXECUTION_PLAN.md`](file:///c:/Users/Akshat/Downloads/Projects/Nexfleet/NEXFLEET_REMAINING_WORK_5_MEMBER_EXECUTION_PLAN.md)  
**Master Research Document:** [`NEXFLEET_MASTER_RESEARCH_AND_PRODUCT_PLAN.md`](file:///c:/Users/Akshat/Downloads/Projects/Nexfleet/NEXFLEET_MASTER_RESEARCH_AND_PRODUCT_PLAN.md)  
**Audit Report:** [`NEXFLEET_CURRENT_IMPLEMENTATION_REPORT.md`](file:///c:/Users/Akshat/Downloads/Projects/Nexfleet/NEXFLEET_CURRENT_IMPLEMENTATION_REPORT.md)  

---

# How to Use This File

Each team member opens their own Antigravity instance and issues the single prompt:

> *"Execute the Member X Implementation Directive from `NEXFLEET_5_MEMBER_IMPLEMENTATION_PROMPTS.md`."*

The agent will read the designated section, inspect the repository, implement only assigned code within exclusive file boundaries, run test suites, and produce a formal handoff report.

---

# MEMBER 1 IMPLEMENTATION PROMPT
### Role: Prediction & Machine Learning Integration Lead

```markdown
You are acting as MEMBER 1 (Prediction & Machine Learning Integration Lead) on the NexFleet 2.0 project.

YOUR MISSION:
Unify all existing fuel consumption prediction models (Physics, LightGBM, MLP, Tensor-Train SVD) into a pluggable predictor suite conformant to the FuelModel protocol, add prediction confidence intervals, and optionally implement the Quantum-Inspired Neural Residual Predictor (QNN/QEPS).

MANDATORY FIRST STEPS:
1. Read `NEXFLEET_MASTER_RESEARCH_AND_PRODUCT_PLAN.md` (Part 4).
2. Read `NEXFLEET_REMAINING_WORK_5_MEMBER_EXECUTION_PLAN.md` (Section 4, Member 1).
3. Inspect `src/nexfleet/optimization/fuel_model.py`, `src/nexfleet/optimization/fuel_predictors.py`, `src/nexfleet/optimization/tensor_network.py`, and `src/nexfleet/optimization/synthetic_telemetry.py`.

EXACT ASSIGNED TASKS:
1. [MANDATORY] Unify Predictor Interface:
   - Ensure `PhysicsFuelModel`, `LightGbmResidualFuelModel`, `MlpResidualFuelModel`, and `TensorTrainResidualFuelModel` all strictly implement the FuelModel protocol:
     - `annual_energy_mj(vessel, fleet, speed_knots, route_id) -> float`
     - `daily_energy_mj(vessel, fleet, speed_knots) -> float`
     - `fuel_consumption_tonnes(vessel, fleet, year, speed_knots, fuel_id, route_id) -> float`
2. [MANDATORY] Implement PredictorHub Factory:
   - Create a clean factory class `PredictorHub` in `fuel_predictors.py`:
     - `PredictorHub.get_predictor(model_name: str, train_samples: list = None, fleet: dict = None) -> FuelModel`
     - Supports model names: `"physics"`, `"lightgbm"`, `"mlp"`, `"tt_svd"`, `"qnn_residual"`.
     - Automatically caches/trains the model on synthetic telemetry when needed.
3. [MANDATORY] Add Residual Confidence Intervals:
   - Implement `predict_with_intervals(vessel, fleet, year, speed_knots, fuel_id, route_id) -> tuple[float, float, float]` returning `(predicted_tonnes, lower_bound_95, upper_bound_95)` based on leave-one-vessel-out residual standard error.
4. [RECOMMENDED / OPTIONAL RESEARCH] Implement QNN / QEPS Residual Model:
   - Implement `QuantumInspiredNeuralResidualModel`: A compact 2-layer residual neural regressor whose weights or initial basis angles are optimized via Quantum-Inspired Evolutionary Parameter Search (rotation gates) to demonstrate quantum-inspired prediction as requested by SIH Objective 1.
5. [MANDATORY] Update Prediction Benchmark Suite:
   - Ensure `scripts/benchmark_fuel_predictor.py` cleanly runs and benchmarks all available prediction arms across 10-fold LOVO cross-validation.

EXCLUSIVE FILES YOU MAY MODIFY:
- `src/nexfleet/optimization/fuel_predictors.py`
- `src/nexfleet/optimization/tensor_network.py`
- `src/nexfleet/optimization/synthetic_telemetry.py`
- `scripts/benchmark_fuel_predictor.py`
- `tests/test_fuel_predictors.py`

FORBIDDEN FILES (DO NOT MODIFY):
- `src/nexfleet/optimization/objective.py` (Owned by Member 2)
- `src/nexfleet/optimization/solver.py` (Owned by Member 3)
- `src/nexfleet/optimization/qiea_solver.py` (Owned by Member 3)
- `src/nexfleet/fleet/baseline.py` (Owned by Member 2)
- `scripts/build_demo_data.py` (Owned by Member 5)
- `frontend/*` (Owned by Member 5)

PRESERVE AND DO NOT REBUILD:
- Do NOT rewrite `PhysicsFuelModel` Admiralty equations.
- Do NOT rewrite `tensor_network.py` TT-SVD decomposition routines.
- Do NOT create any backend or REST API server.

ACCEPTANCE CRITERIA & TESTS TO RUN:
1. Run `python -m pytest tests/test_fuel_predictors.py` — Must pass 100%.
2. Run `python scripts/benchmark_fuel_predictor.py` — Must output valid MAPE/R² benchmark results.
3. Verify that `PredictorHub.get_predictor("tt_svd")` returns a working `FuelModel` callable in < 1ms per inference.

FINAL HANDOFF REPORT REQUIRED:
When complete, output a structured report stating:
- Model arms implemented and verified.
- LOVO MAPE results for each arm.
- Exact import signature for Member 2 and Member 3 (`from nexfleet.optimization.fuel_predictors import PredictorHub`).
```

---

# MEMBER 2 IMPLEMENTATION PROMPT
### Role: Baseline & Mathematical Evaluation Lead

```markdown
You are acting as MEMBER 2 (Baseline & Mathematical Evaluation Lead) on the NexFleet 2.0 project.

YOUR MISSION:
Implement the missing user Business-As-Usual (BAU) baseline evaluator (`nexfleet.fleet.baseline`), maintain the unified objective evaluation engine (`objective.py`), and ensure mathematical consistency across baseline and optimized plans.

MANDATORY FIRST STEPS:
1. Read `NEXFLEET_MASTER_RESEARCH_AND_PRODUCT_PLAN.md` (Parts 3, 5, 8).
2. Read `NEXFLEET_REMAINING_WORK_5_MEMBER_EXECUTION_PLAN.md` (Section 4, Member 2).
3. Inspect `src/nexfleet/fleet/model.py`, `src/nexfleet/fleet/loader.py`, `src/nexfleet/optimization/objective.py`, `src/nexfleet/optimization/compliance_cost.py`, and `src/nexfleet/optimization/costs.py`.

EXACT ASSIGNED TASKS:
1. [MANDATORY] Implement User Baseline Evaluator (`src/nexfleet/fleet/baseline.py`):
   - Implement `BaselineAssignment` dataclass: `(vessel_id: str, year: int, route_id: str, speed_knots: float, fuel_id: str, shore_power: bool)`.
   - Implement `BaselineResult` dataclass:
     - `objective: ObjectiveResult`
     - `total_fuel_tonnes: float`
     - `total_ghg_tco2e: float`
     - `cii_ratings: dict[tuple[str, int], str]`
     - `vessel_breakdown: list[dict]`
   - Implement `evaluate_baseline_plan(fleet, baseline_assignments, regulations, prices, fuel_model=None) -> BaselineResult`:
     - Evaluates the status quo (un-optimized) fleet operations.
     - Calculates bunker fuel mass, bunker expenditure, fixed OPEX, charter time cost, EU ETS allowance cost, FuelEU penalties (without pooling or banking advantages), and IMO CII letter ratings.
2. [MANDATORY] Unify Objective Function Interface (`src/nexfleet/optimization/objective.py`):
   - Ensure `evaluate(genome, fleet, regulations, prices, fuel_model=None, cache=None) -> ObjectiveResult` seamlessly accepts any `FuelModel` instance (passed from Member 1's `PredictorHub` or Member 3's solvers).
   - Ensure slot-local memoization in `ObjectiveCache` remains 100% correct when switching fuel models.
3. [MANDATORY] Weather / Hull Fouling Fact Modifier:
   - Update `vessel_year_facts()` in `objective.py` to optionally accept `fouling_age_days: float = None` and `sea_state_index: float = None` so realistic environmental degradation can be tested.
4. [MANDATORY] Create Baseline Unit Tests:
   - Create `tests/test_baseline.py` testing default status-quo assignments against known manual spreadsheet ledgers.

EXCLUSIVE FILES YOU MAY MODIFY:
- `src/nexfleet/fleet/baseline.py` (New file)
- `src/nexfleet/optimization/objective.py`
- `src/nexfleet/optimization/genome.py`
- `src/nexfleet/optimization/costs.py`
- `src/nexfleet/optimization/constraints.py`
- `src/nexfleet/fleet/loader.py`
- `src/nexfleet/fleet/model.py`
- `tests/test_baseline.py` (New file)
- `tests/test_objective.py`

FORBIDDEN FILES (DO NOT MODIFY):
- `src/nexfleet/optimization/fuel_predictors.py` (Owned by Member 1)
- `src/nexfleet/optimization/solver.py` (Owned by Member 3)
- `src/nexfleet/optimization/qiea_solver.py` (Owned by Member 3)
- `scripts/build_demo_data.py` (Owned by Member 5)
- `frontend/*` (Owned by Member 5)

PRESERVE AND DO NOT REBUILD:
- Do NOT rewrite FuelEU pooling logic in `pooling.py` or ledger calculations in `compliance_cost.py`.
- Do NOT change regulatory constants in `regulations.json` or pricing structures in `prices.json`.
- Do NOT create any web server or API layer.

ACCEPTANCE CRITERIA & TESTS TO RUN:
1. Run `python -m pytest tests/test_baseline.py` — Must pass 100%.
2. Run `python -m pytest tests/test_objective.py` — Must pass 100%.
3. Verify `evaluate_baseline_plan` produces an exact baseline total cost and carbon footprint for the 10-vessel Bharat-Line fleet.

FINAL HANDOFF REPORT REQUIRED:
When complete, output a structured report stating:
- Baseline evaluation contract signature.
- Verified status-quo cost and GHG numbers for default fleet.
- Exact import signature for Member 3 and Member 5 (`from nexfleet.fleet.baseline import evaluate_baseline_plan, BaselineResult`).
```

---

# MEMBER 3 IMPLEMENTATION PROMPT
### Role: Solvers & Multi-Objective Pareto Engine Lead

```markdown
You are acting as MEMBER 3 (Solvers & Multi-Objective Pareto Engine Lead) on the NexFleet 2.0 project.

YOUR MISSION:
Connect classical GA and quantum-inspired QIEA solvers to the unified prediction engine (Member 1) and objective evaluator (Member 2), implement the multi-objective epsilon-constraint Pareto engine, and dynamically generate non-dominated solutions (Cheapest, Balanced, Greenest).

MANDATORY FIRST STEPS:
1. Read `NEXFLEET_MASTER_RESEARCH_AND_PRODUCT_PLAN.md` (Parts 5, 6).
2. Read `NEXFLEET_REMAINING_WORK_5_MEMBER_EXECUTION_PLAN.md` (Section 4, Member 3).
3. Inspect `src/nexfleet/optimization/solver.py`, `src/nexfleet/optimization/qiea_solver.py`, `src/nexfleet/optimization/sweep.py`, and `src/nexfleet/optimization/objective.py`.

EXACT ASSIGNED TASKS:
1. [MANDATORY] Pluggable Predictor Integration in Solvers:
   - In `solver.py:run_ga()` and `qiea_solver.py:run_qiea()`, add parameter `fuel_model: FuelModel | None = None` and pass it directly into `evaluate()` and `ObjectiveCache`.
2. [MANDATORY] Multi-Objective Epsilon-Constraint Pareto Engine (`src/nexfleet/optimization/qiea_solver.py`):
   - Implement `generate_pareto_frontier(fleet, regulations, prices, fuel_model=None, steps=5) -> ParetoSetResult`:
     - Step A: Run unconstrained cost minimization: $\min \text{Cost} \rightarrow (\text{Cost}_{\min}, \text{GHG}_{\max})$ [*Cheapest Plan*].
     - Step B: Run carbon-weighted or unconstrained GHG minimization: $\min \text{GHG} \rightarrow (\text{Cost}_{\max}, \text{GHG}_{\min})$ [*Greenest Plan*].
     - Step C: For $\varepsilon \in \text{linspace}(\text{GHG}_{\min}, \text{GHG}_{\max}, \text{steps})$, solve $\min \text{Cost}$ subject to $\text{GHG}(\mathbf{X}) \le \varepsilon$ (applying quadratic penalty for GHG violations above $\varepsilon$).
     - Step D: Identify the knee-point (maximum marginal abatement $\Delta \text{GHG}/\Delta \text{Cost}$) as the [*Balanced Plan*].
3. [MANDATORY] Define Pareto Contract Dataclasses:
   - In `qiea_solver.py`, define `ParetoAlternative` and `ParetoSetResult` containing `strategy_id`, `definition`, `total_cost_usd`, `lifecycle_ghg_tco2e`, `fuel_tonnes`, `compliance_cost_usd`, and `genome`.
4. [MANDATORY] Dynamic Strategy Serializer:
   - Implement `pareto_result_to_dict(result: ParetoSetResult) -> dict` returning the exact structure expected by `scripts/build_demo_data.py` and frontend `ComparableRecommendations`.
5. [OPTIONAL] MILP / PSO Comparators:
   - If time permits, provide a simplified linear sub-solver in a separate script as an exact baseline comparator.

EXCLUSIVE FILES YOU MAY MODIFY:
- `src/nexfleet/optimization/solver.py`
- `src/nexfleet/optimization/qiea_solver.py`
- `src/nexfleet/optimization/sweep.py`
- `src/nexfleet/optimization/exposure.py`
- `tests/test_solver.py`
- `tests/test_qiea_solver.py`
- `tests/test_sweep.py`

FORBIDDEN FILES (DO NOT MODIFY):
- `src/nexfleet/optimization/objective.py` (Owned by Member 2)
- `src/nexfleet/fleet/baseline.py` (Owned by Member 2)
- `src/nexfleet/optimization/fuel_predictors.py` (Owned by Member 1)
- `scripts/build_demo_data.py` (Owned by Member 5)
- `frontend/*` (Owned by Member 5)

PRESERVE AND DO NOT REBUILD:
- Do NOT rewrite DEAP GA operators or tournament selection in `solver.py`.
- Do NOT rewrite the coordinate-descent polish `_local_search_refine()`.
- Do NOT rewrite qudit registers or Boltzmann mean-field initialization in `qiea_solver.py`.
- Do NOT create any web server or API framework.

ACCEPTANCE CRITERIA & TESTS TO RUN:
1. Run `python -m pytest tests/test_solver.py` — Must pass 100%.
2. Run `python -m pytest tests/test_qiea_solver.py` — Must pass 100%.
3. Run `python -m pytest tests/test_sweep.py` — Must pass 100%.
4. Verify `generate_pareto_frontier()` outputs 3 distinct non-dominated strategies (*Cheapest, Balanced, Greenest*) with valid genomes.

FINAL HANDOFF REPORT REQUIRED:
When complete, output a structured report stating:
- Verified Pareto frontier generation results (Cost vs. GHG for Cheapest, Balanced, Greenest).
- Exact import signature for Member 4 and Member 5 (`from nexfleet.optimization.qiea_solver import generate_pareto_frontier, pareto_result_to_dict`).
```

---

# MEMBER 4 IMPLEMENTATION PROMPT
### Role: Research Validation & Benchmarking Lead

```markdown
You are acting as MEMBER 4 (Research Validation & Benchmarking Lead / Quality Owner) on the NexFleet 2.0 project.

YOUR MISSION:
Execute the rigorous scientific research validation suite: 30-seed statistical benchmark battery comparing Classical GA vs. Quantum QIEA, formal ablation studies, end-to-end integration tests, and verification of all empirical claims.

MANDATORY FIRST STEPS:
1. Read `NEXFLEET_MASTER_RESEARCH_AND_PRODUCT_PLAN.md` (Parts 7, 11, 15).
2. Read `NEXFLEET_REMAINING_WORK_5_MEMBER_EXECUTION_PLAN.md` (Section 4, Member 4).
3. Inspect `scripts/benchmark_optimizers.py`, `scripts/benchmark_fuel_predictor.py`, `scripts/generate_benchmark_plots.py`, and all test files in `tests/`.

EXACT ASSIGNED TASKS:
1. [MANDATORY] End-to-End Computational Integration Test:
   - Create `tests/test_research_integration.py` verifying the complete un-mocked chain:
     `PredictorHub` (Member 1) $\rightarrow$ `evaluate_baseline_plan` (Member 2) $\rightarrow$ `run_ga` & `run_qiea` (Member 3) $\rightarrow$ `generate_pareto_frontier` (Member 3).
   - Assert that all generated genomes are 100% constraint-compliant (zero DWT cargo shortfall).
2. [MANDATORY] Statistical Multi-Seed Optimizer Benchmark:
   - Update `scripts/benchmark_optimizers.py` to support running $N=30$ seeds (or configurable $N$).
   - Compute mean, standard deviation, interquartile range (IQR), and Wilcoxon signed-rank test $p$-values comparing GA vs. QIEA runtime, switching points, and final solution cost.
3. [MANDATORY] Formal Research Ablation Study:
   - Implement ablation logging comparing:
     - QIEA with Boltzmann Mean-Field Prior vs. Uniform Initialization.
     - QIEA with Coordinate-Descent Polish ON vs. OFF.
     - GA with Coordinate-Descent Polish ON vs. OFF.
4. [MANDATORY] Update Output Research Reports:
   - Execute benchmark scripts and generate live, verified artifacts in `outputs/`:
     - `outputs/optimizer_benchmark.md` and `outputs/optimizer_benchmark.json`
     - `outputs/fuel_predictor_benchmark.md` and `outputs/fuel_predictor_benchmark.json`
5. [MANDATORY] Reconcile Documentation & Claims:
   - Audit all markdown documents to ensure zero unsupported claims (e.g., ensure no claims of quantum hardware supremacy, and document that local search accounts for final convergence).

EXCLUSIVE FILES YOU MAY MODIFY:
- `scripts/benchmark_optimizers.py`
- `scripts/benchmark_fuel_predictor.py`
- `scripts/generate_benchmark_plots.py`
- `tests/test_research_integration.py` (New file)
- `outputs/*` (All benchmark markdown, json, and plot artifacts)

FORBIDDEN FILES (DO NOT MODIFY):
- Core library implementations in `src/nexfleet/` (Report any algorithm defects to Members 1, 2, or 3).
- `scripts/build_demo_data.py` (Owned by Member 5).
- `frontend/*` (Owned by Member 5).

PRESERVE AND DO NOT REBUILD:
- Do NOT rewrite working test cases in `tests/`.
- Do NOT fabricate benchmark numbers; all figures must come from genuine script executions.

ACCEPTANCE CRITERIA & TESTS TO RUN:
1. Run `python -m pytest tests/` — All test files across the repository must pass 100%.
2. Run `python scripts/benchmark_optimizers.py --seeds 10` (or 30) — Must complete and write valid statistical markdown reports.
3. Verify that `tests/test_research_integration.py` runs end-to-end without errors.

FINAL HANDOFF REPORT REQUIRED:
When complete, output a structured report stating:
- Full test pass confirmation across all suites.
- Statistical summary of GA vs. QIEA (mean cost, std, runtime, Wilcoxon p-value).
- Confirmation that `outputs/` contains live, verified research artifacts ready for frontend embedding.
```

---

# MEMBER 5 IMPLEMENTATION PROMPT
### Role: Frontend & Product Integration Lead

```markdown
You are acting as MEMBER 5 (Frontend & Product Integration Lead) on the NexFleet 2.0 project.

YOUR MISSION:
Connect the Next.js 16 user interface to the live computational pipeline via `scripts/build_demo_data.py`, implement the 3-Way Benchmark Scorecard, dynamic Savings Waterfall, and Operational Dispatch CSV Export.

MANDATORY FIRST STEPS:
1. Read `NEXFLEET_MASTER_RESEARCH_AND_PRODUCT_PLAN.md` (Parts 8, 9, 10).
2. Read `NEXFLEET_REMAINING_WORK_5_MEMBER_EXECUTION_PLAN.md` (Section 4, Member 5).
3. Inspect `scripts/build_demo_data.py`, `frontend/app/`, `frontend/components/`, `frontend/lib/`, and `frontend/types/`.

EXACT ASSIGNED TASKS:
1. [MANDATORY] Dynamic Pipeline Orchestration (`scripts/build_demo_data.py`):
   - Update `build_demo_data.py` to import and call:
     - Member 1: `PredictorHub`
     - Member 2: `evaluate_baseline_plan` from `nexfleet.fleet.baseline`
     - Member 3: `generate_pareto_frontier` and `pareto_result_to_dict` from `nexfleet.optimization.qiea_solver`
   - Dynamically compute the baseline ledger, classical sweep, QIEA exposure, and Pareto alternatives (*Cheapest, Balanced, Greenest*), eliminating all static/mock hardcoded placeholders.
   - Write the genuine computed output to `outputs/demo_data.json` and copy to `frontend/public/demo_data.json`.
2. [MANDATORY] Tripartite Benchmark Scorecard UI Component:
   - In `frontend/components/` (or inside `/plans`), implement a clean side-by-side comparative table:
     **[Baseline BAU] vs. [Classical GA] vs. [Quantum QIEA] vs. [Balanced Pareto]**
     - Comparing: 5-Year Total Cost ($), Fuel Tonnes, WtW GHG (tCO2e), EU ETS ($), FuelEU Penalty ($), CII Ratings, Runtime (s), and Demand Fulfilled (%).
3. [MANDATORY] Dynamic Savings & Carbon Waterfall Visualization:
   - Connect the waterfall chart in `frontend/components/Charts.tsx` or `RecommendationView.tsx` to render the real computed variance decomposition:
     - Baseline Cost $\rightarrow$ Speed Optimization Savings $\rightarrow$ Alternative Fuel Premium $\rightarrow$ Shore Power Savings $\rightarrow$ FuelEU Pooling Credit $\rightarrow$ EU ETS Avoidance $\rightarrow$ Final Optimized Cost.
4. [MANDATORY] Operational Voyage Dispatch Table CSV Export:
   - In `frontend/components/` or `frontend/app/plans/page.tsx`, add a client-side one-click "Export Dispatch Plan (CSV)" button.
   - Generates and downloads a clean CSV file containing:
     `Vessel_ID, Year, Route, Speed_Knots, Fuel_Type, Shore_Power, FuelEU_Pool, Sea_Days, Fuel_Tonnes, GHG_tCO2e, CII_Rating, Voyage_Cost_USD`.
5. [MANDATORY] Remove Broken UI Callbacks:
   - Clean up `RecommendationView.tsx` so it cleanly uses the dynamic data pipeline rather than attempting dead HTTP requests to a non-existent port 8000 server.

EXCLUSIVE FILES YOU MAY MODIFY:
- `scripts/build_demo_data.py`
- `frontend/app/*` (All Page Routes)
- `frontend/components/*` (All UI Components)
- `frontend/lib/*` (Client Analytics & Helpers)
- `frontend/types/*` (TypeScript Definitions)
- `frontend/public/*` (Public Assets & Demo Data)

FORBIDDEN FILES (DO NOT MODIFY):
- Core algorithm implementations in `src/nexfleet/` (Must import functions without modifying library code).
- `tests/*` (Owned by Member 4).

PRESERVE AND DO NOT REBUILD:
- Preserve the existing high-quality terminal / trading desk styling in `globals.css` and `Charts.tsx`.
- Do NOT create any backend web server or API framework.

ACCEPTANCE CRITERIA & TESTS TO RUN:
1. Run `python scripts/build_demo_data.py` — Must execute all real algorithms and generate valid `demo_data.json`.
2. Run `npm run build` inside `frontend/` — Must compile with zero TypeScript or ESLint errors.
3. Verify in browser: Scorecard renders real numbers, waterfall matches computed ledgers, and CSV export button successfully downloads the dispatch table.

FINAL HANDOFF REPORT REQUIRED:
When complete, output a structured report stating:
- Build confirmation (`npm run build` green).
- Confirmation of dynamic demo data generation from real algorithms.
- Verification of 3-Way Scorecard, Savings Waterfall, and CSV Export functionality.
```

---

# TEAM EXECUTION RULES

To ensure flawless, conflict-free collaboration across all 5 members, the following rules must be observed:

### 1. Sequential Handoff Order
Development must follow the strictly defined dependency sequence:
$$\text{Member 1 (ML)} \longrightarrow \text{Member 2 (Baseline)} \longrightarrow \text{Member 3 (Pareto/Solvers)} \longrightarrow \text{Member 4 (Testing)} \longrightarrow \text{Member 5 (Frontend)}$$

### 2. Git & Branching Protocol
* Every member works in an isolated feature branch:
  * Member 1: `feat/m1-predictor-integration`
  * Member 2: `feat/m2-baseline-evaluator`
  * Member 3: `feat/m3-pareto-engine`
  * Member 4: `feat/m4-research-validation`
  * Member 5: `feat/m5-frontend-product-integration`
* Merging follows the sequential order. Member 4 and Member 5 merge only after Members 1, 2, and 3 have completed and validated their library functions.

### 3. Conflict Prevention & Prohibited Actions
* **Zero Ownership Collisions:** Never modify a file owned by another member. If an interface needs enhancement, coordinate with the file owner.
* **No Backend Web Server Work:** Do not spend time creating FastAPI or REST servers. Use the established local Python execution and demo data pipeline.
* **No Rebuilding Completed Code:** Reuse `PhysicsFuelModel`, GA operators, QIEA qudits, FuelEU pooling, and compliance ledgers as-is.

### 4. Definition of Done for Final Release
The project is complete and ready for SIH presentation when:
1. `pytest tests/` runs 100% green across all unit and research integration tests.
2. `python scripts/build_demo_data.py` runs end-to-end, generating dynamic data from real algorithms.
3. `npm run build` compiles with zero errors.
4. The Next.js dashboard interactively displays the **Baseline vs. GA vs. QIEA vs. Pareto Scorecard**, **Savings Waterfall**, and allows one-click **CSV Dispatch Table Export**.
