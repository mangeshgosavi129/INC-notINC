"""FastAPI app for the dynamic corridor clearing OpenEnv environment."""

from __future__ import annotations

import os

from fastapi.responses import HTMLResponse
from openenv.core.env_server.http_server import create_app

try:
    from ..models import DynamicCorridorAction, DynamicCorridorObservation
    from .dynamic_corridor_environment import DynamicCorridorEnvironment
except (ModuleNotFoundError, ImportError):
    from models import DynamicCorridorAction, DynamicCorridorObservation
    from server.dynamic_corridor_environment import DynamicCorridorEnvironment

_SHARED_ENV: DynamicCorridorEnvironment | None = None


def _build_dynamic_corridor_environment() -> DynamicCorridorEnvironment:
    return DynamicCorridorEnvironment(
        net_file=os.getenv("DYNAMIC_CORRIDOR_NET_FILE"),
        route_file=os.getenv("DYNAMIC_CORRIDOR_ROUTE_FILE"),
        sumo_binary=os.getenv("SUMO_BINARY", "sumo"),
        delta_time_s=int(os.getenv("DYNAMIC_CORRIDOR_DELTA_TIME", "5")),
        max_sim_time_s=int(os.getenv("DYNAMIC_CORRIDOR_MAX_SECONDS", "900")),
        seed=int(os.getenv("DYNAMIC_CORRIDOR_SEED", "42")),
    )


def create_dynamic_corridor_environment() -> DynamicCorridorEnvironment:
    global _SHARED_ENV
    if _SHARED_ENV is None:
        _SHARED_ENV = _build_dynamic_corridor_environment()
    return _SHARED_ENV


app = create_app(
    create_dynamic_corridor_environment,
    DynamicCorridorAction,
    DynamicCorridorObservation,
    env_name="dynamic_corridor_env",
    max_concurrent_envs=1,
)


@app.get("/viz", include_in_schema=False)
def visualization_page() -> HTMLResponse:
    return HTMLResponse(
        """
<!doctype html>
<html>
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Dynamic Corridor Control Room</title>
  <style>
    :root {
      --bg: #0c111b;
      --panel: #151b26;
      --subpanel: #0f1520;
      --line: #2a3344;
      --text: #e7edf7;
      --muted: #96a8c4;
      --accent: #4588ff;
      --warning: #f6d36a;
      --error: #ff9ca6;
      --good: #66d19e;
      --amber: #f5a524;
      --red: #f87171;
    }
    * { box-sizing: border-box; }
    body { font-family: Inter, Arial, sans-serif; margin: 0; padding: 18px; background: var(--bg); color: var(--text); }
    h1 { margin: 0 0 6px; font-size: 24px; }
    h2 { margin: 0 0 8px; font-size: 16px; }
    .muted { color: var(--muted); margin-bottom: 14px; }
    .layout { display: grid; grid-template-columns: 1.55fr 1fr; gap: 14px; }
    .panel { background: var(--panel); border: 1px solid var(--line); border-radius: 10px; padding: 12px; }
    .row { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; margin-bottom: 10px; }
    button {
      background: var(--accent);
      color: #fff;
      border: 0;
      border-radius: 6px;
      padding: 9px 12px;
      cursor: pointer;
      font-weight: 600;
      min-width: 88px;
    }
    button:hover { filter: brightness(1.06); }
    button.alt { background: #394862; }
    button.warn { background: #cd3f50; }
    input, select {
      padding: 8px;
      border-radius: 6px;
      border: 1px solid #3a465e;
      background: #101722;
      color: var(--text);
    }
    .statGrid { display: grid; grid-template-columns: repeat(4, minmax(120px, 1fr)); gap: 8px; margin-bottom: 10px; }
    .stat { background: var(--subpanel); border: 1px solid #283246; border-radius: 8px; padding: 8px; }
    .stat .k { color: var(--muted); font-size: 11px; }
    .stat .v { font-size: 18px; font-weight: 700; margin-top: 3px; }
    .corridorWrap { background: #0f1723; border: 1px solid #283246; border-radius: 8px; padding: 8px; }
    #corridor { width: 100%; height: 620px; display: block; border-radius: 8px; background: #0b1320; }
    .legend { color: var(--muted); font-size: 12px; margin-top: 6px; display: flex; gap: 12px; flex-wrap: wrap; }
    .dot { width: 10px; height: 10px; display: inline-block; border-radius: 50%; margin-right: 4px; vertical-align: middle; }
    .progress { margin-top: 10px; }
    .bar { width: 100%; background: #1f2735; border: 1px solid #2a3344; border-radius: 999px; overflow: hidden; height: 14px; }
    .barFill { height: 100%; width: 0%; background: linear-gradient(90deg, #29b6f6, #66bb6a); transition: width 0.18s linear; }
    .split { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; }
    table { width: 100%; border-collapse: collapse; }
    th, td { text-align: left; border-bottom: 1px solid #34425a; padding: 8px; font-size: 13px; }
    th { color: var(--muted); font-weight: 600; }
    .liveDataGrid { display: grid; grid-template-columns: 1fr 1fr 1.2fr; gap: 10px; margin-top: 12px; }
    .liveDataPanel { background: #091322; border: 1px solid #3d4d68; border-radius: 8px; padding: 10px; min-width: 0; }
    .liveDataPanel h3 { margin: 0 0 8px; font-size: 14px; color: #ffffff; }
    .liveDataPanel td:first-child { color: #a9bad4; width: 42%; }
    .liveDataPanel td:last-child { color: #ffffff; font-weight: 650; }
    .dataGrid { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }
    .dataPanel { background: var(--subpanel); border: 1px solid #283246; border-radius: 8px; padding: 10px; min-width: 0; }
    .dataPanel h3 { margin: 0 0 8px; font-size: 13px; color: #dbe7ff; }
    .tableScroll { overflow-x: auto; }
    .rawJson {
      margin: 0;
      max-height: 360px;
      overflow: auto;
      background: #08111f;
      border: 1px solid #253149;
      border-radius: 8px;
      padding: 10px;
      color: #d7e4f8;
      font-size: 11px;
      line-height: 1.45;
      white-space: pre-wrap;
      word-break: break-word;
    }
    .status { font-family: ui-monospace, SFMono-Regular, Menlo, monospace; white-space: pre-wrap; color: var(--warning); margin-top: 8px; min-height: 44px; }
    .status.error { color: var(--error); }
    .timelineWrap { position: relative; padding: 0 2px; }
    .timelineTicks { display: grid; gap: 0; margin-top: 6px; color: var(--muted); font-size: 11px; }
    .timelineTick {
      position: relative;
      min-width: 0;
      padding-top: 10px;
      text-align: center;
      font-variant-numeric: tabular-nums;
      overflow: hidden;
      text-overflow: ellipsis;
    }
    .timelineTick::before {
      content: "";
      position: absolute;
      top: 0;
      left: 50%;
      width: 1px;
      height: 7px;
      background: #51617b;
    }
    .snapshotPill { color: #d0dcf2; background: #202b3f; border: 1px solid #324059; padding: 2px 8px; border-radius: 999px; font-size: 11px; }
    @media (max-width: 1180px) {
      .layout { grid-template-columns: 1fr; }
      .split { grid-template-columns: 1fr; }
      .dataGrid { grid-template-columns: 1fr; }
      .liveDataGrid { grid-template-columns: 1fr; }
    }
  </style>
</head>
<body>
  <h1>Dynamic Corridor Control Room</h1>
  <div class="muted">Step-by-step simulation for EV, traffic flow, and agent phase decisions.</div>

  <div class="layout">
    <section class="panel">
      <div class="row">
        <button id="resetBtn">Reset</button>
        <button id="stepBtn">Step</button>
        <button id="autoBtn">Auto Step</button>
        <button id="pauseBtn" class="alt">Pause</button>
        <label>Task <input id="taskId" value="grid_4x4_default" /></label>
        <label>Source <input id="sourceId" value="NW_OUT" /></label>
        <label>Destination <input id="destinationId" value="SE_OUT" /></label>
        <label>View
          <select id="intersectionLimit">
            <option value="4">1 row</option>
            <option value="8">2 rows</option>
            <option value="12">3 rows</option>
            <option value="16" selected>Full 4x4 grid</option>
          </select>
        </label>
        <span class="snapshotPill">Snapshots: <span id="snapshotCount">0</span></span>
      </div>

      <div class="statGrid">
        <div class="stat"><div class="k">Sim Time</div><div class="v" id="simTime">-</div></div>
        <div class="stat"><div class="k">Step</div><div class="v" id="step">-</div></div>
        <div class="stat"><div class="k">Reward</div><div class="v" id="reward">-</div></div>
        <div class="stat"><div class="k">Done</div><div class="v" id="done">-</div></div>
      </div>

      <div class="corridorWrap">
        <svg id="corridor" viewBox="0 0 1100 700" preserveAspectRatio="xMidYMid meet"></svg>
        <div class="legend">
          <span><span class="dot" style="background: #66d19e;"></span>Current green phase serves EV</span>
          <span><span class="dot" style="background: #f87171;"></span>Phase mismatch</span>
          <span><span class="dot" style="background: #41b5ff;"></span>Emergency vehicle</span>
          <span><span class="dot" style="background: #f5a524;"></span>Queue bars</span>
          <span><span class="dot" style="background: #22c55e;"></span>Low traffic road weight</span>
          <span><span class="dot" style="background: #facc15;"></span>Medium traffic road weight</span>
          <span><span class="dot" style="background: #ef4444;"></span>High traffic road weight</span>
        </div>
      </div>

      <div class="liveDataGrid">
        <div class="liveDataPanel">
          <h3>Current Step</h3>
          <table><tbody id="liveStepBody"></tbody></table>
        </div>
        <div class="liveDataPanel">
          <h3>Emergency Vehicle</h3>
          <table><tbody id="liveEvBody"></tbody></table>
        </div>
        <div class="liveDataPanel">
          <h3>Route Choice</h3>
          <table><tbody id="liveRouteBody"></tbody></table>
        </div>
      </div>

      <div class="progress">
        <div style="display:flex;justify-content:space-between;color:var(--muted);font-size:12px;margin-bottom:4px;">
          <span>EV route progress</span><span id="evProgressLabel">0%</span>
        </div>
        <div class="bar"><div id="evProgressBar" class="barFill"></div></div>
      </div>

      <div class="status" id="status">Ready.</div>
    </section>

    <section class="panel">
      <h2>Agent Decision Panel</h2>
      <div class="split">
        <div>
          <table>
            <thead>
              <tr><th>Intersection</th><th>Chosen</th><th>Current</th><th>EV target</th><th>Queue</th></tr>
            </thead>
            <tbody id="decisionBody"></tbody>
          </table>
        </div>
        <div>
          <table>
            <thead>
              <tr><th>Metric</th><th>Value</th></tr>
            </thead>
            <tbody id="metricBody"></tbody>
          </table>
          <table style="margin-top:10px;">
            <thead>
              <tr><th>Reward breakdown</th><th>Value</th></tr>
            </thead>
            <tbody id="rewardBody"></tbody>
          </table>
        </div>
      </div>
      <div style="margin-top:10px;color:var(--muted);font-size:12px;">
        Last action reason: <span id="actionReason">Auto target EV phase</span>
      </div>
    </section>
  </div>

  <section class="panel" style="margin-top:14px;">
    <div class="row" style="justify-content:space-between;">
      <h2 style="margin:0;">Timeline</h2>
      <div>
        <button id="timelinePrev" class="alt">Prev snapshot</button>
        <button id="timelineNext" class="alt">Next snapshot</button>
      </div>
    </div>
    <div class="timelineWrap">
      <input type="range" id="timelineSlider" min="0" max="0" value="0" style="width:100%;" />
      <div id="timelineTicks" class="timelineTicks"></div>
    </div>
  </section>

  <section class="panel" style="margin-top:14px;">
    <div class="row" style="justify-content:space-between;">
      <h2 id="stepDataTitle" style="margin:0;">Step Data</h2>
      <span class="snapshotPill">Viewing: <span id="stepDataIndex">-</span></span>
    </div>
    <div class="dataGrid">
      <div class="dataPanel">
        <h3>Step Summary</h3>
        <table><tbody id="stepSummaryBody"></tbody></table>
      </div>
      <div class="dataPanel">
        <h3>Emergency Vehicle</h3>
        <table><tbody id="evDataBody"></tbody></table>
      </div>
      <div class="dataPanel">
        <h3>Intersections</h3>
        <div class="tableScroll">
          <table>
            <thead>
              <tr><th>ID</th><th>Current</th><th>Chosen</th><th>EV target</th><th>Queue</th><th>Vehicles</th><th>Speed</th><th>ETA</th><th>Distance</th></tr>
            </thead>
            <tbody id="intersectionDataBody"></tbody>
          </table>
        </div>
      </div>
      <div class="dataPanel">
        <h3>Route Candidates</h3>
        <div class="tableScroll">
          <table>
            <thead>
              <tr><th>Edge</th><th>From</th><th>To</th><th>Weight</th><th>Level</th><th>Queue</th><th>Delta</th><th>Closer</th><th>Backtrack</th></tr>
            </thead>
            <tbody id="routeCandidateBody"></tbody>
          </table>
        </div>
      </div>
      <div class="dataPanel">
        <h3>Road Weights</h3>
        <div class="tableScroll">
          <table>
            <thead>
              <tr><th>Edge</th><th>Weight</th><th>Traffic</th></tr>
            </thead>
            <tbody id="roadWeightBody"></tbody>
          </table>
        </div>
      </div>
      <div class="dataPanel">
        <h3>Raw Snapshot JSON</h3>
        <pre id="rawSnapshotJson" class="rawJson">{}</pre>
      </div>
    </div>
  </section>

  <script>
    const GRID_SIZE = 4;
    const INTERSECTION_ORDER = Array.from({ length: GRID_SIZE * GRID_SIZE }, (_, idx) => {
      const row = Math.floor(idx / GRID_SIZE) + 1;
      const col = (idx % GRID_SIZE) + 1;
      return `INT_${row}_${col}`;
    });
    const resetBtn = document.getElementById("resetBtn");
    const stepBtn = document.getElementById("stepBtn");
    const autoBtn = document.getElementById("autoBtn");
    const pauseBtn = document.getElementById("pauseBtn");
    const timelinePrev = document.getElementById("timelinePrev");
    const timelineNext = document.getElementById("timelineNext");
    const timelineSlider = document.getElementById("timelineSlider");
    const timelineTicks = document.getElementById("timelineTicks");
    const snapshotCount = document.getElementById("snapshotCount");
    const taskIdInput = document.getElementById("taskId");
    const sourceIdInput = document.getElementById("sourceId");
    const destinationIdInput = document.getElementById("destinationId");
    const intersectionLimit = document.getElementById("intersectionLimit");
    const statusEl = document.getElementById("status");
    const simTimeEl = document.getElementById("simTime");
    const stepEl = document.getElementById("step");
    const rewardEl = document.getElementById("reward");
    const doneEl = document.getElementById("done");
    const evProgressBar = document.getElementById("evProgressBar");
    const evProgressLabel = document.getElementById("evProgressLabel");
    const decisionBody = document.getElementById("decisionBody");
    const metricBody = document.getElementById("metricBody");
    const rewardBody = document.getElementById("rewardBody");
    const actionReason = document.getElementById("actionReason");
    const corridorSvg = document.getElementById("corridor");
    const liveStepBody = document.getElementById("liveStepBody");
    const liveEvBody = document.getElementById("liveEvBody");
    const liveRouteBody = document.getElementById("liveRouteBody");
    const stepDataTitle = document.getElementById("stepDataTitle");
    const stepDataIndex = document.getElementById("stepDataIndex");
    const stepSummaryBody = document.getElementById("stepSummaryBody");
    const evDataBody = document.getElementById("evDataBody");
    const intersectionDataBody = document.getElementById("intersectionDataBody");
    const routeCandidateBody = document.getElementById("routeCandidateBody");
    const roadWeightBody = document.getElementById("roadWeightBody");
    const rawSnapshotJson = document.getElementById("rawSnapshotJson");

    let autoTimer = null;
    let isRunning = false;
    let latestPayload = null;
    let snapshots = [];
    let timelineIndex = -1;
    let lastAction = {};
    let previousSnapshot = null;

    function setStatus(msg, isError = false) {
      statusEl.textContent = msg;
      statusEl.className = isError ? "status error" : "status";
    }

    function parseFeedback(feedback) {
      const fields = {};
      String(feedback || "").split(" ").forEach(part => {
        const idx = part.indexOf("=");
        if (idx > 0) {
          const k = part.slice(0, idx);
          const v = part.slice(idx + 1).replace("s", "");
          fields[k] = v;
        }
      });
      return fields;
    }

    function bestActionFromObservation(obs, visibleIds) {
      const phase_by_intersection = {};
      for (const ix of (obs.intersections || [])) {
        if (!visibleIds.includes(ix.intersection_id)) {
          continue;
        }
        phase_by_intersection[ix.intersection_id] = (ix.ev_target_phase ?? ix.current_phase ?? 0);
      }
      const candidates = (obs.route_choice?.candidates || [])
        .filter(c => c.destination_reachable)
        .sort((a, b) => {
          const aScore = (a.is_backtrack ? 1000 : 0) + (a.moves_closer ? 0 : 100) + Number(a.road_weight || 0) + Number(a.estimated_queue || 0) * 0.05;
          const bScore = (b.is_backtrack ? 1000 : 0) + (b.moves_closer ? 0 : 100) + Number(b.road_weight || 0) + Number(b.estimated_queue || 0) * 0.05;
          return aScore - bScore;
        });
      return {
        action: {
          phase_by_intersection,
          next_edge_id: candidates[0]?.edge_id ?? null,
          reason: "Auto target EV phase and lowest-cost route edge",
        }
      };
    }

    function visibleIntersections(obs) {
      const maxCount = Number(intersectionLimit.value || "4");
      return (obs.intersections || [])
        .filter(ix => INTERSECTION_ORDER.includes(ix.intersection_id))
        .sort((a, b) => INTERSECTION_ORDER.indexOf(a.intersection_id) - INTERSECTION_ORDER.indexOf(b.intersection_id))
        .slice(0, maxCount);
    }

    function pushSnapshot(payload) {
      const obs = payload.observation || {};
      snapshots.push({
        payload,
        observation: obs,
        step: Number(obs.step || 0),
        simTime: Number(obs.sim_time || 0),
      });
      timelineIndex = snapshots.length - 1;
      timelineSlider.max = String(Math.max(0, snapshots.length - 1));
      timelineSlider.value = String(timelineIndex);
      snapshotCount.textContent = String(snapshots.length);
      renderTimelineTicks();
    }

    function renderTimelineTicks() {
      const count = Math.max(1, snapshots.length);
      timelineTicks.style.gridTemplateColumns = `repeat(${count}, minmax(0, 1fr))`;
      timelineTicks.innerHTML = snapshots.map(snapshot => (
        `<span class="timelineTick">${snapshot.step}</span>`
      )).join("");
    }

    function metricRows(obs, payload) {
      const gm = obs.global_metrics || {};
      return [
        ["Throughput", gm.throughput ?? 0],
        ["Vehicle count", gm.vehicle_count ?? 0],
        ["Mean speed", Number(gm.mean_speed ?? 0).toFixed(2)],
        ["Total queue", Number(gm.total_queue ?? 0).toFixed(1)],
        ["Max queue", Number(gm.max_queue ?? 0).toFixed(1)],
        ["Phase changes", gm.phase_changes ?? 0],
        ["EV waiting", Number(obs.ev?.waiting_time ?? 0).toFixed(1) + " s"],
        ["Route node", obs.route_choice?.current_node ?? "-"],
        ["Route target", obs.route_choice?.destination_id ?? "-"],
        ["Done", String(Boolean(payload.done))],
      ];
    }

    function rewardRows(obs, payload, prevPayload) {
      const parsed = parseFeedback(obs.feedback);
      const currentProgress = Number(obs.ev?.progress || 0);
      const prevProgress = Number(prevPayload?.observation?.ev?.progress || 0);
      const progressDelta = currentProgress - prevProgress;
      return [
        ["Reward", Number(payload.reward ?? 0).toFixed(3)],
        ["Progress delta", Number(progressDelta).toFixed(3)],
        ["Feedback progress", parsed.progress_delta ?? "-"],
        ["Feedback ev wait", parsed.ev_wait_delta ?? "-"],
        ["Feedback queue", parsed.queue ?? "-"],
        ["Feedback throughput", parsed.throughput_delta ?? "-"],
        ["Invalid actions", parsed.invalid_actions ?? "0"],
        ["Route edge", parsed.route_edge ?? "-"],
        ["Route backtrack", parsed.route_backtrack ?? "0"],
      ];
    }

    function valueText(value) {
      if (value === null || value === undefined || value === "") {
        return "-";
      }
      if (typeof value === "number") {
        return Number.isInteger(value) ? String(value) : value.toFixed(3);
      }
      if (typeof value === "boolean") {
        return String(value);
      }
      return String(value);
    }

    function renderTableRows(tbody, rows) {
      tbody.innerHTML = rows.map(([k, v]) => `<tr><td>${valueText(k)}</td><td>${valueText(v)}</td></tr>`).join("");
    }

    function previousPayloadFor(payload) {
      const index = snapshots.findIndex(snapshot => snapshot.payload === payload);
      if (index > 0) {
        return snapshots[index - 1].payload;
      }
      return null;
    }

    function renderStepData(payload, actions, prevPayload) {
      const obs = payload.observation || {};
      const gm = obs.global_metrics || {};
      const ev = obs.ev || {};
      const routeChoice = obs.route_choice || {};
      const parsed = parseFeedback(obs.feedback);
      const snapshotIndex = snapshots.findIndex(snapshot => snapshot.payload === payload);
      const progressDelta = Number(ev.progress || 0) - Number(prevPayload?.observation?.ev?.progress || 0);
      const selectedCandidate = (routeChoice.candidates || []).find(
        candidate => candidate.edge_id === payload.action_used?.next_edge_id
      );

      renderTableRows(liveStepBody, [
        ["Step", obs.step ?? 0],
        ["Sim time", `${Number(obs.sim_time || 0).toFixed(1)} s`],
        ["Reward", Number(payload.reward ?? 0).toFixed(3)],
        ["Raw reward", parsed.raw_reward ?? "-"],
        ["Queue", Number(gm.total_queue ?? 0).toFixed(1)],
        ["Throughput", gm.throughput ?? 0],
        ["Done", Boolean(payload.done)],
      ]);

      renderTableRows(liveEvBody, [
        ["Current edge", ev.current_edge],
        ["Next signal", ev.next_intersection],
        ["Route progress", `${(Number(ev.progress || 0) * 100).toFixed(1)}%`],
        ["Edge progress", `${(Number(ev.edge_progress || 0) * 100).toFixed(1)}%`],
        ["Waiting", `${Number(ev.waiting_time ?? 0).toFixed(1)} s`],
        ["Travel time", `${Number(ev.travel_time ?? 0).toFixed(1)} s`],
        ["Arrived", Boolean(ev.arrived)],
      ]);

      renderTableRows(liveRouteBody, [
        ["Current node", routeChoice.current_node],
        ["Selected edge", payload.action_used?.next_edge_id || parsed.route_edge || "-"],
        ["Selected weight", selectedCandidate ? Number(selectedCandidate.road_weight || 0).toFixed(3) : "-"],
        ["Traffic level", selectedCandidate ? roadWeightLevel(selectedCandidate.road_weight) : "-"],
        ["Estimated queue", selectedCandidate ? Number(selectedCandidate.estimated_queue || 0).toFixed(1) : "-"],
        ["Moves closer", selectedCandidate ? Boolean(selectedCandidate.moves_closer) : "-"],
        ["Backtrack", selectedCandidate ? Boolean(selectedCandidate.is_backtrack) : "-"],
      ]);

      stepDataTitle.textContent = `Step Data - Step ${valueText(obs.step ?? 0)}`;
      stepDataIndex.textContent = snapshotIndex >= 0 ? `${snapshotIndex + 1} / ${snapshots.length}` : "-";

      renderTableRows(stepSummaryBody, [
        ["Task", obs.task_id],
        ["Sim time", `${Number(obs.sim_time || 0).toFixed(1)} s`],
        ["Step", obs.step ?? 0],
        ["Reward", Number(payload.reward ?? 0).toFixed(3)],
        ["Raw reward", parsed.raw_reward ?? "-"],
        ["Normalized reward", parsed.normalized_reward ?? "-"],
        ["Progress delta", progressDelta.toFixed(3)],
        ["Feedback progress", parsed.progress_delta ?? "-"],
        ["Feedback EV wait", parsed.ev_wait_delta ?? "-"],
        ["Total queue", Number(gm.total_queue ?? 0).toFixed(1)],
        ["Max queue", Number(gm.max_queue ?? 0).toFixed(1)],
        ["Throughput", gm.throughput ?? 0],
        ["Vehicle count", gm.vehicle_count ?? 0],
        ["Mean speed", Number(gm.mean_speed ?? 0).toFixed(2)],
        ["Phase changes", gm.phase_changes ?? 0],
        ["Done", Boolean(payload.done)],
        ["Feedback", obs.feedback || "-"],
      ]);

      renderTableRows(evDataBody, [
        ["EV ID", ev.ev_id],
        ["Current edge", ev.current_edge],
        ["Route index", ev.route_index ?? 0],
        ["Edge progress", Number(ev.edge_progress ?? 0).toFixed(3)],
        ["Route progress", Number(ev.progress ?? 0).toFixed(3)],
        ["Next intersection", ev.next_intersection],
        ["Waiting time", `${Number(ev.waiting_time ?? 0).toFixed(1)} s`],
        ["Travel time", `${Number(ev.travel_time ?? 0).toFixed(1)} s`],
        ["Arrived", Boolean(ev.arrived)],
        ["Route edges", (ev.route_edges || []).join(" -> ")],
      ]);

      intersectionDataBody.innerHTML = (obs.intersections || []).map(ix => `
        <tr>
          <td>${valueText(ix.intersection_id)}</td>
          <td>${valueText(ix.current_phase)}</td>
          <td>${valueText(actions[ix.intersection_id])}</td>
          <td>${valueText(ix.ev_target_phase)}</td>
          <td>${Number(ix.queue_length || 0).toFixed(1)}</td>
          <td>${valueText(ix.vehicle_count)}</td>
          <td>${Number(ix.mean_speed || 0).toFixed(2)}</td>
          <td>${Number(ix.ev_eta_steps ?? -1).toFixed(1)}</td>
          <td>${Number(ix.ev_distance_m ?? -1).toFixed(1)}</td>
        </tr>
      `).join("");

      routeCandidateBody.innerHTML = (routeChoice.candidates || []).map(candidate => `
        <tr>
          <td>${valueText(candidate.edge_id)}</td>
          <td>${valueText(candidate.from_node)}</td>
          <td>${valueText(candidate.to_node)}</td>
          <td>${Number(candidate.road_weight || 0).toFixed(3)}</td>
          <td>${roadWeightLevel(candidate.road_weight)}</td>
          <td>${Number(candidate.estimated_queue || 0).toFixed(1)}</td>
          <td>${Number(candidate.destination_distance_delta || 0).toFixed(1)}</td>
          <td>${valueText(Boolean(candidate.moves_closer))}</td>
          <td>${valueText(Boolean(candidate.is_backtrack))}</td>
        </tr>
      `).join("");

      roadWeightBody.innerHTML = Object.entries(routeChoice.road_weights || {})
        .sort(([a], [b]) => a.localeCompare(b))
        .map(([edgeId, weight]) => `
          <tr>
            <td>${valueText(edgeId)}</td>
            <td>${Number(weight || 0).toFixed(3)}</td>
            <td>${roadWeightLevel(weight)}</td>
          </tr>
        `).join("");

      rawSnapshotJson.textContent = JSON.stringify(payload, null, 2);
    }

    function phaseSignalColor(ix, chosenPhase) {
      const active = Number(ix.current_phase ?? 0);
      const chosen = Number(chosenPhase ?? active);
      const target = ix.ev_target_phase;
      if (target !== null && target !== undefined && chosen === target) {
        return "#66d19e";
      }
      if (chosen !== active) {
        return "#f5a524";
      }
      return "#f87171";
    }

    function roadWeightColor(weight) {
      const value = Number(weight || 0);
      if (value >= 0.66) {
        return "#ef4444";
      }
      if (value >= 0.33) {
        return "#facc15";
      }
      return "#22c55e";
    }

    function roadWeightLevel(weight) {
      const value = Number(weight || 0);
      if (value >= 0.66) {
        return "High";
      }
      if (value >= 0.33) {
        return "Medium";
      }
      return "Low";
    }

    function roadWeightFor(edgeId, roadWeights) {
      const value = roadWeights?.[edgeId];
      if (value === undefined || value === null) {
        return null;
      }
      return Number(value);
    }

    function drawRoadWeightLine(x1, y1, x2, y2, edgeId, roadWeights, labelOffsetY = -10) {
      const weight = roadWeightFor(edgeId, roadWeights);
      if (weight === null || Number.isNaN(weight)) {
        return "";
      }
      const color = roadWeightColor(weight);
      return `
        <line x1="${x1}" y1="${y1}" x2="${x2}" y2="${y2}" stroke="${color}" stroke-width="8" stroke-linecap="round" opacity="0.98"/>
      `;
    }

    function drawCorridor(obs, actionByIntersection) {
      const intersections = (obs.intersections || [])
        .filter(ix => INTERSECTION_ORDER.includes(ix.intersection_id))
        .sort((a, b) => INTERSECTION_ORDER.indexOf(a.intersection_id) - INTERSECTION_ORDER.indexOf(b.intersection_id));
      const intersectionById = Object.fromEntries(intersections.map(ix => [ix.intersection_id, ix]));
      const width = 1100;
      const height = 700;
      const left = 220;
      const right = 880;
      const top = 110;
      const bottom = 560;
      const xGap = (right - left) / (GRID_SIZE - 1);
      const yGap = (bottom - top) / (GRID_SIZE - 1);
      const roadWeights = obs.route_choice?.road_weights || {};
      const evEdge = obs.ev?.current_edge || "";

      const parseIntersectionId = (id) => {
        const match = /^INT_(\\d+)_(\\d+)$/.exec(id || "");
        return match ? { row: Number(match[1]), col: Number(match[2]) } : null;
      };
      const pointForNode = (nodeId) => {
        const parsed = parseIntersectionId(nodeId);
        if (parsed) {
          return {
            x: left + (parsed.col - 1) * xGap,
            y: top + (parsed.row - 1) * yGap,
          };
        }
        if (nodeId === "NW_OUT") return { x: left - 120, y: top };
        if (nodeId === "SE_OUT") return { x: right + 120, y: bottom };
        let match = /^W(\\d+)$/.exec(nodeId || "");
        if (match) return { x: left - 120, y: top + (Number(match[1]) - 1) * yGap };
        match = /^E(\\d+)$/.exec(nodeId || "");
        if (match) return { x: right + 120, y: top + (Number(match[1]) - 1) * yGap };
        match = /^N(\\d+)$/.exec(nodeId || "");
        if (match) return { x: left + (Number(match[1]) - 1) * xGap, y: top - 82 };
        match = /^S(\\d+)$/.exec(nodeId || "");
        if (match) return { x: left + (Number(match[1]) - 1) * xGap, y: bottom + 82 };
        return null;
      };
      const edgeToNodes = (edgeId) => {
        const parts = String(edgeId || "").split("_TO_");
        return parts.length === 2 ? { from: parts[0], to: parts[1] } : null;
      };
      const signalSideForEdge = (edgeId, intersectionId) => {
        const edge = edgeToNodes(edgeId);
        if (!edge || edge.to !== intersectionId) {
          return "";
        }
        const fromPoint = pointForNode(edge.from);
        const toPoint = pointForNode(edge.to);
        if (!fromPoint || !toPoint) {
          return "";
        }
        const dx = fromPoint.x - toPoint.x;
        const dy = fromPoint.y - toPoint.y;
        if (Math.abs(dx) > Math.abs(dy)) {
          return dx < 0 ? "W" : "E";
        }
        return dy < 0 ? "N" : "S";
      };

      let svg = "";
      svg += `<rect x="0" y="0" width="${width}" height="${height}" fill="#0b1320"/>`;
      svg += `<rect x="${left - 150}" y="${top - 95}" width="${right - left + 300}" height="${bottom - top + 190}" fill="#0d1725" stroke="#243149" stroke-width="1"/>`;

      const drawWeightedPair = (from, to) => {
        const p1 = pointForNode(from);
        const p2 = pointForNode(to);
        if (!p1 || !p2) {
          return;
        }
        const horizontal = Math.abs(p2.x - p1.x) >= Math.abs(p2.y - p1.y);
        svg += `<line x1="${p1.x}" y1="${p1.y}" x2="${p2.x}" y2="${p2.y}" stroke="#52627d" stroke-width="24" stroke-linecap="round" opacity="0.78"/>`;
        svg += `<line x1="${p1.x}" y1="${p1.y}" x2="${p2.x}" y2="${p2.y}" stroke="#172238" stroke-width="2" stroke-dasharray="10 10" opacity="0.9"/>`;
        if (horizontal) {
          svg += drawRoadWeightLine(p1.x, p1.y - 8, p2.x, p2.y - 8, `${from}_TO_${to}`, roadWeights, -14);
          svg += drawRoadWeightLine(p2.x, p2.y + 8, p1.x, p1.y + 8, `${to}_TO_${from}`, roadWeights, 26);
        } else {
          svg += drawRoadWeightLine(p1.x - 8, p1.y, p2.x - 8, p2.y, `${from}_TO_${to}`, roadWeights, -14);
          svg += drawRoadWeightLine(p2.x + 8, p2.y, p1.x + 8, p1.y, `${to}_TO_${from}`, roadWeights, 26);
        }
      };

      for (let row = 1; row <= GRID_SIZE; row++) {
        const rowNodes = [
          row === 1 ? "NW_OUT" : `W${row}`,
          ...Array.from({ length: GRID_SIZE }, (_, idx) => `INT_${row}_${idx + 1}`),
          row === GRID_SIZE ? "SE_OUT" : `E${row}`,
        ];
        for (let idx = 0; idx < rowNodes.length - 1; idx++) {
          drawWeightedPair(rowNodes[idx], rowNodes[idx + 1]);
        }
      }
      for (let col = 1; col <= GRID_SIZE; col++) {
        const colNodes = [
          `N${col}`,
          ...Array.from({ length: GRID_SIZE }, (_, idx) => `INT_${idx + 1}_${col}`),
          `S${col}`,
        ];
        for (let idx = 0; idx < colNodes.length - 1; idx++) {
          drawWeightedPair(colNodes[idx], colNodes[idx + 1]);
        }
      }

      intersections.forEach((ix) => {
        const point = pointForNode(ix.intersection_id);
        if (!point) {
          return;
        }
        const { x, y } = point;
        const chosen = actionByIntersection[ix.intersection_id];
        const signalColor = phaseSignalColor(ix, chosen);
        const queue = Number(ix.queue_length || 0);
        const qHeight = Math.min(52, queue * 5);
        const evSignalSide = signalSideForEdge(ix.ev_approach_edge, ix.intersection_id);
        const signalPoints = [
          ["N", x, y - 34, "N"],
          ["E", x + 34, y, "E"],
          ["S", x, y + 34, "S"],
          ["W", x - 34, y, "W"],
        ];

        svg += `<rect x="${x - 25}" y="${y - 25}" width="50" height="50" rx="8" fill="#111c2d" stroke="#d8e3f7" stroke-width="1.2"/>`;
        signalPoints.forEach(([side, sx, sy, label]) => {
          const fill = side === evSignalSide ? signalColor : "#5f6f88";
          svg += `<circle cx="${sx}" cy="${sy}" r="10" fill="${fill}" stroke="#e8f0ff" stroke-width="1"/>`;
          svg += `<text x="${sx}" y="${sy + 4}" text-anchor="middle" fill="#ffffff" font-size="10" font-weight="800">${label}</text>`;
        });
        svg += `<rect x="${x - 20}" y="${y + 47}" width="40" height="${qHeight}" fill="#f5a524" opacity="0.9"/>`;
        svg += `<text x="${x}" y="${y - 48}" text-anchor="middle" fill="#ffffff" font-size="13" font-weight="800">${ix.intersection_id}</text>`;
        svg += `<text x="${x}" y="${y + 118}" text-anchor="middle" fill="#dbe7ff" font-size="12">Q ${queue.toFixed(1)}</text>`;
      });

      const evNodes = edgeToNodes(evEdge);
      const evFrom = evNodes ? pointForNode(evNodes.from) : null;
      const evTo = evNodes ? pointForNode(evNodes.to) : null;
      if (evFrom && evTo) {
        const edgeProgress = Math.max(0, Math.min(1, Number(obs.ev?.edge_progress || 0)));
        const evX = evFrom.x + (evTo.x - evFrom.x) * edgeProgress;
        const evY = evFrom.y + (evTo.y - evFrom.y) * edgeProgress;
        svg += `<circle cx="${evX}" cy="${evY}" r="15" fill="#41b5ff" stroke="#ffffff" stroke-width="2.5"/>`;
        svg += `<text x="${evX}" y="${evY - 24}" text-anchor="middle" fill="#8fd6ff" font-size="12" font-weight="800">EV</text>`;
      }
      const startPoint = pointForNode(obs.route_choice?.source_id || "NW_OUT") || pointForNode("NW_OUT");
      const endPoint = pointForNode(obs.route_choice?.destination_id || "SE_OUT") || pointForNode("SE_OUT");
      if (startPoint) {
        svg += `<circle cx="${startPoint.x}" cy="${startPoint.y}" r="24" fill="#22c55e" stroke="#ffffff" stroke-width="3"/>`;
        svg += `<text x="${startPoint.x}" y="${startPoint.y + 5}" text-anchor="middle" fill="#03140b" font-size="12" font-weight="900">START</text>`;
        svg += `<text x="${startPoint.x}" y="${startPoint.y - 34}" text-anchor="middle" fill="#d8ffe8" font-size="14" font-weight="900">${obs.route_choice?.source_id || "NW_OUT"}</text>`;
      }
      if (endPoint) {
        svg += `<circle cx="${endPoint.x}" cy="${endPoint.y}" r="24" fill="#ef4444" stroke="#ffffff" stroke-width="3"/>`;
        svg += `<text x="${endPoint.x}" y="${endPoint.y + 5}" text-anchor="middle" fill="#270306" font-size="12" font-weight="900">END</text>`;
        svg += `<text x="${endPoint.x}" y="${endPoint.y + 44}" text-anchor="middle" fill="#ffd5d5" font-size="14" font-weight="900">${obs.route_choice?.destination_id || "SE_OUT"}</text>`;
      }

      corridorSvg.innerHTML = svg;
    }

    function renderFromSnapshot(payload, fromHistory = false) {
      const obs = payload.observation || {};
      latestPayload = payload;
      simTimeEl.textContent = Number(obs.sim_time || 0).toFixed(1) + " s";
      stepEl.textContent = String(obs.step ?? 0);
      rewardEl.textContent = Number(payload.reward ?? 0).toFixed(3);
      doneEl.textContent = String(Boolean(payload.done));

      const evProgress = Math.max(0, Math.min(1, Number(obs.ev?.progress || 0)));
      evProgressBar.style.width = (evProgress * 100).toFixed(1) + "%";
      evProgressLabel.textContent = (evProgress * 100).toFixed(1) + "%";

      const intersections = visibleIntersections(obs);
      const actions = (payload.action_used?.phase_by_intersection || lastAction.phase_by_intersection || {});
      const prevPayload = previousPayloadFor(payload);
      drawCorridor(obs, actions);

      decisionBody.innerHTML = intersections.map(ix => `
        <tr>
          <td>${ix.intersection_id}</td>
          <td>${actions[ix.intersection_id] ?? "-"}</td>
          <td>${ix.current_phase}</td>
          <td>${ix.ev_target_phase ?? "-"}</td>
          <td>${Number(ix.queue_length || 0).toFixed(1)}</td>
        </tr>
      `).join("");

      renderTableRows(metricBody, metricRows(obs, payload));
      renderTableRows(rewardBody, rewardRows(obs, payload, prevPayload));
      renderStepData(payload, actions, prevPayload);
      actionReason.textContent = payload.action_used?.reason || lastAction.reason || "Auto target EV phase";
      if (!fromHistory) {
        previousSnapshot = payload;
      }

      if (!fromHistory) {
        setStatus(obs.feedback || "Updated.");
      }
    }

    async function callApi(path, body) {
      const resp = await fetch(path, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      const text = await resp.text();
      let data = null;
      try { data = JSON.parse(text); } catch (e) {}
      if (!resp.ok) {
        throw new Error(data ? JSON.stringify(data, null, 2) : text || ("HTTP " + resp.status));
      }
      return data;
    }

    function stopAuto() {
      if (autoTimer) {
        clearInterval(autoTimer);
        autoTimer = null;
      }
      isRunning = false;
      autoBtn.textContent = "Auto Step";
    }

    async function doReset() {
      try {
        stopAuto();
        setStatus("Resetting...");
        const task_id = (taskIdInput.value || "grid_4x4_default").trim();
        const source_id = (sourceIdInput.value || "NW_OUT").trim();
        const destination_id = (destinationIdInput.value || "SE_OUT").trim();
        const data = await callApi("/reset", { task_id, source_id, destination_id });
        data.action_used = { phase_by_intersection: {}, reason: "Episode reset" };
        snapshots = [];
        previousSnapshot = null;
        pushSnapshot(data);
        renderFromSnapshot(data);
      } catch (err) {
        setStatus(String(err), true);
      }
    }

    async function doStep() {
      try {
        if (!latestPayload || !latestPayload.observation) {
          setStatus("Please reset first.");
          stopAuto();
          return;
        }
        if (latestPayload.done) {
          setStatus("Episode done. Reset to start a new run.");
          stopAuto();
          return;
        }

        const intersections = visibleIntersections(latestPayload.observation);
        const visibleIds = intersections.map(ix => ix.intersection_id);
        const actionPayload = bestActionFromObservation(latestPayload.observation, visibleIds);
        lastAction = actionPayload.action;
        const data = await callApi("/step", actionPayload);
        data.action_used = actionPayload.action;
        pushSnapshot(data);
        renderFromSnapshot(data);

        if (data.done) {
          setStatus("Episode completed. Reset for a new episode.");
          stopAuto();
        }
      } catch (err) {
        stopAuto();
        setStatus(String(err), true);
      }
    }

    function renderTimelineIndex(index) {
      if (!snapshots.length) {
        return;
      }
      timelineIndex = Math.max(0, Math.min(snapshots.length - 1, index));
      timelineSlider.value = String(timelineIndex);
      renderFromSnapshot(snapshots[timelineIndex].payload, true);
      setStatus("Viewing snapshot " + (timelineIndex + 1) + " / " + snapshots.length);
    }

    resetBtn.addEventListener("click", doReset);
    stepBtn.addEventListener("click", doStep);
    autoBtn.addEventListener("click", () => {
      if (isRunning) {
        stopAuto();
        return;
      }
      isRunning = true;
      autoBtn.textContent = "Running...";
      autoTimer = setInterval(() => {
        if (!isRunning) {
          return;
        }
        doStep();
      }, 850);
    });
    pauseBtn.addEventListener("click", stopAuto);
    intersectionLimit.addEventListener("change", () => {
      if (latestPayload) {
        renderFromSnapshot(latestPayload, timelineIndex >= 0 && timelineIndex < snapshots.length - 1);
      }
    });
    timelineSlider.addEventListener("input", (e) => {
      renderTimelineIndex(Number(e.target.value || "0"));
    });
    timelinePrev.addEventListener("click", () => renderTimelineIndex(timelineIndex - 1));
    timelineNext.addEventListener("click", () => renderTimelineIndex(timelineIndex + 1));
  </script>
</body>
</html>
        """
    )


@app.on_event("shutdown")
def _shutdown_dynamic_corridor_environment() -> None:
    global _SHARED_ENV
    if _SHARED_ENV is not None:
        _SHARED_ENV.shutdown()
        _SHARED_ENV = None


def main(host: str = "0.0.0.0", port: int = 8000) -> None:
    import uvicorn

    uvicorn.run(app, host=host, port=port)


if __name__ == "__main__":
    main()
