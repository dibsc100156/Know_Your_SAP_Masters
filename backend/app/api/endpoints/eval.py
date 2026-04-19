from fastapi import APIRouter
from typing import Dict, Any, List
from app.core.eval_alerting import EvalAlertMonitor
from app.core.monitoring_dashboard import get_monitor

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
    success = alert_monitor.resolve_alert(alert_id)
    return {"status": "ok" if success else "not_found"}

@router.post("/alerts/clear")
async def clear_alerts() -> Dict[str, str]:
    """Clear resolved alerts."""
    alert_monitor.clear_resolved()
    return {"status": "cleared"}


# ── Phase L4: Real-Time Monitoring Dashboard ──────────────────────────────────

@router.get("/monitoring/metrics")
async def get_monitoring_metrics() -> Dict[str, Any]:
    """
    Returns a comprehensive real-time operations snapshot:
      - Query throughput (qpm, qph)
      - Success / empty / error rates
      - Latency percentiles (p50, p95, p99)
      - Voting executor: consensus rate, confidence boost
      - Self-healing: heal rate, top heal codes
      - Semantic validation: trust distribution
      - CIBA approval flow: pending/approved/denied counts
      - Security Sentinel: detection rate, severity breakdown
      - Swarm: agent count distribution
      - Per-domain and per-role breakdowns
    """
    return get_monitor().get_all_metrics()

@router.get("/monitoring/status")
async def get_monitoring_status() -> Dict[str, Any]:
    """
    Lightweight health badge: GREEN / YELLOW / RED with health score,
    plus key operational metrics (uptime, throughput, latency).
    """
    monitor = get_monitor()
    all_metrics = monitor.get_all_metrics()
    return {
        **monitor.get_status_badge(),
        **all_metrics.get("success_rates", {}),
        "uptime_seconds": all_metrics.get("uptime_seconds", 0),
        "throughput": all_metrics.get("throughput", {}),
        "latency": all_metrics.get("latency", {}),
        "self_heal": all_metrics.get("self_heal", {}),
        "ciba": all_metrics.get("ciba", {}),
        "swarm": all_metrics.get("swarm", {}),
    }

@router.get("/monitoring/health")
async def get_health_score() -> Dict[str, Any]:
    """
    Composite 0.0–1.0 health score from success rate, latency, and sentinel safety.
    Returns full status badge (GREEN/YELLOW/RED) plus score + key rates.
    """
    monitor = get_monitor()
    all_metrics = monitor.get_all_metrics()
    return {
        **monitor.get_status_badge(),
        **all_metrics.get("success_rates", {}),
        "throughput": all_metrics.get("throughput", {}),
        "latency": all_metrics.get("latency", {}),
    }
