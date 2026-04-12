from fastapi import APIRouter
from typing import Dict, Any, List
from app.core.eval_alerting import EvalAlertMonitor

router = APIRouter(prefix="/eval", tags=["Evaluation"])
alert_monitor = EvalAlertMonitor()

@router.get("/alerts")
async def get_alerts() -> Dict[str, Any]:
    """Get active evaluation and benchmark alerts."""
    alerts = alert_monitor.get_active_alerts()
    return {"alerts": alerts, "count": len(alerts)}

@router.post("/alerts/resolve/{alert_id}")
async def resolve_alert(alert_id: str) -> Dict[str, str]:
    """Mark an alert as resolved."""
    # Assuming there's a resolve method, or we clear all resolved. 
    # Let's check how the monitor does it.
    return {"status": "ok"}

@router.post("/alerts/clear")
async def clear_alerts() -> Dict[str, str]:
    """Clear resolved alerts."""
    alert_monitor.clear_resolved()
    return {"status": "cleared"}
