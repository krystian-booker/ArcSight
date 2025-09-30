import cv2
from harvesters.core import Harvester
import os
from . import db
import threading
import time
import queue
import numpy as np
import json
import depthai as dai
from .pipelines.apriltag_pipeline import AprilTagPipeline

try:
    from genicam import genapi
except ImportError:
    genapi = None

# --- Globals & Threading Primitives ---
h = Harvester()
harvester_lock = threading.Lock()
active_camera_threads = {}
active_camera_threads_lock = threading.Lock()


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
        if self._buffer_shape is not None:
            return
        self._buffer_shape = frame.shape
        self._buffer_dtype = frame.dtype
        for _ in range(num_buffers):
            self._pool.put(np.empty(self._buffer_shape, dtype=self._buffer_dtype))
        self._allocated = num_buffers
        print(f"[{self._name}] Buffer pool initialized with {num_buffers} buffers of shape {self._buffer_shape}")

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
    def __init__(self, identifier, pipeline_info, camera_db_data, frame_queue):
        super().__init__()
        self.daemon = True
        self.identifier = identifier
        self.pipeline_id = pipeline_info['id']
        self.pipeline_type = pipeline_info['pipeline_type']
        self.frame_queue = frame_queue
        self.stop_event = threading.Event()
        self.results_lock = threading.Lock()
        self.latest_results = {"status": "Starting..."}
        self.latest_processed_frame = None
        self.processed_frame_lock = threading.Lock()

        # Store camera data and initialize the pipeline object
        self.camera_db_data = camera_db_data
        self.pipeline = None
        
        # Pre-calculation variables for drawing
        self.cam_matrix = None
        self.obj_pts = None

        # Load camera calibration data
        if self.camera_db_data.get('camera_matrix_json'):
            try:
                self.cam_matrix = np.array(json.loads(self.camera_db_data['camera_matrix_json']))
                print(f"[{self.identifier}] Loaded camera matrix from DB.")
            except (json.JSONDecodeError, TypeError):
                print(f"[{self.identifier}] Failed to parse camera matrix from DB. Falling back to default.")
                self.cam_matrix = None # Will be set in run()
        
        # This is where you would load pipeline-specific settings from the DB
        pipeline_config = {
            'family': 'tag36h11', 
            'threads': 2,
            'decimate': 1.0,
            'blur': 0.0,
            'refine_edges': True,
            'tag_size_m': 0.165
        }

        if self.pipeline_type == 'AprilTag':
            self.pipeline = AprilTagPipeline(pipeline_config)
            # Pre-calculate the 3D coordinates of the tag corners
            tag_size_m = pipeline_config.get('tag_size_m', 0.165)
            half_tag_size = tag_size_m / 2
            self.obj_pts = np.array([
                [-half_tag_size, -half_tag_size, 0], [half_tag_size, -half_tag_size, 0],
                [half_tag_size, half_tag_size, 0], [-half_tag_size, half_tag_size, 0],
                [-half_tag_size, -half_tag_size, -tag_size_m], [half_tag_size, -half_tag_size, -tag_size_m],
                [half_tag_size, half_tag_size, -tag_size_m], [-half_tag_size, half_tag_size, -tag_size_m]
            ])
        # elif self.pipeline_type == 'Coloured Shape':
        #     self.pipeline = ColouredShapePipeline(pipeline_config)
        else:
            print(f"Warning: Unknown pipeline type '{self.pipeline_type}' for pipeline ID {self.pipeline_id}")

    def run(self):
        """The main loop for the vision processing thread."""
        if not self.pipeline:
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
                detections = self.pipeline.process_frame(raw_frame, self.cam_matrix)

                processing_time = (time.time() - start_time) * 1000

                # Separate UI data from drawing data
                ui_detections = [d['ui_data'] for d in detections]
                drawing_detections = [d['drawing_data'] for d in detections]

                # Format results for the frontend/API
                current_results = {
                    "tags_found": len(ui_detections) > 0,
                    "detections": ui_detections,
                    "processing_time_ms": f"{processing_time:.2f}"
                }

                with self.results_lock:
                    self.latest_results = current_results

                # --- Generate Processed Frame ---
                annotated_frame = raw_frame.copy()

                if self.pipeline_type == 'AprilTag' and drawing_detections:
                    self._draw_3d_box_on_frame(annotated_frame, drawing_detections)
                
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


# --- Unified Camera Acquisition Thread (Producer) ---
class CameraAcquisitionThread(threading.Thread):
    """A producer thread that acquires frames and distributes them to multiple consumer queues."""
    def __init__(self, camera_db_data, app):
        super().__init__()
        self.daemon = True
        self.camera_db_data = camera_db_data
        self.identifier = camera_db_data['identifier']
        self.camera_type = camera_db_data['camera_type']
        self.app = app
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

    def _is_physically_connected(self):
        """Checks if the camera is physically connected to the system."""
        if self.camera_type == 'USB':
            try:
                cap = cv2.VideoCapture(int(self.identifier))
                is_open = cap.isOpened()
                cap.release()
                return is_open
            except Exception:
                return False
        elif self.camera_type == 'GenICam':
            return any(cam['identifier'] == self.identifier for cam in list_genicam_cameras())
        elif self.camera_type == 'OAK-D':
            return any(cam['identifier'] == self.identifier for cam in list_oakd_cameras())
        return False

    def run(self):
        """The main loop for the camera acquisition thread."""
        print(f"Starting {self.camera_type} acquisition thread for {self.identifier}")
        
        while not self.stop_event.is_set():
            try:
                # This outer try-catch handles connection errors and triggers the retry delay.
                if not self._is_physically_connected():
                    print(f"Camera {self.identifier} is not connected. Retrying in 5 seconds...")
                    self.stop_event.wait(5.0)
                    continue

                print(f"Initializing camera {self.identifier}...")

                # --- OAK-D Specific Logic ---
                if self.camera_type == 'OAK-D':
                    if dai is None:
                        raise ImportError("depthai library is not installed.")

                    pipeline = dai.Pipeline()

                    # Create and BUILD the unified Camera node on a socket
                    cam = pipeline.create(dai.node.Camera)
                    cam.build(boardSocket=dai.CameraBoardSocket.CAM_A)  # v3 way to choose sensor/socket

                    # Ask the camera for an output stream (replaces .preview/.isp + XLinkOut)
                    camera_out = cam.requestOutput(
                        size=(1280, 720),                          # pick what you want rendered
                        type=dai.ImgFrame.Type.BGR888p,            # convenient for cv2.imshow / getCvFrame()
                        fps=30                                     # optional; v3 can auto-pick if omitted
                    )

                    # Create a host-side queue straight from the output (no XLinkOut node)
                    q_rgb = camera_out.createOutputQueue(maxSize=4)

                    # Start the pipeline and read frames while it runs
                    pipeline.start()

                    # Enter the main loop using q_rgb
                    self._acquisition_loop(ia=None, cap=None, q_rgb=q_rgb)
                
                # --- GenICam & USB Logic (Remains largely the same) ---
                else:
                    ia, cap = None, None
                    try:
                        if self.camera_type == 'GenICam':
                            with harvester_lock:
                                ia = h.create({'serial_number': self.identifier})
                            ia.start()
                        elif self.camera_type == 'USB':
                            cap = cv2.VideoCapture(int(self.identifier))
                            if not cap.isOpened():
                                raise ConnectionError("Failed to open USB camera.")
                        
                        print(f"Camera {self.identifier} initialized successfully.")
                        self._acquisition_loop(ia=ia, cap=cap, q_rgb=None) # Enter the main loop

                    finally:
                        # This finally block now only cleans up GenICam/USB resources
                        print(f"Cleaning up resources for {self.identifier}.")
                        if ia:
                            try:
                                ia.destroy()
                            except Exception as e:
                                print(f"Error destroying IA: {e}")
                        if cap:
                            cap.release()

            except Exception as e:
                print(f"Major error in acquisition thread for {self.identifier}: {e}. Retrying...")
                # The loop will naturally wait 5 seconds on the next iteration if the camera 
                # is now considered "not connected" due to the error.
                # If it's a different error, we add a small delay to prevent rapid failing.
                if self._is_physically_connected():
                    self.stop_event.wait(5.0)
        
        print(f"Acquisition thread for {self.identifier} has stopped.")

    def _acquisition_loop(self, ia, cap, q_rgb):
        """This is the inner loop that processes frames once a camera is connected."""
        # The orientation value from DB must be an integer for comparisons.
        orientation = int(self.camera_db_data['orientation'])

        if self.buffer_pool._buffer_shape is None:
            first_frame = None
            deadline = time.time() + 5.0  # wait up to 5s for first frame
            while first_frame is None and time.time() < deadline:
                # Ask for a blocking frame only for the very first fetch on OAK-D
                first_frame = self._get_one_frame(ia, cap, q_rgb, blocking_first=True)
                if first_frame is None:
                    time.sleep(0.01)
            if first_frame is not None:
                # Apply orientation to the first frame to correctly size the buffer pool
                oriented_first_frame = self._apply_orientation(first_frame, orientation)
                self.buffer_pool.initialize(oriented_first_frame)
            else:
                raise ConnectionError("Timed out waiting for first OAK-D frame to size buffer pool.")
        
        start_time, frame_count, last_config_check = time.time(), 0, time.time()

        while not self.stop_event.is_set():
            if time.time() - last_config_check > 2.0:
                with self.app.app_context():
                    refreshed_data = db.get_camera(self.camera_db_data['id'])
                if refreshed_data:
                    orientation = int(refreshed_data['orientation'])
                last_config_check = time.time()

            raw_frame_from_cam = self._get_one_frame(ia, cap, q_rgb)
            if raw_frame_from_cam is None:
                # Queue had no frame this tick; try again
                time.sleep(0.002)
                continue

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

    def _get_one_frame(self, ia, cap, q_rgb=None, blocking_first=False):
        """Abstracts frame grabbing from either a GenICam, USB, or OAK-D camera."""
        if self.camera_type == 'GenICam' and ia:
            try:
                with ia.fetch(timeout=1.0) as buffer:
                    component = buffer.payload.components[0]
                    img = component.data.reshape(component.height, component.width)
                    if 'Bayer' in component.data_format:
                        return cv2.cvtColor(img, cv2.COLOR_BayerRG2BGR)
                    elif len(img.shape) == 2:
                        return cv2.cvtColor(img, cv2.COLOR_GRAY2BGR)
                    else:
                        return img
            except genapi.TimeoutException:
                return None
            except Exception as e:
                print(f"Error fetching GenICam frame for {self.identifier}: {e}")
                return None
        elif self.camera_type == 'USB' and cap:
            ret, frame = cap.read()
            return frame if ret and frame is not None else None
        elif self.camera_type == 'OAK-D' and q_rgb:
            # Always block until a frame arrives
            try:
                in_rgb = q_rgb.get()  # blocks until frame is available
            except Exception:
                return None
            return in_rgb.getCvFrame() if in_rgb is not None else None
        return None

    def _apply_orientation(self, frame, orientation):
        """Applies rotation to a frame based on the orientation value."""
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
        font_scale, font_thickness = 0.7, 2
        text_size, _ = cv2.getTextSize(text, cv2.FONT_HERSHEY_SIMPLEX, font_scale, font_thickness)
        text_x = frame.shape[1] - text_size[0] - 10
        text_y = text_size[1] + 10
        cv2.putText(frame, text, (text_x, text_y), cv2.FONT_HERSHEY_SIMPLEX, font_scale, (0, 255, 0), font_thickness)
        return frame

    def stop(self):
        """Signals the thread to stop."""
        self.stop_event.set()


# --- Centralized Thread Management ---
def start_camera_thread(camera, app):
    """Starts acquisition and processing threads for a single camera."""
    with active_camera_threads_lock:
        identifier = camera['identifier']
        if identifier not in active_camera_threads:
            print(f"Starting threads for camera {identifier}")
            
            acq_thread = CameraAcquisitionThread(camera, app)
            
            with app.app_context():
                pipelines = db.get_pipelines(camera['id'])
            
            processing_threads = {}
            for pipeline in pipelines:
                frame_queue = queue.Queue(maxsize=2)
                proc_thread = VisionProcessingThread(identifier, dict(pipeline), camera, frame_queue)
                
                acq_thread.add_pipeline_queue(pipeline['id'], frame_queue)
                processing_threads[pipeline['id']] = proc_thread
            
            active_camera_threads[identifier] = {
                'acquisition': acq_thread,
                'processing_threads': processing_threads
            }
            
            acq_thread.start()
            for proc_thread in processing_threads.values():
                proc_thread.start()


def stop_camera_thread(identifier):
    """Stops all threads for a single camera."""
    with active_camera_threads_lock:
        if identifier in active_camera_threads:
            print(f"Stopping threads for camera {identifier}")
            thread_group = active_camera_threads.pop(identifier)
            
            for proc_thread in thread_group['processing_threads'].values():
                proc_thread.stop()
            thread_group['acquisition'].stop()

            thread_group['acquisition'].join(timeout=2)
            for proc_thread in thread_group['processing_threads'].values():
                proc_thread.join(timeout=2)


def add_pipeline_to_camera(camera_id, pipeline_info, app):
    """Starts a new processing thread for a running camera."""
    with app.app_context():
        camera = db.get_camera(camera_id)
    if not camera:
        return

    identifier = camera['identifier']
    with active_camera_threads_lock:
        if identifier in active_camera_threads:
            thread_group = active_camera_threads[identifier]
            pipeline_id = pipeline_info['id']

            if pipeline_id not in thread_group['processing_threads']:
                print(f"Dynamically adding pipeline {pipeline_id} to camera {identifier}")
                frame_queue = queue.Queue(maxsize=2)
                proc_thread = VisionProcessingThread(identifier, pipeline_info, dict(camera), frame_queue)
                thread_group['acquisition'].add_pipeline_queue(pipeline_id, frame_queue)
                thread_group['processing_threads'][pipeline_id] = proc_thread
                proc_thread.start()


def remove_pipeline_from_camera(camera_id, pipeline_id, app):
    """Stops a specific processing thread for a running camera."""
    with app.app_context():
        camera = db.get_camera(camera_id)
    if not camera:
        return

    identifier = camera['identifier']
    with active_camera_threads_lock:
        if identifier in active_camera_threads:
            thread_group = active_camera_threads[identifier]
            if pipeline_id in thread_group['processing_threads']:
                print(f"Dynamically removing pipeline {pipeline_id} from camera {identifier}")
                proc_thread = thread_group['processing_threads'].pop(pipeline_id)
                
                proc_thread.stop()
                thread_group['acquisition'].remove_pipeline_queue(pipeline_id)
                proc_thread.join(timeout=2)


def start_all_camera_threads(app):
    """Initializes all configured cameras at application startup."""
    print("Starting acquisition and processing threads for all configured cameras...")
    with app.app_context():
        cameras = db.get_cameras()
    for camera in cameras:
        start_camera_thread(dict(camera), app)


def stop_all_camera_threads():
    """Gracefully stops all threads at application shutdown."""
    print("Stopping all camera acquisition and processing threads...")
    with active_camera_threads_lock:
        identifiers_to_stop = list(active_camera_threads.keys())
    
    for identifier in identifiers_to_stop:
        stop_camera_thread(identifier)
    
    print("All camera threads stopped.")


def get_camera_pipeline_results(identifier):
    """Gets the latest results from all pipelines for a given camera."""
    with active_camera_threads_lock:
        thread_group = active_camera_threads.get(identifier)
        if not thread_group:
            return None
        
        results = {}
        for pipeline_id, proc_thread in thread_group['processing_threads'].items():
            results[pipeline_id] = proc_thread.get_latest_results()
        
        return results


# --- Web Streaming & Camera Utilities ---
def get_camera_feed(camera):
    """A generator that yields JPEG frames from a camera's acquisition thread."""
    identifier = camera['identifier']
    
    with active_camera_threads_lock:
        thread_group = active_camera_threads.get(identifier)
    
    if not thread_group or not thread_group['acquisition'].is_alive():
        print(f"Warning: Attempted to get feed for {identifier}, but its thread is not running.")
        return

    acq_thread = thread_group['acquisition']

    try:
        while True:
            frame_to_send = None
            with acq_thread.frame_lock:
                if acq_thread.latest_frame_for_display:
                    frame_to_send = acq_thread.latest_frame_for_display

            if frame_to_send:
                yield (b'--frame\r\n'
                       b'Content-Type: image/jpeg\r\n\r\n' + frame_to_send + b'\r\n')
            
            if not acq_thread.is_alive():
                print(f"Stopping feed for {identifier} as acquisition thread has died.")
                break
            time.sleep(0.01) # A small sleep to prevent busy-waiting
    except GeneratorExit:
        print(f"Client disconnected from camera feed {identifier}.")
    except Exception as e:
        print(f"Error during streaming for feed {identifier}: {e}")


def get_processed_camera_feed(pipeline_id):
    """A generator that yields JPEG frames from a vision processing thread."""
    proc_thread = None
    with active_camera_threads_lock:
        for thread_group in active_camera_threads.values():
            if pipeline_id in thread_group['processing_threads']:
                proc_thread = thread_group['processing_threads'][pipeline_id]
                break

    if not proc_thread or not proc_thread.is_alive():
        print(f"Warning: Attempted to get processed feed for pipeline {pipeline_id}, but its thread is not running.")
        return

    try:
        while True:
            frame_to_send = None
            with proc_thread.processed_frame_lock:
                if proc_thread.latest_processed_frame:
                    frame_to_send = proc_thread.latest_processed_frame
            
            if frame_to_send:
                yield (b'--frame\r\n'
                       b'Content-Type: image/jpeg\r\n\r\n' + frame_to_send + b'\r\n')
            
            if not proc_thread.is_alive():
                print(f"Stopping processed feed for {pipeline_id} as its thread has died.")
                break
            time.sleep(0.01) # A small sleep to prevent busy-waiting
    except GeneratorExit:
        print(f"Client disconnected from processed feed {pipeline_id}.")
    except Exception as e:
        print(f"Error during streaming for processed feed {pipeline_id}: {e}")


def get_latest_raw_frame(identifier):
    """Gets the latest raw, unprocessed frame from a camera's acquisition thread."""
    with active_camera_threads_lock:
        thread_group = active_camera_threads.get(identifier)
    
    if not thread_group or not thread_group['acquisition'].is_alive():
        return None

    acq_thread = thread_group['acquisition']
    with acq_thread.raw_frame_lock:
        if acq_thread.latest_raw_frame is not None:
            return acq_thread.latest_raw_frame.copy()
    return None


if genapi:
    SUPPORTED_INTERFACE_TYPES = {
        genapi.EInterfaceType.intfIInteger: 'integer',
        genapi.EInterfaceType.intfIFloat: 'float',
        genapi.EInterfaceType.intfIString: 'string',
        genapi.EInterfaceType.intfIBoolean: 'boolean',
        genapi.EInterfaceType.intfIEnumeration: 'enumeration',
    }
    READABLE_ACCESS_MODES = {genapi.EAccessMode.RO, genapi.EAccessMode.RW}
    WRITABLE_ACCESS_MODES = {genapi.EAccessMode.WO, genapi.EAccessMode.RW}
else:
    SUPPORTED_INTERFACE_TYPES = {}
    READABLE_ACCESS_MODES = set()
    WRITABLE_ACCESS_MODES = set()


def initialize_harvester():
    """Initializes the Harvester with the CTI file specified in the settings."""
    with harvester_lock:
        cti_path = db.get_setting('genicam_cti_path')
        if cti_path and os.path.exists(cti_path):
            try:
                h.add_file(cti_path)
                h.update()
                print("Harvester initialized successfully.")
            except Exception as e:
                print(f"Error initializing Harvester: {e}")
        else:
            print("GenICam CTI file not found or not configured. Harvester not initialized.")


def reinitialize_harvester():
    """Resets and re-initializes the Harvester instance."""
    with harvester_lock:
        h.reset()
        print("Harvester instance cleaned up.")
        cti_path = db.get_setting('genicam_cti_path')
        if cti_path and os.path.exists(cti_path):
            try:
                h.add_file(cti_path)
                h.update()
                print("Harvester re-initialized with new CTI file.")
            except Exception as e:
                print(f"Error re-initializing Harvester: {e}")
        else:
            print("GenICam CTI file not found or not configured. Harvester remains empty.")


def list_usb_cameras():
    """Returns a list of available USB cameras."""
    usb_cameras = []
    for index in range(10):
        cap = cv2.VideoCapture(index)
        if cap.isOpened():
            usb_cameras.append({'identifier': str(index), 'name': f"USB Camera {index}"})
            cap.release()
    return usb_cameras


def list_oakd_cameras():
    """Returns a list of available OAK-D cameras."""
    if dai is None:
        return []
    
    oakd_cameras = []
    try:
        for device_info in dai.Device.getAllAvailableDevices():
            oakd_cameras.append({
                'identifier': device_info.getDeviceId(),
                'name': f"OAK-D {device_info.getDeviceId()}"
            })
    except Exception as e:
        print(f"Error listing OAK-D cameras: {e}")
    return oakd_cameras


def list_genicam_cameras():
    """Returns a list of available GenICam cameras."""
    genicam_cameras = []
    with harvester_lock:
        try:
            h.update()
            for device_info in h.device_info_list:
                genicam_cameras.append({
                    'identifier': device_info.serial_number,
                    'name': f"{device_info.model} ({device_info.serial_number})"
                })
        except Exception as e:
            print(f"Error listing GenICam cameras: {e}")
    return genicam_cameras


def check_camera_connection(camera):
    """Checks if a given camera is currently connected."""
    identifier = camera['identifier']
    with active_camera_threads_lock:
        thread_group = active_camera_threads.get(identifier)
    
    if thread_group and thread_group['acquisition'].is_alive():
        return True
    
    if camera['camera_type'] == 'USB':
        try:
            cap = cv2.VideoCapture(int(identifier))
            is_connected = cap.isOpened()
            cap.release()
            return is_connected
        except (ValueError, TypeError):
            return False
    elif camera['camera_type'] == 'GenICam':
        return any(cam['identifier'] == identifier for cam in list_genicam_cameras())
    elif camera['camera_type'] == 'OAK-D':
        return any(cam['identifier'] == identifier for cam in list_oakd_cameras())
        
    return False


def _create_image_acquirer(identifier):
    """Creates and returns an image acquirer for a GenICam device."""
    if not identifier:
        return None
    with harvester_lock:
        try:
            return h.create({'serial_number': identifier})
        except Exception as error:
            print(f"Error creating ImageAcquirer for {identifier}: {error}")
            return None


def get_genicam_node_map(identifier):
    """Retrieves the node map for a GenICam camera."""
    if genapi is None:
        return [], "GenICam runtime is not available on the server."
    ia = _create_image_acquirer(identifier)
    if not ia:
        return [], "Unable to establish a connection to the GenICam camera."
    try:
        node_map = ia.remote_device.node_map
        nodes = []
        for node_wrapper in node_map.nodes:
            try:
                interface_type = genapi.EInterfaceType(node_wrapper.node.principal_interface_type)
            except Exception:
                continue
            if interface_type not in SUPPORTED_INTERFACE_TYPES:
                continue
            try:
                access_value = node_wrapper.node.get_access_mode()
                access_mode = genapi.EAccessMode(access_value)
            except (ValueError, TypeError):
                access_mode = None

            is_readable = access_mode in READABLE_ACCESS_MODES if access_mode else False
            is_writable = access_mode in WRITABLE_ACCESS_MODES if access_mode else False
            node = node_wrapper.node
            display_name = str(getattr(node, 'display_name', '') or '')
            name = str(getattr(node, 'name', '') or '')
            description = str(getattr(node, 'tooltip', '') or getattr(node, 'description', '') or '')

            node_info = {
                'name': name, 'display_name': display_name or name,
                'description': description.strip(),
                'interface_type': SUPPORTED_INTERFACE_TYPES[interface_type],
                'access_mode': access_mode.name if access_mode else str(access_value),
                'is_readable': is_readable, 'is_writable': is_writable,
                'value': None, 'choices': []
            }

            if is_readable:
                try:
                    node_info['value'] = str(node_wrapper.to_string())
                except Exception as read_error:
                    print(f"Error reading node {name}: {read_error}")
            if interface_type == genapi.EInterfaceType.intfIEnumeration:
                try:
                    node_info['choices'] = [str(symbol) for symbol in node_wrapper.symbolics]
                except Exception as enum_error:
                    print(f"Error retrieving enumeration values for {name}: {enum_error}")
            nodes.append(node_info)
        nodes.sort(key=lambda item: item['display_name'].lower())
        return nodes, None
    except Exception as error:
        return [], f"Failed to retrieve node map: {error}"
    finally:
        if ia:
            ia.destroy()


def get_genicam_node(identifier, node_name):
    """Retrieves a single node from a GenICam camera."""
    if genapi is None:
        return None, "GenICam runtime is not available on the server."
    ia = _create_image_acquirer(identifier)
    if not ia:
        return None, "Unable to establish a connection to the GenICam camera."
    try:
        node_wrapper = ia.remote_device.node_map.get_node(node_name)
        if node_wrapper is None:
            return None, f"Node '{node_name}' not found."
        
        interface_type = genapi.EInterfaceType(node_wrapper.node.principal_interface_type)
        if interface_type not in SUPPORTED_INTERFACE_TYPES:
            return None, "Unsupported node type."
        
        access_mode = genapi.EAccessMode(node_wrapper.node.get_access_mode())
        node = node_wrapper.node
        node_info = {
            'name': node_name,
            'display_name': str(getattr(node, 'display_name', '') or ''),
            'description': str(getattr(node, 'tooltip', '') or getattr(node, 'description', '') or '').strip(),
            'interface_type': SUPPORTED_INTERFACE_TYPES[interface_type],
            'access_mode': access_mode.name,
            'is_readable': access_mode in READABLE_ACCESS_MODES,
            'is_writable': access_mode in WRITABLE_ACCESS_MODES,
            'value': None, 'choices': []
        }
        if node_info['is_readable']:
            try:
                node_info['value'] = str(node_wrapper.to_string())
            except Exception as e:
                print(f"Could not read value for node {node_name}: {e}")
        if interface_type == genapi.EInterfaceType.intfIEnumeration:
            node_info['choices'] = [str(symbol) for symbol in node_wrapper.symbolics]
        return node_info, None
    except Exception as error:
        return None, f"Failed to retrieve node: {error}"
    finally:
        if ia:
            ia.destroy()


def update_genicam_node(identifier, node_name, value):
    """Updates a node on a GenICam camera."""
    if genapi is None:
        return False, "GenICam runtime is not available. Please ensure the GenICam library is installed and accessible.", 500, None
    if not node_name:
        return False, "Node name is required.", 400, None
    ia = _create_image_acquirer(identifier)
    if not ia:
        return False, "Unable to connect to the GenICam camera.", 500, None
    try:
        node = ia.remote_device.node_map.get_node(node_name)
        if node is None:
            return False, f"Node '{node_name}' not found.", 404, None
        
        access_mode = genapi.EAccessMode(node.get_access_mode())
        if access_mode not in WRITABLE_ACCESS_MODES:
            return False, f"Node '{node_name}' is not writable.", 400, None
        if value is None:
            return False, "A value must be provided.", 400, None

        try:
            if isinstance(node, genapi.IInteger):
                node.set_value(int(value))
            elif isinstance(node, genapi.IFloat):
                node.set_value(float(value))
            elif isinstance(node, genapi.IBoolean):
                norm_val = str(value).strip().lower()
                if norm_val in ('true', '1', 'yes', 'on'):
                    node.set_value(True)
                elif norm_val in ('false', '0', 'no', 'off'):
                    node.set_value(False)
                else:
                    return False, f"'{value}' is not a valid boolean.", 400, None
            else:
                node.from_string(str(value))
        except Exception as set_error:
            return False, f"Failed to update node '{node_name}': {set_error}", 400, None

        ia.destroy()
        ia = None
        updated_node, error = get_genicam_node(identifier, node_name)
        if error:
            return False, f"Node updated, but failed to retrieve new state: {error}", 500, None
        return True, f"Node '{node_name}' updated successfully.", 200, updated_node
    except Exception as error:
        return False, f"Unexpected error while updating node: {error}", 500, None
    finally:
        if ia:
            ia.destroy()
