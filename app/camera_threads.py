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
    """Manages a pool of pre-allocated numpy arrays to avoid repeated memory allocation."""
    def __init__(self, name="DefaultPool"):
        self._pool = queue.Queue()
        self._buffer_shape = None
        self._buffer_dtype = None
        self._allocated = 0
        self._name = name

    def initialize(self, frame, num_buffers=5):
        """Initializes the pool with buffers matching the shape and type of a sample frame."""
        
        # Already initialized with correct shape
        if self._buffer_shape is not None and self._buffer_shape == frame.shape:
            return
        
        # If shape is different, we need to re-initialize.
        print(f"[{self._name}] Initializing buffer pool for shape {frame.shape}...")
        self._pool = queue.Queue()
        self._buffer_shape = frame.shape
        self._buffer_dtype = frame.dtype
        for _ in range(num_buffers):
            self._pool.put(np.empty(self._buffer_shape, dtype=self._buffer_dtype))
        self._allocated = num_buffers
        print(f"[{self._name}] Buffer pool initialized with {num_buffers} buffers.")

    def get_buffer(self):
        """Retrieves a buffer from the pool, allocating a new one if the pool is empty."""
        try:
            return self._pool.get_nowait()
        except queue.Empty:
            if self._buffer_shape is not None:
                print(f"[{self._name}] Pool empty, allocating new buffer. Total allocated: {self._allocated + 1}")
                self._allocated += 1
                return np.empty(self._buffer_shape, dtype=self._buffer_dtype)
            return None

    def release_buffer(self, buffer):
        """Returns a buffer to the pool for reuse."""
        self._pool.put(buffer)


# --- Vision Processing Thread (Consumer) ---
class VisionProcessingThread(threading.Thread):
    """A consumer thread that runs a vision pipeline on frames from a queue."""
    def __init__(self, identifier, pipeline, camera, frame_queue):
        super().__init__()
        self.daemon = True
        self.identifier = identifier
        self.pipeline_id = pipeline.id
        self.pipeline_type = pipeline.pipeline_type
        self.frame_queue = frame_queue
        self.stop_event = threading.Event()
        self.results_lock = threading.Lock()
        self.latest_results = {"status": "Starting..."}
        self.latest_processed_frame = None
        self.processed_frame_lock = threading.Lock()

        # Store camera data and initialize the pipeline object
        self.camera = camera
        self.pipeline_instance = None
   
        # Pre-calculation variables for drawing
        self.cam_matrix = None
        self.obj_pts = None

        # Load camera calibration data
        if self.camera.camera_matrix_json:
            try:
                self.cam_matrix = np.array(json.loads(self.camera.camera_matrix_json))
                print(f"[{self.identifier}] Loaded camera matrix from DB.")
            except (json.JSONDecodeError, TypeError):
                print(f"[{self.identifier}] Failed to parse camera matrix from DB. Falling back to default.")
                self.cam_matrix = None
        
        pipeline_config = {}
        if pipeline.config:
            try:
                pipeline_config = json.loads(pipeline.config)
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
    def __init__(self, camera, app):
        super().__init__()
        self.daemon = True
        self.camera = camera
        self.identifier = camera.identifier
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

    def add_pipeline_queue(self, pipeline_id, frame_queue):
        """Adds a pipeline's frame queue to the list of queues to receive frames."""
        with self.queues_lock:
            self.processing_queues[pipeline_id] = frame_queue

    def remove_pipeline_queue(self, pipeline_id):
        """Removes a pipeline's frame queue from the list of queues."""
        with self.queues_lock:
            self.processing_queues.pop(pipeline_id, None)

    def run(self):
        """The main loop for the camera acquisition thread."""
        print(f"Starting acquisition thread for {self.identifier}")
        
        while not self.stop_event.is_set():
            try:
                # Initialize the driver inside the loop for automatic reconnection
                self.driver = get_driver(self.camera)
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
        orientation = self.camera.orientation
        last_config_check = time.time()

        # Initialize buffer pool with the first frame
        first_frame = self.driver.get_frame()
        if first_frame is None:
            print(f"[{self.identifier}] Failed to get first frame, cannot initialize buffer pool.")
            return # Exit to trigger reconnection

        oriented_first_frame = self._apply_orientation(first_frame, orientation)
        self.buffer_pool.initialize(oriented_first_frame)

        start_time, frame_count = time.time(), 0

        while not self.stop_event.is_set():
            # Periodically check for orientation changes in the DB
            if time.time() - last_config_check > 2.0:
                with self.app.app_context():
                    # Create a new session for thread-safe database access
                    # Using sessionmaker to create an independent session
                    from sqlalchemy.orm import sessionmaker
                    Session = sessionmaker(bind=db.engine)
                    session = Session()
                    try:
                        refreshed_data = session.get(Camera, self.camera.id)
                        if refreshed_data:
                            new_orientation = refreshed_data.orientation
                            if new_orientation != orientation:
                                print(f"[{self.identifier}] Orientation changed to {new_orientation}. Re-initializing resources.")
                                orientation = new_orientation
                                # Re-initialize buffer pool if orientation changes frame size
                                test_frame = self._apply_orientation(first_frame.copy(), orientation)
                                self.buffer_pool.initialize(test_frame)
                    finally:
                        session.close()
                last_config_check = time.time()

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
                continue

            # Copy the oriented frame into the buffer for pipelines.
            np.copyto(pooled_buffer, oriented_frame)
            ref_counted_frame = RefCountedFrame(pooled_buffer, release_callback=self.buffer_pool.release_buffer)
            
            with self.queues_lock:
                for q in self.processing_queues.values():
                    ref_counted_frame.acquire()
                    try:
                        q.put_nowait(ref_counted_frame)
                    except queue.Full:
                        ref_counted_frame.release()

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
            
            frame_count += 1
            elapsed_time = time.time() - start_time
            if elapsed_time >= 1.0:
                self.fps = frame_count / elapsed_time
                frame_count = 0
                start_time = time.time()

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