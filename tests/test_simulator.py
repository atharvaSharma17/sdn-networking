"""
CarbonRoute Test Suite — Simulator Tests

Validates the SDN network simulator including topology construction,
switch power models, M/M/1 queuing delay, and traffic simulation behavior.
"""

import pytest
from src.simulator import SDNNetwork, Switch, Link, build_demo_topology, REGION_CARBON_INTENSITY


class TestSwitch:
    """Tests for the Switch power consumption model (HLD §4.2)."""

    def test_power_at_zero_utilization(self):
        """P(0) should equal idle power."""
        sw = Switch(name="test", region="mixed_region",
                    idle_power_watts=50.0, max_power_watts=200.0)
        assert sw.power_consumption(0.0) == 50.0

    def test_power_at_full_utilization(self):
        """P(1) should equal max power."""
        sw = Switch(name="test", region="mixed_region",
                    idle_power_watts=50.0, max_power_watts=200.0)
        assert sw.power_consumption(1.0) == 200.0

    def test_power_linear_interpolation(self):
        """P(u) = P_idle + u × (P_max - P_idle), HLD §4.2."""
        sw = Switch(name="test", region="coal_region",
                    idle_power_watts=90.0, max_power_watts=380.0)
        u = 0.5
        expected = 90.0 + 0.5 * (380.0 - 90.0)  # = 235.0
        assert sw.power_consumption(u) == pytest.approx(expected)

    def test_power_at_partial_utilization(self):
        """P(0.2) should be between idle and max."""
        sw = Switch(name="test", region="mixed_region",
                    idle_power_watts=40.0, max_power_watts=150.0)
        p = sw.power_consumption(0.2)
        assert 40.0 < p < 150.0
        assert p == pytest.approx(40.0 + 0.2 * (150.0 - 40.0))


class TestLink:
    """Tests for the Link M/M/1 queuing model (HLD §3.1)."""

    def test_latency_at_zero_utilization(self):
        """At u=0, latency should equal base latency."""
        link = Link(src="a", dst="b", bandwidth_mbps=1000,
                    base_latency_ms=2.0, utilization=0.0)
        assert link.current_latency_ms == pytest.approx(2.0)

    def test_latency_increases_with_utilization(self):
        """Latency increases as utilization increases (M/M/1 property)."""
        link = Link(src="a", dst="b", bandwidth_mbps=1000,
                    base_latency_ms=2.0, utilization=0.0)
        lat_0 = link.current_latency_ms
        link.utilization = 0.5
        lat_50 = link.current_latency_ms
        link.utilization = 0.8
        lat_80 = link.current_latency_ms
        assert lat_0 < lat_50 < lat_80

    def test_latency_mm1_formula(self):
        """Verify M/M/1 formula: latency = base × 1/(1-u)."""
        link = Link(src="a", dst="b", bandwidth_mbps=1000,
                    base_latency_ms=5.0, utilization=0.5)
        expected = 5.0 * (1.0 / (1.0 - 0.5))  # = 10.0
        assert link.current_latency_ms == pytest.approx(expected)

    def test_latency_capped_at_10x(self):
        """Latency should be capped at 10× base even at extreme utilization."""
        link = Link(src="a", dst="b", bandwidth_mbps=1000,
                    base_latency_ms=2.0, utilization=0.99)
        assert link.current_latency_ms == pytest.approx(2.0 * 10.0)


class TestCarbonIntensity:
    """Tests for regional carbon intensity values (HLD §4.3)."""

    def test_all_six_regions_present(self):
        """All 6 HLD-specified regions must exist."""
        expected_regions = [
            "coal_region", "gas_region", "mixed_region",
            "hydro_region", "solar_region", "nuclear_region"
        ]
        for region in expected_regions:
            assert region in REGION_CARBON_INTENSITY

    def test_carbon_intensity_values(self):
        """Carbon intensities must match HLD §4.3 exactly."""
        assert REGION_CARBON_INTENSITY["coal_region"] == 820
        assert REGION_CARBON_INTENSITY["gas_region"] == 490
        assert REGION_CARBON_INTENSITY["mixed_region"] == 350
        assert REGION_CARBON_INTENSITY["hydro_region"] == 70
        assert REGION_CARBON_INTENSITY["solar_region"] == 45
        assert REGION_CARBON_INTENSITY["nuclear_region"] == 12


class TestTopologyStructure:
    """Tests for the demo topology (HLD §5)."""

    @pytest.fixture
    def net(self):
        return build_demo_topology()

    def test_switch_count(self, net):
        """Topology must have exactly 10 switches."""
        assert len(net.switches) == 10

    def test_host_count(self, net):
        """Topology must have exactly 2 hosts."""
        assert len(net.hosts) == 2

    def test_host_ips(self, net):
        """Hosts must have correct IPs per HLD §5."""
        assert net.hosts["h1"].ip == "10.0.0.1"
        assert net.hosts["h2"].ip == "10.0.0.2"

    def test_host_connections(self, net):
        """h1 connected to s1, h2 connected to s10."""
        assert net.hosts["h1"].connected_switch == "s1"
        assert net.hosts["h2"].connected_switch == "s10"

    def test_ingress_switch_exists(self, net):
        """s1 must exist as ingress."""
        assert "s1" in net.switches

    def test_egress_switch_exists(self, net):
        """s10 must exist as egress."""
        assert "s10" in net.switches

    def test_all_switches_named(self, net):
        """Switches s1 through s10 must all exist."""
        for i in range(1, 11):
            assert f"s{i}" in net.switches

    def test_path_a_links_exist(self, net):
        """Path A (s1-s2-s6-s10) must have all links."""
        assert ("s1", "s2") in net.links
        assert ("s2", "s6") in net.links
        assert ("s6", "s10") in net.links

    def test_path_d_links_exist(self, net):
        """Path D (s1-s5-s9-s10) must have all links."""
        assert ("s1", "s5") in net.links
        assert ("s5", "s9") in net.links
        assert ("s9", "s10") in net.links

    def test_cross_links_exist(self, net):
        """Cross-links enabling hybrid routing must exist."""
        assert ("s3", "s8") in net.links  # Gas → Hydro hybrid
        assert ("s4", "s9") in net.links  # Mixed → Solar hybrid

    def test_region_assignments(self, net):
        """Key switches must have correct grid region assignments."""
        assert net.switches["s2"].region == "coal_region"
        assert net.switches["s5"].region == "hydro_region"
        assert net.switches["s9"].region == "solar_region"
        assert net.switches["s10"].region == "nuclear_region"

    def test_differentiated_power_profiles(self, net):
        """Coal/gas switches should have higher power draw than hydro/solar."""
        coal_max = net.switches["s2"].max_power_watts
        solar_max = net.switches["s9"].max_power_watts
        assert coal_max > solar_max * 2  # Coal should be >2x solar


class TestTrafficSimulation:
    """Tests for traffic simulation behavior (HLD §6)."""

    @pytest.fixture
    def net(self):
        return build_demo_topology()

    def test_normal_utilization_range(self, net):
        """Normal utilization must be within 10-35% (HLD §6)."""
        net.simulate_traffic()
        for (src, dst), link in net.links.items():
            assert 0.10 <= link.utilization <= 0.35, \
                f"Link {src}-{dst} utilization {link.utilization} outside 10-35%"

    def test_congestion_fixed_at_85_percent(self, net):
        """Congested links must be at exactly 85% (HLD §6)."""
        congested = [("s1", "s2"), ("s2", "s6")]
        net.simulate_traffic(congested_links=congested)
        for src, dst in congested:
            assert net.links[(src, dst)].utilization == pytest.approx(0.85), \
                f"Congested link {src}-{dst} should be at 85%"

    def test_non_congested_links_normal_range(self, net):
        """Non-congested links should still be in normal range."""
        congested = [("s1", "s2")]
        net.simulate_traffic(congested_links=congested)
        # Check a link that is NOT congested
        link_s4_s8 = net.links.get(("s4", "s8"))
        if link_s4_s8:
            assert 0.10 <= link_s4_s8.utilization <= 0.35
