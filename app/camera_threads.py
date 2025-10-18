import cv2
import threading
import time
import queue
import numpy as np
import json

from .extensions import db
from .models import Camera
from .pipelines.apriltag_pipeline import AprilTagPipeline
from .pipelines.coloured_shape_pipeline import ColouredShapePipeline
from .pipelines.object_detection_ml_pipeline import ObjectDetectionMLPipeline
from .camera_discovery import get_driver


# --- Frame Buffer and Reference Counting ---
class RefCountedFrame:
    """A thread-safe wrapper for a numpy frame buffer that manages reference counts."""
    def __init__(self, frame_buffer, release_callback):
        self.frame_buffer = frame_buffer
        self._release_callback = release_callback
        self._ref_count = 0
        self._lock = threading.Lock()

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


class FrameBufferPool:
    """Manages a pool of pre-allocated numpy arrays to avoid repeated memory allocation.

    Uses a water-mark based shrinking strategy to prevent unbounded memory growth:
    - Starts with initial_buffers (default: 5)
    - Can grow up to max_buffers (default: 10) during high load
    - Shrinks back to initial_buffers when pool size exceeds high_water_mark and is idle
    """
    def __init__(self, name="DefaultPool", max_buffers=10, initial_buffers=5, high_water_mark=8, shrink_idle_seconds=10.0):
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
        print(f"[{self._name}] Buffer pool initialized with {num_buffers} buffers (max: {self._max_buffers}).")

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
                        print(f"[{self._name}] Pool empty, allocating new buffer. Total allocated: {self._allocated}")
                        return np.empty(self._buffer_shape, dtype=self._buffer_dtype)
                    else:
                        # Max buffers reached - drop frame to prevent memory leak
                        print(f"[{self._name}] Max buffer limit ({self._max_buffers}) reached. Dropping frame.")
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
                print(f"[{self._name}] Shrunk pool by {removed} buffers. New size: {self._allocated}/{self._max_buffers}")
                self._last_allocation_time = None  # Reset allocation tracking


# --- Vision Processing Thread (Consumer) ---
class VisionProcessingThread(threading.Thread):
    """A consumer thread that runs a vision pipeline on frames from a queue."""
    def __init__(self, identifier, pipeline_id, pipeline_type, pipeline_config_json, camera_matrix_json, frame_queue):
        super().__init__()
        self.daemon = True
        self.identifier = identifier
        self.pipeline_id = pipeline_id
        self.pipeline_type = pipeline_type
        self.frame_queue = frame_queue
        self.stop_event = threading.Event()
        self.results_lock = threading.Lock()
        self.latest_results = {"status": "Starting..."}
        self.latest_processed_frame = None
        self.processed_frame_lock = threading.Lock()

        # Initialize the pipeline object
        self.pipeline_instance = None

        # Pre-calculation variables for drawing
        self.cam_matrix = None
        self.obj_pts = None

        # Load camera calibration data from primitive values
        if camera_matrix_json:
            try:
                self.cam_matrix = np.array(json.loads(camera_matrix_json))
                print(f"[{self.identifier}] Loaded camera matrix from DB.")
            except (json.JSONDecodeError, TypeError):
                print(f"[{self.identifier}] Failed to parse camera matrix from DB. Falling back to default.")
                self.cam_matrix = None

        pipeline_config = {}
        if pipeline_config_json:
            try:
                pipeline_config = json.loads(pipeline_config_json)
            except (json.JSONDecodeError, TypeError):
                print(f"[{self.identifier}] Failed to parse pipeline config from DB. Using default.")
        
        # Merge with default config to ensure all keys are present
        default_config = {
            'family': 'tag36h11', 
            'threads': 2,
            'decimate': 1.0,
            'blur': 0.0,
            'refine_edges': True,
            'tag_size_m': 0.165
        }
        # This ensures user settings override defaults, but defaults are there as a fallback
        final_config = {**default_config, **pipeline_config}

        if self.pipeline_type == 'AprilTag':
            self.pipeline_instance = AprilTagPipeline(final_config)
            # Pre-calculate the 3D coordinates of the tag corners
            tag_size_m = final_config.get('tag_size_m', 0.165)
            half_tag_size = tag_size_m / 2
            self.obj_pts = np.array([
                [-half_tag_size, -half_tag_size, 0], [half_tag_size, -half_tag_size, 0],
                [half_tag_size, half_tag_size, 0], [-half_tag_size, half_tag_size, 0],
                [-half_tag_size, -half_tag_size, -tag_size_m], [half_tag_size, -half_tag_size, -tag_size_m],
                [half_tag_size, half_tag_size, -tag_size_m], [-half_tag_size, half_tag_size, -tag_size_m]
            ])
        elif self.pipeline_type == 'Coloured Shape':
            self.pipeline_instance = ColouredShapePipeline(final_config)
        elif self.pipeline_type == 'Object Detection (ML)':
            self.pipeline_instance = ObjectDetectionMLPipeline(final_config)
        else:
            print(f"Warning: Unknown pipeline type '{self.pipeline_type}' for pipeline ID {self.pipeline_id}")

    def run(self):
        """The main loop for the vision processing thread."""
        if not self.pipeline_instance:
            print(f"Stopping processing thread for pipeline {self.pipeline_id} due to no valid pipeline object.")
            return

        print(f"Starting vision processing thread for pipeline {self.pipeline_id} ({self.pipeline_type}) on camera {self.identifier}")

        # If no calibration data was loaded from the DB, create a default matrix.
        if self.cam_matrix is None:
            print(f"[{self.identifier}] No calibration data found, using default camera matrix.")
            # IMPORTANT: These MUST be replaced with real values from camera calibration!
            camera_params = {
                'fx': 600.0, 'fy': 600.0, # Focal length in pixels
                'cx': 320.0, 'cy': 240.0   # Principal point (image center)
            }
            self.cam_matrix = np.array([
                [camera_params['fx'], 0, camera_params['cx']],
                [0, camera_params['fy'], camera_params['cy']],
                [0, 0, 1]
            ], dtype=np.float32)

        while not self.stop_event.is_set():
            ref_counted_frame = None
            try:
                ref_counted_frame = self.frame_queue.get(timeout=1)
                raw_frame = ref_counted_frame.data

                start_time = time.time()

                # Delegate processing to the pipeline object
                annotated_frame = raw_frame.copy() # Always make a copy to draw on
                detections = []
                current_results = {}

                if self.pipeline_type == 'AprilTag':
                    detections = self.pipeline_instance.process_frame(raw_frame, self.cam_matrix)
                    ui_detections = [d['ui_data'] for d in detections]
                    drawing_detections = [d['drawing_data'] for d in detections]
                    current_results = {"tags_found": len(ui_detections) > 0, "detections": ui_detections}
                    if drawing_detections:
                        self._draw_3d_box_on_frame(annotated_frame, drawing_detections)

                elif self.pipeline_type == 'Object Detection (ML)':
                    detections = self.pipeline_instance.process_frame(raw_frame, self.cam_matrix)
                    for det in detections:
                        box = det['box']
                        label = f"{det['label']}: {det['confidence']:.2f}"
                        cv2.rectangle(annotated_frame, (box[0], box[1]), (box[2], box[3]), (0, 255, 0), 2)
                        y = box[1] - 15 if box[1] - 15 > 15 else box[1] + 15
                        cv2.putText(annotated_frame, label, (box[0], y), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 2)
                    current_results = {"detections": detections}
                
                elif self.pipeline_type == 'Coloured Shape':
                    detections = self.pipeline_instance.process_frame(raw_frame, self.cam_matrix)
                    current_results = {"detections": detections}

                processing_time = (time.time() - start_time) * 1000
                current_results["processing_time_ms"] = f"{processing_time:.2f}"

                with self.results_lock:
                    self.latest_results = current_results

                # --- Generate Processed Frame ---
                ret, buffer = cv2.imencode('.jpg', annotated_frame)
                if ret:
                    with self.processed_frame_lock:
                        self.latest_processed_frame = buffer.tobytes()
            except queue.Empty:
                continue
            finally:
                if ref_counted_frame:
                    ref_counted_frame.release()

        print(f"Stopping vision processing thread for pipeline {self.pipeline_id} on camera {self.identifier}")

    def get_latest_results(self):
        """Safely retrieves the latest results from this pipeline."""
        with self.results_lock:
            return self.latest_results

    def _draw_3d_box_on_frame(self, frame, detections):
        """Draws a 3D bounding box around each detected AprilTag."""
        for det in detections:
            rvec, tvec = det['rvec'], det['tvec']
      
            # Project points assuming an undistorted (zero distortion) image
            img_pts, _ = cv2.projectPoints(self.obj_pts, rvec, tvec, self.cam_matrix, np.zeros((4, 1)))
            img_pts = np.int32(img_pts).reshape(-1, 2)

            # Draw the base
            cv2.drawContours(frame, [img_pts[:4]], -1, (0, 255, 0), 2)
            # Draw the pillars
            for i in range(4):
                cv2.line(frame, tuple(img_pts[i]), tuple(img_pts[i + 4]), (0, 255, 0), 2)
            # Draw the top
            cv2.drawContours(frame, [img_pts[4:]], -1, (0, 255, 0), 2)

            # Draw the tag ID
            corner = tuple(np.int32(det['corners'][0]))
            cv2.putText(frame, str(det['id']), corner, cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)

    def stop(self):
        """Signals the thread to stop."""
        self.stop_event.set()


class CameraAcquisitionThread(threading.Thread):
    """
    A producer thread that uses a driver to acquire frames and distributes them
    to multiple consumer queues. It handles camera connection, disconnection,
    and reconnection automatically.
    """
    def __init__(self, identifier, camera_type, orientation, app):
        super().__init__()
        self.daemon = True
        self.identifier = identifier
        self.camera_type = camera_type
        self.app = app
        self.driver = None
        self.frame_lock = threading.Lock()
        self.latest_frame_for_display = None
        self.raw_frame_lock = threading.Lock()
        self.latest_raw_frame = None
        self.processing_queues = {}
        self.queues_lock = threading.Lock()
        self.stop_event = threading.Event()
        self.fps = 0.0
        self.buffer_pool = FrameBufferPool(name=self.identifier)

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

    def update_orientation(self, new_orientation):
        """Updates the camera orientation and signals the acquisition thread."""
        with self._orientation_lock:
            if self._orientation != new_orientation:
                self._orientation = new_orientation
                self.config_update_event.set()
                print(f"[{self.identifier}] Orientation update signaled: {new_orientation}")

    def run(self):
        """The main loop for the camera acquisition thread."""
        print(f"Starting acquisition thread for {self.identifier}")

        while not self.stop_event.is_set():
            try:
                # Initialize the driver inside the loop for automatic reconnection
                # Pass camera data as a dict to avoid ORM session issues
                camera_data = {'camera_type': self.camera_type, 'identifier': self.identifier}
                self.driver = get_driver(camera_data)
                self.driver.connect()
                print(f"Camera {self.identifier} connected successfully via driver.")

                # The acquisition loop now uses the driver interface
                self._acquisition_loop()

            except Exception as e:
                print(f"Error with camera {self.identifier}: {e}. Retrying in 5 seconds...")
            finally:
                if self.driver:
                    self.driver.disconnect()
                # Wait before retrying connection, but only if we're not stopping.
                if not self.stop_event.is_set():
                    self.stop_event.wait(5.0)

        print(f"Acquisition thread for {self.identifier} has stopped.")

    def _acquisition_loop(self):
        """Inner loop that processes frames once a camera is connected."""
        # Get initial orientation from the thread-safe copy
        with self._orientation_lock:
            orientation = self._orientation

        # Initialize buffer pool with the first frame
        first_frame = self.driver.get_frame()
        if first_frame is None:
            print(f"[{self.identifier}] Failed to get first frame, cannot initialize buffer pool.")
            return # Exit to trigger reconnection

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
                    print(f"[{self.identifier}] Orientation changed to {new_orientation}. Re-initializing resources.")
                    orientation = new_orientation
                    # Re-initialize buffer pool if orientation changes frame size
                    test_frame = self._apply_orientation(first_frame.copy(), orientation)
                    self.buffer_pool.initialize(test_frame)

            raw_frame_from_cam = self.driver.get_frame()
            if raw_frame_from_cam is None:
                print(f"Lost frame from {self.identifier}, attempting to reconnect.")
                break # Exit inner loop to trigger reconnection

            # Apply orientation to the frame right after capture
            oriented_frame = self._apply_orientation(raw_frame_from_cam, orientation)

            with self.raw_frame_lock:
                self.latest_raw_frame = oriented_frame.copy()

            pooled_buffer = self.buffer_pool.get_buffer()
            if pooled_buffer is None:
                # Buffer pool exhausted - drain queues to prevent buildup and memory leaks
                print(f"[{self.identifier}] Buffer pool exhausted, draining queues to prevent memory buildup")
                self._drain_processing_queues()
                continue

            # Copy the oriented frame into the buffer for pipelines.
            np.copyto(pooled_buffer, oriented_frame)
            ref_counted_frame = RefCountedFrame(pooled_buffer, release_callback=self.buffer_pool.release_buffer)

            # Acquire initial reference for the acquisition thread to ensure buffer is released
            # even if all queues are full or display frame encoding fails
            ref_counted_frame.acquire()

            try:
                # Distribute frame to pipeline queues
                with self.queues_lock:
                    for q in self.processing_queues.values():
                        ref_counted_frame.acquire()
                        try:
                            q.put_nowait(ref_counted_frame)
                        except queue.Full:
                            ref_counted_frame.release()

                # Prepare display frame
                ref_counted_frame.acquire()
                try:
                    display_frame_copy = ref_counted_frame.get_writable_copy()
                    display_frame_with_overlay = self._prepare_display_frame(display_frame_copy)
                    ret, buffer = cv2.imencode('.jpg', display_frame_with_overlay)
                    if ret:
                        with self.frame_lock:
                            self.latest_frame_for_display = buffer.tobytes()
                finally:
                    ref_counted_frame.release()
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
                    print(f"[{self.identifier}] Drained {drained_count} old frames from queue")

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
        cv2.putText(frame, text, (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
        return frame

    def stop(self):
        """Signals the thread to stop."""
        self.stop_event.set()