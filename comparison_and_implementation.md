# Comparative Analysis: Rolling Horizon MCTS vs. State-of-the-Art Traffic Control Systems

## 1. The Global and Domestic Landscape

Traffic Signal Optimization and Emergency Vehicle (EV) Preemption represent classic challenges in stochastic queuing theory and urban network management. The fundamental difficulty is clearing a high-priority path without inducing cascading "shockwaves" of congestion across the entire network. Existing solutions fall into two primary categories: Reactive Rule-Based Systems and Deep Reinforcement Learning (DRL) approaches.

### 1.1 Reactive Rule-Based Systems (Standard Indian & Global Implementations)
The majority of current deployments, including the Adaptive Traffic Management Systems (ATMS) being rolled out in cities like Pune, rely heavily on hardware-based triggers (RFID, Optic, Acoustic, or basic GPS radius geofencing).
*   **Mechanism:** When an EV enters a predefined radius, the controller executes a hard override (e.g., immediate green phase) and holds cross-traffic indefinitely until the EV clears the intersection.
*   **Engineering Limitations:** These systems operate exclusively in the present tense. They are "greedy" and entirely reactive. By suddenly truncating background traffic phases, they violate existing timing offsets, leading to massive downstream queue accumulation and secondary gridlock once the EV has passed.

### 1.2 Model-Free Deep Reinforcement Learning (Academic State-of-the-Art)
The current academic trend for advanced traffic control involves Deep Q-Networks (DQN) or Deep Deterministic Policy Gradients (DDPG).
*   **Mechanism:** A neural network maps state spaces (camera feeds, queue matrices) to action spaces (signal configurations) by learning from millions of episodes of trial and error in simulators like SUMO.
*   **Engineering Limitations:** 
    *   **Sample Inefficiency:** Requires weeks of GPU training to converge.
    *   **The Black Box Problem:** Lack of interpretability. If a DQN controller makes a catastrophic routing choice, traffic engineers cannot trace *why*, making municipalities hesitant to adopt them.
    *   **Catastrophic Forgetting:** Neural nets struggle with non-stationary environments. An accident altering the corridor topology often requires complete retraining.

---

## 2. Our Approach: Rolling Horizon Monte Carlo Tree Search (RH-MCTS)

INC discards the heavy "black-box" neural network paradigm in favor of an active, predictive search algorithm. RH-MCTS models traffic control as a sequential decision-making process, executing rapid forward-simulations to mathematically evaluate the consequences of actions before applying them to the live intersection.

### 2.1 Technical Operation
1.  **State Snapshot:** At every decision interval (e.g., 15 seconds), the algorithm receives the current live state (queue lengths, signal phases, EV position).
2.  **Look-ahead Horizon:** It constructs a search tree representing the next 60 seconds of possible signal manipulations.
3.  **Action Space:** The root node branches into permissible actions: `HOLD`, `TERMINATE`, `SKIP_TO_EV_PHASE`, and `EXTEND`.
4.  **Rollout & Reward Evaluation:** The system runs an ultra-fast, event-less analytical simulation down each branch. It scores the future state using a multi-objective reward function:
    `Reward = - (W_EV * ev_delay) - (W_QUEUE * total_queue) + (W_THROUGHPUT * discharged) - (W_STABILITY * phase_changes)`

---

## 3. Why INC is Conceptually and Practically Superior (The USP)

INC’s architectural choices were deliberately made to outperform traditional models in real-world, resource-constrained municipal environments.

*   **Computational Efficiency & Edge Deployability:** Because INC does not use Deep Learning, it requires **zero training data and zero GPU clusters.** The algorithm calculates the optimal path analytically at runtime. It can be deployed on standard, low-cost servers directly at edge command centers.
*   **Total Interpretability (Determinism):** Every decision made by the RH-MCTS algorithm leaves a traceable mathematical footprint. Engineers can review the generated tree and the exact reward score that led to an action, ensuring accountability and facilitating easy hyperparameter tuning (`W_EV`, `W_QUEUE`).
*   **Proactive Shockwave Mitigation:** Unlike RFID preemption, which acts only when the EV is adjacent to the intersection, INC simulates 60 seconds into the future. It actively begins flushing queues *before* the EV arrives, ensuring a true "green wave" while simultaneously micro-adjusting cross-traffic to prevent generalized gridlock.
*   **Graceful Degradation:** If network telemetry drops, INC falls back natively to its fixed-time baseline FSM (Finite State Machine). Deep learning models typically degrade unpredictably when fed out-of-distribution input vectors.

---

## 4. Implementation Plan for Urban Scaling

Deploying INC into a smart-city grid (such as Pune) avoids heavy infrastructural overhauls. The deployment utilizes existing telemetry, focusing on software-level orchestration:

1.  **Corridor Digitization:** Map the target arterial routes into JSON topologies (defining links, capacities, and baseline timings) to create the system's internal digital twin.
2.  **Telemetry Integration:** Interface the INC backend with the city's existing Adaptive Traffic Control System (ATCS). INC will operate as a supervisor, reading live queue data and dispatching REST commands to local signal controllers.
3.  **EV GPS Onboarding:** Equip emergency vehicle fleets with lightweight mobile clients or tap into existing CAD (Computer-Aided Dispatch) GPS streams to feed high-frequency coordinates to the INC backend.
4.  **Baseline Calibration:** Run INC in "Shadow Mode," capturing live data and tuning the MCTS Reward Weights (EV delay vs. Queue accumulation) against historical profiles without altering physical lights.
5.  **Active Piloting & Analytics:** Execute active MCTS control. Utilize the built-in automated comparison modules to continuously measure MCTS performance against fixed-time baselines, generating concrete metrics on EV journey time reduction.
