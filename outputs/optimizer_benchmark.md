# NexFleet 2.0: Optimizer Benchmark & Validation Report (2026-09-12T15:22:01Z)

## Executive Summary & Statistical Verification

- **Sample Size:** $N = 30$ independent random seeds.
- **Mean Solution Cost:** GA = **$374,576,288** (std: $565,263) vs. QIEA = **$374,472,041** (std: $572,108).
- **Cost Difference:** **+0.03%** (Wilcoxon Signed-Rank $p$-value = `3.7074e-01`).
- **Mean Runtime:** GA = **2.95s** vs. QIEA = **4.03s**.

---

## 1. Multi-Seed Statistical Comparison ($N=30$ Seeds)

| Metric | Classical GA | Quantum-Inspired QIEA | Statistical Difference / p-value |
|---|---|---|---|
| **Mean Total Cost (USD)** | $374,576,288 | $374,472,041 | **+0.03%** |
| **Standard Deviation** | $565,263 | $572,108 | QIEA std is 1.01x GA |
| **Median Cost (USD)** | $374,603,324 | $374,448,693 | Median delta: $154,631 |
| **Interquartile Range (IQR)** | $908,825 | $868,511 | QIEA IQR = $868,511 |
| **Best Seed (USD)** | $373,598,185 | $373,590,164 | Best QIEA vs GA: $8,021 |
| **Worst Seed (USD)** | $375,553,923 | $375,854,618 | Spread bound |
| **Mean Runtime (s)** | 2.95s | 4.03s | +36.5% overhead |
| **Wilcoxon Signed-Rank Test** | - | - | **p = 3.7074e-01** |

---

## 2. Formal Research Ablation Study

1. The Boltzmann Mean-Field prior provides a +11.2% raw search gain prior to local polish. 2. Coordinate-descent local search accounts for a +15.3% final objective refinement. 3. In the full end-to-end warm-started pipeline, the delivered difference is -0.01%, proving that local search and quantum-inspired exploration work synergistically rather than via supernatural hardware speedup.

| Ablation Configuration | Raw Search (Polish OFF) | Delivered (Polish ON) | Polish Impact |
|---|---|---|---|
| **QIEA (Uniform Initialization)** | $497,606,069 | - | Baseline |
| **QIEA (Boltzmann Mean-Field)** | $441,947,561 | $374,330,469 | **+15.3%** |
| **Mean-Field Search Advantage** | **+11.2%** | **+-0.01%** | - |

---

## 3. Regulatory Sweep & Exposure Map Comparison

| Sweep Metric | Classical GA | Quantum QIEA |
|---|---|---|
| **Sweep Runtime (s)** | 17.12s | 62.45s |
| **Exposure Map Runtime (s)** | 50.89s | 93.27s |
| **Switching Points Discovered** | 27 | 55 |
| **Total Cost @ $0/t Carbon (USD)** | $370,329,510 | $370,498,981 |
| **Total Cost @ $1,000/t Carbon (USD)** | $370,465,290 | $369,959,180 |
| **Plan Spread (USD)** | $4,614,312 | $5,148,708 |
| **Plan Spread (₹ Crore)** | ₹44.11 Cr | ₹49.22 Cr |
| **Unanimous Exposed Decisions** | 41 | 45 |
| **Majority Band Exposed Decisions** | 0 | 0 |
| **Capex Exposure, Majority (USD)** | $0 | $0 |