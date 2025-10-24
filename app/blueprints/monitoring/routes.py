from flask import current_app, jsonify, render_template

from . import monitoring
from ...metrics import metrics_registry, system_metrics_collector


def _to_bool(value) -> bool:
    if isinstance(value, str):
        return value.lower() not in ("0", "false", "no", "off", "")
    return bool(value)


@monitoring.route("/monitoring")
def monitoring_dashboard():
    """Render the monitoring dashboard that visualizes pipeline metrics."""
    refresh_interval_ms = int(
        current_app.config.get("METRICS_REFRESH_INTERVAL_MS", 2000)
    )
    metrics_enabled = _to_bool(current_app.config.get("METRICS_ENABLED", True))
    return render_template(
        "pages/monitoring.html",
        metrics_enabled=metrics_enabled,
        refresh_interval_ms=refresh_interval_ms,
    )


@monitoring.route("/api/metrics/summary")
def metrics_summary():
    """Return the latest metrics snapshot for all pipelines."""
    if not current_app.config.get("METRICS_ENABLED", True):
        return jsonify({"enabled": False, "pipelines": [], "memory": {"rss_bytes": 0}})
    snapshot = metrics_registry.get_snapshot()
    return jsonify(snapshot)


@monitoring.route("/api/metrics/system")
def system_metrics():
    """Return the latest system metrics snapshot including CPU, RAM, and temperature."""
    if not current_app.config.get("METRICS_ENABLED", True):
        return jsonify({
            "enabled": False,
            "cpu_percent": 0.0,
            "cpu_count": 0,
            "ram_total_bytes": 0,
            "ram_used_bytes": 0,
            "ram_percent": 0.0,
            "temperatures": [],
        })
    snapshot = system_metrics_collector.get_snapshot()
    return jsonify(snapshot)
