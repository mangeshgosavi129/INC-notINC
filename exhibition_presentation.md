# INC: Dynamic Corridor Clearing with RH-MCTS
## Engineering Project Presentation & Design Document

---

## 1. Executive Pitch & Project Vision
Current traffic infrastructure suffers from a fatal paradox in emergency situations: intersections rely heavily on rigid, fixed-time signal offsets that fail to adapt to live anomalies. When standard Emergency Vehicle (EV) preemption systems are used—such as RFID or optic strobe detection—they execute brutally reactive overrides. While this forces a green light for the ambulance, it completely disrupts the network's phase coordination, causing massive "shockwaves" of congestion that can delay secondary emergency vehicles and gridlock the city for hours. 

Recent academic attempts to solve this use Deep Reinforcement Learning (DRL), which requires massive computational power, prolonged training, and yields an opaque "black-box" model that municipalities cannot safely audit or trust.

**INC** represents a paradigm shift in traffic orchestration. We have engineered a deterministic, real-time optimization engine using **Rolling Horizon Monte Carlo Tree Search (RH-MCTS)**. By executing thousands of lightweight, forward-looking simulations every 15 seconds, INC analytically calculates the exact signal phase sequence required to clear a path for the EV—while mathematically penalizing queue accumulation in cross-traffic. INC delivers the adaptability of AI without the black-box opacity, training overhead, or hardware costs.

---

## 2. Technical Architecture & System Mechanics

### 2.1 Event-Driven Simulation Engine
At its core, INC maintains an internal "Digital Twin" of the corridor network.
*   **Lazy Evaluation Queuing Model:** Instead of calculating vehicle kinematics frame-by-frame, queuing dynamics are resolved through a highly efficient lazy-evaluation macroscopic model. Traffic congestion is modeled using the Bureau of Public Roads (BPR) function: `speed_factor = 1 / (1 + 0.15 * (V/C)^4)`.
*   **Signal Controller FSM:** The traffic lights operate on strict deterministic constraints using a Finite State Machine (FSM), ensuring safety parameters (Minimum Green, non-interruptible 3s Amber, non-interruptible 2s All-Red) are invariant.

### 2.2 Algorithmic Core: Rolling Horizon MCTS
The MCTS algorithm operates as the intelligence layer, acting as a real-time supervisor over the local signal controllers.
*   **Search Space:** Every 15 seconds, the algorithm snapshot-captures the network state. It then explores an action space across the next 60-second horizon. Actions include `HOLD`, `TERMINATE`, `SKIP_TO_EV_PHASE`, and `EXTEND`.
*   **Fast-Forward Rollouts:** The system uses an accelerated, eventless simulation to rapidly play out chosen actions to the end of the 60s horizon.
*   **Multi-Objective Reward Function:** The quality of the simulated future is evaluated via a meticulously tuned equation:
    ```python
    Reward = - (W_EV * ev_delay) 
             - (W_QUEUE * total_queue) 
             + (W_THROUGHPUT * discharged) 
             - (W_STABILITY * phase_changes) 
             - (W_MAX_QUEUE * overflow)
    ```
*   **Result:** The algorithm identifies the phase sequence that yields the highest cumulative reward and transmits the immediate next step (e.g., `EXTEND_10`) to the physical intersection.

---

## 3. Core Technical Features & System Mechanics

INC boasts a complete, full-stack architecture that transforms mathematical theory into an applicable edge-computing node. The system provides the following highly technical capabilities:

### 3.1. Predictive Traffic Orchestration via Search Trees (RH-MCTS)
*   **How it Works:** Rather than using static rules or trained neural weights, INC dynamically builds a state-action tree of the immediate future (a 60-second Rolling Horizon). At every 15-second epoch, it explores action nodes (`HOLD`, `TERMINATE`, `EXTEND_10`, `SKIP_TO_EV_PHASE`) and uses an Upper Confidence Bound for Trees (UCT) heuristic to navigate the optimal sequence of simulated events. The chosen best-reward trajectory directly dictates the next phase of the physical intersection.

### 3.2. Asynchronous Bi-directional Telemetry (WebSocket Layer)
*   **How it Works:** The system bypasses standard REST HTTP polling bottlenecks by implementing a high-throughput FastAPI WebSocket protocol. The centralized backend holds persistent asynchronous sockets with both the `Admin Dashboard` (React/Vite centralized control room) and the local `Driver Dashboard` (in the EV). This delivers sub-millisecond state pushes, feeding the driver dynamically updated ETAs and intercept speed advisories (e.g., "SLOW DOWN - 12s to Green") derived directly from the MCTS path projection.

### 3.3. Deterministic "Digital Twin" Simulator (Event-Driven)
*   **How it Works:** To evaluate MCTS nodes instantaneously without overwhelming the CPU, INC utilizes an event-based architectural pattern rather than a heavy, frame-by-frame kinematics simulation (such as SUMO or CARLA). It implements Lazy Evaluation for vehicle queues, only mutating network state when chronologically critical events occur (signal phase transitions, EV sensor crossings). Congestion curves are mathematically derived via the Bureau of Public Roads (BPR) capacity function, enabling thousands of "fast-forward" rollouts per second on standard commercial hardware.

### 3.4. Multi-Objective Reward Architecture for Shockwave Mitigation
*   **How it Works:** Most RFID-based preemption algorithms generate severe secondary gridlock ("shockwaves"). INC mitigates this via a scalar Reward Function that governs the MCTS engine. By penalizing accumulated cross-traffic queues `- (W_QUEUE * total_queue)` against EV progression, the system is mathematically constrained: it will proactively clear cross queues *before* the EV arrives to prevent catastrophic downstream gridlock.

### 3.5. Automated Parallel Baseline Verification Engine
*   **How it Works:** To empirically prove algorithmic superiority for academic review, INC houses a dual-execution test environment. Driven by deterministic seeded inputs, the system subjects an identical traffic demand profile to *two parallel routing engines*: the MCTS intelligent controller and a rigid Fixed-Time baseline model. It outputs hard, quantifiable deltas demonstrating the precise reduction in both EV journey time and generalized network delay.

### 3.6. Robust Signal Finite State Machine (FSM) Constraints
*   **How it Works:** To guarantee absolute physical safety, the intelligent algorithmic output is sandboxed by a rigorous, hardware-mimicking FSM. Regardless of the urgency calculated by the MCTS, the FSM strictly enforces inviolable physical transition states: minimum green times, a 3-second non-interruptible Amber phase, and a 2-second non-interruptible All-Red clearance interval. The solver evaluates solutions *around* these hard constraints, structurally preventing the generation of unsafe signal configurations.

---

## 4. The Business Scope & Commercial Edge

INC is positioned as a high-value B2G (Business-to-Government) integration for Smart City initiatives. 

*   **Low Barrier to Entry:** Because INC does not require localized edge-AI hardware (vision processing units for neural nets) or centralized cloud GPU clusters, it provides a highly attractive, cost-reduced architectural profile for public tenders.
*   **Retrofit Capability:** It interfaces via REST APIs with established Adaptive Traffic Control Systems (ATCS). It does not replace the hardware; it acts as an intelligent supervisor, massively lowering the capital expenditure for cities.
*   **Scalability:** The algorithm scales horizontally. A city can be segmented into discrete sub-corridors, each managed by independent, parallelized instances of the INC microservice.

---

## 5. Engineering Defense / Technical FAQs

**Q1: Why use MCTS instead of Deep Q-Networks (DQN) or A*?**
A: A* is computationally intractable for continuous traffic state spaces due to the branching factor. DQNs are sample-inefficient, non-deterministic, and prone to catastrophic forgetting. MCTS provides an elegant middle ground: it explores a massive state space efficiently via randomized rollouts and Upper Confidence Bounds (UCT), and most importantly, relies on an explainable, mathematical reward function rather than an opaque neural net.

**Q2: How does the system handle stochastic (unpredictable) background traffic?**
A: By utilizing a "Rolling Horizon." The algorithm only commits to the immediate 15-second action block before completely recalculating the entire tree based on fresh telemetry. This constant feedback loop natively corrects for unpredictable traffic surges or sensor noise.

**Q3: What guarantees that you won't trap cross-traffic indefinitely?**
A: Complete starvation is algorithmically prevented by our formulation of the Reward Function. The penalty term `- (W_QUEUE * total_queue)` grows non-linearly. Even if the EV priority is weighted high (`W_EV = 10`), the queue penalty will eventually surpass the EV priority mathematically, forcing the MCTS to deploy a green phase to the saturated approach to prevent system gridlock.
