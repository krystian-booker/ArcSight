"""Thread-safe metrics registry for camera acquisition and pipeline processing."""

from __future__ import annotations

import math
import threading
import time
from collections import deque
from dataclasses import dataclass
from typing import Deque, Dict, Iterable, Optional, Tuple

try:  # psutil is optional during testing environments
    import psutil  # type: ignore
except ImportError:  # pragma: no cover - psutil is available in production env
    psutil = None


def _quantile(values: Iterable[float], quantile: float) -> float:
    """Return the quantile for the given values using linear interpolation."""
    values_list = sorted(values)
    if not values_list:
        return 0.0
    if quantile <= 0:
        return values_list[0]
    if quantile >= 1:
        return values_list[-1]

    position = (len(values_list) - 1) * quantile
    lower_index = int(math.floor(position))
    upper_index = int(math.ceil(position))
    lower_value = values_list[lower_index]
    upper_value = values_list[upper_index]
    if lower_index == upper_index:
        return lower_value
    fraction = position - lower_index
    return lower_value + (upper_value - lower_value) * fraction


def _prune_series(series: Deque[Tuple[float, float]], cutoff: float) -> None:
    """Remove samples older than the cutoff timestamp."""
    while series and series[0][0] < cutoff:
        series.popleft()


@dataclass
class LatencyBreakdown:
    avg_ms: float = 0.0
    p50_ms: float = 0.0
    p95_ms: float = 0.0
    max_ms: float = 0.0
    count: int = 0


def _build_latency_stats(values: Iterable[float]) -> LatencyBreakdown:
    values_list = list(values)
    if not values_list:
        return LatencyBreakdown()

    avg = sum(values_list) / len(values_list)
    p50 = _quantile(values_list, 0.5)
    p95 = _quantile(values_list, 0.95)
    maximum = max(values_list)
    return LatencyBreakdown(
        avg_ms=avg, p50_ms=p50, p95_ms=p95, max_ms=maximum, count=len(values_list)
    )


class PipelineMetrics:
    """Stores rolling metrics for a single pipeline."""

    def __init__(
        self,
        camera_identifier: str,
        pipeline_id: int,
        pipeline_type: str,
        queue_max_size: int,
        window_seconds: float,
        fps_window_seconds: float,
    ):
        self.camera_identifier = camera_identifier
        self.pipeline_id = pipeline_id
        self.pipeline_type = pipeline_type
        self.queue_max_size = queue_max_size
        self._window_seconds = window_seconds
        self._fps_window_seconds = fps_window_seconds

        self._lock = threading.Lock()
        self._dropped_frames_total = 0
        self._drop_events: Deque[Tuple[float, float]] = deque()
        self._queue_samples: Deque[Tuple[float, float]] = deque()
        self._queue_high_watermark = 0
        self._last_queue_size = 0

        self._total_latency_samples: Deque[Tuple[float, float]] = deque()
        self._queue_latency_samples: Deque[Tuple[float, float]] = deque()
        self._processing_latency_samples: Deque[Tuple[float, float]] = deque()
        self._processed_timestamps: Deque[Tuple[float, float]] = deque()

    def update_metadata(
        self, pipeline_type: Optional[str], queue_max_size: Optional[int]
    ) -> None:
        with self._lock:
            if pipeline_type:
                self.pipeline_type = pipeline_type
            if queue_max_size is not None and queue_max_size > 0:
                self.queue_max_size = queue_max_size

    def record_drop(self, timestamp: float, queue_size: int) -> None:
        with self._lock:
            self._dropped_frames_total += 1
            self._drop_events.append((timestamp, 1.0))
            if isinstance(queue_size, (int, float)):
                queue_value = int(float(queue_size))
                if queue_value > self._queue_high_watermark:
                    self._queue_high_watermark = queue_value

    def record_queue(self, timestamp: float, queue_size: int) -> None:
        with self._lock:
            self._record_queue_locked(timestamp, queue_size)

    def _record_queue_locked(self, timestamp: float, queue_size: int) -> None:
        if not isinstance(queue_size, (int, float)):
            return
        queue_value = float(queue_size)
        self._queue_samples.append((timestamp, queue_value))
        queue_int = int(queue_value)
        self._last_queue_size = queue_int
        if queue_int > self._queue_high_watermark:
            self._queue_high_watermark = queue_int

    def record_latencies(
        self,
        timestamp: float,
        total_latency_ms: float,
        queue_latency_ms: float,
        processing_latency_ms: float,
    ) -> None:
        with self._lock:
            self._total_latency_samples.append((timestamp, total_latency_ms))
            self._queue_latency_samples.append((timestamp, queue_latency_ms))
            self._processing_latency_samples.append((timestamp, processing_latency_ms))

    def record_processed_frame(self, timestamp: float) -> None:
        with self._lock:
            self._processed_timestamps.append((timestamp, 1.0))

    def snapshot(self, timestamp: float) -> Dict[str, object]:
        window_cutoff = timestamp - self._window_seconds
        fps_cutoff = timestamp - self._fps_window_seconds

        with self._lock:
            _prune_series(self._drop_events, window_cutoff)
            _prune_series(self._queue_samples, window_cutoff)
            _prune_series(self._total_latency_samples, window_cutoff)
            _prune_series(self._queue_latency_samples, window_cutoff)
            _prune_series(self._processing_latency_samples, window_cutoff)
            _prune_series(self._processed_timestamps, fps_cutoff)

            queue_utilization = 0.0
            high_watermark_pct = 0.0
            max_size = self.queue_max_size or 0
            if max_size > 0:
                queue_utilization = min(self._last_queue_size / max_size, 1.0)
                high_watermark_pct = min(self._queue_high_watermark / max_size, 1.0)

            drop_count = sum(value for _, value in self._drop_events)
            window_minutes = max(self._window_seconds / 60.0, 1.0)
            drops_per_minute = drop_count / window_minutes

            fps = 0.0
            if self._processed_timestamps:
                elapsed = (
                    self._processed_timestamps[-1][0] - self._processed_timestamps[0][0]
                )
                if elapsed > 0:
                    fps = len(self._processed_timestamps) / elapsed

            total_latency = _build_latency_stats(
                value for _, value in self._total_latency_samples
            )
            queue_latency = _build_latency_stats(
                value for _, value in self._queue_latency_samples
            )
            processing_latency = _build_latency_stats(
                value for _, value in self._processing_latency_samples
            )

            return {
                "camera_identifier": self.camera_identifier,
                "pipeline_id": self.pipeline_id,
                "pipeline_type": self.pipeline_type,
                "queue": {
                    "max_size": max_size,
                    "current_depth": self._last_queue_size,
                    "utilization_pct": queue_utilization * 100.0,
                    "high_watermark_pct": high_watermark_pct * 100.0,
                },
                "drops": {
                    "total": self._dropped_frames_total,
                    "window_total": drop_count,
                    "per_minute": drops_per_minute,
                },
                "latency_ms": {
                    "total": total_latency.__dict__,
                    "queue_wait": queue_latency.__dict__,
                    "processing": processing_latency.__dict__,
                },
                "fps": fps,
            }


class MetricsRegistry:
    """Global metrics registry shared between acquisition and processing threads."""

    def __init__(self):
        self._pipelines: Dict[Tuple[str, int], PipelineMetrics] = {}
        self._lock = threading.Lock()
        self._memory_lock = threading.Lock()
        self._memory_rss_bytes: float = 0.0

        self.window_seconds = 300.0
        self.fps_window_seconds = 10.0
        self.enabled = True
        self.queue_high_utilization_pct = 80.0
        self.latency_warn_ms = 150.0

        self._memory_sampler_interval = 2.0
        self._memory_thread: Optional[threading.Thread] = None
        self._memory_stop_event = threading.Event()

    def configure(
        self,
        enabled: bool = True,
        window_seconds: float = 300.0,
        fps_window_seconds: float = 10.0,
        memory_sampler_interval: float = 2.0,
        queue_high_utilization_pct: float = 80.0,
        latency_warn_ms: float = 150.0,
    ) -> None:
        self.enabled = enabled
        self.window_seconds = window_seconds
        self.fps_window_seconds = fps_window_seconds
        self._memory_sampler_interval = memory_sampler_interval
        self.queue_high_utilization_pct = queue_high_utilization_pct
        self.latency_warn_ms = latency_warn_ms

    def start_memory_sampler(self) -> None:
        if not self.enabled or psutil is None:
            return

        with self._memory_lock:
            if self._memory_thread and self._memory_thread.is_alive():
                return
            self._memory_stop_event.clear()
            self._memory_thread = threading.Thread(
                target=self._memory_sampler_loop,
                name="MetricsMemorySampler",
                daemon=True,
            )
            self._memory_thread.start()

    def _memory_sampler_loop(self) -> None:
        process = psutil.Process() if psutil else None
        while not self._memory_stop_event.is_set():
            if process:
                with self._memory_lock:
                    self._memory_rss_bytes = float(process.memory_info().rss)
            self._memory_stop_event.wait(self._memory_sampler_interval)

    def shutdown(self) -> None:
        self._memory_stop_event.set()
        with self._memory_lock:
            if self._memory_thread and self._memory_thread.is_alive():
                self._memory_thread.join(timeout=1.0)
            self._memory_thread = None

    def reset(self) -> None:
        """Reset all recorded metrics. Intended for test isolation."""
        with self._lock:
            self._pipelines.clear()
        with self._memory_lock:
            self._memory_rss_bytes = 0.0

    def register_pipeline(
        self,
        camera_identifier: str,
        pipeline_id: int,
        pipeline_type: str,
        queue_max_size: int,
    ) -> None:
        if not self.enabled:
            return
        key = (camera_identifier, pipeline_id)
        with self._lock:
            if key not in self._pipelines:
                self._pipelines[key] = PipelineMetrics(
                    camera_identifier=camera_identifier,
                    pipeline_id=pipeline_id,
                    pipeline_type=pipeline_type,
                    queue_max_size=queue_max_size,
                    window_seconds=self.window_seconds,
                    fps_window_seconds=self.fps_window_seconds,
                )
            else:
                self._pipelines[key].update_metadata(pipeline_type, queue_max_size)

    def record_drop(
        self,
        camera_identifier: str,
        pipeline_id: int,
        queue_size: int,
        queue_max_size: int,
    ) -> None:
        if not self.enabled:
            return
        metrics = self._get_or_create_pipeline(
            camera_identifier=camera_identifier,
            pipeline_id=pipeline_id,
            pipeline_type="unknown",
            queue_max_size=queue_max_size,
        )
        metrics.record_drop(time.time(), queue_size)

    def record_queue_depth(
        self,
        camera_identifier: str,
        pipeline_id: int,
        queue_size: int,
        queue_max_size: int,
    ) -> None:
        if not self.enabled:
            return
        if not isinstance(queue_size, (int, float)):
            return
        metrics = self._get_or_create_pipeline(
            camera_identifier=camera_identifier,
            pipeline_id=pipeline_id,
            pipeline_type="unknown",
            queue_max_size=queue_max_size,
        )
        metrics.record_queue(time.time(), queue_size)

    def record_latencies(
        self,
        camera_identifier: str,
        pipeline_id: int,
        pipeline_type: str,
        total_latency_ms: float,
        queue_latency_ms: float,
        processing_latency_ms: float,
    ) -> None:
        if not self.enabled:
            return
        metrics = self._get_or_create_pipeline(
            camera_identifier=camera_identifier,
            pipeline_id=pipeline_id,
            pipeline_type=pipeline_type,
            queue_max_size=0,
        )
        now = time.time()
        metrics.record_latencies(
            now, total_latency_ms, queue_latency_ms, processing_latency_ms
        )
        metrics.record_processed_frame(now)

    def get_snapshot(self) -> Dict[str, object]:
        if not self.enabled:
            return {"enabled": False, "pipelines": [], "memory": {"rss_bytes": 0.0}}

        with self._lock:
            pipelines = list(self._pipelines.values())

        timestamp = time.time()
        pipeline_snapshots = [pipeline.snapshot(timestamp) for pipeline in pipelines]
        with self._memory_lock:
            rss = self._memory_rss_bytes

        return {
            "enabled": True,
            "generated_at": time.time(),
            "pipelines": pipeline_snapshots,
            "memory": {"rss_bytes": rss},
            "config": {
                "window_seconds": self.window_seconds,
                "fps_window_seconds": self.fps_window_seconds,
                "queue_high_utilization_pct": self.queue_high_utilization_pct,
                "latency_warn_ms": self.latency_warn_ms,
            },
        }

    def _get_or_create_pipeline(
        self,
        camera_identifier: str,
        pipeline_id: int,
        pipeline_type: str,
        queue_max_size: int,
    ) -> PipelineMetrics:
        key = (camera_identifier, pipeline_id)
        with self._lock:
            pipeline = self._pipelines.get(key)
            if pipeline is None:
                pipeline = PipelineMetrics(
                    camera_identifier=camera_identifier,
                    pipeline_id=pipeline_id,
                    pipeline_type=pipeline_type,
                    queue_max_size=queue_max_size,
                    window_seconds=self.window_seconds,
                    fps_window_seconds=self.fps_window_seconds,
                )
                self._pipelines[key] = pipeline
            else:
                pipeline.update_metadata(pipeline_type, queue_max_size)
        return pipeline


# Shared singleton registry used by the application.
metrics_registry = MetricsRegistry()
