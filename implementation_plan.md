# Driver Dashboard Enhancements — Implementation Plan

Three enhancements to the driver dashboard: navigation directions, start/destination node fixes, and post-arrival baseline comparison.

## User Review Required

> [!IMPORTANT]
> **Feature 3 (post-arrival comparison)** requires running a complete fixed-time baseline simulation automatically when the ambulance arrives. This adds ~1-3s of compute per arrival. If you'd prefer a lighter approach (e.g., using pre-computed estimates instead of running a real baseline), let me know.

> [!NOTE]
> The start/destination node issue (Feature 2) appears to be a frontend display problem — the [RouteProgress](file:///c:/Users/ASUS/Downloads/INC/frontend/driver-dashboard/src/components/RouteProgress.tsx#10-83) component hardcodes intersection labels as `I1, I2...` without marking start/destination, and the corridor's first intersection (`INT_01`) is the origin but isn't visually distinguished. The backend data model (`corridor.intersection_ids`) does track the correct order.

---

## Proposed Changes

### Feature 1: Navigation Directions on Driver Dashboard

The backend already sends `next_intersection` and `instruction` in the driver status. We'll enhance this with turn-by-turn navigation data: distance to next intersection, link name, and bearing/heading info.

---

#### [MODIFY] [driver_routes.py](file:///c:/Users/ASUS/Downloads/INC/backend/app/api/driver_routes.py)

Add `directions` object to `/status/{run_id}` response containing:
- `current_link_name` — "INT_01 → INT_02"
- `distance_remaining_m` — remaining distance on current link
- `next_intersection_name` — human-readable name
- `total_distance_remaining_m` — total remaining to destination
- `heading` — "Straight ahead" (all links are a single corridor)

```diff
 return {
     "ev_id": ev.ev_id,
     "status": ev.status.value,
     "instruction": instruction,
     ...
+    "directions": {
+        "current_link": f"{link.from_intersection} → {link.to_intersection}" if link else None,
+        "distance_remaining_m": round(dist_remaining, 0),
+        "next_intersection_name": ix_name,
+        "total_distance_remaining_m": round(total_remaining, 0),
+        "heading": "Straight ahead",
+    },
 }
```

#### [MODIFY] [simulation_service.py](file:///c:/Users/ASUS/Downloads/INC/backend/app/services/simulation_service.py)

Add `directions` to the WebSocket driver instruction push in [_send_driver_update()](file:///c:/Users/ASUS/Downloads/INC/backend/app/services/simulation_service.py#225-268), mirroring the REST endpoint.

#### [NEW] [DirectionsBanner.tsx](file:///c:/Users/ASUS/Downloads/INC/frontend/driver-dashboard/src/components/DirectionsBanner.tsx)

New component showing:
- Navigation arrow icon (↑ straight ahead)
- Distance to next intersection
- Current link (e.g., "INT_01 → INT_02")
- Total remaining distance

Styled as a compact card below the instruction banner.

#### [MODIFY] [index.ts](file:///c:/Users/ASUS/Downloads/INC/frontend/driver-dashboard/src/types/index.ts)

Add `DirectionInfo` type and add `directions` field to [DriverStatus](file:///c:/Users/ASUS/Downloads/INC/frontend/driver-dashboard/src/types/index.ts#2-12) interface.

#### [MODIFY] [App.tsx](file:///c:/Users/ASUS/Downloads/INC/frontend/driver-dashboard/src/App.tsx)

Integrate `DirectionsBanner` between [InstructionBanner](file:///c:/Users/ASUS/Downloads/INC/frontend/driver-dashboard/src/components/InstructionBanner.tsx#16-33) and `SignalAhead`.

---

### Feature 2: Fix Start and Destination Node Display

The root cause: the [RouteProgress](file:///c:/Users/ASUS/Downloads/INC/frontend/driver-dashboard/src/components/RouteProgress.tsx#10-83) component labels intersections as `I1..I5` but doesn't mark origin/destination. The `/status` response doesn't include corridor start/end info. The corridor model correctly knows `INT_01` is the start and `INT_05` is the end.

---

#### [MODIFY] [driver_routes.py](file:///c:/Users/ASUS/Downloads/INC/backend/app/api/driver_routes.py)

Add `start_node` and `destination_node` to `/status`, `/route`, and `/live-corridor` responses, derived from `corridor.intersection_ids[0]` and `corridor.intersection_ids[-1]`.

```diff
 return {
     "ev_id": ev.ev_id,
     ...
+    "start_node": state.corridor.intersection_ids[0] if state.corridor.intersection_ids else None,
+    "destination_node": state.corridor.intersection_ids[-1] if state.corridor.intersection_ids else None,
 }
```

#### [MODIFY] [RouteProgress.tsx](file:///c:/Users/ASUS/Downloads/INC/frontend/driver-dashboard/src/components/RouteProgress.tsx)

- Accept `startNode` and `destinationNode` props
- Display first waypoint with "START" label (green badge)
- Display last waypoint with "DEST" label (accent badge)
- Properly label intersection names from backend data

#### [MODIFY] [InstructionBanner.tsx](file:///c:/Users/ASUS/Downloads/INC/frontend/driver-dashboard/src/components/InstructionBanner.tsx)

Show "From: {startNode} → To: {destinationNode}" under the instruction text when available.

#### [MODIFY] [CorridorStatus.tsx](file:///c:/Users/ASUS/Downloads/INC/frontend/driver-dashboard/src/components/CorridorStatus.tsx)

Add visual indicators for start and destination nodes — a "START" badge on the first intersection, "DEST" badge on the last.

#### [MODIFY] [App.tsx](file:///c:/Users/ASUS/Downloads/INC/frontend/driver-dashboard/src/App.tsx)

Pass `start_node` and `destination_node` from [status](file:///c:/Users/ASUS/Downloads/INC/backend/app/services/ev_service.py#16-18) to child components.

#### [MODIFY] [index.ts](file:///c:/Users/ASUS/Downloads/INC/frontend/driver-dashboard/src/types/index.ts)

Add `start_node` and `destination_node` fields to [DriverStatus](file:///c:/Users/ASUS/Downloads/INC/frontend/driver-dashboard/src/types/index.ts#2-12) and [LiveCorridor](file:///c:/Users/ASUS/Downloads/INC/frontend/driver-dashboard/src/types/index.ts#48-56) types.

---

### Feature 3: Post-Arrival MCTS vs Baseline Comparison

When the ambulance arrives at its destination, automatically run a baseline (fixed-time) simulation with the same parameters, then show a comparison screen.

---

#### [NEW] [arrival_comparison.py](file:///c:/Users/ASUS/Downloads/INC/backend/app/api/arrival_comparison.py) (helper, not a full route file)

New endpoint integrated into [driver_routes.py](file:///c:/Users/ASUS/Downloads/INC/backend/app/api/driver_routes.py):

`GET /api/driver/arrival-comparison/{run_id}` — When called:
1. Retrieves the original run's config from `simulation_service._run_configs`
2. Creates a new fixed-time simulation with same parameters (seed, duration, traffic profile)
3. Dispatches EV with same params
4. Runs to completion synchronously
5. Uses `analytics_service.compare_runs()` to generate comparison
6. Returns comparison data + computed time saved

#### [MODIFY] [driver_routes.py](file:///c:/Users/ASUS/Downloads/INC/backend/app/api/driver_routes.py)

Add the `/arrival-comparison/{run_id}` endpoint that orchestrates the baseline run and comparison.

#### [NEW] [BaselineComparison.tsx](file:///c:/Users/ASUS/Downloads/INC/frontend/driver-dashboard/src/components/BaselineComparison.tsx)

New component displayed on the arrival screen showing:
- **Time Saved** — big hero number with percentage
- **Comparison Table** — MCTS vs Baseline for: EV delay, avg queue, throughput
- **Improvement Bars** — visual progress bars showing % improvement
- Loading state while baseline simulation runs
- Styled with green/accent highlights for improvements

#### [MODIFY] [JourneyStats.tsx](file:///c:/Users/ASUS/Downloads/INC/frontend/driver-dashboard/src/components/JourneyStats.tsx)

Integrate `BaselineComparison` below the existing journey stats on arrival.

#### [MODIFY] [index.ts](file:///c:/Users/ASUS/Downloads/INC/frontend/driver-dashboard/src/types/index.ts)

Add `BaselineComparisonData` type.

---

## Verification Plan

### Automated Tests

**Existing tests** (95 tests in `backend/tests/`):
```bash
python -m pytest backend/tests/ -q
```

Key existing tests that validate our changes don't break anything:
- `test_api_endpoints.py::TestDriverEndpoints::test_driver_status` — verifies `/api/driver/status/{run_id}`
- `test_api_endpoints.py::TestDriverEndpoints::test_driver_route` — verifies `/api/driver/route/{run_id}`
- `test_comparison_integration.py::test_mcts_outperforms_baseline_on_ev_delay` — validates comparison logic

**New test to add** in `test_api_endpoints.py`:
- `test_driver_status_has_directions` — verify the directions field in status response
- `test_driver_status_has_start_destination_nodes` — verify start/destination nodes present
- `test_arrival_comparison_endpoint` — init MCTS run, dispatch EV, run to completion, call arrival-comparison endpoint, verify comparison fields returned

```bash
python -m pytest backend/tests/test_api_endpoints.py -v -k "driver"
```

### Manual Verification

1. Start the backend: `python -m uvicorn backend.app.main:app --reload --host 0.0.0.0 --port 8000`
2. Start the driver dashboard: `cd frontend && npm run dev --workspace=driver-dashboard`
3. Open admin dashboard (port 3000), create a simulation, start it, dispatch EV
4. Open driver dashboard (port 3001), connect to the running simulation
5. Verify:
   - **Directions**: Navigation directions card visible between instruction banner and signal ahead
   - **Start/Dest nodes**: Route progress bar shows "START" and "DEST" labels with green/accent badges
   - **Arrival comparison**: When EV reaches destination, a comparison panel loads showing MCTS time vs baseline time with % improvement
