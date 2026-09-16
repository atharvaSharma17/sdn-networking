"""
CarbonRoute Routing Algorithms

Implements two routing strategies:
  1. Baseline Dijkstra — minimizes latency only (traditional approach)
  2. CarbonRoute — multi-objective cost function balancing latency, energy, and carbon

Both algorithms operate on the same network graph and return comparable
results so experiments can directly compare them.
"""

import networkx as nx
from dataclasses import dataclass
from typing import List, Dict, Tuple, Optional
from src.simulator import SDNNetwork, REGION_CARBON_INTENSITY


@dataclass
class RouteResult:
    """Result of a routing computation."""
    algorithm: str
    path: List[str]
    total_latency_ms: float
    total_energy_joules: float
    total_carbon_mgco2: float
    total_cost: float
    per_hop: List[dict]

    def to_dict(self) -> dict:
        return {
            "algorithm": self.algorithm,
            "path": self.path,
            "total_latency_ms": round(self.total_latency_ms, 3),
            "total_energy_joules": round(self.total_energy_joules, 3),
            "total_carbon_mgco2": round(self.total_carbon_mgco2, 3),
            "total_cost": round(self.total_cost, 3),
            "per_hop": self.per_hop,
        }


def _compute_link_energy(net: SDNNetwork, src: str, dst: str) -> float:
    """
    Compute energy consumed by traversing a link (in millijoules).
    Uses a per-packet processing energy model scaled by switch power
    draw and link utilization, providing realistic differentiation
    between high-power and low-power paths.
    """
    link = net.links.get((src, dst))
    if not link:
        return 0.0

    sw_src = net.switches.get(src)
    sw_dst = net.switches.get(dst)
    if not sw_src or not sw_dst:
        return 0.0

    # Per-packet processing energy (mJ) scaled by switch power profile
    avg_power = (sw_src.power_consumption(link.utilization) +
                 sw_dst.power_consumption(link.utilization)) / 2.0

    # Scale: higher power switches = more energy per packet forwarded
    # Normalized to produce values in 5-50 mJ range for clear differentiation
    return avg_power * (0.1 + link.utilization * 0.2)


def _compute_link_carbon(net: SDNNetwork, src: str, dst: str) -> float:
    """
    Compute carbon emissions for a link traversal (in mgCO2eq).
    Carbon = Energy × Carbon Intensity of the destination switch's region.
    """
    energy_mj = _compute_link_energy(net, src, dst)

    sw_dst = net.switches.get(dst)
    if not sw_dst:
        return 0.0
    ci = REGION_CARBON_INTENSITY.get(sw_dst.region, 350)

    # Scale: energy_mj × (carbon_intensity / baseline_intensity)
    # Produces values in 1-100 mgCO2eq range — clearly differentiates dirty vs clean
    return energy_mj * (ci / 100.0)


def _evaluate_path(net: SDNNetwork, path: List[str], algorithm: str) -> RouteResult:
    """Evaluate all metrics for a given path through the network."""
    total_latency = 0.0
    total_energy = 0.0
    total_carbon = 0.0
    per_hop = []

    for i in range(len(path) - 1):
        src, dst = path[i], path[i + 1]
        link = net.links.get((src, dst))
        if not link:
            continue

        hop_latency = link.current_latency_ms
        hop_energy = _compute_link_energy(net, src, dst)
        hop_carbon = _compute_link_carbon(net, src, dst)

        total_latency += hop_latency
        total_energy += hop_energy
        total_carbon += hop_carbon

        per_hop.append({
            "hop": f"{src} → {dst}",
            "latency_ms": round(hop_latency, 3),
            "energy_j": round(hop_energy, 3),
            "carbon_mgco2": round(hop_carbon, 3),
            "utilization": round(link.utilization, 3),
        })

    return RouteResult(
        algorithm=algorithm,
        path=path,
        total_latency_ms=total_latency,
        total_energy_joules=total_energy,
        total_carbon_mgco2=total_carbon,
        total_cost=0.0,  # Filled in by algorithm
        per_hop=per_hop,
    )


def baseline_dijkstra(net: SDNNetwork, src_host: str, dst_host: str) -> Optional[RouteResult]:
    """
    Traditional shortest-path routing. Minimizes latency only.
    This is the baseline comparison algorithm (e.g., OSPF behavior).
    """
    # Build a weighted graph using only current latency
    G = nx.Graph()
    seen = set()
    for (s, d), link in net.links.items():
        key = tuple(sorted([s, d]))
        if key not in seen:
            seen.add(key)
            G.add_edge(s, d, weight=link.current_latency_ms)

    src_sw = net.hosts[src_host].connected_switch
    dst_sw = net.hosts[dst_host].connected_switch

    try:
        path = nx.shortest_path(G, source=src_sw, target=dst_sw, weight="weight")
    except nx.NetworkXNoPath:
        return None

    result = _evaluate_path(net, path, "Baseline Dijkstra")
    result.total_cost = result.total_latency_ms
    return result


def carbonroute(net: SDNNetwork, src_host: str, dst_host: str,
                alpha: float = 0.33, beta: float = 0.33,
                gamma: float = 0.34) -> Optional[RouteResult]:
    """
    CarbonRoute multi-objective routing algorithm.

    Cost(edge) = α × Normalized_Latency + β × Normalized_Energy + γ × Normalized_Carbon

    Where α + β + γ = 1.0
    """
    src_sw = net.hosts[src_host].connected_switch
    dst_sw = net.hosts[dst_host].connected_switch

    # Step 1: Collect raw metrics for all links
    raw_metrics = {}
    seen = set()
    for (s, d), link in net.links.items():
        key = tuple(sorted([s, d]))
        if key not in seen:
            seen.add(key)
            raw_metrics[key] = {
                "latency": link.current_latency_ms,
                "energy": _compute_link_energy(net, s, d),
                "carbon": _compute_link_carbon(net, s, d),
            }

    # Step 2: Min-max normalization across all links
    all_lat = [m["latency"] for m in raw_metrics.values()]
    all_eng = [m["energy"] for m in raw_metrics.values()]
    all_crb = [m["carbon"] for m in raw_metrics.values()]

    def normalize(val, vals):
        mn, mx = min(vals), max(vals)
        if mx == mn:
            return 0.5
        return (val - mn) / (mx - mn)

    # Step 3: Build weighted graph with composite cost
    G = nx.Graph()
    for (s, d), metrics in raw_metrics.items():
        norm_l = normalize(metrics["latency"], all_lat)
        norm_e = normalize(metrics["energy"], all_eng)
        norm_c = normalize(metrics["carbon"], all_crb)
        cost = alpha * norm_l + beta * norm_e + gamma * norm_c
        G.add_edge(s, d, weight=cost)

    try:
        path = nx.shortest_path(G, source=src_sw, target=dst_sw, weight="weight")
    except nx.NetworkXNoPath:
        return None

    result = _evaluate_path(net, path, "CarbonRoute")
    # Compute total composite cost for the selected path
    total_cost = sum(G[path[i]][path[i+1]]["weight"] for i in range(len(path)-1))
    result.total_cost = total_cost
    return result


def get_all_paths_evaluated(net: SDNNetwork, src_host: str, dst_host: str,
                            alpha: float = 0.33, beta: float = 0.33,
                            gamma: float = 0.34) -> List[dict]:
    """
    Find ALL possible paths and evaluate each one.
    Used for the dashboard to show why a particular path was chosen.
    """
    src_sw = net.hosts[src_host].connected_switch
    dst_sw = net.hosts[dst_host].connected_switch

    # Step 1: Collect raw metrics for all links
    raw_metrics = {}
    seen = set()
    for (s, d), link in net.links.items():
        key = tuple(sorted([s, d]))
        if key not in seen:
            seen.add(key)
            raw_metrics[key] = {
                "latency": link.current_latency_ms,
                "energy": _compute_link_energy(net, s, d),
                "carbon": _compute_link_carbon(net, s, d),
            }

    # Step 2: Min-max normalization
    all_lat = [m["latency"] for m in raw_metrics.values()]
    all_eng = [m["energy"] for m in raw_metrics.values()]
    all_crb = [m["carbon"] for m in raw_metrics.values()]

    def normalize(val, vals):
        mn, mx = min(vals), max(vals)
        if mx == mn:
            return 0.5
        return (val - mn) / (mx - mn)

    # Step 3: Build weighted graph with composite cost
    G = nx.Graph()
    for (s, d), metrics in raw_metrics.items():
        norm_l = normalize(metrics["latency"], all_lat)
        norm_e = normalize(metrics["energy"], all_eng)
        norm_c = normalize(metrics["carbon"], all_crb)
        cost = alpha * norm_l + beta * norm_e + gamma * norm_c
        G.add_edge(s, d, weight=cost)

    # Step 4: Use Yen's Algorithm (K-Shortest Paths) to get the top 8 paths
    K = 8
    evaluated = []
    
    try:
        # shortest_simple_paths yields paths in increasing order of weight (Yen's algorithm)
        path_generator = nx.shortest_simple_paths(G, source=src_sw, target=dst_sw, weight="weight")
        
        for i, path in enumerate(path_generator):
            if i >= K:
                break
                
            switch_path = [n for n in path if n in net.switches]
            if len(switch_path) < 2:
                continue
                
            result = _evaluate_path(net, switch_path, "Evaluation")
            
            evaluated.append({
                "path": switch_path,
                "total_latency_ms": round(result.total_latency_ms, 3),
                "total_energy_joules": round(result.total_energy_joules, 3),
                "total_carbon_mgco2": round(result.total_carbon_mgco2, 3),
            })
    except nx.NetworkXNoPath:
        pass

    return evaluated
