import cv2
from harvesters.core import Harvester
from genicam import genapi
import os
import db
import threading
import time

# Global Harvester instance
h = Harvester()

# A lock to ensure thread-safe access to the harvester
harvester_lock = threading.Lock()

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


def _safe_get_attribute(obj, attr_name, default=None):
    """Safely retrieve an attribute or property from a GenICam node."""
    try:
        value = getattr(obj, attr_name)
        if callable(value):
            try:
                return value()
            except TypeError:
                # Some attributes are methods that require parameters; ignore those
                return default
        return value
    except Exception:
        return default


def _normalize_node_value(value):
    if isinstance(value, (bool, int, float, str)) or value is None:
        return value
    if isinstance(value, (list, tuple)):
        return [_normalize_node_value(item) for item in value]
    try:
        return float(value)
    except Exception:
        try:
            return str(value)
        except Exception:
            return None


def _extract_node_metadata(node, interface_type):
    metadata = {}
    if interface_type in (genapi.EInterfaceType.intfIInteger, genapi.EInterfaceType.intfIFloat):
        for key in ('min', 'max', 'inc', 'unit'):
            value = _safe_get_attribute(node, key)
            if value is not None:
                normalized = _normalize_node_value(value)
                if normalized is not None:
                    metadata[key] = normalized
    return metadata


def _read_node_value(node, interface_type):
    try:
        if interface_type == genapi.EInterfaceType.intfIInteger:
            return _normalize_node_value(node.value)
        if interface_type == genapi.EInterfaceType.intfIFloat:
            return _normalize_node_value(node.value)
        if interface_type == genapi.EInterfaceType.intfIBoolean:
            return bool(node.value)
        if interface_type == genapi.EInterfaceType.intfIString:
            return _normalize_node_value(node.value)
        if interface_type == genapi.EInterfaceType.intfIEnumeration:
            return _normalize_node_value(node.value)
    except Exception:
        return None
    return None


def _node_choices(node, interface_type):
    if interface_type == genapi.EInterfaceType.intfIEnumeration:
        try:
            return list(node.symbolics)
        except Exception:
            return []
    if interface_type == genapi.EInterfaceType.intfIBoolean:
        return ['True', 'False']
    return []


def _interface_name(interface_type):
    if interface_type is None:
        return "Unknown"
    try:
        return str(interface_type).split('.')[-1]
    except Exception:
        return "Unknown"

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


def get_genicam_node_map(identifier):
    """
    Retrieve the node map for a GenICam camera.

    Returns a dictionary with either a "nodes" key that contains a list of
    node information or an "error" key describing why the node map could not
    be fetched.
    """
    with harvester_lock:
        if not h.files:
            return {'error': 'No GenTL producers have been loaded.'}

        try:
            ia = h.create({'serial_number': identifier})
        except Exception as create_err:
            return {'error': f'Unable to connect to camera: {create_err}'}

        if not ia:
            return {'error': 'Failed to create an image acquirer for the camera.'}

        with ia:
            node_map = ia.remote_device.node_map
            try:
                raw_nodes = node_map._get_nodes()
            except Exception as node_err:
                return {'error': f'Unable to read node map: {node_err}'}

            nodes = []
            if not raw_nodes:
                return {'nodes': nodes}

            if hasattr(raw_nodes, 'items'):
                iterable = raw_nodes.items()
            else:
                iterable = ((
                    _safe_get_attribute(node, 'name') or 'Unnamed',
                    node
                ) for node in raw_nodes)

            for node_name, node in iterable:
                try:
                    if hasattr(node, 'is_feature') and not node.is_feature():
                        continue

                    interface_type = _safe_get_attribute(node, 'principal_interface_type')
                    access_mode = None
                    try:
                        access_mode = node.get_access_mode()
                        access_name = str(access_mode).split('.')[-1]
                    except Exception:
                        access_name = 'Unknown'

                    node_info = {
                        'name': node_name,
                        'display_name': _safe_get_attribute(node, 'display_name') or node_name,
                        'description': _safe_get_attribute(node, 'description') or '',
                        'tooltip': _safe_get_attribute(node, 'tooltip') or '',
                        'interface': _interface_name(interface_type),
                        'access_mode': access_name,
                        'is_readable': access_mode in (genapi.EAccessMode.RO, genapi.EAccessMode.RW),
                        'is_writable': access_mode in (genapi.EAccessMode.WO, genapi.EAccessMode.RW),
                        'metadata': _extract_node_metadata(node, interface_type),
                    }

                    if node_info['is_readable']:
                        node_info['value'] = _read_node_value(node, interface_type)
                    else:
                        node_info['value'] = None

                    choices = _node_choices(node, interface_type)
                    if choices:
                        node_info['choices'] = choices

                    nodes.append(node_info)
                except Exception as node_error:
                    nodes.append({
                        'name': node_name,
                        'display_name': node_name,
                        'interface': 'Unknown',
                        'access_mode': 'Unknown',
                        'is_readable': False,
                        'is_writable': False,
                        'value': None,
                        'error': str(node_error),
                    })

            nodes.sort(key=lambda n: (n.get('display_name') or n['name']).lower())
            return {'nodes': nodes}


def set_genicam_node_value(identifier, node_name, value):
    """
    Update a writable GenICam node with a new value.

    Returns a tuple of (success: bool, payload: dict). On success the payload
    contains the updated node information, otherwise it contains an "error"
    message.
    """
    with harvester_lock:
        if not h.files:
            return False, {'error': 'No GenTL producers have been loaded.'}

        try:
            ia = h.create({'serial_number': identifier})
        except Exception as create_err:
            return False, {'error': f'Unable to connect to camera: {create_err}'}

        if not ia:
            return False, {'error': 'Failed to create an image acquirer for the camera.'}

        with ia:
            node_map = ia.remote_device.node_map
            try:
                node = node_map.get_node(node_name)
            except Exception:
                return False, {'error': f'Node "{node_name}" was not found on the device.'}

            interface_type = _safe_get_attribute(node, 'principal_interface_type')
            access_mode = None
            try:
                access_mode = node.get_access_mode()
            except Exception:
                pass

            if access_mode not in (genapi.EAccessMode.WO, genapi.EAccessMode.RW):
                return False, {'error': f'Node "{node_name}" is not writable.'}

            try:
                if interface_type == genapi.EInterfaceType.intfIEnumeration:
                    if value is None or (isinstance(value, str) and not value.strip()):
                        return False, {'error': 'A value is required to update this node.'}
                    node.value = str(value)
                elif interface_type == genapi.EInterfaceType.intfIInteger:
                    if value is None or (isinstance(value, str) and not value.strip()):
                        return False, {'error': 'A value is required to update this node.'}
                    node.value = int(value)
                elif interface_type == genapi.EInterfaceType.intfIFloat:
                    if value is None or (isinstance(value, str) and not value.strip()):
                        return False, {'error': 'A value is required to update this node.'}
                    node.value = float(value)
                elif interface_type == genapi.EInterfaceType.intfIBoolean:
                    if isinstance(value, bool):
                        node.value = value
                    else:
                        node.value = str(value).strip().lower() in ('1', 'true', 'yes', 'on')
                elif interface_type == genapi.EInterfaceType.intfIString:
                    if value is None:
                        return False, {'error': 'A value is required to update this node.'}
                    node.value = str(value)
                else:
                    return False, {'error': f'Updating nodes of type {_interface_name(interface_type)} is not supported.'}
            except Exception as update_error:
                return False, {'error': f'Failed to update node: {update_error}'}

            updated_value = _read_node_value(node, interface_type)
            response = {
                'name': node_name,
                'value': updated_value,
                'interface': _interface_name(interface_type),
            }
            return True, response
