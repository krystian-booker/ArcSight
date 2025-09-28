import cv2
from harvesters.core import Harvester
import os
from . import db
import threading
import time
import queue
import uuid

try:
    from genicam import genapi
except ImportError:
    genapi = None

# --- GLOBALS & THREADING PRIMITIVES ---

# Global Harvester instance
h = Harvester()
harvester_lock = threading.Lock()

# Store active camera threads {identifier: {'acquisition': acq_thread, 'processing_threads': {pipeline_id: proc_thread}}}
active_camera_threads = {}
active_camera_threads_lock = threading.Lock()


# --- VISION PROCESSING THREAD (CONSUMER) ---
class VisionProcessingThread(threading.Thread):
    """
    A dedicated thread for running a specific vision pipeline on raw frames from a queue.
    This is a 'Consumer' in the producer-consumer pattern.
    """
    def __init__(self, identifier, pipeline_info, frame_queue):
        super().__init__()
        self.daemon = True
        self.identifier = identifier
        self.pipeline_id = pipeline_info['id']
        self.pipeline_type = pipeline_info['pipeline_type']
        self.frame_queue = frame_queue
        self.stop_event = threading.Event()

        # Thread-safe storage for vision processing results
        self.results_lock = threading.Lock()
        self.latest_results = {"status": "Starting..."}

    def run(self):
        """The main loop for the vision processing thread."""
        print(f"Starting vision processing thread for pipeline {self.pipeline_id} ({self.pipeline_type}) on camera {self.identifier}")
        while not self.stop_event.is_set():
            try:
                # Block and wait for a raw frame from the acquisition thread's queue.
                # A timeout allows the thread to periodically check the stop_event.
                raw_frame = self.frame_queue.get(timeout=1)
            except queue.Empty:
                continue

            # --- <<< VISION PROCESSING LOGIC GOES HERE >>> ---
            # This is where you would call your specific CV functions based on self.pipeline_type
            start_time = time.time()
            # Example placeholder logic
            if self.pipeline_type == 'AprilTag':
                # apriltag_results = apriltag_detector.process(raw_frame)
                time.sleep(0.05) # Simulate 50ms processing
                current_results = {"tags_found": 1, "id": 5}
            elif self.pipeline_type == 'Object Detection (ML)':
                # ml_results = ml_model.predict(raw_frame)
                time.sleep(0.1) # Simulate 100ms processing
                current_results = {"objects": [{"label": "note", "confidence": 0.92}]}
            else:
                # default_results = some_other_process(raw_frame)
                time.sleep(0.02) # Simulate 20ms processing
                current_results = {"status": "Processed"}

            processing_time = (time.time() - start_time) * 1000 # in ms
            current_results['processing_time_ms'] = f"{processing_time:.2f}"
            
            with self.results_lock:
                self.latest_results = current_results

        print(f"Stopping vision processing thread for pipeline {self.pipeline_id} on camera {self.identifier}")

    def get_latest_results(self):
        """Safely retrieve the latest results from this pipeline."""
        with self.results_lock:
            return self.latest_results

    def stop(self):
        """Signals the thread to stop."""
        self.stop_event.set()


# --- UNIFIED CAMERA ACQUISITION THREAD (PRODUCER) ---

class CameraAcquisitionThread(threading.Thread):
    """
    A dedicated thread for continuous camera acquisition.
    It produces raw frames and distributes them to multiple processing queues.
    This is the 'Producer' in a one-to-many producer-consumer pattern.
    """
    def __init__(self, camera_db_data, app):
        super().__init__()
        self.daemon = True
        self.camera_db_data = camera_db_data
        self.identifier = camera_db_data['identifier']
        self.camera_type = camera_db_data['camera_type']
        self.app = app
        self.frame_lock = threading.Lock()
        self.latest_frame_for_display = None

        # A dictionary to hold the queues for fanning-out frames to consumers
        # { pipeline_id: queue }
        self.processing_queues = {}
        self.queues_lock = threading.Lock()

        self.stop_event = threading.Event()
        self.fps = 0.0

    def add_pipeline_queue(self, pipeline_id, frame_queue):
        """Register a new queue for a vision pipeline."""
        with self.queues_lock:
            self.processing_queues[pipeline_id] = frame_queue

    def remove_pipeline_queue(self, pipeline_id):
        """Remove a queue for a vision pipeline."""
        with self.queues_lock:
            self.processing_queues.pop(pipeline_id, None)

    def _is_physically_connected(self):
        """Helper to check the physical connection."""
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
        return False

    def run(self):
        """The main resilient loop for the acquisition thread."""
        print(f"Starting {self.camera_type} acquisition thread for {self.identifier}")

        while not self.stop_event.is_set():
            ia = None
            cap = None
            try:
                if not self._is_physically_connected():
                    print(f"Camera {self.identifier} is not connected. Retrying in 5 seconds...")
                    self.stop_event.wait(5.0)
                    continue

                with self.app.app_context():
                    camera_data = db.get_camera(self.camera_db_data['id'])
                
                if camera_data:
                    orientation = int(camera_data['orientation'])
                else:
                    print(f"Camera {self.identifier} no longer in database. Stopping thread.")
                    break

                # --- Initialize Camera Resource ---
                print(f"Initializing camera {self.identifier}...")
                if self.camera_type == 'GenICam':
                    with harvester_lock:
                        ia = h.create({'serial_number': self.identifier})
                    ia.start()
                elif self.camera_type == 'USB':
                    cap = cv2.VideoCapture(int(self.identifier))
                    if not cap.isOpened():
                        print(f"Failed to open USB camera {self.identifier}. Will retry.")
                        self.stop_event.wait(5.0)
                        continue
                
                print(f"Camera {self.identifier} initialized successfully.")

                start_time = time.time()
                frame_count = 0

                while not self.stop_event.is_set():
                    raw_frame = None
                    # --- Frame Acquisition Logic ---
                    if self.camera_type == 'GenICam':
                        try:
                            with ia.fetch(timeout=1.0) as buffer:
                                component = buffer.payload.components[0]
                                img = component.data.reshape(component.height, component.width)
                                if 'Bayer' in component.data_format:
                                    raw_frame = cv2.cvtColor(img, cv2.COLOR_BayerRG2BGR)
                                elif len(img.shape) == 2:
                                    raw_frame = cv2.cvtColor(img, cv2.COLOR_GRAY2BGR)
                                else:
                                    raw_frame = img
                        except genapi.TimeoutException:
                            continue
                        except Exception as fetch_e:
                            print(f"Error fetching GenICam buffer for {self.identifier}: {fetch_e}. Reconnecting...")
                            break
                    elif self.camera_type == 'USB':
                        ret, frame = cap.read()
                        if not ret or frame is None:
                            print(f"Failed to read from USB camera {self.identifier}. Reconnecting...")
                            break
                        raw_frame = frame

                    if raw_frame is not None:
                        # --- Fan-out to all registered processing queues (Producer) ---
                        with self.queues_lock:
                            for q in self.processing_queues.values():
                                try:
                                    q.put_nowait(raw_frame.copy())
                                except queue.Full:
                                    pass # Expected, drop frame for slow consumers

                        # Prepare the frame for web display
                        display_frame = self._prepare_display_frame(raw_frame, orientation)

                        # Encode and store the final JPEG for streaming
                        ret, buffer = cv2.imencode('.jpg', display_frame)
                        if ret:
                            with self.frame_lock:
                                self.latest_frame_for_display = buffer.tobytes()
                        
                        # --- FPS Calculation ---
                        frame_count += 1
                        elapsed_time = time.time() - start_time
                        if elapsed_time >= 1.0:
                            self.fps = frame_count / elapsed_time
                            frame_count = 0
                            start_time = time.time()

            except Exception as e:
                print(f"Major error in acquisition loop for {self.identifier}: {e}. Retrying...")
                self.stop_event.wait(5.0)
            finally:
                print(f"Cleaning up resources for {self.identifier}.")
                if ia:
                    try: ia.destroy()
                    except Exception as e: print(f"Error destroying IA for {self.identifier}: {e}")
                if cap:
                    cap.release()
        
        print(f"Acquisition thread for {self.identifier} has stopped.")

    def _prepare_display_frame(self, frame, orientation):
        """Applies orientation and FPS overlay to a frame."""
        if orientation == 90:
            frame = cv2.rotate(frame, cv2.ROTATE_90_CLOCKWISE)
        elif orientation == 180:
            frame = cv2.rotate(frame, cv2.ROTATE_180)
        elif orientation == 270:
            frame = cv2.rotate(frame, cv2.ROTATE_90_COUNTERCLOCKWISE)

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


# --- CENTRALIZED THREAD MANAGEMENT ---

def start_camera_thread(camera, app):
    """Starts acquisition and all associated processing threads for a single camera."""
    with active_camera_threads_lock:
        identifier = camera['identifier']
        if identifier not in active_camera_threads:
            print(f"Starting threads for camera {identifier}")
            
            # 1. Create the single acquisition thread
            acq_thread = CameraAcquisitionThread(camera, app)
            
            # 2. Find all pipelines for this camera and create a processing thread for each
            with app.app_context():
                pipelines = db.get_pipelines(camera['id'])
            
            processing_threads = {}
            for pipeline in pipelines:
                # Create a queue for this specific pipeline
                frame_queue = queue.Queue(maxsize=2)
                proc_thread = VisionProcessingThread(identifier, dict(pipeline), frame_queue)
                
                # Register the queue with the acquisition thread
                acq_thread.add_pipeline_queue(pipeline['id'], frame_queue)
                processing_threads[pipeline['id']] = proc_thread
            
            active_camera_threads[identifier] = {
                'acquisition': acq_thread,
                'processing_threads': processing_threads
            }
            
            # 3. Start all threads
            acq_thread.start()
            for proc_thread in processing_threads.values():
                proc_thread.start()

def stop_camera_thread(identifier):
    """Stops all threads for a single camera."""
    with active_camera_threads_lock:
        if identifier in active_camera_threads:
            print(f"Stopping threads for camera {identifier}")
            thread_group = active_camera_threads.pop(identifier)
            
            # Stop all processing threads first
            for proc_thread in thread_group['processing_threads'].values():
                proc_thread.stop()

            # Stop the acquisition thread
            thread_group['acquisition'].stop()

            # Wait for them to terminate
            thread_group['acquisition'].join(timeout=2)
            for proc_thread in thread_group['processing_threads'].values():
                proc_thread.join(timeout=2)

def start_all_camera_threads(app):
    """To be called once at application startup to initialize all configured cameras."""
    print("Starting acquisition and processing threads for all configured cameras...")
    with app.app_context():
        cameras = db.get_cameras()
    for camera in cameras:
        start_camera_thread(dict(camera), app)

def stop_all_camera_threads():
    """To be called once at application shutdown to gracefully stop all threads."""
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

# --- WEB STREAMING & CAMERA UTILITIES ---

def get_camera_feed(camera):
    """Generator that yields JPEG frames from a camera's running acquisition thread."""
    identifier = camera['identifier']
    
    with active_camera_threads_lock:
        thread_group = active_camera_threads.get(identifier)
    
    if not thread_group or not thread_group['acquisition'].is_alive():
        print(f"Warning: Attempted to get feed for {identifier}, but its thread is not running.")
        return

    acq_thread = thread_group['acquisition']

    try:
        while True:
            time.sleep(0.02)  # Control the streaming rate to avoid overwhelming the client

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
    except GeneratorExit:
        print(f"Client disconnected from camera feed {identifier}.")
    except Exception as e:
        print(f"Error during streaming for feed {identifier}: {e}")

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
    usb_cameras = []
    for index in range(10):
        cap = cv2.VideoCapture(index)
        if cap.isOpened():
            usb_cameras.append({'identifier': str(index), 'name': f"USB Camera {index}"})
            cap.release()
    return usb_cameras

def list_genicam_cameras():
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
    """
    Checks if a given camera is currently connected.
    The primary check is the liveness of its dedicated acquisition thread.
    """
    identifier = camera['identifier']
    with active_camera_threads_lock:
        thread_group = active_camera_threads.get(identifier)
    
    if thread_group and thread_group['acquisition'].is_alive():
        return True
    
    # Fallback to a physical check if no thread is running
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
        
    return False

def _create_image_acquirer(identifier):
    if not identifier:
        return None
    with harvester_lock:
        try:
            return h.create({'serial_number': identifier})
        except Exception as error:
            print(f"Error creating ImageAcquirer for {identifier}: {error}")
            return None

def get_genicam_node_map(identifier):
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
        if ia: ia.destroy()

def get_genicam_node(identifier, node_name):
    if genapi is None: return None, "GenICam runtime is not available on the server."
    ia = _create_image_acquirer(identifier)
    if not ia: return None, "Unable to establish a connection to the GenICam camera."
    try:
        node_wrapper = ia.remote_device.node_map.get_node(node_name)
        if node_wrapper is None: return None, f"Node '{node_name}' not found."
        
        interface_type = genapi.EInterfaceType(node_wrapper.node.principal_interface_type)
        if interface_type not in SUPPORTED_INTERFACE_TYPES: return None, "Unsupported node type."
        
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
        if ia: ia.destroy()

def update_genicam_node(identifier, node_name, value):
    if genapi is None: return False, "GenICam runtime is not available...", 500, None
    if not node_name: return False, "Node name is required.", 400, None
    ia = _create_image_acquirer(identifier)
    if not ia: return False, "Unable to connect to the GenICam camera.", 500, None
    try:
        node = ia.remote_device.node_map.get_node(node_name)
        if node is None: return False, f"Node '{node_name}' not found.", 404, None
        
        access_mode = genapi.EAccessMode(node.get_access_mode())
        if access_mode not in WRITABLE_ACCESS_MODES: return False, f"Node '{node_name}' is not writable.", 400, None
        if value is None: return False, "A value must be provided.", 400, None

        try:
            if isinstance(node, genapi.IInteger): node.set_value(int(value))
            elif isinstance(node, genapi.IFloat): node.set_value(float(value))
            elif isinstance(node, genapi.IBoolean):
                norm_val = str(value).strip().lower()
                if norm_val in ('true', '1', 'yes', 'on'): node.set_value(True)
                elif norm_val in ('false', '0', 'no', 'off'): node.set_value(False)
                else: return False, f"'{value}' is not a valid boolean.", 400, None
            else: node.from_string(str(value))
        except Exception as set_error:
            return False, f"Failed to update node '{node_name}': {set_error}", 400, None

        ia.destroy()
        ia = None # Prevent double destroy
        updated_node, error = get_genicam_node(identifier, node_name)
        if error: return False, f"Node updated, but failed to retrieve new state: {error}", 500, None
        return True, f"Node '{node_name}' updated successfully.", 200, updated_node
    except Exception as error:
        return False, f"Unexpected error while updating node: {error}", 500, None
    finally:
        if ia: ia.destroy()
