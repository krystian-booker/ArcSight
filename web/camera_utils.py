import cv2
from harvesters.core import Harvester
import os
import db
import threading
import time

try:
    from genicam import genapi
except ImportError:
    genapi = None

# Global Harvester instance
h = Harvester()

# A lock to ensure thread-safe access to the harvester
harvester_lock = threading.Lock()

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
else:  # pragma: no cover - allows graceful degradation when GenICam is unavailable
    SUPPORTED_INTERFACE_TYPES = {}
    READABLE_ACCESS_MODES = set()
    WRITABLE_ACCESS_MODES = set()

def initialize_harvester():
    """
    Initializes the global Harvester instance with the CTI file from the database.
    This should be called once at application startup.
    """
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

def list_usb_cameras():
    """
    Lists available USB cameras by trying to open them.
    """
    usb_cameras = []
    for index in range(10):
        cap = cv2.VideoCapture(index)
        if cap.isOpened():
            usb_cameras.append({
                'identifier': str(index),
                'name': f"USB Camera {index}"
            })
            cap.release()
    return usb_cameras

def list_genicam_cameras():
    """
    Lists available GenICam cameras using the global Harvester instance.
    """
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
    """
    if camera['camera_type'] == 'USB':
        try:
            index = int(camera['identifier'])
            cap = cv2.VideoCapture(index)
            is_connected = cap.isOpened()
            cap.release()
            return is_connected
        except (ValueError, TypeError):
            return False
    
    elif camera['camera_type'] == 'GenICam':
        connected_genicams = list_genicam_cameras()
        return any(cam['identifier'] == camera['identifier'] for cam in connected_genicams)
        
    return False

def get_camera_feed(camera):
    """
    Generator function that yields JPEG frames from a camera with FPS overlay.
    """
    if camera['camera_type'] == 'USB':
        cap = cv2.VideoCapture(int(camera['identifier']))
        if not cap.isOpened():
            print(f"Could not open USB camera {camera['identifier']}")
            return
        
        try:
            start_time = time.time()
            frame_count = 0
            fps = 0
            while True:
                ret, frame = cap.read()
                if not ret:
                    print(f"Stopping feed for USB camera {camera['identifier']} as it appears to be disconnected.")
                    break

                # Calculate FPS
                frame_count += 1
                elapsed_time = time.time() - start_time
                if elapsed_time >= 1.0:
                    fps = frame_count / elapsed_time
                    frame_count = 0
                    start_time = time.time()

                # Draw FPS on the frame in the top-right corner
                text = f"FPS: {fps:.2f}"
                font_scale = 0.7
                font_thickness = 2
                text_size, _ = cv2.getTextSize(text, cv2.FONT_HERSHEY_SIMPLEX, font_scale, font_thickness)
                text_x = frame.shape[1] - text_size[0] - 10
                text_y = text_size[1] + 10
                cv2.putText(frame, text, (text_x, text_y), cv2.FONT_HERSHEY_SIMPLEX, font_scale, (0, 255, 0), font_thickness)
                
                ret, buffer = cv2.imencode('.jpg', frame)
                if ret:
                    yield (b'--frame\r\n'
                           b'Content-Type: image/jpeg\r\n\r\n' + buffer.tobytes() + b'\r\n')
        finally:
            print(f"Releasing USB camera {camera['identifier']}")
            cap.release()

    elif camera['camera_type'] == 'GenICam':
        try:
            with harvester_lock:
                ia = h.create({'serial_number': camera['identifier']})
            
            if not ia:
                print(f"Failed to create image acquirer for {camera['identifier']}")
                return

            with ia:
                ia.start_acquisition()
                start_time = time.time()
                frame_count = 0
                fps = 0
                while True:
                    try:
                        with ia.fetch_buffer() as buffer:
                            component = buffer.payload.components[0]
                            img = component.data.reshape(component.height, component.width)
                            
                            # Convert to BGR for color text overlay
                            if 'Bayer' in component.data_format:
                                img = cv2.cvtColor(img, cv2.COLOR_BayerRG2BGR)
                            elif len(img.shape) == 2:
                                img = cv2.cvtColor(img, cv2.COLOR_GRAY2BGR)

                            # Calculate FPS
                            frame_count += 1
                            elapsed_time = time.time() - start_time
                            if elapsed_time >= 1.0:
                                fps = frame_count / elapsed_time
                                frame_count = 0
                                start_time = time.time()
                            
                            # Draw FPS on the frame in the top-right corner
                            text = f"FPS: {fps:.2f}"
                            font_scale = 0.7
                            font_thickness = 2
                            text_size, _ = cv2.getTextSize(text, cv2.FONT_HERSHEY_SIMPLEX, font_scale, font_thickness)
                            text_x = img.shape[1] - text_size[0] - 10
                            text_y = text_size[1] + 10
                            cv2.putText(img, text, (text_x, text_y), cv2.FONT_HERSHEY_SIMPLEX, font_scale, (0, 255, 0), font_thickness)

                            ret, jpeg = cv2.imencode('.jpg', img)
                            if ret:
                                yield (b'--frame\r\n'
                                       b'Content-Type: image/jpeg\r\n\r\n' + jpeg.tobytes() + b'\r\n')
                    except Exception as fetch_e:
                        print(f"Error fetching buffer for GenICam {camera['identifier']}: {fetch_e}")
                        break
        except Exception as e:
            print(f"Error with GenICam feed for {camera['identifier']}: {e}")


def _create_image_acquirer(identifier):
    """Create an ImageAcquirer for a GenICam camera identifier."""
    if not identifier:
        return None

    with harvester_lock:
        try:
            ia = h.create({'serial_number': identifier})
            return ia
        except Exception as error:
            print(f"Error creating ImageAcquirer for {identifier}: {error}")
            return None


def get_genicam_node_map(identifier):
    """Retrieve the GenICam node map for a camera."""
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

            access_value = node_wrapper.get_access_mode()
            try:
                access_mode = genapi.EAccessMode(access_value)
            except ValueError:
                access_mode = None

            is_readable = access_mode in READABLE_ACCESS_MODES if access_mode else False
            is_writable = access_mode in WRITABLE_ACCESS_MODES if access_mode else False

            node = node_wrapper.node
            display_name = str(getattr(node, 'display_name', '') or '')
            name = str(getattr(node, 'name', '') or '')
            description = str(getattr(node, 'tooltip', '') or getattr(node, 'description', '') or '')

            node_info = {
                'name': name,
                'display_name': display_name or name,
                'description': description.strip(),
                'interface_type': SUPPORTED_INTERFACE_TYPES[interface_type],
                'access_mode': access_mode.name if access_mode else str(access_value),
                'is_readable': is_readable,
                'is_writable': is_writable,
                'value': None,
                'choices': []
            }

            if is_readable:
                try:
                    node_info['value'] = str(node_wrapper.to_string())
                except Exception as read_error:
                    print(f"Error reading node {name}: {read_error}")
                    node_info['value'] = None

            if interface_type == genapi.EInterfaceType.intfIEnumeration:
                try:
                    node_info['choices'] = [str(symbol) for symbol in node_wrapper.symbolics]
                except Exception as enum_error:
                    print(f"Error retrieving enumeration values for {name}: {enum_error}")

            nodes.append(node_info)

        nodes.sort(key=lambda item: item['display_name'].lower())
        return nodes, None
    except Exception as error:
        print(f"Error retrieving node map for {identifier}: {error}")
        return [], f"Failed to retrieve node map: {error}"
    finally:
        try:
            ia.destroy()
        except Exception as destroy_error:
            print(f"Error releasing ImageAcquirer for {identifier}: {destroy_error}")


def update_genicam_node(identifier, node_name, value):
    """Update a GenICam node with a new value."""
    if genapi is None:
        return False, "GenICam runtime is not available on the server.", 500

    if not node_name:
        return False, "Node name is required.", 400

    ia = _create_image_acquirer(identifier)
    if not ia:
        return False, "Unable to establish a connection to the GenICam camera.", 500

    try:
        node_map = ia.remote_device.node_map
        node = node_map.get_node(node_name)
        if node is None:
            return False, f"Node '{node_name}' was not found on the camera.", 404

        try:
            access_mode = genapi.EAccessMode(node.get_access_mode())
        except ValueError:
            access_mode = None

        if not access_mode or access_mode not in WRITABLE_ACCESS_MODES:
            return False, f"Node '{node_name}' is not writable.", 400

        if value is None:
            return False, "A value must be provided.", 400

        try:
            if isinstance(node, genapi.IInteger):
                node.set_value(int(value))
            elif isinstance(node, genapi.IFloat):
                node.set_value(float(value))
            elif isinstance(node, genapi.IBoolean):
                normalized = str(value).strip().lower()
                if normalized in ('true', '1', 'yes', 'on'):
                    node.set_value(True)
                elif normalized in ('false', '0', 'no', 'off'):
                    node.set_value(False)
                else:
                    return False, f"'{value}' is not a valid boolean value.", 400
            elif isinstance(node, genapi.IEnumeration):
                try:
                    node.set_value(str(value))
                except Exception:
                    node.from_string(str(value))
            elif isinstance(node, genapi.IString):
                node.set_value(str(value))
            else:
                node.from_string(str(value))
        except Exception as set_error:
            return False, f"Failed to update node '{node_name}': {set_error}", 400

        return True, f"Node '{node_name}' updated successfully.", 200
    except Exception as error:
        print(f"Error updating node {node_name} for {identifier}: {error}")
        return False, f"Unexpected error while updating node: {error}", 500
    finally:
        try:
            ia.destroy()
        except Exception as destroy_error:
            print(f"Error releasing ImageAcquirer for {identifier} after update: {destroy_error}")