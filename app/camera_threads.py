import cv2
import threading
import time
import queue
import numpy as np
import json
import logging
from typing import Dict, Optional
from numbers import Real

from .pipelines.apriltag_pipeline import AprilTagPipeline
from .pipelines.coloured_shape_pipeline import ColouredShapePipeline
from .pipelines.object_detection_ml_pipeline import ObjectDetectionMLPipeline
from .camera_discovery import get_driver
from .metrics import metrics_registry
from .pipeline_validators import (
    get_default_config,
    recommended_apriltag_threads,
)

logger = logging.getLogger(__name__)


def _coerce_real(value) -> Optional[float]:
    """Return float(value) when possible, otherwise None."""
    if isinstance(value, Real):
        return float(value)
    return None


def _coerce_int(value) -> Optional[int]:
    """Return int(value) when possible, otherwise None."""
    real_value = _coerce_real(value)
    if real_value is None:
        return None
    try:
        return int(real_value)
    except (TypeError, ValueError):
        return None


# --- Frame Buffer and Reference Counting ---
class RefCountedFrame:
    """A thread-safe wrapper for a numpy frame buffer that manages reference counts."""

    def __init__(self, frame_buffer, release_callback):
        self.frame_buffer = frame_buffer
        self._release_callback = release_callback
        self._ref_count = 0
        self._lock = threading.Lock()
        self._created_time = time.perf_counter()
        self._enqueue_times: Dict[int, float] = {}

    def acquire(self):
        """Increments the reference count."""
        with self._lock:
            self._ref_count += 1

    def release(self):
        """Decrements the reference count and calls the release callback if the count is zero."""
        with self._lock:
            if self._ref_count > 0:
                self._ref_count -= 1
                if self._ref_count == 0 and self._release_callback:
                    self._release_callback(self.frame_buffer)

    @property
    def data(self):
        """Returns the read-only numpy array."""
        return self.frame_buffer

    def get_writable_copy(self):
        """Returns a deep copy of the frame for pipelines that need to modify it."""
        return self.frame_buffer.copy()

    def get_modifiable_view(self):
        """Returns either the buffer directly (if ref_count <= 2) or a copy.

        This is an optimization for the display frame overlay. If only the acquisition
        thread and the display frame hold references (ref_count <= 2), we can safely
        modify the buffer directly. Otherwise, we need a copy to avoid affecting pipelines.

        Returns:
            tuple: (numpy.ndarray, bool) - The frame and whether it's safe to modify in place
        """
        with self._lock:
            # ref_count <= 2 means only acquisition thread + display/latest_raw_frame
            if self._ref_count <= 2:
                return self.frame_buffer, True
            else:
                return self.frame_buffer.copy(), False

    @property
    def created_timestamp(self) -> float:
        """Monotonic timestamp captured when the frame was created."""
        return self._created_time

    def mark_enqueued(
        self, pipeline_id: int, timestamp: Optional[float] = None
    ) -> None:
        """Record when the frame was enqueued for a specific pipeline."""
        ts = time.perf_counter() if timestamp is None else timestamp
        with self._lock:
            self._enqueue_times[pipeline_id] = ts

    def pop_enqueue_timestamp(self, pipeline_id: int) -> Optional[float]:
        """Return and clear the stored enqueue timestamp for a pipeline."""
        with self._lock:
            return self._enqueue_times.pop(pipeline_id, None)


class FrameBufferPool:
    """Manages a pool of pre-allocated numpy arrays to avoid repeated memory allocation.

    Uses a water-mark based shrinking strategy to prevent unbounded memory growth:
    - Starts with initial_buffers (default: 5)
    - Can grow up to max_buffers (default: 10) during high load
    - Shrinks back to initial_buffers when pool size exceeds high_water_mark and is idle
    """

    def __init__(
        self,
        name="DefaultPool",
        max_buffers=10,
        initial_buffers=5,
        high_water_mark=8,
        shrink_idle_seconds=10.0,
    ):
        self._pool = queue.Queue()
        self._buffer_shape = None
        self._buffer_dtype = None
        self._allocated = 0
        self._name = name
        self._max_buffers = max_buffers
        self._initial_buffers = initial_buffers
        self._high_water_mark = high_water_mark
        self._shrink_idle_seconds = shrink_idle_seconds
        self._lock = threading.Lock()
        self._last_allocation_time = None
        self._shrink_check_counter = 0

    def initialize(self, frame, num_buffers=None):
        """Initializes the pool with buffers matching the shape and type of a sample frame."""

        # Already initialized with correct shape
        if self._buffer_shape is not None and self._buffer_shape == frame.shape:
            return

        # If shape is different, we need to re-initialize.
        if num_buffers is None:
            num_buffers = self._initial_buffers

        print(f"[{self._name}] Initializing buffer pool for shape {frame.shape}...")
        self._pool = queue.Queue()
        self._buffer_shape = frame.shape
        self._buffer_dtype = frame.dtype
        for _ in range(num_buffers):
            self._pool.put(np.empty(self._buffer_shape, dtype=self._buffer_dtype))
        self._allocated = num_buffers
        self._last_allocation_time = None
        self._shrink_check_counter = 0
        print(
            f"[{self._name}] Buffer pool initialized with {num_buffers} buffers (max: {self._max_buffers})."
        )

    def get_buffer(self):
        """Retrieves a buffer from the pool, allocating a new one if the pool is empty.
        Returns None if the maximum buffer limit is reached to prevent memory leaks."""
        try:
            return self._pool.get_nowait()
        except queue.Empty:
            if self._buffer_shape is not None:
                with self._lock:
                    if self._allocated < self._max_buffers:
                        self._allocated += 1
                        self._last_allocation_time = time.time()
                        print(
                            f"[{self._name}] Pool empty, allocating new buffer. Total allocated: {self._allocated}"
                        )
                        return np.empty(self._buffer_shape, dtype=self._buffer_dtype)
                    else:
                        # Max buffers reached - drop frame to prevent memory leak
                        print(
                            f"[{self._name}] Max buffer limit ({self._max_buffers}) reached. Dropping frame."
                        )
                        return None
            return None

    def release_buffer(self, buffer):
        """Returns a buffer to the pool for reuse.

        Implements water-mark based shrinking to prevent unbounded memory growth.
        Periodically checks if the pool should be shrunk back to initial size.
        """
        self._pool.put(buffer)

        # Check for shrinking periodically (every N releases) to avoid overhead
        self._shrink_check_counter += 1
        if self._shrink_check_counter >= 100:
            self._shrink_check_counter = 0
            self._try_shrink_pool()

    def _try_shrink_pool(self):
        """Attempts to shrink the pool if conditions are met.

        Shrinking occurs when:
        1. Pool has grown beyond high_water_mark
        2. No new allocations have occurred for shrink_idle_seconds
        3. Pool is currently full (all buffers returned)
        """
        with self._lock:
            # Only shrink if we've grown beyond initial size
            if self._allocated <= self._initial_buffers:
                return

            # Only shrink if we've exceeded the high water mark
            if self._allocated < self._high_water_mark:
                return

            # Check if pool has been idle (no new allocations recently)
            if self._last_allocation_time is not None:
                idle_time = time.time() - self._last_allocation_time
                if idle_time < self._shrink_idle_seconds:
                    return

            # Check if pool is currently full (indicates low demand)
            current_pool_size = self._pool.qsize()
            if current_pool_size < self._allocated:
                # Buffers are still in use, don't shrink
                return

            # Perform the shrink: drain excess buffers
            buffers_to_remove = self._allocated - self._initial_buffers
            removed = 0
            for _ in range(buffers_to_remove):
                try:
                    self._pool.get_nowait()
                    removed += 1
                except queue.Empty:
                    break

            if removed > 0:
                self._allocated -= removed
                print(
                    f"[{self._name}] Shrunk pool by {removed} buffers. New size: {self._allocated}/{self._max_buffers}"
                )
                self._last_allocation_time = None  # Reset allocation tracking


# --- Vision Processing Thread (Consumer) ---
class VisionProcessingThread(threading.Thread):
    """A consumer thread that runs a vision pipeline on frames from a queue."""

    def __init__(
        self,
        identifier,
        pipeline_id,
        pipeline_type,
        pipeline_config_json,
        camera_matrix_json,
        dist_coeffs_json,
        frame_queue,
        jpeg_quality=75,
    ):
        super().__init__()
        self.daemon = True
        self.identifier = identifier
        self.pipeline_id = pipeline_id
        self.pipeline_type = pipeline_type
        self.frame_queue = frame_queue
        self.stop_event = threading.Event()
        self.results_lock = threading.Lock()
        self.latest_results = {"status": "Starting..."}
        self.latest_processed_frame_raw = None  # Raw annotated frame for lazy encoding
        self.processed_frame_lock = threading.Lock()
        self.jpeg_quality = jpeg_quality
        self.processed_frame_seq = 0
        self.latest_processed_frame_timestamp = 0.0

        # Initialize the pipeline object
        self.pipeline_instance = None

        # Pre-calculation variables for drawing
        self.cam_matrix = None
        self.dist_coeffs = None
        self.obj_pts = None
        self._using_dynamic_default_cam_matrix = False
        self._default_cam_matrix_shape = None

        # Load camera calibration data from primitive values
        if camera_matrix_json:
            try:
                self.cam_matrix = np.array(json.loads(camera_matrix_json))
                print(f"[{self.identifier}] Loaded camera matrix from DB.")
            except (json.JSONDecodeError, TypeError):
                print(
                    f"[{self.identifier}] Failed to parse camera matrix from DB. Falling back to default."
                )
                self.cam_matrix = None

        # Load distortion coefficients
        if dist_coeffs_json:
            try:
                self.dist_coeffs = np.array(
                    json.loads(dist_coeffs_json), dtype=np.float32
                ).reshape(-1, 1)
                print(f"[{self.identifier}] Loaded distortion coefficients from DB.")
            except (json.JSONDecodeError, TypeError):
                print(
                    f"[{self.identifier}] Failed to parse dist_coeffs from DB. Assuming zero distortion."
                )
                self.dist_coeffs = np.zeros((4, 1), dtype=np.float32)
        else:
            # Default to zero distortion if not provided
            self.dist_coeffs = np.zeros((4, 1), dtype=np.float32)

        pipeline_config = {}
        if pipeline_config_json:
            try:
                parsed_config = json.loads(pipeline_config_json)
                if isinstance(parsed_config, dict):
                    pipeline_config = parsed_config
                else:
                    print(
                        f"[{self.identifier}] Pipeline config was not a JSON object. Using default."
                    )
            except (json.JSONDecodeError, TypeError):
                print(
                    f"[{self.identifier}] Failed to parse pipeline config from DB. Using default."
                )

        default_config = get_default_config(self.pipeline_type) or {}
        if not isinstance(default_config, dict):
            default_config = {}
        else:
            default_config = default_config.copy()

        # This ensures user settings override defaults, but defaults are there as a fallback
        final_config = {**default_config, **pipeline_config}

        self._auto_threads_enabled = False
        self._detector_threads = None
        if self.pipeline_type == "AprilTag":
            recommended_threads = recommended_apriltag_threads()
            auto_threads = final_config.get("auto_threads", True)
            auto_threads_enabled = bool(auto_threads)
            configured_threads = final_config.get("threads")

            if auto_threads_enabled:
                if configured_threads != recommended_threads:
                    logger.info(
                        "Auto-scaling AprilTag detector threads for pipeline %s on camera %s: %s -> %s",
                        self.pipeline_id,
                        self.identifier,
                        configured_threads,
                        recommended_threads,
                    )
                final_config["threads"] = recommended_threads
            else:
                try:
                    manual_threads = int(configured_threads)
                except (TypeError, ValueError):
                    manual_threads = 1
                if manual_threads < 1:
                    manual_threads = 1
                final_config["threads"] = manual_threads

            self._auto_threads_enabled = auto_threads_enabled
            self._detector_threads = final_config["threads"]

        if self.pipeline_type == "AprilTag":
            self.pipeline_instance = AprilTagPipeline(final_config)
            # Pre-calculate the 3D coordinates of the tag corners
            tag_size_m = final_config.get("tag_size_m", 0.165)
            half_tag_size = tag_size_m / 2
            self.obj_pts = np.array(
                [
                    [-half_tag_size, -half_tag_size, 0],
                    [half_tag_size, -half_tag_size, 0],
                    [half_tag_size, half_tag_size, 0],
                    [-half_tag_size, half_tag_size, 0],
                    [-half_tag_size, -half_tag_size, -tag_size_m],
                    [half_tag_size, -half_tag_size, -tag_size_m],
                    [half_tag_size, half_tag_size, -tag_size_m],
                    [-half_tag_size, half_tag_size, -tag_size_m],
                ]
            )
        elif self.pipeline_type == "Coloured Shape":
            self.pipeline_instance = ColouredShapePipeline(final_config)
        elif self.pipeline_type == "Object Detection (ML)":
            self.pipeline_instance = ObjectDetectionMLPipeline(final_config)
        else:
            print(
                f"Warning: Unknown pipeline type '{self.pipeline_type}' for pipeline ID {self.pipeline_id}"
            )
        metrics_registry.register_pipeline(
            camera_identifier=self.identifier,
            pipeline_id=self.pipeline_id,
            pipeline_type=self.pipeline_type,
            queue_max_size=getattr(frame_queue, "maxsize", 0),
        )
        self._latency_log_state = {"last_warn": 0.0, "last_latency_ms": 0.0}

    def run(self):
        """The main loop for the vision processing thread."""
        if not self.pipeline_instance:
            print(
                f"Stopping processing thread for pipeline {self.pipeline_id} due to no valid pipeline object."
            )
            return

        print(
            f"Starting vision processing thread for pipeline {self.pipeline_id} ({self.pipeline_type}) on camera {self.identifier}"
        )

        # If no calibration data was loaded from the DB, create a default matrix.
        if self.cam_matrix is None:
            print(
                f"[{self.identifier}] No calibration data found, will estimate camera matrix from frame resolution."
            )

        while not self.stop_event.is_set():
            ref_counted_frame = None
            try:
                ref_counted_frame = self.frame_queue.get(timeout=1)
                dequeue_timestamp = time.perf_counter()
                raw_frame = ref_counted_frame.data
                queue_depth_after_pop = _coerce_int(self.frame_queue.qsize())
                queue_max_size = _coerce_int(getattr(self.frame_queue, "maxsize", 0))
                if queue_depth_after_pop is not None:
                    metrics_registry.record_queue_depth(
                        camera_identifier=self.identifier,
                        pipeline_id=self.pipeline_id,
                        queue_size=queue_depth_after_pop,
                        queue_max_size=queue_max_size or 0,
                    )
                queue_util_pct = 0.0
                if queue_depth_after_pop is not None and queue_max_size:
                    queue_util_pct = min(
                        ((queue_depth_after_pop + 1) / queue_max_size) * 100.0, 100.0
                    )

                enqueue_timestamp = ref_counted_frame.pop_enqueue_timestamp(
                    self.pipeline_id
                )
                queue_wait_ms = 0.0
                if isinstance(enqueue_timestamp, Real):
                    queue_wait_ms = max(
                        (dequeue_timestamp - float(enqueue_timestamp)) * 1000.0, 0.0
                    )

                self._ensure_default_cam_matrix(raw_frame)

                processing_start = time.perf_counter()

                # Delegate processing to the pipeline object
                annotated_frame = raw_frame.copy()  # Always make a copy to draw on
                detections = []
                current_results = {}

                if self.pipeline_type == "AprilTag":
                    result = self.pipeline_instance.process_frame(
                        raw_frame, self.cam_matrix, self.dist_coeffs
                    )

                    detections_payload = result.get("detections")
                    overlays = result.get("overlays")

                    if detections_payload is None and "single_tags" in result:
                        detections_payload = [
                            entry.get("ui_data")
                            for entry in result.get("single_tags", [])
                            if entry.get("ui_data") is not None
                        ]

                    if overlays is None and "single_tags" in result:
                        overlays = [
                            entry.get("drawing_data")
                            for entry in result.get("single_tags", [])
                            if entry.get("drawing_data") is not None
                        ]

                    multi_tag_pose = result.get("multi_tag_pose")
                    if multi_tag_pose is None and "multi_tag" in result:
                        multi_tag_pose = result.get("multi_tag")

                    detections = detections_payload or []
                    current_results = {
                        "tags_found": bool(detections),
                        "detections": detections,
                        "multi_tag_pose": multi_tag_pose,
                    }
                    if "multi_tag" in result:
                        current_results["multi_tag"] = result.get("multi_tag")
                    if overlays:
                        self._draw_3d_box_on_frame(annotated_frame, overlays)

                elif self.pipeline_type == "Object Detection (ML)":
                    detections = self.pipeline_instance.process_frame(
                        raw_frame, self.cam_matrix
                    )
                    for det in detections:
                        box = det["box"]
                        label = f"{det['label']}: {det['confidence']:.2f}"
                        cv2.rectangle(
                            annotated_frame,
                            (box[0], box[1]),
                            (box[2], box[3]),
                            (0, 255, 0),
                            2,
                        )
                        y = box[1] - 15 if box[1] - 15 > 15 else box[1] + 15
                        cv2.putText(
                            annotated_frame,
                            label,
                            (box[0], y),
                            cv2.FONT_HERSHEY_SIMPLEX,
                            0.5,
                            (0, 255, 0),
                            2,
                        )
                    current_results = {"detections": detections}

                elif self.pipeline_type == "Coloured Shape":
                    detections = self.pipeline_instance.process_frame(
                        raw_frame, self.cam_matrix
                    )
                    current_results = {"detections": detections}

                processing_end = time.perf_counter()
                processing_latency_ms = (processing_end - processing_start) * 1000.0
                created_timestamp = getattr(
                    ref_counted_frame, "created_timestamp", None
                )
                if not isinstance(created_timestamp, Real):
                    created_timestamp = (
                        enqueue_timestamp
                        if isinstance(enqueue_timestamp, Real)
                        else dequeue_timestamp
                    )
                total_latency_ms = max(
                    (processing_end - float(created_timestamp)) * 1000.0, 0.0
                )
                current_results["processing_time_ms"] = f"{processing_latency_ms:.2f}"
                current_results["queue_wait_ms"] = f"{queue_wait_ms:.2f}"
                current_results["total_latency_ms"] = f"{total_latency_ms:.2f}"

                with self.results_lock:
                    self.latest_results = current_results

                # --- Store Processed Frame (raw, for lazy encoding) ---
                with self.processed_frame_lock:
                    self.latest_processed_frame_raw = annotated_frame
                    self.processed_frame_seq += 1
                    self.latest_processed_frame_timestamp = time.perf_counter()

                metrics_registry.record_latencies(
                    camera_identifier=self.identifier,
                    pipeline_id=self.pipeline_id,
                    pipeline_type=self.pipeline_type,
                    total_latency_ms=total_latency_ms,
                    queue_latency_ms=queue_wait_ms,
                    processing_latency_ms=processing_latency_ms,
                )
                self._log_latency_if_needed(
                    total_latency_ms=total_latency_ms,
                    queue_wait_ms=queue_wait_ms,
                    queue_util_pct=queue_util_pct,
                )
            except queue.Empty:
                continue
            finally:
                if ref_counted_frame:
                    ref_counted_frame.release()

        print(
            f"Stopping vision processing thread for pipeline {self.pipeline_id} on camera {self.identifier}"
        )

    def _ensure_default_cam_matrix(self, frame):
        """Derives a rough pinhole camera matrix from the current frame size when calibration is missing."""
        if frame is None:
            return

        if self.cam_matrix is not None and not self._using_dynamic_default_cam_matrix:
            return

        h, w = frame.shape[:2]

        if (
            self._using_dynamic_default_cam_matrix
            and self._default_cam_matrix_shape == (h, w)
        ):
            return

        fx = fy = w * 0.9
        cx, cy = w / 2.0, h / 2.0
        self.cam_matrix = np.array(
            [[fx, 0.0, cx], [0.0, fy, cy], [0.0, 0.0, 1.0]], dtype=np.float32
        )
        self._default_cam_matrix_shape = (h, w)
        self._using_dynamic_default_cam_matrix = True
        print(
            f"[{self.identifier}] Using default calibration for {w}x{h}: fx={fx:.2f}, cx={cx:.2f}, cy={cy:.2f}"
        )

    def get_latest_results(self):
        """Safely retrieves the latest results from this pipeline."""
        with self.results_lock:
            return self.latest_results

    def get_processed_frame(self):
        """Encodes and returns the latest processed frame as JPEG bytes.

        This performs lazy encoding - JPEG compression only happens when a client
        requests the frame, avoiding wasteful encoding when no clients are connected.

        Returns:
            bytes: JPEG-encoded frame, or None if no frame is available
        """
        with self.processed_frame_lock:
            if self.latest_processed_frame_raw is None:
                return None

            ret, buffer = cv2.imencode(
                ".jpg",
                self.latest_processed_frame_raw,
                [cv2.IMWRITE_JPEG_QUALITY, self.jpeg_quality],
            )
            if ret:
                return buffer.tobytes()
            return None

    def _draw_3d_box_on_frame(self, frame, detections):
        """Draws a 3D bounding box around each detected AprilTag."""
        for det in detections:
            rvec, tvec = det["rvec"], det["tvec"]

            # Project points using camera distortion coefficients
            img_pts, _ = cv2.projectPoints(
                self.obj_pts, rvec, tvec, self.cam_matrix, self.dist_coeffs
            )
            img_pts = np.int32(img_pts).reshape(-1, 2)

            # Draw the base
            cv2.drawContours(frame, [img_pts[:4]], -1, (0, 255, 0), 2)
            # Draw the pillars
            for i in range(4):
                cv2.line(
                    frame, tuple(img_pts[i]), tuple(img_pts[i + 4]), (0, 255, 0), 2
                )
            # Draw the top
            cv2.drawContours(frame, [img_pts[4:]], -1, (0, 255, 0), 2)

            # Draw the tag ID
            corner = tuple(np.int32(det["corners"][0]))
            cv2.putText(
                frame,
                str(det["id"]),
                corner,
                cv2.FONT_HERSHEY_SIMPLEX,
                0.7,
                (0, 0, 255),
                2,
            )

    def stop(self):
        """Signals the thread to stop."""
        self.stop_event.set()

    def _log_latency_if_needed(
        self,
        total_latency_ms: float,
        queue_wait_ms: float,
        queue_util_pct: float,
    ) -> None:
        """Emit throttled warnings when pipelines fall behind."""
        now = time.time()
        last_warn = self._latency_log_state.get("last_warn", 0.0)
        if now - last_warn < 5.0:
            return

        latency_threshold = metrics_registry.latency_warn_ms or 0.0
        queue_threshold = metrics_registry.queue_high_utilization_pct or 100.0

        if latency_threshold > 0.0 and total_latency_ms > latency_threshold:
            logger.warning(
                "Slow pipeline %s (%s) on camera %s: total latency %.1f ms (threshold %.1f ms, queue wait %.1f ms)",
                self.pipeline_id,
                self.pipeline_type,
                self.identifier,
                total_latency_ms,
                latency_threshold,
                queue_wait_ms,
            )
            self._latency_log_state["last_warn"] = now
            return

        if queue_threshold > 0.0 and queue_util_pct >= queue_threshold:
            logger.warning(
                "Pipeline %s (%s) nearing queue saturation on camera %s: utilization %.1f%% (threshold %.1f%%)",
                self.pipeline_id,
                self.pipeline_type,
                self.identifier,
                queue_util_pct,
                queue_threshold,
            )
            self._latency_log_state["last_warn"] = now
            return

        queue_wait_threshold = max(latency_threshold * 0.6, 50.0)
        if queue_wait_ms > queue_wait_threshold:
            logger.warning(
                "Pipeline %s (%s) experiencing queue delays on camera %s: queue wait %.1f ms",
                self.pipeline_id,
                self.pipeline_type,
                self.identifier,
                queue_wait_ms,
            )
            self._latency_log_state["last_warn"] = now


class CameraAcquisitionThread(threading.Thread):
    """
    A producer thread that uses a driver to acquire frames and distributes them
    to multiple consumer queues. It handles camera connection, disconnection,
    and reconnection automatically.
    """

    def __init__(
        self, identifier, camera_type, orientation, app, jpeg_quality=85, camera_id=None
    ):
        super().__init__()
        self.daemon = True
        self.identifier = identifier
        self.camera_type = camera_type
        self.app = app
        self.camera_db_id = camera_id
        self.driver = None
        self.frame_lock = threading.Lock()
        self.latest_display_frame_raw = None  # Raw frame for lazy encoding
        self.raw_frame_lock = threading.Lock()
        self.latest_raw_frame = None
        self.processing_queues = {}
        self.queues_lock = threading.Lock()
        self.stop_event = threading.Event()
        self.fps = 0.0
        self.buffer_pool = FrameBufferPool(name=self.identifier)
        self.jpeg_quality = jpeg_quality
        self._drop_states: Dict[int, Dict[str, float]] = {}
        self.display_frame_seq = 0
        self.latest_display_frame_timestamp = 0.0

        # Event-based configuration update
        self.config_update_event = threading.Event()
        self._orientation = orientation
        self._orientation_lock = threading.Lock()

    def add_pipeline_queue(self, pipeline_id, frame_queue):
        """Adds a pipeline's frame queue to the list of queues to receive frames."""
        with self.queues_lock:
            self.processing_queues[pipeline_id] = frame_queue

    def remove_pipeline_queue(self, pipeline_id):
        """Removes a pipeline's frame queue from the list of queues."""
        with self.queues_lock:
            self.processing_queues.pop(pipeline_id, None)

    def _reset_drop_state(self, pipeline_id: int) -> None:
        state = self._drop_states.get(pipeline_id)
        if state:
            state["consecutive"] = 0

    def _handle_pipeline_drop(
        self, pipeline_id: int, frame_queue, queue_size: int, queue_max_size: int
    ) -> None:
        state = self._drop_states.setdefault(
            pipeline_id, {"last_log": 0.0, "consecutive": 0}
        )
        state["consecutive"] += 1
        now = time.time()
        max_size = (
            queue_max_size or _coerce_int(getattr(frame_queue, "maxsize", 0)) or 0
        )
        utilization_pct = 0.0
        if max_size:
            utilization_pct = min(float(queue_size) / max_size, 1.0) * 100.0
        should_log = now - state["last_log"] >= 5.0 or state["consecutive"] in (
            1,
            5,
            10,
        )
        if should_log:
            logger.warning(
                "Dropped frame for pipeline %s on camera %s (queue depth %d/%s, utilization %.1f%%, consecutive drops %d)",
                pipeline_id,
                self.identifier,
                queue_size,
                max_size if max_size else "unbounded",
                utilization_pct,
                state["consecutive"],
            )
            state["last_log"] = now

    def update_orientation(self, new_orientation):
        """Updates the camera orientation and signals the acquisition thread."""
        with self._orientation_lock:
            if self._orientation != new_orientation:
                self._orientation = new_orientation
                self.config_update_event.set()
                print(
                    f"[{self.identifier}] Orientation update signaled: {new_orientation}"
                )

    def _should_cache_raw_frame(self):
        """Returns True when raw frames should be cached for calibration workflows."""
        manager = getattr(self.app, "calibration_manager", None)
        if manager is None or self.camera_db_id is None:
            return False
        return manager.get_session(self.camera_db_id) is not None

    def get_display_frame(self):
        """Encodes and returns the latest display frame as JPEG bytes.

        This performs lazy encoding - JPEG compression only happens when a client
        requests the frame, avoiding wasteful encoding when no clients are connected.

        Returns:
            bytes: JPEG-encoded frame, or None if no frame is available
        """
        with self.frame_lock:
            if self.latest_display_frame_raw is None:
                return None

            ret, buffer = cv2.imencode(
                ".jpg",
                self.latest_display_frame_raw,
                [cv2.IMWRITE_JPEG_QUALITY, self.jpeg_quality],
            )
            if ret:
                return buffer.tobytes()
            return None

    def run(self):
        """The main loop for the camera acquisition thread."""
        print(f"Starting acquisition thread for {self.identifier}")

        while not self.stop_event.is_set():
            try:
                # Initialize the driver inside the loop for automatic reconnection
                # Pass camera data as a dict to avoid ORM session issues
                camera_data = {
                    "camera_type": self.camera_type,
                    "identifier": self.identifier,
                }
                self.driver = get_driver(camera_data)
                self.driver.connect()
                print(f"Camera {self.identifier} connected successfully via driver.")

                # The acquisition loop now uses the driver interface
                self._acquisition_loop()

            except Exception as e:
                print(
                    f"Error with camera {self.identifier}: {e}. Retrying in 5 seconds..."
                )
            finally:
                if self.driver:
                    self.driver.disconnect()
                # Wait before retrying connection, but only if we're not stopping.
                if not self.stop_event.is_set():
                    self.stop_event.wait(5.0)

        # Clean up the ref-counted frame
        with self.raw_frame_lock:
            if self.latest_raw_frame is not None:
                self.latest_raw_frame.release()
                self.latest_raw_frame = None

        print(f"Acquisition thread for {self.identifier} has stopped.")

    def _acquisition_loop(self):
        """Inner loop that processes frames once a camera is connected."""
        # Get initial orientation from the thread-safe copy
        with self._orientation_lock:
            orientation = self._orientation

        # Initialize buffer pool with the first frame
        first_frame = self.driver.get_frame()
        if first_frame is None:
            print(
                f"[{self.identifier}] Failed to get first frame, cannot initialize buffer pool."
            )
            return  # Exit to trigger reconnection

        oriented_first_frame = self._apply_orientation(first_frame, orientation)
        self.buffer_pool.initialize(oriented_first_frame)

        start_time, frame_count = time.time(), 0

        while not self.stop_event.is_set():
            # Check for configuration updates via event (non-blocking)
            if self.config_update_event.is_set():
                self.config_update_event.clear()
                with self._orientation_lock:
                    new_orientation = self._orientation
                if new_orientation != orientation:
                    print(
                        f"[{self.identifier}] Orientation changed to {new_orientation}. Re-initializing resources."
                    )
                    orientation = new_orientation
                    # Re-initialize buffer pool if orientation changes frame size
                    test_frame = self._apply_orientation(
                        first_frame.copy(), orientation
                    )
                    self.buffer_pool.initialize(test_frame)

            raw_frame_from_cam = self.driver.get_frame()
            if raw_frame_from_cam is None:
                print(f"Lost frame from {self.identifier}, attempting to reconnect.")
                break  # Exit inner loop to trigger reconnection

            # Apply orientation to the frame right after capture
            oriented_frame = self._apply_orientation(raw_frame_from_cam, orientation)

            pooled_buffer = self.buffer_pool.get_buffer()
            if pooled_buffer is None:
                # Buffer pool exhausted - drain queues to prevent buildup and memory leaks
                print(
                    f"[{self.identifier}] Buffer pool exhausted, draining queues to prevent memory buildup"
                )
                self._drain_processing_queues()
                continue

            # Copy the oriented frame into the buffer for pipelines.
            np.copyto(pooled_buffer, oriented_frame)
            ref_counted_frame = RefCountedFrame(
                pooled_buffer, release_callback=self.buffer_pool.release_buffer
            )

            # Acquire initial reference for the acquisition thread to ensure buffer is released
            # even if all queues are full or display frame encoding fails
            ref_counted_frame.acquire()

            try:
                # Store ref-counted frame for raw frame access (eliminates copy #1)
                should_cache_raw = self._should_cache_raw_frame()
                with self.raw_frame_lock:
                    # Release previous frame if it exists
                    if self.latest_raw_frame is not None:
                        self.latest_raw_frame.release()
                        self.latest_raw_frame = None
                    # Store new frame with reference only when calibration requires it
                    if should_cache_raw:
                        ref_counted_frame.acquire()
                        self.latest_raw_frame = ref_counted_frame

                # Distribute frame to pipeline queues
                with self.queues_lock:
                    queue_targets = list(self.processing_queues.items())

                for pipeline_id, frame_queue in queue_targets:
                    ref_counted_frame.acquire()
                    queue_max_size = (
                        _coerce_int(getattr(frame_queue, "maxsize", 0)) or 0
                    )
                    queue_size_before = _coerce_int(frame_queue.qsize())
                    if queue_size_before is not None:
                        metrics_registry.record_queue_depth(
                            camera_identifier=self.identifier,
                            pipeline_id=pipeline_id,
                            queue_size=queue_size_before,
                            queue_max_size=queue_max_size,
                        )
                    try:
                        frame_queue.put_nowait(ref_counted_frame)
                        enqueue_timestamp = time.perf_counter()
                        ref_counted_frame.mark_enqueued(pipeline_id, enqueue_timestamp)
                        queue_size_after = _coerce_int(frame_queue.qsize())
                        if queue_size_after is not None:
                            metrics_registry.record_queue_depth(
                                camera_identifier=self.identifier,
                                pipeline_id=pipeline_id,
                                queue_size=queue_size_after,
                                queue_max_size=queue_max_size,
                            )
                        self._reset_drop_state(pipeline_id)
                    except queue.Full:
                        # Queue is full - drop the oldest frame and add the new one
                        # This ensures consumers always have the most recent frames
                        try:
                            old_frame = frame_queue.get_nowait()
                            old_frame.release()  # Release the old frame
                        except queue.Empty:
                            pass  # Queue was drained by another thread

                        # Now try to add the new frame again
                        try:
                            frame_queue.put_nowait(ref_counted_frame)
                            enqueue_timestamp = time.perf_counter()
                            ref_counted_frame.mark_enqueued(pipeline_id, enqueue_timestamp)
                        except queue.Full:
                            # Still full (shouldn't happen), release the new frame
                            ref_counted_frame.release()

                        metrics_registry.record_drop(
                            camera_identifier=self.identifier,
                            pipeline_id=pipeline_id,
                            queue_size=queue_size_before,
                            queue_max_size=queue_max_size,
                        )
                        self._handle_pipeline_drop(
                            pipeline_id,
                            frame_queue,
                            queue_size_before if queue_size_before is not None else 0,
                            queue_max_size,
                        )

                # Prepare display frame (store raw frame for lazy encoding)
                # Use get_modifiable_view to avoid unnecessary copy when possible
                display_frame, is_direct = ref_counted_frame.get_modifiable_view()
                display_frame_with_overlay = self._prepare_display_frame(display_frame)

                # Store the raw frame instead of encoding immediately (lazy encoding)
                with self.frame_lock:
                    self.latest_display_frame_raw = display_frame_with_overlay
                    self.display_frame_seq += 1
                    self.latest_display_frame_timestamp = time.perf_counter()
            finally:
                # Release initial reference - this ensures buffer is returned to pool
                # when all consumers (pipelines + display) have finished with it
                ref_counted_frame.release()

            frame_count += 1
            elapsed_time = time.time() - start_time
            if elapsed_time >= 1.0:
                self.fps = frame_count / elapsed_time
                frame_count = 0
                start_time = time.time()

    def _drain_processing_queues(self):
        """Drains old frames from processing queues when buffer pool is exhausted.
        This prevents queue buildup and releases buffer pool resources."""
        with self.queues_lock:
            for q in self.processing_queues.values():
                drained_count = 0
                # Drain up to 2 frames from each queue (non-blocking)
                while drained_count < 2:
                    try:
                        old_frame = q.get_nowait()
                        old_frame.release()  # Release the ref-counted frame
                        drained_count += 1
                    except queue.Empty:
                        break
                if drained_count > 0:
                    print(
                        f"[{self.identifier}] Drained {drained_count} old frames from queue"
                    )

    def _apply_orientation(self, frame, orientation):
        if orientation == 90:
            return cv2.rotate(frame, cv2.ROTATE_90_CLOCKWISE)
        elif orientation == 180:
            return cv2.rotate(frame, cv2.ROTATE_180)
        elif orientation == 270:
            return cv2.rotate(frame, cv2.ROTATE_90_COUNTERCLOCKWISE)
        return frame

    def _prepare_display_frame(self, frame):
        """Applies an FPS overlay to a frame."""
        text = f"FPS: {self.fps:.2f}"
        cv2.putText(
            frame, text, (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2
        )
        return frame

    def stop(self):
        """Signals the thread to stop."""
        self.stop_event.set()
