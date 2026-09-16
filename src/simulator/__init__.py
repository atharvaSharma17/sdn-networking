"""
CarbonRoute SDN Network Simulator

Simulates an SDN network topology with switches, hosts, and links.
Each link carries properties for latency, bandwidth, and is assigned
to a geographic region with a specific energy grid carbon intensity.

This module replaces the need for Mininet + Open vSwitch by providing
a fully in-memory simulation of the data plane.
"""

import networkx as nx
import random
import time
from dataclasses import dataclass, field
from typing import Dict, List, Tuple, Optional


@dataclass
class Link:
    """Represents a network link between two switches."""
    src: str
    dst: str
    bandwidth_mbps: float     # Max capacity
    base_latency_ms: float    # Base propagation delay
    utilization: float = 0.0  # Current utilization (0.0 - 1.0)
    packet_loss: float = 0.0  # Current packet loss rate

    @property
    def current_latency_ms(self) -> float:
        """Latency increases under congestion (M/M/1 queuing model approximation)."""
        congestion_factor = 1.0 / max(0.01, 1.0 - self.utilization)
        return self.base_latency_ms * min(congestion_factor, 10.0)


@dataclass
class Switch:
    """Represents an OpenFlow-compatible SDN switch."""
    name: str
    region: str               # Geographic region (affects carbon intensity)
    idle_power_watts: float = 50.0
    max_power_watts: float = 200.0
    flow_table: List[dict] = field(default_factory=list)

    def power_consumption(self, utilization: float) -> float:
        """Linear interpolation energy model: P = P_idle + U × (P_max - P_idle)"""
        return self.idle_power_watts + utilization * (self.max_power_watts - self.idle_power_watts)


@dataclass
class Host:
    """Represents a network endpoint."""
    name: str
    ip: str
    mac: str
    connected_switch: str


# Carbon intensity per region (gCO2eq per kWh)
REGION_CARBON_INTENSITY = {
    "coal_region":       820,   # Coal-heavy grid
    "gas_region":        490,   # Natural gas grid
    "mixed_region":      350,   # Mixed energy sources
    "hydro_region":      70,    # Hydroelectric
    "solar_region":      45,    # Solar/wind dominant
    "nuclear_region":    12,    # Nuclear power
}


class SDNNetwork:
    """
    Full in-memory simulation of an SDN network.
    Replaces Mininet + Open vSwitch for demonstration purposes.
    """

    def __init__(self):
        self.graph = nx.Graph()
        self.switches: Dict[str, Switch] = {}
        self.hosts: Dict[str, Host] = {}
        self.links: Dict[Tuple[str, str], Link] = {}
        self._running = False

    def add_switch(self, name: str, region: str = "mixed_region",
                   idle_power: float = 50.0, max_power: float = 200.0) -> Switch:
        sw = Switch(name=name, region=region,
                    idle_power_watts=idle_power, max_power_watts=max_power)
        self.switches[name] = sw
        self.graph.add_node(name, type="switch", region=region)
        return sw

    def add_host(self, name: str, ip: str, mac: str, connected_switch: str) -> Host:
        host = Host(name=name, ip=ip, mac=mac, connected_switch=connected_switch)
        self.hosts[name] = host
        self.graph.add_node(name, type="host")
        self.graph.add_edge(name, connected_switch, bandwidth=1000, latency=0.1)
        return host

    def add_link(self, src: str, dst: str,
                 bandwidth_mbps: float = 100.0,
                 latency_ms: float = 2.0) -> Link:
        link = Link(src=src, dst=dst, bandwidth_mbps=bandwidth_mbps,
                    base_latency_ms=latency_ms)
        self.links[(src, dst)] = link
        self.links[(dst, src)] = link  # Bidirectional
        self.graph.add_edge(src, dst, bandwidth=bandwidth_mbps, latency=latency_ms)
        return link

    def simulate_traffic(self, congested_links: Optional[List[Tuple[str, str]]] = None):
        """
        Simulate network traffic by randomizing utilization on all links.
        Optionally inject heavy congestion on specific links.
        """
        for key, link in self.links.items():
            # Base random utilization between 5% and 35%
            link.utilization = random.uniform(0.10, 0.35)
            link.packet_loss = random.uniform(0.0, 0.5)

        # Inject congestion on specified links
        if congested_links:
            for src, dst in congested_links:
                if (src, dst) in self.links:
                    self.links[(src, dst)].utilization = 0.85
                    self.links[(src, dst)].packet_loss = random.uniform(2.0, 8.0)

    def get_link_stats(self, src: str, dst: str) -> dict:
        """Get current statistics for a link."""
        link = self.links.get((src, dst))
        if not link:
            return {}
        return {
            "src": src,
            "dst": dst,
            "bandwidth_mbps": link.bandwidth_mbps,
            "base_latency_ms": link.base_latency_ms,
            "current_latency_ms": round(link.current_latency_ms, 2),
            "utilization": round(link.utilization, 3),
            "packet_loss": round(link.packet_loss, 3),
            "throughput_mbps": round(link.bandwidth_mbps * (1 - link.utilization), 2),
        }

    def get_all_stats(self) -> List[dict]:
        """Get stats for all unique links."""
        seen = set()
        stats = []
        for (src, dst), link in self.links.items():
            key = tuple(sorted([src, dst]))
            if key not in seen:
                seen.add(key)
                stats.append(self.get_link_stats(src, dst))
        return stats

    def get_topology_data(self) -> dict:
        """Return serializable topology for the frontend."""
        nodes = []
        for name, sw in self.switches.items():
            nodes.append({
                "id": name, "label": name, "type": "switch",
                "region": sw.region,
                "carbon_intensity": REGION_CARBON_INTENSITY.get(sw.region, 350),
            })
        for name, host in self.hosts.items():
            nodes.append({
                "id": name, "label": f"{name} ({host.ip})", "type": "host",
            })

        edges = []
        seen = set()
        for (src, dst), link in self.links.items():
            key = tuple(sorted([src, dst]))
            if key not in seen:
                seen.add(key)
                edges.append({
                    "from": src, "to": dst,
                    "bandwidth": link.bandwidth_mbps,
                    "latency": link.base_latency_ms,
                    "utilization": round(link.utilization, 3),
                })
        # Add host-switch edges
        for name, host in self.hosts.items():
            edges.append({"from": name, "to": host.connected_switch,
                          "bandwidth": 1000, "latency": 0.1, "utilization": 0})

        return {"nodes": nodes, "edges": edges}


def build_demo_topology() -> SDNNetwork:
    """
    Build a 10-switch two-tier partial mesh topology for CarbonRoute demonstration.

    Topology:
                  ┌────── s2 [Coal] ──────── s6 [Gas] ──────┐
                  │         │ ╲            ╱   │              │
    h1 ── s1 ────┤       s2↔s3  ╲      ╱    s6↔s7           ├── s10 ── h2
       [Mixed]    │         │    ╲    ╱       │           [Nuclear]
                  ├──── s3 [Gas] ──── s7 [Mixed] ────────────┤
                  │         │   ╲          ╱   │              │
                  │       s3↔s4  ╲        ╱    │              │
                  ├──── s4 [Mixed]──── s8 [Hydro] ────────────┤
                  │         │              │                  │
                  │         │            s8↔s9                │
                  └──── s5 [Hydro] ──── s9 [Solar] ───────────┘

    Key paths (all Pareto non-dominated):
      Path A: s1 → s2 → s6 → s10  (Fastest, highest carbon)
      Path B: s1 → s3 → s7 → s10  (Medium speed, medium carbon)
      Path C: s1 → s4 → s8 → s10  (Slower, clean)
      Path D: s1 → s5 → s9 → s10  (Slowest, greenest)

    Cross-links enable hybrid routing:
      X1: s1 → s3 → s8 → s10  (Gas entry, Hydro exit)
      X2: s1 → s4 → s9 → s10  (Mixed entry, Solar exit)
    """
    net = SDNNetwork()

    # Switches with differentiated power profiles and regional grid assignments
    net.add_switch("s1",  region="mixed_region",   idle_power=40,  max_power=150)   # Ingress
    net.add_switch("s2",  region="coal_region",    idle_power=90,  max_power=380)   # Tier-1 fast/dirty
    net.add_switch("s3",  region="gas_region",     idle_power=70,  max_power=290)   # Tier-1 medium
    net.add_switch("s4",  region="mixed_region",   idle_power=45,  max_power=175)   # Tier-1 medium
    net.add_switch("s5",  region="hydro_region",   idle_power=38,  max_power=145)   # Tier-1 clean
    net.add_switch("s6",  region="gas_region",     idle_power=68,  max_power=275)   # Tier-2 fast exit
    net.add_switch("s7",  region="mixed_region",   idle_power=42,  max_power=165)   # Tier-2 medium exit
    net.add_switch("s8",  region="hydro_region",   idle_power=35,  max_power=135)   # Tier-2 clean exit
    net.add_switch("s9",  region="solar_region",   idle_power=28,  max_power=110)   # Tier-2 greenest exit
    net.add_switch("s10", region="nuclear_region", idle_power=30,  max_power=120)   # Egress

    # Hosts
    net.add_host("h1", ip="10.0.0.1", mac="00:00:00:00:00:01", connected_switch="s1")
    net.add_host("h2", ip="10.0.0.2", mac="00:00:00:00:00:02", connected_switch="s10")

    # --- Ingress links (s1 → Tier-1) ---
    net.add_link("s1", "s2", bandwidth_mbps=10000, latency_ms=0.5)   # Ultra-fast entry
    net.add_link("s1", "s3", bandwidth_mbps=5000,  latency_ms=1.5)   # Fast entry
    net.add_link("s1", "s4", bandwidth_mbps=2000,  latency_ms=3.0)   # Medium entry
    net.add_link("s1", "s5", bandwidth_mbps=1000,  latency_ms=6.0)   # Slow clean entry

    # --- Corridor links (Tier-1 → Tier-2 along same corridor) ---
    net.add_link("s2", "s6", bandwidth_mbps=8000,  latency_ms=0.8)   # Coal → Gas backbone
    net.add_link("s3", "s7", bandwidth_mbps=4000,  latency_ms=1.5)   # Gas → Mixed
    net.add_link("s4", "s8", bandwidth_mbps=3500,  latency_ms=1.5)   # Mixed → Hydro
    net.add_link("s5", "s9", bandwidth_mbps=2500,  latency_ms=1.5)   # Hydro → Solar

    # --- Cross-links (Tier-1 → Tier-2 across corridors) ---
    net.add_link("s2", "s7", bandwidth_mbps=1500,  latency_ms=3.0)   # Coal → Mixed
    net.add_link("s3", "s6", bandwidth_mbps=5000,  latency_ms=1.0)   # Gas → Gas fast
    net.add_link("s3", "s8", bandwidth_mbps=2500,  latency_ms=2.0)   # Gas → Hydro (hybrid)
    net.add_link("s4", "s7", bandwidth_mbps=3000,  latency_ms=2.0)   # Mixed → Mixed
    net.add_link("s4", "s9", bandwidth_mbps=1500,  latency_ms=2.5)   # Mixed → Solar (hybrid)
    net.add_link("s5", "s8", bandwidth_mbps=2000,  latency_ms=2.5)   # Hydro → Hydro

    # --- Within-tier cross-links ---
    net.add_link("s2", "s3", bandwidth_mbps=2000,  latency_ms=2.0)   # Tier-1: Coal ↔ Gas
    net.add_link("s3", "s4", bandwidth_mbps=1500,  latency_ms=2.5)   # Tier-1: Gas ↔ Mixed
    net.add_link("s6", "s7", bandwidth_mbps=2000,  latency_ms=2.0)   # Tier-2: Gas ↔ Mixed
    net.add_link("s8", "s9", bandwidth_mbps=2000,  latency_ms=1.5)   # Tier-2: Hydro ↔ Solar

    # --- Egress links (Tier-2 → s10) ---
    net.add_link("s6",  "s10", bandwidth_mbps=10000, latency_ms=0.5)  # Fast exit
    net.add_link("s7",  "s10", bandwidth_mbps=5000,  latency_ms=1.5)  # Medium exit
    net.add_link("s8",  "s10", bandwidth_mbps=2000,  latency_ms=3.0)  # Slower clean exit
    net.add_link("s9",  "s10", bandwidth_mbps=1000,  latency_ms=5.0)  # Greenest exit

    return net

