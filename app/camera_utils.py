import cv2
from harvesters.core import Harvester
import os
from . import db
import threading
import time
import queue

try:
    from genicam import genapi
except ImportError:
    genapi = None

# --- GLOBALS & THREADING PRIMITIVES ---

# Global Harvester instance
h = Harvester()
harvester_lock = threading.Lock()

# Store active camera threads {identifier: {'acquisition': acq_thread, 'processing': proc_thread}}
active_camera_threads = {}
active_camera_threads_lock = threading.Lock()


# --- VISION PROCESSING THREAD (CONSUMER) ---
class VisionProcessingThread(threading.Thread):
    """
    A dedicated thread for running vision pipelines on raw frames from a queue.
    This is the 'Consumer' in the producer-consumer pattern.
    """
    def __init__(self, acquisition_thread):
        super().__init__()
        self.daemon = True
        self.acquisition_thread = acquisition_thread
        self.identifier = acquisition_thread.identifier
        self.stop_event = threading.Event()

        # Thread-safe storage for vision processing results
        self.results_lock = threading.Lock()
        self.latest_results = None

    def run(self):
        """The main loop for the vision processing thread."""
        print(f"Starting vision processing thread for {self.identifier}")
        while not self.stop_event.is_set():
            try:
                # Block and wait for a raw frame from the acquisition thread's queue.
                # A timeout allows the thread to periodically check the stop_event.
                raw_frame = self.acquisition_thread.raw_frame_queue.get(timeout=1)
            except queue.Empty:
                # This is expected if the acquisition thread is paused or slow.
                continue

            # --- <<< PLACEHOLDER FOR VISION PROCESSING >>> ---
            # This is where you would call your AprilTag, ML, or other CV functions.
            # The processing should be done on the 'raw_frame'.
            # Example:
            # results = self.vision_pipeline.process(raw_frame)
            # with self.results_lock:
            #     self.latest_results = results
            
            # For demonstration, we'll just simulate work.
            time.sleep(0.05) # Simulate a 50ms processing time

        print(f"Stopping vision processing thread for {self.identifier}")

    def stop(self):
        """Signals the thread to stop."""
        self.stop_event.set()


# --- UNIFIED CAMERA ACQUISITION THREAD (PRODUCER) ---

class CameraAcquisitionThread(threading.Thread):
    """
    A dedicated thread for continuous camera acquisition.
    It produces raw frames and puts them into a queue for the processing thread.
    This is the 'Producer' in the producer-consumer pattern.
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

        # This queue passes raw frames to the VisionProcessingThread.
        # maxsize=2 is a good practice: it holds the most recent frame and allows one
        # to be in-flight. If processing is slow, older frames are dropped automatically.
        self.raw_frame_queue = queue.Queue(maxsize=2)

        self.stop_event = threading.Event()
        self.fps = 0.0

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
                    if self.camera_type == 'GenICam':
                        try:
                            with ia.fetch_buffer(timeout=1.0) as buffer:
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
                        # Put raw frame in the queue for the vision thread (Producer)
                        try:
                            self.raw_frame_queue.put_nowait(raw_frame.copy())
                        except queue.Full:
                            # This is expected and desirable. It means vision processing is
                            # lagging, so we drop an old frame to prioritize recent data.
                            pass

                        # Prepare the frame for web display (can be done in parallel to vision)
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
    """Starts acquisition and processing threads for a single camera."""
    with active_camera_threads_lock:
        identifier = camera['identifier']
        if identifier not in active_camera_threads:
            print(f"Starting threads for camera {identifier}")
            acq_thread = CameraAcquisitionThread(camera, app)
            proc_thread = VisionProcessingThread(acq_thread)
            
            active_camera_threads[identifier] = {
                'acquisition': acq_thread,
                'processing': proc_thread
            }
            acq_thread.start()
            proc_thread.start()

def stop_camera_thread(identifier):
    """Stops the threads for a single camera."""
    with active_camera_threads_lock:
        if identifier in active_camera_threads:
            print(f"Stopping threads for camera {identifier}")
            thread_pair = active_camera_threads.pop(identifier)
            thread_pair['processing'].stop()
            thread_pair['acquisition'].stop()
            thread_pair['acquisition'].join(timeout=2)
            thread_pair['processing'].join(timeout=2)

def start_all_camera_threads(app):
    """To be called once at application startup to initialize all configured cameras."""
    print("Starting acquisition and processing threads for all configured cameras...")
    cameras = db.get_cameras()
    for camera in cameras:
        start_camera_thread(camera, app)

def stop_all_camera_threads():
    """To be called once at application shutdown to gracefully stop all threads."""
    print("Stopping all camera acquisition and processing threads...")
    with active_camera_threads_lock:
        identifiers_to_stop = list(active_camera_threads.keys())
    
    for identifier in identifiers_to_stop:
        stop_camera_thread(identifier)
    
    print("All camera threads stopped.")

def is_camera_thread_connected(identifier):
    """Checks if an acquisition thread is active and alive for a given identifier."""
    with active_camera_threads_lock:
        thread_pair = active_camera_threads.get(identifier)
        return thread_pair and thread_pair['acquisition'].is_alive()


# --- WEB STREAMING & CAMERA UTILITIES ---

def get_camera_feed(camera):
    """Generator that yields JPEG frames from a camera's running acquisition thread."""
    identifier = camera['identifier']
    
    if not is_camera_thread_connected(identifier):
        print(f"Warning: Attempted to get feed for {identifier}, but its thread is not running.")
        return

    with active_camera_threads_lock:
        thread_pair = active_camera_threads.get(identifier)
    
    if not thread_pair: return
    acq_thread = thread_pair['acquisition']

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

# The rest of your utility functions (list_usb_cameras, list_genicam_cameras, etc.)
# are well-structured and do not need changes for this refactor.
# They can be appended below this comment.

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
    if is_camera_thread_connected(identifier):
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
