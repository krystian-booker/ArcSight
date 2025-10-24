"""System metrics collection for CPU, RAM, and temperature across platforms."""

from __future__ import annotations

import platform
import threading
import time
from dataclasses import dataclass
from typing import Dict, List, Optional

try:
    import psutil  # type: ignore
except ImportError:
    psutil = None


@dataclass
class SystemSnapshot:
    """Snapshot of system metrics at a point in time."""

    cpu_percent: float
    cpu_count: int
    ram_total_bytes: int
    ram_used_bytes: int
    ram_percent: float
    temperatures: List[Dict[str, float]]
    platform: str
    timestamp: float


class SystemMetricsCollector:
    """Collects system metrics including CPU, RAM, and temperature."""

    def __init__(self, sample_interval: float = 2.0):
        """
        Initialize the system metrics collector.

        Args:
            sample_interval: Interval in seconds between metric samples.
        """
        self._sample_interval = sample_interval
        self._lock = threading.Lock()
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._enabled = psutil is not None

        # Latest snapshot data
        self._cpu_percent: float = 0.0
        self._cpu_count: int = 0
        self._ram_total_bytes: int = 0
        self._ram_used_bytes: int = 0
        self._ram_percent: float = 0.0
        self._temperatures: List[Dict[str, float]] = []
        self._platform: str = platform.system()

        if self._enabled:
            self._cpu_count = psutil.cpu_count() or 0

    def start(self) -> None:
        """Start the background metrics collection thread."""
        if not self._enabled:
            return

        with self._lock:
            if self._thread and self._thread.is_alive():
                return
            self._stop_event.clear()
            self._thread = threading.Thread(
                target=self._collection_loop,
                name="SystemMetricsCollector",
                daemon=True,
            )
            self._thread.start()

    def stop(self) -> None:
        """Stop the background metrics collection thread."""
        self._stop_event.set()
        with self._lock:
            if self._thread and self._thread.is_alive():
                self._thread.join(timeout=2.0)
            self._thread = None

    def _collection_loop(self) -> None:
        """Background thread that periodically collects system metrics."""
        # Initialize CPU percent (first call returns 0)
        if psutil:
            psutil.cpu_percent(interval=None)

        while not self._stop_event.is_set():
            try:
                self._collect_metrics()
            except Exception:
                # Silently continue on errors
                pass
            self._stop_event.wait(self._sample_interval)

    def _collect_metrics(self) -> None:
        """Collect current system metrics."""
        if not psutil:
            return

        # CPU metrics
        cpu_percent = psutil.cpu_percent(interval=None)

        # Memory metrics
        memory = psutil.virtual_memory()
        ram_total = memory.total
        ram_used = memory.used
        ram_percent = memory.percent

        # Temperature metrics (platform-specific)
        temperatures = self._collect_temperatures()

        with self._lock:
            self._cpu_percent = cpu_percent
            self._ram_total_bytes = ram_total
            self._ram_used_bytes = ram_used
            self._ram_percent = ram_percent
            self._temperatures = temperatures

    def _collect_temperatures(self) -> List[Dict[str, float]]:
        """
        Collect temperature sensors from the system.

        Returns:
            List of temperature readings with sensor name and value in Celsius.
        """
        if not psutil or not hasattr(psutil, "sensors_temperatures"):
            return []

        try:
            temps = psutil.sensors_temperatures()
            if not temps:
                return []

            result = []
            for sensor_name, entries in temps.items():
                for entry in entries:
                    # Filter out invalid readings
                    if entry.current > 0 and entry.current < 150:
                        result.append(
                            {
                                "sensor": f"{sensor_name}_{entry.label}" if entry.label else sensor_name,
                                "temperature_c": round(entry.current, 1),
                                "critical": entry.critical if entry.critical else None,
                                "high": entry.high if entry.high else None,
                            }
                        )
            return result
        except (AttributeError, OSError):
            # sensors_temperatures may not be available on all platforms
            return []

    def get_snapshot(self) -> Dict[str, object]:
        """
        Get the current system metrics snapshot.

        Returns:
            Dictionary containing system metrics.
        """
        if not self._enabled:
            return {
                "enabled": False,
                "cpu_percent": 0.0,
                "cpu_count": 0,
                "ram_total_bytes": 0,
                "ram_used_bytes": 0,
                "ram_percent": 0.0,
                "temperatures": [],
                "platform": platform.system(),
                "timestamp": time.time(),
            }

        with self._lock:
            return {
                "enabled": True,
                "cpu_percent": round(self._cpu_percent, 1),
                "cpu_count": self._cpu_count,
                "ram_total_bytes": self._ram_total_bytes,
                "ram_used_bytes": self._ram_used_bytes,
                "ram_percent": round(self._ram_percent, 1),
                "temperatures": self._temperatures.copy(),
                "platform": self._platform,
                "timestamp": time.time(),
            }


# Shared singleton instance
system_metrics_collector = SystemMetricsCollector()
