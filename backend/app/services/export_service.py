"""Export service — JSON/CSV report generation."""

from __future__ import annotations

import csv
import io
import json

from backend.app.services.analytics_service import analytics_service
from backend.app.services.simulation_service import simulation_service


class ExportService:
    def export_json(self, run_id: str) -> dict:
        state_data = simulation_service.get_state(run_id)
        metrics = simulation_service.get_metrics(run_id)
        events = simulation_service.get_event_history(run_id)
        ev_status = simulation_service.get_ev_status(run_id)
        agent_decisions = simulation_service.get_agent_decisions(run_id)

        return {
            "run_id": run_id,
            "state": state_data,
            "metrics_history": metrics,
            "event_count": len(events),
            "ev_journey": analytics_service.get_ev_journey_summary(run_id),
            "agent_decisions_count": len(agent_decisions),
        }

    def export_metrics_csv(self, run_id: str) -> str:
        metrics = simulation_service.get_metrics(run_id)
        if not metrics:
            return ""

        output = io.StringIO()
        writer = csv.DictWriter(output, fieldnames=metrics[0].keys())
        writer.writeheader()
        writer.writerows(metrics)
        return output.getvalue()

    def export_comparison_report(self, agent_run_id: str,
                                 baseline_run_id: str) -> dict:
        comparison = analytics_service.compare_runs(agent_run_id, baseline_run_id)
        return {
            "report_type": "comparison",
            "comparison": comparison,
            "agent_plots": analytics_service.get_plots_data(agent_run_id),
            "baseline_plots": analytics_service.get_plots_data(baseline_run_id),
        }


export_service = ExportService()
