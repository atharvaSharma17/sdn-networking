"""
CarbonRoute Test Suite — Experiment Runner Tests

Validates the experiment orchestration including scenario definitions,
optimization profiles, single experiment runs, and full benchmark execution.
"""

import pytest
from src.experiments import (
    PROFILES, SCENARIOS,
    run_single_comparison, run_experiment, run_full_benchmark
)
from src.simulator import build_demo_topology


class TestProfiles:
    """Tests for optimization profiles (HLD §6)."""

    def test_three_profiles_exist(self):
        """Exactly 3 profiles must be defined."""
        assert len(PROFILES) == 3

    def test_performance_profile_weights(self):
        """Performance: α=0.80, β=0.15, γ=0.05 (HLD §6)."""
        p = PROFILES["performance"]
        assert p["alpha"] == 0.80
        assert p["beta"] == 0.15
        assert p["gamma"] == 0.05

    def test_balanced_profile_weights(self):
        """Balanced: α=0.40, β=0.30, γ=0.30 (HLD §6)."""
        p = PROFILES["balanced"]
        assert p["alpha"] == 0.40
        assert p["beta"] == 0.30
        assert p["gamma"] == 0.30

    def test_green_profile_weights(self):
        """Sustainability-First: α=0.10, β=0.30, γ=0.60 (HLD §6)."""
        p = PROFILES["green"]
        assert p["alpha"] == 0.10
        assert p["beta"] == 0.30
        assert p["gamma"] == 0.60

    def test_all_weights_sum_to_one(self):
        """α + β + γ must equal 1.0 for all profiles (HLD §4.1)."""
        for name, profile in PROFILES.items():
            total = profile["alpha"] + profile["beta"] + profile["gamma"]
            assert total == pytest.approx(1.0), \
                f"Profile '{name}' weights sum to {total}, not 1.0"


class TestScenarios:
    """Tests for network scenarios (HLD §6)."""

    def test_four_scenarios_exist(self):
        """Exactly 4 scenarios must be defined (HLD §6)."""
        assert len(SCENARIOS) == 4

    def test_scenario_keys(self):
        """Expected scenario keys must exist."""
        expected = ["normal", "path_a_congested", "path_b_congested", "multi_congestion"]
        for key in expected:
            assert key in SCENARIOS

    def test_normal_has_no_congestion(self):
        """Normal scenario should have empty congested_links."""
        assert SCENARIOS["normal"]["congested_links"] == []

    def test_path_a_congests_fast_corridor(self):
        """Fast path congestion should target s1-s2 and s2-s6."""
        links = SCENARIOS["path_a_congested"]["congested_links"]
        assert ("s1", "s2") in links
        assert ("s2", "s6") in links

    def test_path_b_congests_medium_corridor(self):
        """Medium path congestion should target s1-s3 and s3-s7."""
        links = SCENARIOS["path_b_congested"]["congested_links"]
        assert ("s1", "s3") in links
        assert ("s3", "s7") in links

    def test_multi_congestion_covers_both(self):
        """Multi-congestion should include links from both Path A and Path B."""
        links = SCENARIOS["multi_congestion"]["congested_links"]
        assert ("s1", "s2") in links
        assert ("s2", "s6") in links
        assert ("s1", "s3") in links
        assert ("s3", "s7") in links

    def test_all_scenarios_have_required_fields(self):
        """Each scenario must have label, description, and congested_links."""
        for name, scenario in SCENARIOS.items():
            assert "label" in scenario, f"Scenario '{name}' missing label"
            assert "description" in scenario, f"Scenario '{name}' missing description"
            assert "congested_links" in scenario, f"Scenario '{name}' missing congested_links"


class TestRunExperiment:
    """Tests for experiment execution."""

    def test_single_comparison_returns_results(self):
        """run_single_comparison should return baseline and carbonroute results."""
        net = build_demo_topology()
        net.simulate_traffic()
        result = run_single_comparison(net, "test", 0.40, 0.30, 0.30)
        assert "baseline" in result
        assert "carbonroute" in result
        assert result["baseline"] is not None
        assert result["carbonroute"] is not None

    def test_run_experiment_returns_structured_data(self):
        """run_experiment should return complete experiment data."""
        result = run_experiment("normal")
        assert "scenario" in result
        assert "comparisons" in result
        assert "link_stats" in result
        assert "all_possible_paths" in result
        assert len(result["comparisons"]) == 3  # 3 profiles

    def test_run_experiment_each_scenario(self):
        """All 4 scenarios should execute without error."""
        for scenario_name in SCENARIOS:
            result = run_experiment(scenario_name)
            assert result is not None
            assert len(result["comparisons"]) == 3

    def test_full_benchmark_runs_all_scenarios(self):
        """Full benchmark should produce results for all 4 scenarios."""
        result = run_full_benchmark()
        assert "scenarios" in result
        assert len(result["scenarios"]) == 4
        for scenario_name in SCENARIOS:
            assert scenario_name in result["scenarios"]

    def test_full_benchmark_has_12_comparisons(self):
        """Full benchmark: 4 scenarios × 3 profiles = 12 comparisons total."""
        result = run_full_benchmark()
        total_comparisons = sum(
            len(s["comparisons"]) for s in result["scenarios"].values()
        )
        assert total_comparisons == 12
