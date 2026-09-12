"""Focused tests for the NexFleet Optimizer API (server.py)."""

from __future__ import annotations

import json
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from nexfleet.api.server import app


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


def test_health_check(client: TestClient):
    resp = client.get("/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "healthy"
    assert data["service"] == "nexfleet-optimizer"


def test_estimate_endpoint(client: TestClient):
    payload = {
        "carbon_price_usd_per_tco2e": 150.0,
        "cargo_demand_multiplier": 1.0,
    }
    resp = client.post("/api/estimate", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "completed"
    assert data["data_mode"] == "synthetic_estimate"
    assert "estimated_total_cost_usd" in data
    assert data["estimated_total_cost_usd"] > 0


def test_valid_ga_request(client: TestClient):
    payload = {
        "carbon_price_usd_per_tco2e": 50.0,
        "cargo_demand_multiplier": 1.0,
        "run_both": False,
        "optimizer": "ga",
        "population_size": 10,
        "generations": 2,
        "seed": 42,
    }
    resp = client.post("/api/optimize", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "completed"
    assert data["best_optimizer"] == "ga"
    assert data["ga_result"]["available"] is True
    assert data["ga_result"]["total_cost_usd"] > 0
    assert data["qiea_result"]["available"] is False
    assert len(data["best_plan"]["configuration"]) == 50  # 10 vessels * 5 years


def test_valid_qiea_request(client: TestClient):
    payload = {
        "carbon_price_usd_per_tco2e": 50.0,
        "cargo_demand_multiplier": 1.0,
        "run_both": False,
        "optimizer": "qiea",
        "population_size": 10,
        "generations": 2,
        "seed": 42,
    }
    resp = client.post("/api/optimize", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "completed"
    assert data["best_optimizer"] == "qiea"
    assert data["qiea_result"]["available"] is True
    assert data["qiea_result"]["total_cost_usd"] > 0
    assert data["ga_result"]["available"] is False


def test_valid_both_optimizer_request(client: TestClient):
    payload = {
        "carbon_price_usd_per_tco2e": 50.0,
        "cargo_demand_multiplier": 1.0,
        "run_both": True,
        "optimizer": "both",
        "population_size": 10,
        "generations": 2,
        "seed": 42,
    }
    resp = client.post("/api/optimize", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "completed"
    assert data["ga_result"]["available"] is True
    assert data["qiea_result"]["available"] is True
    assert data["best_optimizer"] in ("ga", "qiea", "equivalent")
    assert "cost_difference_usd" in data["comparison"]
    assert "runtime_difference_seconds" in data["comparison"]
    # Check JSON serializability
    assert json.dumps(data)


def test_invalid_population_size(client: TestClient):
    payload = {
        "population_size": 2,  # min is 5
        "generations": 10,
        "optimizer": "ga",
    }
    resp = client.post("/api/optimize", json=payload)
    assert resp.status_code == 422


def test_invalid_generations(client: TestClient):
    payload = {
        "population_size": 20,
        "generations": 0,  # min is 1
        "optimizer": "ga",
    }
    resp = client.post("/api/optimize", json=payload)
    assert resp.status_code == 422


def test_invalid_carbon_price(client: TestClient):
    payload = {
        "carbon_price_usd_per_tco2e": -10.0,  # min is 0
        "population_size": 20,
        "generations": 10,
        "optimizer": "ga",
    }
    resp = client.post("/api/optimize", json=payload)
    assert resp.status_code == 422


def test_invalid_optimizer(client: TestClient):
    payload = {
        "optimizer": "pso",  # invalid
        "population_size": 20,
        "generations": 10,
    }
    resp = client.post("/api/optimize", json=payload)
    assert resp.status_code == 422


def test_identical_settings_passed_to_solvers(client: TestClient):
    """Verify that both GA and QIEA receive matched population, generation, and seed settings."""
    with patch("nexfleet.optimization.solver.run_ga") as mock_ga, \
         patch("nexfleet.optimization.qiea_solver.run_qiea") as mock_qiea:
        
        # Make mocks return mock SolverResults with minimal evaluate breakdown
        from nexfleet.fleet.loader import load_fleet, load_prices
        from nexfleet.optimization.objective import evaluate
        from nexfleet.optimization.solver import SolverResult

        fl = load_fleet()
        pr = load_prices()
        sc = {r["vessel_id"]: r for r in fl["vessels"]}
        from nexfleet.optimization.genome import random_genome
        import random
        g = random_genome(fl, random.Random(0))
        from nexfleet.regulatory.scenario_resolution import resolve_regulations_for_scenario
        reg = resolve_regulations_for_scenario("approved_text")
        bk = evaluate(g, fl, reg, pr)
        mock_res = SolverResult(best_genome=g, best_total_usd=bk.total_usd, best_breakdown=bk, generations_run=3)
        mock_ga.return_value = mock_res
        mock_qiea.return_value = mock_res

        payload = {
            "carbon_price_usd_per_tco2e": 100.0,
            "cargo_demand_multiplier": 1.1,
            "optimizer": "both",
            "population_size": 25,
            "generations": 12,
            "seed": 99,
        }
        resp = client.post("/api/optimize", json=payload)
        assert resp.status_code == 200

        # Verify call args
        assert mock_ga.call_args.kwargs["seed"] == 99
        assert mock_ga.call_args.kwargs["population_size"] == 25
        assert mock_ga.call_args.kwargs["n_generations"] == 12

        assert mock_qiea.call_args.kwargs["seed"] == 99
        assert mock_qiea.call_args.kwargs["population_size"] == 25
        assert mock_qiea.call_args.kwargs["n_generations"] == 12


def test_failed_solver_execution_does_not_hide_success(client: TestClient):
    """If QIEA fails with an exception, GA result is still returned cleanly."""
    with patch("nexfleet.optimization.qiea_solver.run_qiea", side_effect=RuntimeError("Simulated QIEA error")):
        payload = {
            "optimizer": "both",
            "population_size": 10,
            "generations": 2,
            "seed": 0,
        }
        resp = client.post("/api/optimize", json=payload)
        assert resp.status_code == 200
        data = resp.json()
        assert data["ga_result"]["available"] is True
        assert data["qiea_result"]["available"] is False
        assert "Simulated QIEA error" in data["qiea_result"]["error"]
        assert data["best_optimizer"] == "ga"


def test_fuel_compatibility_validation_valid(client: TestClient):
    # A1 is conventional_hfo_scrubber -> vlsfo is compatible
    payload = {
        "optimizer": "ga",
        "population_size": 10,
        "generations": 1,
        "vessel_id": "A1",
        "fuel_id": "vlsfo",
    }
    resp = client.post("/api/optimize", json=payload)
    assert resp.status_code == 200


def test_fuel_compatibility_validation_invalid(client: TestClient):
    # A1 is conventional_hfo_scrubber -> methanol is INCOMPATIBLE
    payload = {
        "optimizer": "ga",
        "population_size": 10,
        "generations": 1,
        "vessel_id": "A1",
        "fuel_id": "methanol",
    }
    resp = client.post("/api/optimize", json=payload)
    assert resp.status_code == 422
    assert "This fuel is not compatible with the selected vessel." in resp.json()["detail"]
