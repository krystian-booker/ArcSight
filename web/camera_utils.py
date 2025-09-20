import cv2
from harvesters.core import Harvester
import os
import db
import threading
import time

try:
    from genicam import genapi
except ImportError:  # pragma: no cover - the module should be available in production
    genapi = None

# Global Harvester instance
h = Harvester()

# A lock to ensure thread-safe access to the harvester
harvester_lock = threading.Lock()

if genapi is not None:
    ACCESS_MODE_LABELS = {
        genapi.EAccessMode.NA: 'NA',
        genapi.EAccessMode.NI: 'NI',
        genapi.EAccessMode.RO: 'RO',
        genapi.EAccessMode.RW: 'RW',
        genapi.EAccessMode.WO: 'WO',
    }

    INTERFACE_TYPE_NAMES = {
        genapi.EInterfaceType.intfIInteger: 'integer',
        genapi.EInterfaceType.intfIFloat: 'float',
        genapi.EInterfaceType.intfIBoolean: 'boolean',
        genapi.EInterfaceType.intfIString: 'string',
        genapi.EInterfaceType.intfIEnumeration: 'enum',
        genapi.EInterfaceType.intfICommand: 'command',
        genapi.EInterfaceType.intfIRegister: 'register',
        genapi.EInterfaceType.intfICategory: 'category',
        genapi.EInterfaceType.intfIPort: 'port',
        genapi.EInterfaceType.intfIBase: 'base',
        genapi.EInterfaceType.intfIValue: 'value',
    }
else:  # pragma: no cover - protects against environments without GenICam
    ACCESS_MODE_LABELS = {}
    INTERFACE_TYPE_NAMES = {}


def _safe_get(getter, default=None):
    """Safely execute a callable, returning a default value if it fails."""

    try:
        return getter()
    except Exception:
        return default


def _normalize_value(value):
    """Convert values to built-in Python types suitable for JSON serialization."""

    if isinstance(value, (int, float, bool)) or value is None:
        return value
    if isinstance(value, str):
        return value
    if hasattr(value, 'item'):
        try:
            return value.item()
        except Exception:
            pass
    return str(value)


def _access_mode_to_text(access_mode):
    if access_mode is None:
        return 'Unknown'
    return ACCESS_MODE_LABELS.get(access_mode, str(access_mode).split('.')[-1])


def _interface_to_value_type(interface_type):
    if interface_type is None:
        return 'unknown'
    return INTERFACE_TYPE_NAMES.get(interface_type, str(interface_type).split('.')[-1])


def _read_integer(node, readable):
    integer_node = genapi.IInteger(node)
    value = None
    if readable:
        raw_value = _safe_get(lambda: integer_node.value)
        if raw_value is not None:
            try:
                value = int(raw_value)
            except Exception:
                value = _normalize_value(raw_value)
    metadata = {
        'min': _normalize_value(_safe_get(lambda: integer_node.min)),
        'max': _normalize_value(_safe_get(lambda: integer_node.max)),
        'increment': _normalize_value(_safe_get(lambda: integer_node.inc)),
        'unit': _normalize_value(_safe_get(lambda: integer_node.unit)),
    }
    return value, metadata


def _read_float(node, readable):
    float_node = genapi.IFloat(node)
    value = None
    if readable:
        raw_value = _safe_get(lambda: float_node.value)
        if raw_value is not None:
            try:
                value = float(raw_value)
            except Exception:
                value = _normalize_value(raw_value)
    metadata = {
        'min': _normalize_value(_safe_get(lambda: float_node.min)),
        'max': _normalize_value(_safe_get(lambda: float_node.max)),
        'unit': _normalize_value(_safe_get(lambda: float_node.unit)),
        'display_precision': _normalize_value(_safe_get(lambda: float_node.display_precision)),
    }
    return value, metadata


def _read_boolean(node, readable):
    bool_node = genapi.IBoolean(node)
    value = None
    if readable:
        raw_value = _safe_get(lambda: bool_node.value)
        if raw_value is not None:
            value = bool(raw_value)
    return value, {}


def _read_string(node, readable):
    string_node = genapi.IString(node)
    value = None
    if readable:
        raw_value = _safe_get(lambda: string_node.value)
        if raw_value is not None:
            value = str(raw_value)
    metadata = {
        'max_length': _normalize_value(_safe_get(lambda: string_node.max_length)),
    }
    return value, metadata


def _read_enum(node, readable):
    enum_node = genapi.IEnumeration(node)
    value = None
    if readable:
        raw_value = _safe_get(lambda: enum_node.value)
        if raw_value is not None:
            value = str(raw_value)
    options = []
    entries = _safe_get(lambda: enum_node.entries)
    if entries:
        for entry in entries:
            if not entry:
                continue
            if not _safe_get(lambda e=entry: genapi.is_available(e), default=False):
                continue
            symbolic = _safe_get(lambda e=entry: e.symbolic)
            if symbolic is None:
                continue
            option_label = _safe_get(lambda e=entry: getattr(e, 'display_name', None))
            option_name = option_label or _safe_get(lambda e=entry: e.name, default=symbolic)
            options.append({
                'value': str(symbolic),
                'name': str(option_name) if option_name else str(symbolic),
            })
    metadata = {'options': options}
    return value, metadata


def _write_integer(node, value):
    integer_node = genapi.IInteger(node)
    try:
        int_value = int(value)
    except (TypeError, ValueError):
        raise ValueError("Value must be an integer.")

    min_value = _safe_get(lambda: integer_node.min)
    max_value = _safe_get(lambda: integer_node.max)
    if min_value is not None and int_value < min_value:
        raise ValueError(f"Value must be greater than or equal to {int(min_value)}.")
    if max_value is not None and int_value > max_value:
        raise ValueError(f"Value must be less than or equal to {int(max_value)}.")

    integer_node.value = int_value
    return int(integer_node.value)


def _write_float(node, value):
    float_node = genapi.IFloat(node)
    try:
        float_value = float(value)
    except (TypeError, ValueError):
        raise ValueError("Value must be a number.")

    min_value = _safe_get(lambda: float_node.min)
    max_value = _safe_get(lambda: float_node.max)
    if min_value is not None and float_value < min_value:
        raise ValueError(f"Value must be greater than or equal to {float(min_value)}.")
    if max_value is not None and float_value > max_value:
        raise ValueError(f"Value must be less than or equal to {float(max_value)}.")

    float_node.value = float_value
    return float(float_node.value)


def _write_boolean(node, value):
    bool_node = genapi.IBoolean(node)
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {'1', 'true', 'yes', 'on'}:
            bool_value = True
        elif normalized in {'0', 'false', 'no', 'off'}:
            bool_value = False
        else:
            raise ValueError("Value must be true or false.")
    else:
        bool_value = bool(value)

    bool_node.value = bool_value
    return bool(bool_node.value)


def _write_string(node, value):
    string_node = genapi.IString(node)
    if value is None:
        value_str = ''
    else:
        value_str = str(value)

    max_length = _safe_get(lambda: string_node.max_length)
    if max_length and len(value_str) > max_length:
        raise ValueError(f"Value exceeds the maximum length of {int(max_length)} characters.")

    string_node.value = value_str
    return string_node.value


def _write_enum(node, value):
    enum_node = genapi.IEnumeration(node)
    if value is None:
        raise ValueError("A value must be provided for enumeration nodes.")

    value_str = str(value)
    entries = _safe_get(lambda: enum_node.entries)
    valid_values = set()
    if entries:
        for entry in entries:
            if not entry:
                continue
            if not _safe_get(lambda e=entry: genapi.is_available(e), default=False):
                continue
            symbolic = _safe_get(lambda e=entry: e.symbolic)
            if symbolic is not None:
                valid_values.add(str(symbolic))

    if valid_values and value_str not in valid_values:
        options_text = ', '.join(sorted(valid_values))
        raise ValueError(f"'{value_str}' is not a valid option. Choose from: {options_text}.")

    enum_node.value = value_str
    return enum_node.value


if genapi is not None:
    VALUE_READERS = {
        genapi.EInterfaceType.intfIInteger: _read_integer,
        genapi.EInterfaceType.intfIFloat: _read_float,
        genapi.EInterfaceType.intfIBoolean: _read_boolean,
        genapi.EInterfaceType.intfIString: _read_string,
        genapi.EInterfaceType.intfIEnumeration: _read_enum,
    }

    VALUE_WRITERS = {
        genapi.EInterfaceType.intfIInteger: _write_integer,
        genapi.EInterfaceType.intfIFloat: _write_float,
        genapi.EInterfaceType.intfIBoolean: _write_boolean,
        genapi.EInterfaceType.intfIString: _write_string,
        genapi.EInterfaceType.intfIEnumeration: _write_enum,
    }
else:  # pragma: no cover - protects against environments without GenICam
    VALUE_READERS = {}
    VALUE_WRITERS = {}


def initialize_harvester(force_reload: bool = False) -> bool:
    """Initialize the harvester with the CTI file stored in the database."""

    if genapi is None:
        print("genapi module is not available; skipping harvester initialization.")
        return False

    with harvester_lock:
        cti_path = db.get_setting('genicam_cti_path')
        if not cti_path:
            if force_reload:
                h.reset()
            print("GenICam CTI file not configured. Harvester not initialized.")
            return False

        if not os.path.exists(cti_path):
            if force_reload:
                h.reset()
            print(f"GenICam CTI file not found at {cti_path}. Harvester not initialized.")
            return False

        try:
            if force_reload or cti_path not in h.files:
                h.reset()
                h.add_file(cti_path)
            h.update()
            print("Harvester initialized successfully.")
            return True
        except Exception as e:  # pragma: no cover - relies on hardware specific stack
            print(f"Error initializing Harvester: {e}")
            return False

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
    if genapi is None:
        return []

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


def ensure_harvester_initialized():
    """Confirm that the harvester is ready to communicate with GenICam devices."""

    if genapi is None:
        return False, "GenICam libraries are not available on this system."

    cti_path = db.get_setting('genicam_cti_path')
    if not cti_path:
        return False, "GenICam CTI path is not configured."

    if not os.path.exists(cti_path):
        return False, f"Configured GenICam CTI file was not found at {cti_path}."

    if cti_path not in h.files:
        if not initialize_harvester(force_reload=True):
            return False, "Failed to initialize the GenICam interface."

    return True, None


def _serialize_node(node):
    if genapi is None or not node:
        return None

    try:
        interface_type = node.principal_interface_type
    except Exception as exc:
        return {
            'name': _normalize_value(_safe_get(lambda: node.name, default='Unknown')),
            'display_name': _normalize_value(_safe_get(lambda: node.display_name, default='Unknown')),
            'value_type': 'unknown',
            'access_mode': 'Unknown',
            'is_readable': False,
            'is_writable': False,
            'editable': False,
            'error': str(exc),
        }

    name = _normalize_value(_safe_get(lambda: node.name, default=''))
    display_name = _normalize_value(_safe_get(lambda: node.display_name, default=name))
    description = _normalize_value(_safe_get(lambda: node.description, default='')) or ''
    category = _normalize_value(_safe_get(lambda: node.name_space, default='')) or ''
    qualified_name = _normalize_value(_safe_get(lambda: node.name_full_qualified, default=name))
    tooltip = _normalize_value(_safe_get(lambda: getattr(node, 'tooltip', ''), default='')) or ''

    try:
        is_readable = bool(genapi.is_readable(node))
    except Exception:
        is_readable = False

    try:
        is_writable = bool(genapi.is_writable(node))
    except Exception:
        is_writable = False

    access_mode = _access_mode_to_text(_safe_get(lambda: node.get_access_mode()))
    value_type = _interface_to_value_type(interface_type)

    info = {
        'name': name,
        'display_name': display_name,
        'description': description,
        'category': category,
        'qualified_name': qualified_name,
        'tooltip': tooltip,
        'access_mode': access_mode,
        'is_readable': is_readable,
        'is_writable': is_writable,
        'value_type': value_type,
        'interface_type': str(interface_type),
        'value': None,
        'editable': False,
    }

    reader = VALUE_READERS.get(interface_type)
    if reader:
        value, metadata = reader(node, is_readable)
        info['value'] = _normalize_value(value)
        if metadata:
            for key, meta_value in metadata.items():
                if key == 'options' and isinstance(meta_value, list):
                    normalized_options = []
                    for option in meta_value:
                        if not isinstance(option, dict):
                            continue
                        normalized_options.append({
                            'value': _normalize_value(option.get('value')),
                            'name': _normalize_value(option.get('name')),
                        })
                    info[key] = normalized_options
                else:
                    info[key] = _normalize_value(meta_value)
        info['editable'] = bool(is_writable and interface_type in VALUE_WRITERS)
    elif value_type == 'command':
        info['editable'] = bool(is_writable)

    return info


def _collect_node_map(node_map):
    nodes = []
    try:
        for node in node_map.nodes:
            serialized = _serialize_node(node)
            if serialized:
                nodes.append(serialized)
    except Exception as exc:  # pragma: no cover - relies on hardware behavior
        nodes.append({
            'name': 'Error',
            'display_name': 'Error',
            'value_type': 'error',
            'access_mode': 'Unknown',
            'is_readable': False,
            'is_writable': False,
            'editable': False,
            'error': str(exc),
        })

    nodes.sort(key=lambda item: (
        (item.get('category') or '').lower(),
        (item.get('display_name') or item.get('name') or '').lower(),
    ))
    return nodes


def get_genicam_node_map(identifier):
    """Retrieve the GenICam node map for the specified camera identifier."""

    ready, error = ensure_harvester_initialized()
    if not ready:
        return [], error

    if not identifier:
        return [], "Camera identifier is required."

    with harvester_lock:
        try:
            h.update()
        except Exception as exc:
            return [], f"Unable to update GenICam device list: {exc}"

        try:
            with h.create({'serial_number': identifier}) as ia:
                node_map = ia.remote_device.node_map
                nodes = _collect_node_map(node_map)
                return nodes, None
        except Exception as exc:
            return [], f"Unable to access GenICam device: {exc}"


def set_genicam_node_value(identifier, node_name, value):
    """Update a writable GenICam node with a new value."""

    ready, error = ensure_harvester_initialized()
    if not ready:
        return False, error, None

    if not identifier:
        return False, "Camera identifier is required.", None

    if not node_name:
        return False, "Node name is required.", None

    with harvester_lock:
        try:
            h.update()
        except Exception as exc:
            return False, f"Unable to update GenICam device list: {exc}", None

        try:
            with h.create({'serial_number': identifier}) as ia:
                node_map = ia.remote_device.node_map
                if not node_map.has_node(node_name):
                    return False, f"Node '{node_name}' was not found on the device.", None

                node = node_map.get_node(node_name)

                try:
                    if not genapi.is_writable(node):
                        return False, f"Node '{node_name}' is not writable.", None
                except Exception:
                    return False, f"Node '{node_name}' is not writable.", None

                interface_type = _safe_get(lambda: node.principal_interface_type)
                writer = VALUE_WRITERS.get(interface_type)
                if not writer:
                    return False, f"Updates are not supported for node '{node_name}'.", None

                try:
                    updated_value = writer(node, value)
                except ValueError as validation_error:
                    return False, str(validation_error), None
                except Exception as exc:
                    return False, f"Failed to update node '{node_name}': {exc}", None

                reader = VALUE_READERS.get(interface_type)
                if reader:
                    refreshed_value, _ = reader(node, True)
                else:
                    refreshed_value = updated_value

                return True, None, _normalize_value(refreshed_value)
        except Exception as exc:
            return False, f"Unable to access GenICam device: {exc}", None
