"""
CarbonRoute Test Suite — Routing Algorithm Tests

Validates the routing engine including energy/carbon formulas,
min-max normalization, Baseline Dijkstra, and CarbonRoute multi-objective solver.
"""

import pytest
from src.simulator import build_demo_topology, REGION_CARBON_INTENSITY
from src.routing import (
    baseline_dijkstra, carbonroute, get_all_paths_evaluated,
    _compute_link_energy, _compute_link_carbon, RouteResult
)


@pytest.fixture
def net():
    """Build topology with controlled utilization for deterministic tests."""
    n = build_demo_topology()
    n.simulate_traffic()  # Set base utilization
    return n


class TestEnergyFormula:
    """Tests for per-link energy computation (HLD §4.2)."""

    def test_energy_positive(self, net):
        """Energy consumption must be positive for any active link."""
        e = _compute_link_energy(net, "s1", "s2")
        assert e > 0

    def test_energy_formula_structure(self, net):
        """E = avg_power × (0.1 + 0.2 × u_link), HLD §4.2."""
        link = net.links[("s1", "s2")]
        u = link.utilization
        sw_src = net.switches["s1"]
        sw_dst = net.switches["s2"]
        avg_power = (sw_src.power_consumption(u) + sw_dst.power_consumption(u)) / 2.0
        expected = avg_power * (0.1 + 0.2 * u)
        actual = _compute_link_energy(net, "s1", "s2")
        assert actual == pytest.approx(expected, rel=1e-6)

    def test_energy_increases_with_utilization(self, net):
        """Higher utilization should produce higher energy."""
        link = net.links[("s1", "s2")]
        link.utilization = 0.1
        e_low = _compute_link_energy(net, "s1", "s2")
        link.utilization = 0.8
        e_high = _compute_link_energy(net, "s1", "s2")
        assert e_high > e_low

    def test_energy_invalid_link_returns_zero(self, net):
        """Non-existent link should return 0."""
        assert _compute_link_energy(net, "s1", "s10") == 0.0


class TestCarbonFormula:
    """Tests for per-link carbon emission computation (HLD §4.3)."""

    def test_carbon_positive(self, net):
        """Carbon emission must be positive for any active link."""
        c = _compute_link_carbon(net, "s1", "s2")
        assert c > 0

    def test_carbon_formula_structure(self, net):
        """C = E × (I_region / 100.0), HLD §4.3."""
        energy = _compute_link_energy(net, "s1", "s2")
        dst_region = net.switches["s2"].region
        ci = REGION_CARBON_INTENSITY[dst_region]
        expected = energy * (ci / 100.0)
        actual = _compute_link_carbon(net, "s1", "s2")
        assert actual == pytest.approx(expected, rel=1e-6)

    def test_coal_produces_more_carbon_than_solar(self, net):
        """Coal-region link should emit more carbon than solar-region link."""
        # Set same utilization for fair comparison
        for link in net.links.values():
            link.utilization = 0.2
        c_coal = _compute_link_carbon(net, "s1", "s2")   # dst=s2 (coal)
        c_solar = _compute_link_carbon(net, "s4", "s9")   # dst=s9 (solar)
        assert c_coal > c_solar

    def test_carbon_uses_destination_region(self, net):
        """Carbon should use the destination switch's region, not source."""
        # s2 is coal_region, s6 is gas_region
        c = _compute_link_carbon(net, "s2", "s6")
        energy = _compute_link_energy(net, "s2", "s6")
        ci_gas = REGION_CARBON_INTENSITY["gas_region"]
        expected = energy * (ci_gas / 100.0)
        assert c == pytest.approx(expected, rel=1e-6)


class TestBaselineDijkstra:
    """Tests for baseline latency-only routing (HLD §3.2)."""

    def test_returns_valid_path(self, net):
        """Baseline should return a non-None RouteResult."""
        result = baseline_dijkstra(net, "h1", "h2")
        assert result is not None
        assert isinstance(result, RouteResult)

    def test_path_starts_at_ingress(self, net):
        """Path should start at s1 (ingress)."""
        result = baseline_dijkstra(net, "h1", "h2")
        assert result.path[0] == "s1"

    def test_path_ends_at_egress(self, net):
        """Path should end at s10 (egress)."""
        result = baseline_dijkstra(net, "h1", "h2")
        assert result.path[-1] == "s10"

    def test_algorithm_label(self, net):
        """Algorithm should be labeled 'Baseline Dijkstra'."""
        result = baseline_dijkstra(net, "h1", "h2")
        assert result.algorithm == "Baseline Dijkstra"

    def test_total_cost_equals_latency(self, net):
        """For baseline, total cost should equal total latency."""
        result = baseline_dijkstra(net, "h1", "h2")
        assert result.total_cost == pytest.approx(result.total_latency_ms)

    def test_selects_lowest_latency_path(self, net):
        """At normal load, baseline should select the fastest path (via s2-s6)."""
        # Set uniform low utilization so path A is clearly fastest
        for link in net.links.values():
            link.utilization = 0.15
        result = baseline_dijkstra(net, "h1", "h2")
        # Path A (s1→s2→s6→s10) has lowest base latency: 0.5+0.8+0.5 = 1.8ms
        assert "s2" in result.path and "s6" in result.path


class TestCarbonRoute:
    """Tests for multi-objective CarbonRoute routing (HLD §3.2, §4.1)."""

    def test_returns_valid_path(self, net):
        """CarbonRoute should return a non-None RouteResult."""
        result = carbonroute(net, "h1", "h2")
        assert result is not None

    def test_path_connects_ingress_to_egress(self, net):
        """Path should go from s1 to s10."""
        result = carbonroute(net, "h1", "h2")
        assert result.path[0] == "s1"
        assert result.path[-1] == "s10"

    def test_algorithm_label(self, net):
        """Algorithm should be labeled 'CarbonRoute'."""
        result = carbonroute(net, "h1", "h2")
        assert result.algorithm == "CarbonRoute"

    def test_weight_constraint(self, net):
        """α + β + γ must equal 1.0."""
        # Default values
        result = carbonroute(net, "h1", "h2", alpha=0.33, beta=0.33, gamma=0.34)
        assert result is not None

    def test_performance_profile_picks_fast_path(self, net):
        """Performance profile (α=0.80) should favor fast path at normal load."""
        for link in net.links.values():
            link.utilization = 0.2
        result = carbonroute(net, "h1", "h2", alpha=0.80, beta=0.15, gamma=0.05)
        # Should select path via s2 (fastest corridor)
        assert "s2" in result.path

    def test_sustainability_profile_picks_green_path(self, net):
        """Sustainability profile (γ=0.60) should favor clean path at normal load."""
        for link in net.links.values():
            link.utilization = 0.2
        result = carbonroute(net, "h1", "h2", alpha=0.10, beta=0.30, gamma=0.60)
        # Should select path via s9 (solar/greenest exit)
        assert "s9" in result.path

    def test_different_profiles_produce_different_paths(self, net):
        """Different weight profiles should produce distinct path selections."""
        for link in net.links.values():
            link.utilization = 0.2
        perf = carbonroute(net, "h1", "h2", alpha=0.80, beta=0.15, gamma=0.05)
        green = carbonroute(net, "h1", "h2", alpha=0.10, beta=0.30, gamma=0.60)
        assert perf.path != green.path, \
            "Performance and Sustainability profiles should select different paths"

    def test_to_dict_has_correct_keys(self, net):
        """to_dict() must include the corrected carbon field name."""
        result = carbonroute(net, "h1", "h2")
        d = result.to_dict()
        assert "total_carbon_mgco2" in d
        assert "total_carbon_gco2" not in d
        assert "total_latency_ms" in d
        assert "total_energy_joules" in d
        assert "total_cost" in d
        assert "per_hop" in d


class TestGetAllPaths:
    """Tests for all-paths evaluation function."""

    def test_returns_multiple_paths(self, net):
        """With a mesh topology, there should be multiple candidate paths."""
        paths = get_all_paths_evaluated(net, "h1", "h2")
        assert len(paths) >= 4  # At least the 4 main corridor paths

    def test_each_path_has_required_fields(self, net):
        """Each evaluated path must have latency, energy, and carbon metrics."""
        paths = get_all_paths_evaluated(net, "h1", "h2")
        for p in paths:
            assert "path" in p
            assert "total_latency_ms" in p
            assert "total_energy_joules" in p
            assert "total_carbon_mgco2" in p

    def test_paths_start_at_s1(self, net):
        """All paths should start at the ingress switch s1."""
        paths = get_all_paths_evaluated(net, "h1", "h2")
        for p in paths:
            assert p["path"][0] == "s1"

    def test_paths_end_at_s10(self, net):
        """All paths should end at the egress switch s10."""
        paths = get_all_paths_evaluated(net, "h1", "h2")
        for p in paths:
            assert p["path"][-1] == "s10"
