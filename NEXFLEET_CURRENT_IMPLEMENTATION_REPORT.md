# NEXFLEET 2.0: CURRENT IMPLEMENTATION REPORT
## Factual Codebase Audit, Execution Status, and Architecture Gap Analysis

**Document Status:** Complete & Factual Codebase Audit (Zero Assumptions)  
**Date of Audit:** September 11, 2026  
**Audited Target:** `himanshuvkm/Nexfleet` (Python Backend Core + Next.js 16 Frontend)  

---

# 1. Executive Summary of Current Reality

| Domain | Reality Status | Summary Verdict |
| :--- | :--- | :--- |
| **Python Optimization Core** | **WORKING (Offline/Batch)** | Pure Python modules for GA, QIEA (qudits), Coordinate Descent, FuelEU Pooling, and Scope Gating are implemented in `src/nexfleet/` and tested via offline batch scripts. |
| **Python ML/Prediction Models**| **WORKING (Offline/Batch)** | Physics Admiralty Model, LightGBM, MLP, and TT-SVD low-rank tensor decomposition are implemented in `src/nexfleet/optimization/fuel_predictors.py` on synthetic telemetry. |
| **Backend Web Server / API**  | **COMPLETELY MISSING** | **No FastAPI, Flask, Django, or aiohttp server exists anywhere in the repository.** No HTTP listening port or API process exists. |
| **Frontend Execution Mode**   | **STATIC / PRECOMPUTED MOCK** | Next.js frontend loads precomputed JSON dumps (`/public/demo_data.json`, 880 KB). An attempted live fetch in `RecommendationView.tsx` fails because no backend server exists. |
| **End-to-End System State**   | **DISCONNECTED** | The frontend and backend are completely decoupled; frontend cannot dynamically run Python solvers without manual CLI batch script re-runs. |

---

# 2. Detailed Technical Audit (Questions 1–16)

---

### 1. What is Currently Implemented and Working?
The following standalone Python computational modules are fully implemented:
* **Physics Admiralty Fuel Model:** `src/nexfleet/optimization/fuel_model.py` (`PhysicsFuelModel`) calculating cubic power energy, sea days, and bunker tonnes.
* **Classical Genetic Algorithm:** `src/nexfleet/optimization/solver.py` (`run_ga`) wrapping DEAP with tournament selection and coordinate-descent polish (`_local_search_refine`).
* **Quantum-Inspired QIEA Solver:** `src/nexfleet/optimization/qiea_solver.py` (`run_qiea`) with qudit probability vectors, Boltzmann mean-field initialization (`mean_field_init`), and Q-gate rotation dynamics.
* **FuelEU Compliance Pooling & Ledger:** `src/nexfleet/optimization/pooling.py` (`resolve_pool`) and `src/nexfleet/optimization/compliance_cost.py` (`compute_fueleu_ledger`).
* **Four-Regime Regulatory Scope Gating:** `src/nexfleet/compliance/scope_gating.py` (`applicable_regimes`) gating CII, EU ETS, FuelEU, and NZF applicability by gross tonnage and voyage pattern.
* **Carbon Price Sweep Orchestrator:** `src/nexfleet/optimization/sweep.py` (`run_sweep`) evaluating 11 grid points ($0 to $1,000/t).
* **Batch Data Builder Script:** `scripts/build_demo_data.py` generating `outputs/demo_data.json`.

---

### 2. What is Partially Implemented?
* **Multi-Objective Trade-Offs:** The frontend displays three cards ("Cheapest", "Balanced", "Greenest"), but they are produced via scalarized penalties during offline sweeps rather than an interactive $\varepsilon$-constraint Pareto frontier generator.
* **Live Re-Solve UI Component:** `frontend/components/RecommendationView.tsx` has form inputs for Carbon Price and Cargo Demand Multiplier, but the fetch call fails because no backend API exists.
* **Quantum-Inspired Fuel Prediction:** Tensor-Train SVD (`TensorTrainResidualFuelModel`) is implemented on a discretized 4D grid, but dynamic quantum-inspired parameter optimization (QEPS/QNN) is not yet built.

---

### 3. What is Only Mock / Static / Demo?
* **Next.js Global State (`AtlasContext.tsx`):** Hardcoded to fetch `/demo_data.json` on mount. All metrics, maps, sensitivity curves, and switching points come from this static 880 KB JSON file.
* **Interactive Sliders in Frontend:** Moving the carbon price slider on `/sensitivity` or `/exposure` merely looks up the nearest precomputed grid point in `data.sweep.grid_points`; it does **not** execute an optimization solver.
* **Voyage Routes & Maps:** `LeafletMap.tsx` renders static waypoints hardcoded in `ROUTES_GEO` inside `scripts/build_demo_data.py`.

---

### 4. Does a Backend Currently Exist?
* **Backend Web Framework:** **NONE.** (No FastAPI, Flask, Starlette, or Django).
* **Backend Entry File:** **NONE.** (There is no `main.py`, `app.py`, `server.py`, or `api/` directory in `src/nexfleet`).
* **Existing Endpoints:** **NONE.**
* **How to Start It:** Cannot be started because no server script exists.
* **Do Endpoints Work:** **NO.** When `RecommendationView.tsx` tries to `POST http://localhost:8000/api/recommendations`, the browser returns a connection refused error, displaying: *"Solver service unreachable. Start the Python API, then try again."*

---

### 5. Is the Frontend Connected to the Backend?
* **Connection Status:** **NOT CONNECTED.**
* **Exact Fetch Calls in Frontend:**
  1. `frontend/lib/AtlasContext.tsx:105` $\rightarrow$ `fetch('/demo_data.json')` *(Static public asset)*.
  2. `frontend/lib/AtlasContext.tsx:119-121` $\rightarrow$ `fetch('/optimizer_scaling_benchmark.json')`, `fetch('/optimizer_scaling_fair_start.json')`, `fetch('/optimizer_phase6_benchmark.json')` *(Static benchmark files)*.
  3. `frontend/components/RecommendationView.tsx:270` $\rightarrow$ `fetch(`${liveApiBaseUrl}/api/recommendations`)` *(Dead endpoint, fails silently)*.

---

### 6. What Prediction Models Currently Exist?

| Model Name | Exact File Path | Class / Function Name | Status | Executable? |
| :--- | :--- | :--- | :--- | :--- |
| **Physics Admiralty Model** | `src/nexfleet/optimization/fuel_model.py` | `PhysicsFuelModel.fuel_consumption_tonnes()` | **WORKING** | Yes (Deterministic Python) |
| **LightGBM Residual Regressor**| `src/nexfleet/optimization/fuel_predictors.py` | `LightGbmResidualFuelModel.fit()` / `predict` | **WORKING** | Yes (Requires `lightgbm`) |
| **MLP Neural Regressor** | `src/nexfleet/optimization/fuel_predictors.py` | `MlpResidualFuelModel.fit()` / `predict` | **WORKING** | Yes (Requires `scikit-learn`) |
| **Tensor-Train SVD Predictor**| `src/nexfleet/optimization/fuel_predictors.py` | `TensorTrainResidualFuelModel.fit()` / `predict` | **WORKING** | Yes (Low-rank SVD over discretized grid) |
| **Quantum-Inspired Neural Predictor** | N/A | N/A | **MISSING** | Not yet implemented |

---

### 7. What Optimization Algorithms Currently Exist?

| Algorithm Name | Exact File Path | Class / Function Name | Status | Executable? |
| :--- | :--- | :--- | :--- | :--- |
| **Classical Genetic Algorithm**| `src/nexfleet/optimization/solver.py` | `run_ga()` | **WORKING** | Yes (DEAP + coordinate descent) |
| **Quantum-Inspired QIEA** | `src/nexfleet/optimization/qiea_solver.py` | `run_qiea()` | **WORKING** | Yes (Qudit registers + Q-gate rotation) |
| **Coordinate-Descent Local Polish**| `src/nexfleet/optimization/solver.py` | `_local_search_refine()` | **WORKING** | Yes (Deterministic single-slot search) |
| **Multi-Objective $\varepsilon$-Constraint**| N/A | N/A | **MISSING** | Currently scalarized single-objective only |
| **Exact MILP Solver** | N/A | N/A | **MISSING** | Not yet implemented |

---

### 8. What Regulatory, Cost, Emission, CII, and Constraint Calculations Exist?
* **FuelEU Maritime:**
  * Target GHG intensity formula: `src/nexfleet/optimization/compliance_cost.py:fueleu_target_intensity()` [WORKING]
  * Compliance balance formula: `src/nexfleet/regulatory/implied_price.py:fueleu_compliance_balance_gco2eq()` [WORKING]
  * Multi-year banking/borrowing ledger: `src/nexfleet/optimization/compliance_cost.py:compute_fueleu_ledger()` [WORKING]
  * Cross-vessel compliance pooling: `src/nexfleet/optimization/pooling.py:resolve_pool()` [WORKING]
* **EU ETS Maritime:**
  * 50%/100% scope calculation & EUA allowance cost: `src/nexfleet/optimization/compliance_cost.py:eu_ets_cost()` [WORKING]
* **IMO Carbon Intensity Indicator (CII):**
  * Annual $Z$-factor reduction & rating boundaries: `src/nexfleet/optimization/compliance_cost.py:cii_cost()` [WORKING]
* **IMO Net-Zero Framework (NZF):**
  * Two-tier remedial unit fee calculation: `src/nexfleet/optimization/compliance_cost.py:nzf_cost()` [WORKING]
* **Operational Constraints:**
  * Route DWT capacity shortfall penalty: `src/nexfleet/optimization/constraints.py:demand_shortfall_penalty()` [WORKING]
  * Engine-fuel compatibility filter: `src/nexfleet/fleet/model.py:option_menu_for()` [WORKING]

---

### 9. What User Inputs Are Currently Accepted?
* **In Python Code (`fleet.json`, `prices.json`):**
  * 10 fixed synthetic vessels (A1–A4, B1–B3, C1–C3) across 3 bands.
  * 6 fixed routes with hardcoded distances and DWT requirements.
  * 6 fixed fuel prices ($/tonne) for HFO, VLSFO, MGO, LNG, B30, and Methanol.
* **In Frontend UI:**
  * The user **cannot** currently create vessels, edit routes, or upload baseline operational plans. The UI only provides sliders that read from pre-calculated JSON keys.

---

### 10. What Outputs Are Currently Generated?
* **Offline Files (`outputs/`):**
  * `outputs/demo_data.json` (886 KB JSON payload for Next.js).
  * `outputs/optimizer_benchmark.json` and `outputs/optimizer_benchmark.md` (GA vs. QIEA metrics).
  * `outputs/fuel_predictor_benchmark.json` and `outputs/fuel_predictor_benchmark.md` (LOVO MAPE metrics).
* **Missing Outputs:**
  * No user-specific exportable operational voyage schedule (CSV/PDF).
  * No side-by-side Baseline vs. GA vs. QIEA dynamic comparison matrix.
  * No dynamic savings waterfall attribution ledger.

---

### 11. What is the Actual Current End-to-End Flow?

```
┌────────────────────────────────────────────────────────────────────────────────────────┐
│                              ACTUAL CURRENT SYSTEM FLOW                                │
├────────────────────────────────────────────────────────────────────────────────────────┤
│ 1. Developer manually executes in CLI:                                                 │
│    `python scripts/build_demo_data.py`                                                 │
│                                                                                        │
│ 2. Python backend computes sweeps using `fleet.json` and writes:                       │
│    `outputs/demo_data.json`  ──►  Copied to `frontend/public/demo_data.json`           │
│                                                                                        │
│ 3. User launches Next.js frontend (`npm run dev`) at `http://localhost:3000`           │
│                                                                                        │
│ 4. React App mounts `AtlasContext.tsx` ──► `fetch('/demo_data.json')`                  │
│                                                                                        │
│ 5. Frontend renders pre-baked data. When user changes sliders, the app filters the     │
│    in-memory JSON. Live re-solve button fails because no HTTP API exists.              │
└────────────────────────────────────────────────────────────────────────────────────────┘
```

---

### 12. Which Modules Are Disconnected?
1. **Frontend $\leftrightarrow$ Python Backend:** Completely disconnected at runtime. No REST or WebSocket bridge exists.
2. **Predictors $\leftrightarrow$ Solver Pipeline:** Predictors (`fuel_predictors.py`) run in offline benchmark scripts (`benchmark_fuel_predictor.py`), but `objective.py` defaults to calling raw `PhysicsFuelModel` during GA/QIEA solves unless manually injected.
3. **Baseline Comparison $\leftrightarrow$ Optimization Output:** No dedicated module exists to evaluate the user's status-quo operational plan; all savings are measured against arbitrary zero-points or $0 carbon price sweeps.

---

### 13. Which Features Are Missing According to the SIH Problem Statement?
1. **Quantum-Inspired Parameterized Fuel Prediction:** True quantum-inspired residual training (QEPS / QNN) beyond static low-rank TT-SVD.
2. **Dynamic Alternative Fuel & Bunkering Scenarios:** User-defined fuel price and port availability toggles.
3. **Hydrogen and Ammonia Representation:** Inclusion of zero-carbon fuel pathways in the fuel catalog and option menus.
4. **Schedule Reliability & Laycan Constraints:** Explicit penalty functions for vessel sea days exceeding contractual transit windows.

---

### 14. Which Features Are Missing According to the Master Plan?
1. **FastAPI REST Application (`src/nexfleet/api/`):** Providing `/api/predict`, `/api/optimize`, and `/api/baseline` endpoints.
2. **Dedicated Baseline Plan Evaluator (`src/nexfleet/fleet/baseline.py`):** Ingesting and evaluating historical operational status quo.
3. **Multi-Objective $\varepsilon$-Constraint Engine:** Systematically generating the non-dominated Pareto front.
4. **Interactive Scenario & Baseline UI (`/scenario`):** Enabling fleet operators to input real-world fleet parameters.
5. **Tripartite Benchmark Scorecard:** Displaying Baseline vs. GA vs. QIEA side-by-side with convergence metrics.
6. **Actionable Operational Dispatch Exporter:** One-click CSV/PDF export of vessel assignments and speed schedules.

---

### 15. What Should Be Reused Instead of Rebuilt?
Do **NOT** rebuild the following high-value, thoroughly tested components:
* ✅ `src/nexfleet/compliance/scope_gating.py` (Flawless 4-regime applicability rules).
* ✅ `src/nexfleet/optimization/pooling.py` (Complete FuelEU compliance pooling solver).
* ✅ `src/nexfleet/optimization/compliance_cost.py` (Exhaustive FuelEU ledger & EU ETS formulas).
* ✅ `src/nexfleet/optimization/fuel_model.py` (Clean Admiralty physics power formulations).
* ✅ `src/nexfleet/optimization/genome.py` (Structured categorical decision representations).
* ✅ `src/nexfleet/optimization/solver.py` & `qiea_solver.py` (Core search mechanisms and coordinate descent).
* ✅ `frontend/components/Charts.tsx` & visual components (High quality terminal UI styling).

---

### 16. What Exactly Needs to Be Added or Fixed?

```
┌────────────────────────────────────────────────────────────────────────────────────────┐
│                              REQUIRED ACTIONABLE FIXES                                 │
├────────────────────────────────┬───────────────────────────────────────────────────────┤
│ Module to Add / Fix            │ Exact Action Required                                 │
├────────────────────────────────┼───────────────────────────────────────────────────────┤
│ **1. FastAPI REST Gateway**    │ Create `src/nexfleet/api/` with `/api/optimize`,      │
│                                │ `/api/predict`, `/api/baseline`, and `/api/scenario`. │
├────────────────────────────────┼───────────────────────────────────────────────────────┤
│ **2. Shared Pydantic Schemas** │ Create `src/nexfleet/schema/contracts.py` as the      │
│                                │ single data contract between backend and frontend.    │
├────────────────────────────────┼───────────────────────────────────────────────────────┤
│ **3. Baseline Plan Evaluator** │ Implement `src/nexfleet/fleet/baseline.py` to evaluate│
│                                │ status-quo fleet operations.                          │
├────────────────────────────────┼───────────────────────────────────────────────────────┤
│ **4. Quantum Predictor Arm**   │ Add `QuantumInspiredNeuralResidualModel` to           │
│                                │ `fuel_predictors.py` alongside TT-SVD and LightGBM.   │
├────────────────────────────────┼───────────────────────────────────────────────────────┤
│ **5. Multi-Objective Engine**  │ Implement $\varepsilon$-constraint generator in        │
│                                │ `qiea_solver.py` to yield genuine Pareto alternatives.│
├────────────────────────────────┼───────────────────────────────────────────────────────┤
│ **6. Live Frontend Wiring**    │ Connect Next.js UI to live FastAPI backend via        │
│                                │ environment-configured client API calls.              │
├────────────────────────────────┼───────────────────────────────────────────────────────┤
│ **7. 3-Way Scorecard & Export**│ Build the dynamic side-by-side benchmark table and    │
│                                │ CSV voyage dispatch table exporter.                   │
└────────────────────────────────┴───────────────────────────────────────────────────────┘
```

---

# 3. Comparative Architecture Diagrams

### Diagram A: Current Actual Flow (Offline & Precomputed)

```
[ Developer CLI ] ──► `python scripts/build_demo_data.py`
                             │
                             ▼
                 [ Offline Python Solvers ]
                 (GA & QIEA in `src/nexfleet/`)
                             │
                             ▼
                 `outputs/demo_data.json` (Static 880 KB Dump)
                             │
                             ▼ (Manual File Copy)
                 `frontend/public/demo_data.json`
                             │
                             ▼ (HTTP GET on Mount)
                 [ Next.js React UI ] ──► User manipulates static filters
                                          (Live re-solve fails: 404/Connection Refused)
```

---

### Diagram B: Target Required Flow (Live & Interactive)

```
                                  [ Fleet Operator / Browser ]
                                                │
                                                ▼
                         [ Next.js 16 Interactive Frontend Client ]
                      (Scenario Setup | Model Lab | Plans | Dispatch)
                                                │
                                     HTTP POST / GET (JSON)
                                                ▼
                           [ FastAPI Asynchronous REST Gateway ]
                     (/api/scenario, /api/predict, /api/optimize, /api/export)
                                                │
                 ┌──────────────────────────────┼──────────────────────────────┐
                 ▼                              ▼                              ▼
     [ Baseline Evaluator ]         [ Predictive Fuel Engine ]     [ Dual Optimization Core ]
     `nexfleet.fleet.baseline`      • Physics Admiralty Model      • Classical GA (DEAP)
     • Ingests Status Quo BAU       • Quantum-Inspired TT-SVD      • Quantum-Inspired QIEA
     • Computes Base Cost & GHG     • QNN Residual Regressor       • ε-Constraint Pareto Core
                                    • LightGBM / MLP Baselines                 │
                                                │                              │
                                                └──────────────┬───────────────┘
                                                               ▼
                                                  [ Regulatory & Scope Engine ]
                                                  • FuelEU Ledger & Pooling
                                                  • EU ETS Carbon Compliance
                                                  • IMO CII Trajectory (A–E)
                                                               │
                                                               ▼
                                                  [ Explainability & Dispatch ]
                                                  • 3-Way Benchmark Scorecard
                                                  • Savings Waterfall Model
                                                  • CSV/PDF Dispatch Serializer
```

---

### Diagram C: Gap Analysis Between Current and Target

```
┌───────────────────────────────────────┬───────────────────────────────────────┬───────────────────────────────┐
│ Current State                         │ Target State                          │ Delta / Engineering Required  │
├───────────────────────────────────────┼───────────────────────────────────────┼───────────────────────────────┤
│ No backend server exists              │ FastAPI REST application running      │ Create `src/nexfleet/api/`    │
│                                       │ on port 8000                          │ with routing and controllers  │
├───────────────────────────────────────┼───────────────────────────────────────┼───────────────────────────────┤
│ Frontend loads static demo_data.json  │ Frontend calls live FastAPI endpoints │ Implement API client in       │
│ on page load                          │ dynamically based on user input       │ `frontend/lib/api.ts`         │
├───────────────────────────────────────┼───────────────────────────────────────┼───────────────────────────────┤
│ No baseline (BAU) evaluator           │ Dedicated status-quo evaluator        │ Implement `baseline.py` in    │
│ exists                                │ establishing reference zero-point     │ `src/nexfleet/fleet/`         │
├───────────────────────────────────────┼───────────────────────────────────────┼───────────────────────────────┤
│ Prediction models disconnected        │ Prediction models unified behind      │ Expose uniform `Predictor`    │
│ from solver execution                 │ clean interface for solver and API    │ protocol in `fuel_predictors` │
├───────────────────────────────────────┼───────────────────────────────────────┼───────────────────────────────┤
│ Scalarized single-objective solves    │ Multi-objective ε-constraint Pareto   │ Implement Pareto generator in │
│ only                                  │ frontier (Cost vs GHG vs Delay)       │ `qiea_solver.py`              │
├───────────────────────────────────────┼───────────────────────────────────────┼───────────────────────────────┤
│ Benchmark results scattered in        │ Dynamic Tripartite Scorecard          │ Build side-by-side scorecard  │
│ offline markdown files                │ rendered directly in Next.js UI       │ component in frontend         │
├───────────────────────────────────────┼───────────────────────────────────────┼───────────────────────────────┤
│ No operational plan export            │ One-click CSV / PDF dispatch table    │ Implement dispatch serializer │
│ available                             │ for shipboard deployment              │ and download handler          │
└───────────────────────────────────────┴───────────────────────────────────────┴───────────────────────────────┘
```

---

# 4. Final Conclusion & Ready State

* **The computational core is strong and mathematically sound:** Algorithms for GA, QIEA, FuelEU pooling, and Admiralty physics are fully written and tested.
* **The missing link is architectural integration:** The platform requires a lightweight FastAPI gateway, shared Pydantic data schemas, a baseline plan evaluator, dynamic frontend wiring, and the quantum-inspired prediction residual model.
* **All existing computational logic must be preserved and reused directly** within the 5-member modular plan without unnecessary rewrites.
