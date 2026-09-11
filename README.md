# NexFleet 2.0 🚢⚡

**Quantum-Inspired Green Fleet Optimization & Regulatory Uncertainty Risk Atlas**

NexFleet is a maritime decision-support platform for fleet operators and charterers to optimize fleet deployment, fuel selection, cruising speed, and regulatory compliance across four overlapping maritime regimes:

- **IMO CII** (Carbon Intensity Indicator)
- **IMO Net-Zero Framework (NZF)**
- **EU FuelEU Maritime**
- **EU ETS** (Emissions Trading System)

---

## 📑 Table of Contents

1. [Prerequisites](#️-prerequisites)
2. [Project Structure](#-project-structure)
3. [Quick Start (Run the Web App)](#-quick-start-run-the-web-app)
4. [How to Recompute & Update Data (demo_data.json)](#-how-to-recompute--update-data-demo_datajson)
5. [Running Benchmarks & Tests](#-running-benchmarks--tests)
6. [Configuration & Environment Variables](#️-configuration--environment-variables)
7. [How It Works Under the Hood](#-how-it-works-under-the-hood)
8. [Troubleshooting](#-troubleshooting)

---

## 🛠️ Prerequisites

Make sure you have the following installed:

| Tool | Minimum Version | Check |
|---|---|---|
| Python | 3.11+ | `python --version` |
| Node.js | 18+ | `node --version` |
| npm | (bundled with Node) | `npm --version` |

---

## 📂 Project Structure

```text
Nexfleet/
├── src/nexfleet/          # Python computational & optimization engine
│   ├── compliance/        # Scope gating & regime applicability
│   ├── fleet/              # Fleet definitions & market prices (fleet.json, prices.json)
│   ├── optimization/       # GA, QIEA, ML predictors, Born-machine MPS, sweep logic
│   └── regulatory/         # Scenarios & implied price converters (regulations.json)
├── scripts/                # Data generation and benchmarking scripts
│   ├── build_demo_data.py            # Primary pipeline (generates demo_data.json)
│   ├── benchmark_fuel_predictor.py   # LOVO ML benchmark (LightGBM, TT, Physics)
│   └── benchmark_optimizers.py       # GA vs QIEA performance benchmark
├── frontend/                # Next.js 16 web dashboard & interactive risk atlas
│   ├── app/                 # Next.js App Router pages
│   ├── public/               # Static assets & demo_data.json target
│   └── lib/AtlasContext.tsx  # React context loading the computed JSON
├── outputs/                # Generated JSON and benchmark markdown reports
└── tests/                   # 286 Pytest test cases
```

---

## 🚀 Quick Start (Run the Web App)

If you just want to launch and explore the interactive dashboard using the pre-computed demo data:

```bash
# 1. Navigate to the frontend directory
cd frontend

# 2. Install dependencies (only needed once, or after pulling changes)
npm install

# 3. Start the Next.js development server
npm run dev
```

Then open **[http://localhost:3000](http://localhost:3000)** in your browser.

> This mode reads the existing `frontend/public/demo_data.json` — no Python setup required. Skip to the next section only if you need to regenerate the data itself.

---

## 🔄 How to Recompute & Update Data (`demo_data.json`)

The frontend reads pre-calculated optimization data from `frontend/public/demo_data.json`. Whenever you change rules, prices, or fleet parameters in `src/nexfleet/`, re-run the pipeline below to refresh the dataset.

### 1. Set Up the Python Environment (first time only)

From the project root:

```bash
# Optional but recommended: create a virtual environment
python -m venv venv

# Activate it
# Windows:
venv\Scripts\activate
# macOS / Linux:
source venv/bin/activate

# Install the project in editable mode with its dependencies
pip install -e .
```

### 2. Run the Build Script

Run from the project root. Pick the mode that fits your need:

**Option A — Fast run (~5–10 seconds)**
Best for quick iteration while developing; uses a reduced population/generation count.
```bash
python scripts/build_demo_data.py --fast
```

**Option B — Full production run (~30–60 seconds)**
Runs the full 41-point carbon-price sweep ($0 → $1,000/tCO₂e) with 3-seed stability checks.
```bash
python scripts/build_demo_data.py
```

**Option C — Quantum-Inspired Optimizer (QIEA)**
Same as Option B, but solves using QIEA instead of the classical GA.
```bash
python scripts/build_demo_data.py --optimizer qiea
```

> **Note:** The script writes output to **both** `outputs/demo_data.json` and `frontend/public/demo_data.json` automatically — no manual copy step needed. Refresh the browser (or restart `npm run dev`) to see updated results.

---

## 📊 Running Benchmarks & Tests

### Fuel Predictor Benchmark (Physics vs LightGBM vs Tensor-Train vs MLP)

Runs a 10-fold Leave-One-Vessel-Out (LOVO) cross-validation comparison:

```bash
python scripts/benchmark_fuel_predictor.py
```
Outputs: `outputs/fuel_predictor_benchmark.json` and `outputs/fuel_predictor_benchmark.md`

### Optimizer Benchmark (GA vs QIEA)

Compares search quality, convergence time, and ablation gains:

```bash
python scripts/benchmark_optimizers.py
```
Outputs: `outputs/optimizer_benchmark.json` and `outputs/optimizer_benchmark.md`

### Full Test Suite

Runs all 286 unit and regression tests:

```bash
pytest
```

Add `-v` for verbose per-test output, or `pytest tests/test_solver.py` to run a single file.

---

### Plotting benchmarking data
after running all benchmark tests, simple run
```
python scripts/generate_benchmark_plots.py
```
to generate all the respected plots

## ⚙️ Configuration & Environment Variables

Create your local `.env` from the example file:

```bash
# Windows (PowerShell):
Copy-Item .env.example .env

# macOS / Linux:
cp .env.example .env
```

| Variable | Description | Default |
|---|---|---|
| `NEXT_PUBLIC_DEFAULT_CARBON_PRICE` | Initial carbon-price slider value shown in the UI ($/tCO₂e) | `100` |
| `NEXFLEET_OPTIMIZER` | Default solver used by the build pipeline: `ga` or `qiea` | `ga` |
| `NEXFLEET_FAST_MODE` | Set to `1` to force fast/reduced-iteration mode by default | `0` |

---

## 🧠 How It Works Under the Hood

At a high level, the pipeline runs in this order:

1. **Load static catalogs** — `fleet.json`, `prices.json`, `regulations.json`, `scenarios.json`.
2. **Scope gating** — determine which regulatory regimes apply to each vessel/route/year.
3. **Fuel prediction** — Admiralty physics baseline, optionally corrected by a learned residual model (LightGBM / Tensor-Train / MLP).
4. **Optimization** — solve the fleet deployment problem with GA or QIEA across a carbon-price sweep, extracting decision "switching points."
5. **Exposure analysis** — multi-seed stability checks plus a Matrix Product State (Born machine) quantum mutual-information cross-check.
6. **Assembly** — all results are serialized into `demo_data.json` for the frontend to consume.

For full mathematical detail, see the technical report and architecture audit documents in the repo.

---

## 🩺 Troubleshooting

| Symptom | Likely Cause | Fix |
|---|---|---|
| `ModuleNotFoundError: nexfleet` | Package not installed in editable mode | Run `pip install -e .` from the project root |
| Frontend shows stale data | `demo_data.json` wasn't regenerated after a change | Re-run `python scripts/build_demo_data.py` and refresh the browser |
| `npm run dev` fails to start | Dependencies not installed / Node version too old | Run `npm install` inside `frontend/`, confirm Node 18+ |
| Build script runs very slowly | Running the full (non-`--fast`) sweep | Use `--fast` during development; reserve the full run for final builds |
| Tests fail after editing regulatory files | Core logic files were modified | Some files are integrity-locked by design — see `BACKEND_AUDIT.md` §15 for the list of files that must not be changed |

---

**License / Status:** Internal research & competition prototype. See repository root for license details, if applicable.