"""Generate presentation-ready benchmark visualization plots from benchmark JSON outputs.

Reads:
- outputs/fuel_predictor_benchmark.json
- outputs/optimizer_benchmark.json

Generates:
- outputs/plots/fuel_mape_comparison.png
- outputs/plots/fuel_fold_stability.png
- outputs/plots/fuel_fit_time.png
- outputs/plots/optimizer_runtime_cost.png
- outputs/plots/optimizer_polish_effect.png
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
import numpy as np
import matplotlib.pyplot as plt

try:
    import seaborn as sns
    sns.set_theme(style="whitegrid", font_scale=1.1)
except ImportError:
    plt.style.use("seaborn-v0_8-whitegrid" if "seaborn-v0_8-whitegrid" in plt.style.available else "default")

PROJECT_ROOT = Path(__file__).resolve().parent.parent
OUTPUTS_DIR = PROJECT_ROOT / "outputs"
PLOTS_DIR = OUTPUTS_DIR / "plots"


def load_json_file(filepath: Path) -> dict:
    if not filepath.exists():
        raise FileNotFoundError(f"Benchmark file not found: {filepath}")
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        raise RuntimeError(f"Failed to parse JSON from {filepath}: {e}") from e


def plot_fuel_mape_comparison(data: dict, output_path: Path) -> None:
    """Grouped/bar chart comparing mean MAPE % with the physics baseline distinguished."""
    arms_data = data.get("arms", {})
    if not arms_data:
        raise KeyError("Key 'arms' missing or empty in fuel predictor benchmark data")

    models = ["physics", "lightgbm", "tensor_train", "mlp"]
    display_names = ["Physics Baseline\n(Reference)", "LightGBM\n(Residual)", "Tensor-Train\n(SVD Grid)", "MLP\n(Neural Net)"]
    
    mean_mapes = []
    
    for m in models:
        m_info = arms_data.get(m, {})
        mean_mapes.append(m_info.get("mean_mape_percent", 0.0))

    fig, ax = plt.subplots(figsize=(9, 6), dpi=150)
    
    colors = ["#718096", "#2B6CB0", "#319795", "#D69E2E"]
    bars = ax.bar(display_names, mean_mapes, color=colors, width=0.55, edgecolor="#1A202C", linewidth=1.2, zorder=3)
    
    ax.grid(axis="y", linestyle="--", alpha=0.7, zorder=0)
    ax.set_ylabel("Mean Absolute Percentage Error (MAPE %)", fontsize=12, fontweight="bold")
    ax.set_title("Fuel Prediction Model Benchmark: Mean MAPE (%)\n(10-Fold Leave-One-Vessel-Out Cross-Validation)", fontsize=14, fontweight="bold", pad=15)
    
    # Value labels on top of bars
    for bar, val in zip(bars, mean_mapes):
        yval = bar.get_height()
        ax.text(bar.get_x() + bar.get_width() / 2.0, yval + 0.08, f"{val:.2f}%", ha="center", va="bottom", fontsize=11, fontweight="bold")
        
    ax.set_ylim(0, max(mean_mapes) * 1.25)
    
    # Highlight baseline reference line
    phys_val = mean_mapes[0]
    ax.axhline(phys_val, color="#E53E3E", linestyle=":", linewidth=1.5, alpha=0.8, label=f"Physics Baseline ({phys_val:.2f}%)")
    ax.legend(loc="upper right", frameon=True)
    
    plt.tight_layout()
    fig.savefig(output_path, dpi=150)
    plt.close(fig)
    print(f"Saved: {output_path}")


def plot_fuel_fold_stability(data: dict, output_path: Path) -> None:
    """Box & strip plot of per-fold MAPE exposing MLP instability vs LightGBM/TT consistency."""
    per_fold = data.get("per_fold_mape_percent", {})
    if not per_fold:
        raise KeyError("Key 'per_fold_mape_percent' missing or empty in fuel predictor benchmark data")

    models = ["physics", "lightgbm", "tensor_train", "mlp"]
    labels = ["Physics-Only", "LightGBM", "Tensor-Train", "MLP Regressor"]
    
    fold_values = [per_fold.get(m, []) for m in models]
    
    fig, ax = plt.subplots(figsize=(10, 6), dpi=150)
    
    colors = ["#A0AEC0", "#3182CE", "#38B2AC", "#E53E3E"]
    
    # Box plot
    bp = ax.boxplot(
        fold_values,
        tick_labels=labels,
        patch_artist=True,
        showmeans=True,
        meanprops={"marker": "o", "markerfacecolor": "black", "markeredgecolor": "black", "markersize": 6},
        medianprops={"color": "black", "linewidth": 1.5},
        whiskerprops={"linewidth": 1.2},
        capprops={"linewidth": 1.2},
        boxprops={"linewidth": 1.2},
        widths=0.45,
        zorder=2
    )
    
    for patch, color in zip(bp['boxes'], colors):
        patch.set_facecolor(color)
        patch.set_alpha(0.65)
        
    # Overlay jittered strip points
    np.random.seed(42)
    for i, values in enumerate(fold_values):
        jitter = np.random.normal(0, 0.04, size=len(values))
        ax.scatter([i + 1 + j for j in jitter], values, color="#1A202C", alpha=0.85, s=35, zorder=4, edgecolor="white", linewidth=0.5)
        
    # Annotate outlier fold on MLP
    mlp_worst = max(per_fold.get("mlp", [0]))
    ax.annotate(
        f"Severe Local Minimum\n(Fold A3: {mlp_worst:.1f}%)",
        xy=(4, mlp_worst),
        xytext=(3.2, mlp_worst - 1.5),
        arrowprops=dict(facecolor="#E53E3E", shrink=0.08, width=1.5, headwidth=7),
        fontsize=10,
        fontweight="bold",
        color="#9B2C2C",
        bbox=dict(boxstyle="round,pad=0.3", facecolor="#FFF5F5", edgecolor="#E53E3E", alpha=0.9)
    )

    ax.grid(axis="y", linestyle="--", alpha=0.7, zorder=0)
    ax.set_ylabel("Per-Fold MAPE (%)", fontsize=12, fontweight="bold")
    ax.set_title("Leave-One-Vessel-Out (LOVO) Cross-Validation Stability Across 10 Folds\n(Exposing MLP Instability vs. LightGBM/Tensor-Train Consistency)", fontsize=13, fontweight="bold", pad=15)
    
    from matplotlib.lines import Line2D
    legend_elements = [
        Line2D([0], [0], marker='o', color='w', markerfacecolor='black', markersize=8, label='Mean MAPE'),
        Line2D([0], [0], color='black', linewidth=1.5, label='Median Fold')
    ]
    ax.legend(handles=legend_elements, loc="upper left", frameon=True)

    plt.tight_layout()
    fig.savefig(output_path, dpi=150)
    plt.close(fig)
    print(f"Saved: {output_path}")


def plot_fuel_fit_time(data: dict, output_path: Path) -> None:
    """Bar chart of fit time per model on log scale."""
    arms_data = data.get("arms", {})
    models = ["tensor_train", "lightgbm", "mlp"]
    display_names = ["Tensor-Train SVD", "LightGBM GBDT", "MLP Neural Net"]
    fit_times = [max(arms_data.get(m, {}).get("fit_seconds_total", 0.0), 0.001) for m in models]

    fig, ax = plt.subplots(figsize=(8, 5), dpi=150)
    colors = ["#319795", "#2B6CB0", "#E53E3E"]
    bars = ax.bar(display_names, fit_times, color=colors, width=0.5, edgecolor="#1A202C", linewidth=1.2, zorder=3)
    
    ax.set_yscale("log")
    ax.grid(axis="y", which="both", linestyle="--", alpha=0.6, zorder=0)
    ax.set_ylabel("Total Fit Time across 10 Folds (Seconds, Log Scale)", fontsize=11, fontweight="bold")
    ax.set_title("Fuel Prediction Model Fitting Time Benchmark", fontsize=13, fontweight="bold", pad=15)
    
    for bar, val in zip(bars, fit_times):
        ax.text(bar.get_x() + bar.get_width() / 2.0, val * 1.25, f"{val:.2f} s", ha="center", va="bottom", fontsize=10, fontweight="bold")
        
    ax.set_ylim(0.01, max(fit_times) * 6)
    plt.tight_layout()
    fig.savefig(output_path, dpi=150)
    plt.close(fig)
    print(f"Saved: {output_path}")


def plot_optimizer_runtime_cost(data: dict, output_path: Path) -> None:
    """Grouped comparison of GA vs QIEA runtime and best fleet cost."""
    ga_info = data.get("ga", {})
    qiea_info = data.get("qiea", {})
    if not ga_info or not qiea_info:
        raise KeyError("Keys 'ga' and/or 'qiea' missing from optimizer benchmark JSON")

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(12, 5.5), dpi=150)
    
    optimizers = ["Classical GA", "Quantum-Inspired\n(QIEA)"]
    runtimes = [ga_info.get("total_seconds", 0.0), qiea_info.get("total_seconds", 0.0)]
    min_costs_m = [ga_info.get("min_total_usd_across_grid", 0.0) / 1e6, qiea_info.get("min_total_usd_across_grid", 0.0) / 1e6]
    
    # Subplot 1: Runtime
    bar_colors1 = ["#3182CE", "#805AD5"]
    bars1 = ax1.bar(optimizers, runtimes, color=bar_colors1, width=0.45, edgecolor="#1A202C", linewidth=1.2, zorder=3)
    ax1.grid(axis="y", linestyle="--", alpha=0.7, zorder=0)
    ax1.set_ylabel("Total Benchmark Runtime (Seconds)", fontsize=11, fontweight="bold")
    ax1.set_title("Optimization Runtime\n(GA is ~2.4x Faster)", fontsize=12, fontweight="bold")
    for bar, val in zip(bars1, runtimes):
        ax1.text(bar.get_x() + bar.get_width() / 2.0, val + 1.5, f"{val:.1f} s", ha="center", va="bottom", fontsize=10, fontweight="bold")
    ax1.set_ylim(0, max(runtimes) * 1.2)

    # Subplot 2: Best Total Fleet Cost
    bars2 = ax2.bar(optimizers, min_costs_m, color=bar_colors1, width=0.45, edgecolor="#1A202C", linewidth=1.2, zorder=3)
    ax2.grid(axis="y", linestyle="--", alpha=0.7, zorder=0)
    ax2.set_ylabel("5-Year Optimal Fleet Cost (Million USD)", fontsize=11, fontweight="bold")
    ax2.set_title("Delivered Best Cost Across Grid\n(Virtual Tie: 0.10% Margin)", fontsize=12, fontweight="bold")
    
    min_val = min(min_costs_m)
    ax2.set_ylim(min_val * 0.98, max(min_costs_m) * 1.01)
    
    for bar, val in zip(bars2, min_costs_m):
        ax2.text(bar.get_x() + bar.get_width() / 2.0, val + (max(min_costs_m) - min_val) * 0.1, f"M", ha="center", va="bottom", fontsize=10, fontweight="bold")

    fig.suptitle("Optimizer Benchmark: Classical GA vs. Quantum-Inspired QIEA", fontsize=14, fontweight="bold", y=1.02)
    plt.tight_layout()
    fig.savefig(output_path, dpi=150)
    plt.close(fig)
    print(f"Saved: {output_path}")


def plot_optimizer_polish_effect(data: dict, output_path: Path) -> None:
    """Cost gap closing after coordinate-descent polish for search attribution."""
    attr = data.get("search_attribution", {})
    if not attr or "raw_search_polish_disabled" not in attr or "end_to_end_polish_enabled" not in attr:
        raise KeyError("Search attribution ablation data missing in optimizer benchmark JSON")

    raw = attr["raw_search_polish_disabled"]
    end = attr["end_to_end_polish_enabled"]
    
    raw_uni = raw["uniform_init"]["mean_total_usd"] / 1e6
    raw_mf = raw["mean_field_init"]["mean_total_usd"] / 1e6
    
    end_uni = end["uniform_init"]["mean_total_usd"] / 1e6
    end_mf = end["mean_field_init"]["mean_total_usd"] / 1e6
    
    fig, ax = plt.subplots(figsize=(9, 6), dpi=150)
    
    stages = ["Raw Search\n(Polish Disabled)", "Delivered Solution\n(Polish Enabled)"]
    x = np.arange(len(stages))
    width = 0.32
    
    rects1 = ax.bar(x - width/2, [raw_uni, end_uni], width, label="Uniform Prior (Classical-Style)", color="#718096", edgecolor="#1A202C", linewidth=1.2, zorder=3)
    rects2 = ax.bar(x + width/2, [raw_mf, end_mf], width, label="Mean-Field Prior (Quantum-Inspired)", color="#805AD5", edgecolor="#1A202C", linewidth=1.2, zorder=3)
    
    ax.grid(axis="y", linestyle="--", alpha=0.7, zorder=0)
    ax.set_ylabel("Mean 5-Year Fleet Plan Cost (Million USD)", fontsize=11, fontweight="bold")
    ax.set_title("Optimizer Ablation: Coordinate-Descent Polish Impact\n(Quantum Prior Advantage is Absorbed by Classical Polish)", fontsize=13, fontweight="bold", pad=15)
    ax.set_xticks(x)
    ax.set_xticklabels(stages, fontsize=11, fontweight="bold")
    ax.legend(loc="upper right", frameon=True)
    
    for rect in rects1:
        y = rect.get_height()
        ax.text(rect.get_x() + rect.get_width()/2.0, y + 5, f"M", ha="center", va="bottom", fontsize=10, fontweight="bold")
    for rect in rects2:
        y = rect.get_height()
        ax.text(rect.get_x() + rect.get_width()/2.0, y + 5, f"M", ha="center", va="bottom", fontsize=10, fontweight="bold")

    ax.annotate(
        "-11.2% Raw Search\nAdvantage with Prior",
        xy=(0 + width/2, raw_mf),
        xytext=(0.35, (raw_uni + raw_mf)/2),
        arrowprops=dict(facecolor="#2B6CB0", shrink=0.08, width=1.5, headwidth=6),
        fontsize=10,
        fontweight="bold",
        color="#2B6CB0",
        bbox=dict(boxstyle="round,pad=0.3", facecolor="#EBF8FF", edgecolor="#3182CE", alpha=0.9)
    )
    
    ax.annotate(
        "Equalized at ~\n(0.04% Difference)",
        xy=(1, end_mf),
        xytext=(0.85, end_mf + 45),
        arrowprops=dict(facecolor="#2F855A", shrink=0.08, width=1.5, headwidth=6),
        fontsize=10,
        fontweight="bold",
        color="#22543D",
        bbox=dict(boxstyle="round,pad=0.3", facecolor="#F0FFF4", edgecolor="#38A169", alpha=0.9)
    )

    ax.set_ylim(320, max(raw_uni, raw_mf) * 1.15)
    plt.tight_layout()
    fig.savefig(output_path, dpi=150)
    plt.close(fig)
    print(f"Saved: {output_path}")


def main() -> None:
    PLOTS_DIR.mkdir(parents=True, exist_ok=True)
    print(f"Output directory ready: {PLOTS_DIR}")

    fuel_json_path = OUTPUTS_DIR / "fuel_predictor_benchmark.json"
    opt_json_path = OUTPUTS_DIR / "optimizer_benchmark.json"

    # 1-3. Fuel Predictor Plots
    try:
        fuel_data = load_json_file(fuel_json_path)
        print("Loaded fuel_predictor_benchmark.json successfully.")
        plot_fuel_mape_comparison(fuel_data, PLOTS_DIR / "fuel_mape_comparison.png")
        plot_fuel_fold_stability(fuel_data, PLOTS_DIR / "fuel_fold_stability.png")
        plot_fuel_fit_time(fuel_data, PLOTS_DIR / "fuel_fit_time.png")
    except Exception as e:
        print(f"[ERROR] Could not generate fuel predictor plots: {e}", file=sys.stderr)

    # 4-5. Optimizer Plots
    try:
        opt_data = load_json_file(opt_json_path)
        print("Loaded optimizer_benchmark.json successfully.")
        plot_optimizer_runtime_cost(opt_data, PLOTS_DIR / "optimizer_runtime_cost.png")
        plot_optimizer_polish_effect(opt_data, PLOTS_DIR / "optimizer_polish_effect.png")
    except Exception as e:
        print(f"[ERROR] Could not generate optimizer plots: {e}", file=sys.stderr)

    print("\nBenchmark plotting completed.")


if __name__ == "__main__":
    main()