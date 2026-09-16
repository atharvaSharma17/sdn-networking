# CarbonRoute: High-Level Design Document

## 1. Executive Summary

CarbonRoute is a Software-Defined Networking (SDN) routing framework that selects network paths by jointly optimizing three core metrics:

1. End-to-end transmission latency (Quality of Service)
2. Network hardware energy consumption (derived from switch utilization and port activity)
3. Estimated carbon footprint (derived from energy consumption and regional power grid emission factors)

Traditional routing protocols (such as OSPF, IS-IS, and standard Dijkstra implementations) evaluate shortest-path metrics solely through hop counts or link delays. CarbonRoute introduces a multi-objective cost formulation that integrates environmental impact metrics directly into the routing decision plane.

---

## 2. Technical Stack and Dependencies

The system is implemented as a modular Python-based architecture:


| Subsystem               | Technology                     | Source Location    |
| ------------------------- | -------------------------------- | -------------------- |
| Network Data Plane Sim  | Python 3, NetworkX Graph Model | `src/simulator/`   |
| Routing Engine          | Dijkstra, Multi-Objective Norm | `src/routing/`     |
| Experiment Orchestrator | Python Benchmark Runner        | `src/experiments/` |
| Application API Layer   | FastAPI, Uvicorn               | `src/backend/`     |
| Web Telemetry Console   | Vue.js 3, Tailwind CSS, Vis.js | `src/frontend/`    |

Runtime dependencies: `fastapi`, `uvicorn`, `networkx`.

---

## 3. Subsystem Architecture

The system operates across three decoupled planes:

```
[ Management & Visualization Console ]
      (Vue.js 3 / Tailwind CSS / Vis.js Canvas)
                       |
                       | REST API (JSON over HTTP)
                       v
[ Application & Decision Plane ]
      (FastAPI Server / In-Memory Graph Orchestrator)
         |                             |
         v                             v
[ Routing Computation Engine ]   [ SDN Network Simulator ]
  - Baseline Dijkstra Solver       - 7-Switch Mesh Topology
  - CarbonRoute Composite Solver   - Dynamic M/M/1 Queuing Delay
  - Min-Max Feature Normalizer     - Regional Grid Carbon Factor
```

### 3.1 Network Simulator (`src/simulator/`)

Represents the emulated SDN data plane. Switches and links maintain real-time operational states:

- **Switches:** Parameterized by idle power consumption (Watts), maximum load power consumption (Watts), and regional power grid assignment.
- **Links:** Parameterized by bandwidth capacity (Mbps), base physical propagation delay (ms), and dynamic link utilization (0.0 to 1.0).
- **Queuing Model:** Uses an M/M/1 queuing approximation where effective latency increases asymptotically as link utilization approaches capacity.

### 3.2 Routing Engine (`src/routing/`)

Evaluates candidate paths between ingress switch `s1` and egress switch `s7`. Supports two distinct algorithmic paths:

- **Baseline Dijkstra:** Solves for path minimizing link latency only.
- **CarbonRoute:** Solves for path minimizing composite weighted cost.

### 3.3 Application Backend (`src/backend/`)

Provides REST endpoints enabling external controllers and dashboards to query topology structure, trigger re-routing calculations, and execute benchmark suites.

---

## 4. Algorithmic Formulation

### 4.1 Multi-Objective Cost Function

For each directed network edge $e = (u, v)$, the composite cost is calculated as:

$$
\text{Cost}(e) = \alpha \cdot \hat{L}(e) + \beta \cdot \hat{E}(e) + \gamma \cdot \hat{C}(e)

$$

Subject to:

$$
\alpha + \beta + \gamma = 1.0, \quad \alpha, \beta, \gamma \ge 0

$$

Where $\hat{L}(e)$, $\hat{E}(e)$, and $\hat{C}(e)$ represent min-max normalized values of link latency, energy consumption, and carbon emissions across all active topology edges:

$$
\hat{X}(e) = \frac{X(e) - X_{\min}}{X_{\max} - X_{\min}}

$$

### 4.2 Power and Energy Model

Switch power dissipation follows a linear model based on forwarding utilization $u$:

$$
P(u) = P_{\text{idle}} + u \cdot (P_{\text{max}} - P_{\text{idle}})

$$

Per-packet forwarding energy for traversing link $(u, v)$ is formulated as:

$$
E(u, v) = \frac{P(u) + P(v)}{2} \cdot (0.10 + 0.20 \cdot u_{\text{link}}) \quad [\text{mJ}]

$$

### 4.3 Carbon Emission Model

Carbon emissions are calculated by mapping the egress switch to its regional power grid carbon intensity factor:

$$
C(u, v) = E(u, v) \cdot \left(\frac{I_{\text{region}}}{100.0}\right) \quad [\text{mgCO}_2\text{eq}]

$$

Standard carbon intensity factors applied:

- Coal-dominant grid: 820 $\text{gCO}_2/\text{kWh}$
- Natural gas grid: 490 $\text{gCO}_2/\text{kWh}$
- Regional mixed grid: 350 $\text{gCO}_2/\text{kWh}$
- Hydroelectric dominant: 70 $\text{gCO}_2/\text{kWh}$
- Solar/renewable dominant: 45 $\text{gCO}_2/\text{kWh}$
- Nuclear dominant: 12 $\text{gCO}_2/\text{kWh}$

---

## 5. Network Topology Design

The experimental topology consists of 7 OpenFlow-style switches connecting Host 1 (`10.0.0.1`) to Host 2 (`10.0.0.2`):

```
                 +-- s2 (Coal Grid) ---- s5 (Gas Grid) ---+
   h1 --- s1 ----+                                        +---- s7 --- h2
                 +-- s3 (Mixed Grid) --- s6 (Hydro Grid) -+
                 |                                        |
                 +-- s4 (Solar Grid) ---------------------+
```

Candidate transit paths:

1. **Path A (High Speed / High Carbon):** `s1 -> s2 -> s5 -> s7` (1000 Mbps capacity, ~3 ms base delay, high grid emission).
2. **Path B (Balanced Transit):** `s1 -> s3 -> s6 -> s7` (500 Mbps capacity, ~9 ms base delay, moderate grid emission).
3. **Path C (Low Emission Transit):** `s1 -> s4 -> s7` (200 Mbps capacity, ~10 ms base delay, clean renewable grid).

---

## 6. Experimental Evaluation Methodology

The test suite evaluates 4 network traffic scenarios across 3 optimization profiles:

### Scenarios

1. **Normal Network:** Baseline traffic conditions across all links (10-35% utilization).
2. **Fast Path Congested:** 85% traffic load injected onto Path A (`s1-s2`, `s2-s5`).
3. **Medium Path Congested:** 85% traffic load injected onto Path B (`s1-s3`, `s3-s6`).
4. **Multi-Path Congestion:** Heavy load injected on both Path A and Path B.

### Profiles

- **Performance-Optimized:** $\alpha = 0.80, \beta = 0.15, \gamma = 0.05$
- **Balanced Profile:** $\alpha = 0.40, \beta = 0.30, \gamma = 0.30$
- **Sustainability-First:** $\alpha = 0.10, \beta = 0.30, \gamma = 0.60$

---

## 7. Team Contributions

* **Naman Goyal (Core Developer):** Designed the multi-layer framework architecture. Formulated the composite cost function and normalization engine in Python. Developed the switch energy dissipation and regional carbon accounting models. Built the FastAPI backend routing endpoints, application schemas, and coordinated subsystem integration.
* **Saiyam Kalra (Frontend Developer):** Built the web-based monitoring dashboard using Vue.js and Tailwind CSS. Implemented the network graph canvas utilizing Vis.js with real-time active route rendering.
* **Arnav Kumar (Network Engineer):** Designed the 7-switch multi-path topology structure. Formulated link parameter definitions and queuing delay behavior under simulated link utilization.
* **Ranjit Mohanty (Data Analyst & Research):** Researched real-world regional power grid carbon intensity datasets. Designed the experimental scenario matrix and structured automated benchmarking routines.
* **Atharva Sharma (QA & Technical Documentation):** Authored the High-Level Design document and presentation deck. Executed integration test verification across the API and simulation pipelines.
