from unittest.mock import patch

import pytest

from app.metrics import metrics_registry


@pytest.fixture()
def metrics_app(app):
    """Enable metrics for tests and ensure registry state is isolated."""
    previous_enabled = app.config.get("METRICS_ENABLED", False)
    app.config["METRICS_ENABLED"] = True
    metrics_registry.shutdown()
    metrics_registry.reset()
    metrics_registry.configure(
        enabled=True,
        window_seconds=60.0,
        fps_window_seconds=10.0,
        memory_sampler_interval=60.0,
        queue_high_utilization_pct=75.0,
        latency_warn_ms=120.0,
    )
    try:
        yield app
    finally:
        metrics_registry.shutdown()
        metrics_registry.reset()
        metrics_registry.configure(enabled=previous_enabled)
        app.config["METRICS_ENABLED"] = previous_enabled


@pytest.fixture()
def metrics_client(metrics_app):
    with metrics_app.test_client() as client:
        yield client


def test_monitoring_page_disabled_shows_warning(client):
    """Monitoring page should display guidance when metrics are disabled."""
    response = client.get("/monitoring")
    assert response.status_code == 200
    assert b"Metrics disabled" in response.data


def test_metrics_registry_snapshot_contains_pipeline(metrics_app):
    """Snapshot should reflect recorded drops, queue depth, and latency."""
    metrics_registry.register_pipeline("cam-1", 1, "AprilTag", 2)
    metrics_registry.record_queue_depth("cam-1", 1, queue_size=1, queue_max_size=2)
    metrics_registry.record_drop("cam-1", 1, queue_size=2, queue_max_size=2)

    with patch("app.metrics.registry.time.perf_counter", side_effect=[1.0, 2.0, 3.0]):
        metrics_registry.record_latencies(
            camera_identifier="cam-1",
            pipeline_id=1,
            pipeline_type="AprilTag",
            total_latency_ms=45.0,
            queue_latency_ms=15.0,
            processing_latency_ms=30.0,
        )

    snapshot = metrics_registry.get_snapshot()
    assert snapshot["enabled"] is True
    assert snapshot["config"]["latency_warn_ms"] == 120.0

    assert len(snapshot["pipelines"]) == 1
    pipeline_snapshot = snapshot["pipelines"][0]

    assert pipeline_snapshot["camera_identifier"] == "cam-1"
    assert pipeline_snapshot["drops"]["total"] == 1.0
    assert pipeline_snapshot["queue"]["current_depth"] == 1
    assert pipeline_snapshot["queue"]["max_size"] == 2
    assert pipeline_snapshot["latency_ms"]["total"]["avg_ms"] == pytest.approx(45.0)
    assert pipeline_snapshot["latency_ms"]["queue_wait"]["avg_ms"] == pytest.approx(15.0)
    assert pipeline_snapshot["latency_ms"]["processing"]["avg_ms"] == pytest.approx(30.0)


def test_metrics_summary_endpoint(metrics_app, metrics_client):
    """API endpoint should serve the current metrics snapshot."""
    with metrics_app.app_context():
        metrics_registry.register_pipeline("cam-1", 1, "AprilTag", 2)
        metrics_registry.record_queue_depth("cam-1", 1, queue_size=1, queue_max_size=2)
        metrics_registry.record_latencies(
            camera_identifier="cam-1",
            pipeline_id=1,
            pipeline_type="AprilTag",
            total_latency_ms=33.0,
            queue_latency_ms=10.0,
            processing_latency_ms=23.0,
        )

    response = metrics_client.get("/api/metrics/summary")
    assert response.status_code == 200
    data = response.get_json()
    assert data["enabled"] is True
    assert len(data["pipelines"]) == 1
    assert data["pipelines"][0]["pipeline_id"] == 1
    assert data["pipelines"][0]["latency_ms"]["total"]["avg_ms"] == pytest.approx(33.0)
