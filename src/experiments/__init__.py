"""
CarbonRoute Experiment Runner

Automates comparisons between baseline Dijkstra and CarbonRoute
across multiple network scenarios and optimization profiles.
Produces structured results suitable for charting.
"""

from typing import List, Dict
from src.simulator import SDNNetwork, build_demo_topology
from src.routing import baseline_dijkstra, carbonroute, get_all_paths_evaluated
import time
import uuid


# Predefined optimization profiles
PROFILES = {
    "performance": {"alpha": 0.80, "beta": 0.15, "gamma": 0.05, "label": "Performance-First"},
    "balanced":    {"alpha": 0.40, "beta": 0.30, "gamma": 0.30, "label": "Balanced"},
    "green":       {"alpha": 0.10, "beta": 0.30, "gamma": 0.60, "label": "Green-First"},
}

# Predefined network scenarios
SCENARIOS = {
    "normal": {
        "label": "Normal Network",
        "description": "All links at low utilization, stable conditions.",
        "congested_links": [],
    },
    "path_a_congested": {
        "label": "Fast Path Congested",
        "description": "The fastest path (via s2→s6) is under heavy load.",
        "congested_links": [("s1", "s2"), ("s2", "s6")],
    },
    "path_b_congested": {
        "label": "Medium Path Congested",
        "description": "The medium path (via s3→s7) is under heavy load.",
        "congested_links": [("s1", "s3"), ("s3", "s7")],
    },
    "multi_congestion": {
        "label": "Multiple Path Congestion",
        "description": "Both fast and medium paths are congested, forcing greener routing.",
        "congested_links": [("s1", "s2"), ("s2", "s6"), ("s1", "s3"), ("s3", "s7")],
    },
}


def run_single_comparison(net: SDNNetwork, profile_name: str,
                          alpha: float, beta: float, gamma: float) -> dict:
    """Run a single baseline vs CarbonRoute comparison."""
    baseline = baseline_dijkstra(net, "h1", "h2")
    carbon = carbonroute(net, "h1", "h2", alpha, beta, gamma)

    return {
        "profile": profile_name,
        "baseline": baseline.to_dict() if baseline else None,
        "carbonroute": carbon.to_dict() if carbon else None,
    }


def run_experiment(scenario_name: str = "normal",
                   custom_profiles: Dict = None) -> dict:
    """
    Run a full experiment: build network, apply scenario, run all profiles.
    Returns structured data ready for charting.
    """
    scenario = SCENARIOS.get(scenario_name, SCENARIOS["normal"])
    profiles = custom_profiles or PROFILES

    net = build_demo_topology()
    net.simulate_traffic(congested_links=scenario["congested_links"])

    results = []
    for name, profile in profiles.items():
        comparison = run_single_comparison(
            net, profile.get("label", name),
            profile["alpha"], profile["beta"], profile["gamma"]
        )
        results.append(comparison)

    # Get all paths with current metrics for visualization
    all_paths = get_all_paths_evaluated(net, "h1", "h2")

    return {
        "id": str(uuid.uuid4())[:8],
        "scenario": scenario,
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "topology": net.get_topology_data(),
        "link_stats": net.get_all_stats(),
        "all_possible_paths": all_paths,
        "comparisons": results,
    }


def run_full_benchmark() -> dict:
    """
    Run all scenarios × all profiles for the full experiment matrix.
    This is the main function for generating presentation-ready data.
    """
    all_results = {}
    for scenario_name in SCENARIOS:
        all_results[scenario_name] = run_experiment(scenario_name)

    return {
        "benchmark_id": str(uuid.uuid4())[:8],
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "scenarios": all_results,
    }
