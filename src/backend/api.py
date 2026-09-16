"""
CarbonRoute Application API

FastAPI-based REST backend providing endpoints for:
  - Network topology retrieval
  - Real-time route computation (baseline vs CarbonRoute)
  - Experiment execution and benchmarking
  - Live network statistics

Serves as the Application Layer in the SDN architecture.
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
from typing import Optional
import os

from src.simulator import build_demo_topology
from src.routing import baseline_dijkstra, carbonroute, get_all_paths_evaluated
from src.experiments import (
    run_experiment, run_full_benchmark,
    PROFILES, SCENARIOS
)

app = FastAPI(
    title="CarbonRoute API",
    description="Multi-Objective Green SDN Routing Framework",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Global network instance (simulates persistent SDN data plane)
network = build_demo_topology()
network.simulate_traffic()

# Serve frontend
FRONTEND_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "src", "frontend")


class RouteRequest(BaseModel):
    alpha: float = 0.33
    beta: float = 0.33
    gamma: float = 0.34
    scenario: Optional[str] = None


class ExperimentRequest(BaseModel):
    scenario: str = "normal"


# ─── Topology Endpoints ──────────────────────────────────────────

@app.get("/api/v1/topology")
def get_topology():
    """Return the full network topology for visualization."""
    return network.get_topology_data()


# ─── Metrics Endpoints ───────────────────────────────────────────

@app.get("/api/v1/metrics")
def get_metrics():
    """Return current link-level statistics."""
    return {"links": network.get_all_stats()}


@app.post("/api/v1/metrics/refresh")
def refresh_metrics():
    """Simulate new traffic patterns (randomize link utilization)."""
    network.simulate_traffic()
    return {"status": "refreshed", "links": network.get_all_stats()}


# ─── Routing Endpoints ───────────────────────────────────────────

@app.post("/api/v1/routes/compute")
def compute_routes(req: RouteRequest):
    """
    Compute routes using both algorithms and return comparison.
    This is the core endpoint that the dashboard calls in real-time.
    """
    # Apply scenario congestion if specified
    if req.scenario and req.scenario in SCENARIOS:
        congested = SCENARIOS[req.scenario]["congested_links"]
        network.simulate_traffic(congested_links=congested)
    else:
        network.simulate_traffic()

    baseline = baseline_dijkstra(network, "h1", "h2")
    carbon = carbonroute(network, "h1", "h2", req.alpha, req.beta, req.gamma)
    all_paths = get_all_paths_evaluated(network, "h1", "h2", req.alpha, req.beta, req.gamma)

    return {
        "weights": {"alpha": req.alpha, "beta": req.beta, "gamma": req.gamma},
        "baseline": baseline.to_dict() if baseline else None,
        "carbonroute": carbon.to_dict() if carbon else None,
        "all_paths": all_paths,
        "link_stats": network.get_all_stats(),
    }


# ─── Experiment Endpoints ────────────────────────────────────────

@app.get("/api/v1/experiments/profiles")
def get_profiles():
    """Return available optimization profiles."""
    return PROFILES


@app.get("/api/v1/experiments/scenarios")
def get_scenarios():
    """Return available network scenarios."""
    return SCENARIOS


@app.post("/api/v1/experiments/run")
def run_single_experiment(req: ExperimentRequest):
    """Run a single experiment for a given scenario across all profiles."""
    return run_experiment(req.scenario)


@app.post("/api/v1/experiments/benchmark")
def run_benchmark():
    """Run the full benchmark: all scenarios × all profiles."""
    return run_full_benchmark()


# ─── Frontend Serving ────────────────────────────────────────────

@app.get("/")
def serve_frontend():
    return FileResponse(os.path.join(FRONTEND_DIR, "index.html"))
