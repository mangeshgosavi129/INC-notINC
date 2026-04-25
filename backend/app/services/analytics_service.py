"""Analytics service — metrics aggregation and comparison."""

from __future__ import annotations

from backend.app.services.simulation_service import simulation_service


class AnalyticsService:
    def get_queue_history(self, run_id: str) -> list[dict]:
        metrics = simulation_service.get_metrics(run_id)
        return [
            {"sim_time": m["sim_time"],
             "total_queue": m.get("total_queue_length", 0),
             "max_queue": m.get("max_queue_length", 0),
             "avg_queue": m.get("avg_queue_length", 0),
             "per_intersection": m.get("per_intersection", {})}
            for m in metrics
        ]

    def get_ev_waterfall(self, run_id: str) -> list[dict]:
        """Per-intersection wait times for EV journey waterfall chart."""
        events = simulation_service.get_event_history(run_id, limit=5000)
        waits: dict[str, float] = {}
        wait_starts: dict[str, float] = {}

        for e in events:
            etype = e.get("event_type", "")
            payload = e.get("payload", {}) or {}
            iid = payload.get("intersection_id", "")
            t = e.get("sim_time", 0)

            if etype == "EV_ARRIVE_INTERSECTION" and iid:
                wait_starts[iid] = t
            elif etype == "EV_ENTER_INTERSECTION" and iid:
                start = wait_starts.get(iid)
                if start is not None:
                    waits[iid] = t - start

        state = simulation_service._states.get(run_id)
        if state is None:
            return []

        result = []
        for link in state.corridor.links:
            iid = link.to_intersection
            result.append({
                "intersection_id": iid,
                "wait_time_s": round(waits.get(iid, 0), 2),
            })
        return result

    def get_delay_history(self, run_id: str) -> list[dict]:
        metrics = simulation_service.get_metrics(run_id)
        return [
            {"sim_time": m["sim_time"],
             "avg_delay": m.get("avg_delay_per_vehicle", 0)}
            for m in metrics
        ]

    def get_throughput_history(self, run_id: str) -> list[dict]:
        metrics = simulation_service.get_metrics(run_id)
        return [
            {"sim_time": m["sim_time"],
             "throughput": m.get("total_throughput", 0)}
            for m in metrics
        ]

    def get_ev_journey_summary(self, run_id: str) -> dict | None:
        ev_status = simulation_service.get_ev_status(run_id)
        if ev_status is None:
            return None

        state = simulation_service._states.get(run_id)
        if state is None:
            return None

        ev = state.ev
        if ev is None:
            return None

        free_flow_time = state.corridor.free_flow_travel_time_s()
        actual_time = None
        if ev.dispatch_time is not None and ev.arrival_time is not None:
            actual_time = ev.arrival_time - ev.dispatch_time

        return {
            "ev_id": ev.ev_id,
            "free_flow_time_s": round(free_flow_time, 1),
            "actual_time_s": round(actual_time, 1) if actual_time else None,
            "total_signal_delay_s": round(ev.total_delay_at_signals, 1),
            "intersections_cleared": ev.intersections_cleared,
            "intersections_waited": ev.intersections_waited,
            "status": ev.status.value,
        }

    def compare_runs(self, agent_run_id: str, baseline_run_id: str) -> dict:
        agent_metrics = simulation_service.get_metrics(agent_run_id)
        base_metrics = simulation_service.get_metrics(baseline_run_id)
        agent_ev = self.get_ev_journey_summary(agent_run_id)
        base_ev = self.get_ev_journey_summary(baseline_run_id)

        agent_avg_q = _avg_field(agent_metrics, "total_queue_length")
        base_avg_q = _avg_field(base_metrics, "total_queue_length")
        agent_throughput = _last_field(agent_metrics, "total_throughput")
        base_throughput = _last_field(base_metrics, "total_throughput")

        agent_ev_delay = agent_ev["total_signal_delay_s"] if agent_ev else 0
        base_ev_delay = base_ev["total_signal_delay_s"] if base_ev else 0

        return {
            "agent_run_id": agent_run_id,
            "baseline_run_id": baseline_run_id,
            "agent_ev_delay": agent_ev_delay,
            "baseline_ev_delay": base_ev_delay,
            "ev_delay_improvement_pct": _pct_improvement(base_ev_delay, agent_ev_delay),
            "agent_avg_queue": round(agent_avg_q, 2),
            "baseline_avg_queue": round(base_avg_q, 2),
            "queue_improvement_pct": _pct_improvement(base_avg_q, agent_avg_q),
            "agent_throughput": agent_throughput,
            "baseline_throughput": base_throughput,
            "throughput_improvement_pct": _pct_improvement(
                base_throughput, agent_throughput, higher_is_better=True
            ),
            "agent_journey": agent_ev,
            "baseline_journey": base_ev,
        }

    def get_plots_data(self, run_id: str) -> dict:
        return {
            "queue_history": self.get_queue_history(run_id),
            "delay_history": self.get_delay_history(run_id),
            "throughput_history": self.get_throughput_history(run_id),
            "ev_journey": self.get_ev_journey_summary(run_id),
        }


def _avg_field(metrics: list[dict], field: str) -> float:
    vals = [m.get(field, 0) for m in metrics if field in m]
    return sum(vals) / max(1, len(vals))


def _last_field(metrics: list[dict], field: str) -> int:
    if not metrics:
        return 0
    return metrics[-1].get(field, 0)


def _pct_improvement(baseline: float, improved: float,
                     higher_is_better: bool = False) -> float:
    if baseline == 0:
        return 0.0
    if higher_is_better:
        return round((improved - baseline) / baseline * 100, 1)
    return round((baseline - improved) / baseline * 100, 1)


analytics_service = AnalyticsService()
