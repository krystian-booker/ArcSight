from flask import current_app, jsonify

from . import monitoring
from ...metrics import metrics_registry, system_metrics_collector

# Monitoring page is now served by the React app
# Removed: @monitoring.route("/monitoring") def monitoring_dashboard()
# React handles the UI, this blueprint only provides API endpoints


@monitoring.route("/api/metrics/summary")
def metrics_summary():
    """Return the latest metrics snapshot for all pipelines and system."""
    if not current_app.config.get("METRICS_ENABLED", True):
        return jsonify({
            "enabled": False,
            "pipelines": [],
            "system": {
                "cpu_percent": 0.0,
                "ram_percent": 0.0,
                "ram_used_mb": 0.0,
                "ram_total_mb": 0.0,
                "cpu_temp_celsius": None,
                "active_pipelines": 0,
                "process_rss_mb": 0.0,
                "total_drops_per_minute": 0.0,
            },
            "thresholds": {
                "queue_high_utilization_pct": 80.0,
                "latency_warn_ms": 150.0,
            },
        })

    # Get pipeline metrics
    pipeline_snapshot = metrics_registry.get_snapshot()

    # Get system metrics
    system_snapshot = system_metrics_collector.get_snapshot()

    # Calculate total drops per minute across all pipelines
    pipelines = pipeline_snapshot.get("pipelines", [])
    total_drops_per_minute = sum(p.get("drops_per_minute", 0.0) for p in pipelines)

    # Combine into a single response with the structure the frontend expects
    return jsonify({
        "enabled": True,
        "pipelines": pipelines,
        "system": {
            "cpu_percent": system_snapshot.get("cpu_percent", 0.0),
            "ram_percent": system_snapshot.get("ram_percent", 0.0),
            "ram_used_mb": system_snapshot.get("ram_used_bytes", 0) / (1024 * 1024),
            "ram_total_mb": system_snapshot.get("ram_total_bytes", 0) / (1024 * 1024),
            "cpu_temp_celsius": (
                system_snapshot.get("temperatures", [{}])[0].get("current")
                if system_snapshot.get("temperatures")
                else None
            ),
            "active_pipelines": len(pipelines),
            "process_rss_mb": pipeline_snapshot.get("memory", {}).get("rss_bytes", 0) / (1024 * 1024),
            "total_drops_per_minute": total_drops_per_minute,
        },
        "thresholds": {
            "queue_high_utilization_pct": pipeline_snapshot.get("thresholds", {}).get("queue_high_utilization_pct", 80.0),
            "latency_warn_ms": pipeline_snapshot.get("thresholds", {}).get("latency_warn_ms", 150.0),
        },
    })


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
