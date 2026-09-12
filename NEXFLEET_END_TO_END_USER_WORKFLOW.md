# NexFleet 2.0 End-to-End User & Operational Workflow Guide

This document provides a practical, step-by-step manual testing guide for verifying the complete NexFleet 2.0 application end-to-end. It details system setup, complete data flow architecture, route-by-route manual testing procedures, input-to-output examples, data lineage verification steps, expected output checklists, troubleshooting, and final acceptance criteria.

---

## 1. How to Start the System

### Prerequisites & Working Directory
Ensure you are in the project root directory:
```powershell
cd c:\Users\Akshat\Downloads\Projects\Nexfleet
```

### Step 1: Generate Demo Data (`demo_data.json`)
Run the Python data generation pipeline to build the computational outputs for the frontend:

- **Fast Iteration Mode (Dev / Smoke Test)**:
  ```powershell
  python -u scripts/build_demo_data.py --fast
  ```
  *Expected Output*:
  ```text
  ============================================================
  NexFleet: Building demo_data.json [--fast dev mode] [optimizer=ga]
  ============================================================
  [1/6] Loading fleet, prices, and regulations specifications...
  [1b/6] Evaluating Business-As-Usual (BAU) status-quo baseline plan...
  [1c/6] Generating multi-objective Epsilon-Constraint Pareto frontier...
  [2/6] Running carbon-price sweep ($0–$1000, step $25, warm-started)...
  [3/6] Validating scenario axis positions against price grid...
  [4/6] Computing multi-scenario exposure map...
  [5/6] Cross-checking classical exposure against real tensor-network mutual information...
  [6/6] Assembling final demo_data.json payload...

  Writing outputs/demo_data.json...
  Copying to frontend/public/demo_data.json...
  Successfully completed build_demo_data.py!
  ```

- **Production Mode (Full Convergence)**:
  ```powershell
  python -u scripts/build_demo_data.py
  ```

### Step 2: Start the Next.js Frontend
In a separate terminal or the same workspace, navigate to `frontend/` and launch the dev server:
```powershell
cd frontend
npm run dev
```
*Expected Output*:
```text
> frontend-claude@0.1.0 dev
> next dev --turbopack

✓ Ready in 1.2s
- Local: http://localhost:3000
```
Open [http://localhost:3000](http://localhost:3000) in your web browser.

---

## 2. Complete Data Flow Architecture

The following pipeline details how data flows from Python backend calculations into frontend UI components:

```
[Fleet Specs / Fuel Prices / Regulatory Regimes]
                        │
                        ▼
    ┌───────────────────────────────────────┐
    │     scripts/build_demo_data.py        │
    └───────────────────┬───────────────────┘
                        │
       ┌────────────────┼────────────────┐
       ▼                ▼                ▼
┌──────────────┐ ┌──────────────┐ ┌──────────────┐
│  Baseline    │ │ Pareto QIEA  │ │ Price Sweep  │
│  Evaluator   │ │ Optimization │ │ & Exposure   │
│(baseline.py) │ │(qiea_solver) │ │ (sweep.py)   │
└──────┬───────┘ └──────┬───────┘ └──────┬───────┘
       │                │                │
       └────────────────┼────────────────┘
                        │
                        ▼
         outputs/demo_data.json
         frontend/public/demo_data.json
                        │
                        ▼
     ┌─────────────────────────────────────┐
     │  DataGate & AtlasContext (React)    │
     │  Reads /public/demo_data.json       │
     └──────────────────┬──────────────────┘
                        │
                        ▼
┌───────────────────────────────────────────────────────────┐
│                    Frontend UI Pages                      │
├─────────────┬─────────────┬─────────────┬─────────────────┤
│ Overview    │ Plans       │ Prediction  │ Engine /        │
│ (/)         │ (/plans)    │ (/predict)  │ Exposure        │
└─────────────┴─────────────┴─────────────┴─────────────────┘
```

1. **User Input / Scenario Specs**: `data/fleet.json`, `data/prices.json`, and regulatory loaders in `src/nexfleet/regulatory/loader.py`.
2. **Baseline Evaluator** (`nexfleet.fleet.baseline.evaluate_baseline_plan`): Evaluates Business-As-Usual (BAU) status quo voyage assignments across 10 vessels over 2026–2030 under CII, EU ETS, FuelEU Maritime, and Net-Zero Framework (NZF).
3. **Pareto Optimization** (`nexfleet.optimization.qiea_solver.generate_pareto_frontier`): Solves Epsilon-Constraint multi-objective frontier (*Cheapest*, *Balanced*, *Greenest* alternatives). Calculates per-vessel metrics (`speed_knots`, `fuel_tonnes`, `ghg_tco2e`, `cii_rating`, `voyage_cost_usd`).
4. **Carbon Price Sweep & Exposure Analysis** (`nexfleet.optimization.sweep`, `nexfleet.optimization.exposure`): Evaluates 41 price points ($0–$1,000/tCO₂e) and computes regulatory cost spread and Born-machine tensor-network mutual information (`mps_crosscheck`).
5. **Serialization**: `build_demo_data.py` writes computed payload including `waterfall_breakdown` to `outputs/demo_data.json` and `frontend/public/demo_data.json`.
6. **React Context (`AtlasContext`)**: Fetches `demo_data.json` via `DataGate.tsx` and exposes state (`price`, `closest`, `currentConfig`, `baselineConfig`, `unstableKeys`, `cargoDemand`) to all page components.

---

## 3. Route-by-Route Manual Testing

### Route 1: `/` (Overview)
- **URL**: `http://localhost:3000/`
- **Controls to Test**: Carbon Tax Price Slider ($0–$1,000/tCO₂e), Scenario buttons (*Approved Text*, *Tuvalu Levy*, *FuelEU Baseline*), Interactive Map zoom/pan.
- **Expected Behavior**:
  - Dragging slider from $0/t to $300/t updates "Selected plan", "Five-year fleet cost", "Low-carbon vessel-years", and "Bunker mass".
  - Map route lines highlight assigned trade corridors for 2028.
- **Powering Data Fields**: `data.sweep.grid_points`, `data.routes_geo`, `deepestCut(data)`, `data.exposure.plan_spread`.

### Route 2: `/plans` (Plans & Recommendations)
- **URL**: `http://localhost:3000/plans`
- **Controls to Test**:
  - Compare the 3 Plan Cards (*Cheapest, Balanced, Greenest*).
  - Inspect Abatement Curve Chart.
  - Review 3-Way Scorecard table comparing Baseline (BAU), Classical GA, Quantum QIEA, and Balanced Pareto.
  - Review **Dynamic Savings & Emissions Waterfall** bars.
  - Click **"Export Dispatch Plan (CSV)"**.
- **Expected Behavior**:
  - Waterfall shows exact calculated steps (`Baseline Operational Cost` → `Speed Profile & Charter Time` → `Fuel & Shore Power` → `Penalty Avoidance` → `Final Optimized Cost`).
  - Clicking "Export Dispatch Plan (CSV)" downloads `nexfleet_dispatch_schedule.csv` with 12 real columns.
- **Powering Data Fields**: `data.baseline.waterfall_breakdown`, `data.comparable_recommendations.alternatives`.

### Route 3: `/prediction` (Fuel Consumption Prediction)
- **URL**: `http://localhost:3000/prediction`
- **Controls to Test**: Inspect DotPlot per-vessel held-out error distribution, view Model Comparison Table.
- **Expected Behavior**: Displays leave-one-vessel-out (LOVO) cross-validation MAPE %, R² variance explained, and stability spread for Physics vs LightGBM vs MLP vs Tensor-Train models.
- **Powering Data Fields**: `data.fuel_predictor_benchmark` (`arms`, `per_fold_mape_percent`, `fold_vessel_ids`).

### Route 4: `/engine` (Quantum-Inspired Solver Engine)
- **URL**: `http://localhost:3000/engine`
- **Controls to Test**: Review head-to-head scaling advantage chart, inspect ablation stages, verify exact brute-force reference optimum gap.
- **Expected Behavior**: Displays paired GA vs QIEA win ratio, median cost gap per fleet size (10 to 80 vessels), initialization vs polish search attribution, and exact reference optimum gap ($0.00).
- **Powering Data Fields**: `data.optimizer_benchmark` (`scaling`, `search_attribution`, `exact_reference`).

### Route 5: `/exposure` (Regulatory Uncertainty Exposure)
- **URL**: `http://localhost:3000/exposure`
- **Controls to Test**: Review Regulatory Uncertainty Spread, Capex Exposure, Confidence Tiers Table, and Tensor-Network Decision Confidence Table.
- **Expected Behavior**: Displays plan cost spread in INR Crore and USD, capex at risk, and Born-machine mutual information (bits) sorted by decision confidence.
- **Powering Data Fields**: `data.exposure` (`plan_spread`, `capex_exposure`, `summary`, `mps_crosscheck`).

### Route 6: `/fleet-matrix` (Fleet Decision Matrix)
- **URL**: `http://localhost:3000/fleet-matrix`
- **Controls to Test**:
  - Drag Carbon Tax Price Slider.
  - Toggle Strategy View buttons (*Fuel Option*, *Speed Profile*, *Assigned Trade Route*, *Shore Power*, *FuelEU Pooling*, *Banking/Borrowing*).
  - Click **"Export Matrix CSV"**.
- **Expected Behavior**:
  - Matrix table updates 10 vessels × 5 years (2026–2030) with cell-flip highlighting against the $0/t baseline.
  - Clicking "Export Matrix CSV" downloads `nexfleet_matrix_<field>_p<price>.csv`.
- **Powering Data Fields**: `data.fleet.vessels`, `AtlasContext` (`currentConfig`, `baselineConfig`, `unstableKeys`).

### Route 7: `/sensitivity` (Carbon Price Sensitivity)
- **URL**: `http://localhost:3000/sensitivity`
- **Controls to Test**: Drag Carbon Price Slider, inspect the 4 small-multiple panels (*Total fleet cost*, *Compliance bill*, *Lifecycle GHG*, *Bunker mass*).
- **Expected Behavior**: Each panel updates its line chart marker to the selected price point; highlights plateau lock-in region above Tier 2 remedial price ceiling.
- **Powering Data Fields**: `data.sweep.grid_points` (41 grid points).

### Route 8: `/fuels` (Fuel Transition & Catalog)
- **URL**: `http://localhost:3000/fuels`
- **Controls to Test**: Inspect low-carbon vessel-year transition summary strip, review Fuel Catalog and Switching Thresholds table, view Well-to-wake GHG Intensity Ladder chart.
- **Expected Behavior**: Displays switching thresholds ($/tCO₂e) at which alternative fuels (LNG, Bio-VLSFO, Green Methanol, E-Ammonia, Green Hydrogen) enter the fleet.
- **Powering Data Fields**: `data.fleet.fuel_properties`, `fuelCatalog(data)`, `fuelEntryPrices(data)`.

### Route 9: `/guide` (Platform Guide)
- **URL**: `http://localhost:3000/guide`
- **Controls to Test**: Scroll through methodology sections, click cross-page navigation links.
- **Expected Behavior**: Displays plain-English explanation of regulatory regimes, solver mechanics, scenario tick positions, and data provenance.
- **Powering Data Fields**: `data.sweep.scenario_ticks`, `data.exposure.plan_spread`, `data.optimizer_benchmark`.

---

## 4. Input-to-Output Manual Verification Scenarios

### Scenario A: Carbon Price Slider Adjustment ($0/t → $300/t)
1. Open `/plans` or `/fleet-matrix`.
2. Move the slider to `$300/t`.
3. **Visible Change**:
   - On `/plans`: The active operating scenario reflects `$300/tCO₂e`.
   - On `/fleet-matrix`: Multiple cells in the 2026–2030 matrix switch to green cell-flip styling (e.g., VLSFO → Bio-VLSFO or E-Ammonia, speed band reduction).
4. **Why It Happens**: `AtlasContext` updates `price` state, finding the nearest precomputed grid point in `data.sweep.grid_points` and comparing `currentConfig` against `baselineConfig` ($0/t).

### Scenario B: Dispatch CSV Export Verification
1. Navigate to `/plans`.
2. Scroll to the bottom of the page and click **"Export Dispatch Plan (CSV)"**.
3. Open the downloaded `nexfleet_dispatch_schedule.csv` in Excel or a text editor.
4. **Verification**: Confirm all 12 columns are present with valid numerical values:
   `Vessel_ID, Year, Route, Speed_Knots, Fuel_Type, Shore_Power, FuelEU_Pool, Borrow_Election, Fuel_Tonnes, GHG_tCO2e, CII_Rating, Voyage_Cost_USD`.
5. **Why It Happens**: `exportDispatchCsv` consumes enriched `configuration` items generated by `pareto_result_to_dict()` in `qiea_solver.py`.

### Scenario C: Fleet Matrix CSV Export Verification
1. Navigate to `/fleet-matrix`.
2. Select **"Speed Profile"** strategy view button.
3. Set Carbon Tax Price Slider to `$200/t`.
4. Click **"Export Matrix CSV"**.
5. Open the downloaded `nexfleet_matrix_speed_band_index_p200.csv`.
6. **Verification**: Confirm the CSV contains 10 vessel rows with columns `Vessel_ID`, `Vessel_Class`, `DWT_Tonnes`, `Strategy_Field`, `Carbon_Price_USD`, `2026`, `2027`, `2028`, `2029`, `2030`.

---

## 5. Data-Lineage Verification (Audit Guide)

To prove that UI values are dynamically derived from Python outputs rather than hardcoded:

1. **Locate Source Value in `frontend/public/demo_data.json`**:
   Open `frontend/public/demo_data.json` and inspect `baseline.waterfall_breakdown`:
   ```json
   "waterfall_breakdown": {
     "baseline_total_usd": 823537676.62,
     "balanced_total_usd": 392085013.54,
     "speed_time_savings_usd": -129359818.42,
     "fuel_ops_savings_usd": 402036496.65,
     "compliance_savings_usd": 158775984.85
   }
   ```

2. **Verify Frontend Component Consumption**:
   In `frontend/components/RecommendationView.tsx`, observe `SavingsWaterfallSection`:
   ```tsx
   const waterfall = baseline.waterfall_breakdown;
   const steps = [
     { label: 'Baseline Operational Cost (BAU)', value: waterfall.baseline_total_usd, kind: 'base' },
     { label: 'Speed Profile & Charter Time Optimization', value: -waterfall.speed_time_savings_usd, kind: 'saving' },
     { label: 'Alternative Fuel & Shore Power Selection', value: -waterfall.fuel_ops_savings_usd, kind: 'saving' },
     { label: 'EU ETS & FuelEU Penalty Avoidance', value: -waterfall.compliance_savings_usd, kind: 'saving' },
     { label: 'Final Optimized Balanced Plan Cost', value: waterfall.balanced_total_usd, kind: 'final' },
   ];
   ```

3. **Safe Modification Test**:
   - Temporarily edit `frontend/public/demo_data.json` and change `baseline_total_usd` to `900000000.0`.
   - Refresh `http://localhost:3000/plans`.
   - Verify that the first waterfall row immediately updates to `$900.0M`.
   - Revert `frontend/public/demo_data.json`.

---

## 6. Expected Output Checklist

- [x] **`/` (Overview)**: Renders live price slider, hero savings percentage, fuel mix donut chart, Leaflet map with 6 route polylines, and proof strip links.
- [x] **`/plans` (Plans)**: Renders 3 Plan Cards (*Cheapest, Balanced, Greenest*), Pareto Abatement Curve with marginal abatement cost labels ($/tCO₂e), 3-Way Benchmark Scorecard, Dynamic Savings Waterfall, and Dispatch CSV Exporter.
- [x] **`/prediction` (Prediction)**: Renders best model headline MAPE error %, DotPlot for 10 vessel folds across 4 models, and Model Comparison Table.
- [x] **`/engine` (Engine)**: Renders scaling advantage headline bar, paired wins (e.g. 30/30), ablation range bars, and exact brute-force reference gap ($0.00).
- [x] **`/exposure` (Exposure)**: Renders plan spread (INR Crore & USD), capex exposure, confidence tiers table, and Born-machine mutual information crosscheck table.
- [x] **`/fleet-matrix` (Fleet Matrix)**: Renders 10-vessel × 5-year decision matrix with cell-flip highlighting, strategy field toggle, cargo demand table, fuel options table, and Matrix CSV Exporter.
- [x] **`/sensitivity` (Sensitivity)**: Renders 4 small-multiple panels (*Total Cost, Compliance, GHG, Fuel Mass*), plateau shading above remedial price ceiling, and selected point summary bar.
- [x] **`/fuels` (Fuels)**: Renders transition summary strip, FuelTransitionStages chart, fuel catalog switching thresholds, and well-to-wake GHG intensity ladder.
- [x] **`/guide` (Guide)**: Renders 7 plain-English methodology sections, scenario axis positions table, and dataset provenance footer.

---

## 7. Troubleshooting Common Issues

| Symptom | Cause | Solution |
| :--- | :--- | :--- |
| `demo_data.json not found` error on UI | Pipeline script hasn't been executed. | Run `python scripts/build_demo_data.py --fast` from project root. |
| UI values don't update after code changes | Browser or Next.js static asset cache is stale. | Clear browser cache or delete `.next/` directory in `frontend/` and restart `npm run dev`. |
| `AttributeError: 'NoneType' object has no attribute 'fuel_consumption_tonnes'` | `fuel_model` parameter passed as `None` in serialization. | Handled automatically in `qiea_solver.py` via `fuel_model = fuel_model or PhysicsFuelModel()`. |
| Exported CSV file shows `N/A` for metrics | Older `demo_data.json` missing enriched configuration fields. | Re-run `python scripts/build_demo_data.py --fast` to regenerate payload with enriched vessel breakdown metrics. |
| `npm run build` TypeScript error | Type mismatch in `demo.ts` interfaces. | Verify `BaselineData` contains `waterfall_breakdown` and `VesselYearGene` contains optional physical metrics. |

---

## 8. Final Acceptance Test Checklist

Perform these steps before final PR approval:

1. [ ] **Pipeline Execution**: Run `python scripts/build_demo_data.py --fast` and confirm exit code 0.
2. [ ] **Frontend Build**: Run `cd frontend; npm run build` and confirm 0 compilation errors across all static routes.
3. [ ] **Python Integration Tests**: Run `python -m pytest tests/test_research_integration.py tests/test_demo_frontend.py` and confirm all 6 tests pass.
4. [ ] **Waterfall Verification**: Open `/plans`, verify waterfall bars match exact pipeline deltas without arbitrary multiplier fractions (`0.45`, `0.25`, `0.30`).
5. [ ] **Dispatch CSV Verification**: Click "Export Dispatch Plan (CSV)" on `/plans` and verify all 12 columns contain valid computed data.
6. [ ] **Matrix CSV Verification**: Open `/fleet-matrix`, click "Export Matrix CSV" and verify exported 10-vessel × 5-year CSV ledger.
