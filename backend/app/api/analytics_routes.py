"""Analytics routes — /api/analytics/*"""

from fastapi import APIRouter, HTTPException
from fastapi.responses import PlainTextResponse

from backend.app.services.analytics_service import analytics_service
from backend.app.services.export_service import export_service

router = APIRouter(prefix="/api/analytics", tags=["analytics"])


@router.get("/queue/{run_id}")
async def queue_history(run_id: str):
    return analytics_service.get_queue_history(run_id)


@router.get("/delay/{run_id}")
async def delay_history(run_id: str):
    return analytics_service.get_delay_history(run_id)


@router.get("/throughput/{run_id}")
async def throughput_history(run_id: str):
    return analytics_service.get_throughput_history(run_id)


@router.get("/ev-journey/{run_id}")
async def ev_journey(run_id: str):
    summary = analytics_service.get_ev_journey_summary(run_id)
    if summary is None:
        return {"message": "No EV journey data"}
    return summary


@router.get("/ev-waterfall/{run_id}")
async def ev_waterfall(run_id: str):
    return analytics_service.get_ev_waterfall(run_id)


@router.get("/compare-baseline")
async def compare_baseline(mcts_run_id: str, baseline_run_id: str):
    try:
        return analytics_service.compare_runs(mcts_run_id, baseline_run_id)
    except Exception as e:
        raise HTTPException(400, str(e))


@router.get("/plots/{run_id}")
async def plots_data(run_id: str):
    return analytics_service.get_plots_data(run_id)


@router.get("/report/{run_id}")
async def export_report(run_id: str):
    try:
        return export_service.export_json(run_id)
    except Exception as e:
        raise HTTPException(400, str(e))


@router.get("/report-csv/{run_id}")
async def export_csv(run_id: str):
    csv_data = export_service.export_metrics_csv(run_id)
    return PlainTextResponse(csv_data, media_type="text/csv")


@router.get("/comparison-report")
async def comparison_report(mcts_run_id: str, baseline_run_id: str):
    try:
        return export_service.export_comparison_report(mcts_run_id, baseline_run_id)
    except Exception as e:
        raise HTTPException(400, str(e))
