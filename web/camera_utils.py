import cv2
from harvesters.core import Harvester
from genicam.genapi import EAccessMode, EInterfaceType
import os
import db
import threading
import time

# Global Harvester instance
h = Harvester()

# A lock to ensure thread-safe access to the harvester
harvester_lock = threading.Lock()

_SUPPORTED_INTERFACE_TYPES = {
    EInterfaceType.intfIInteger,
    EInterfaceType.intfIFloat,
    EInterfaceType.intfIString,
    EInterfaceType.intfIBoolean,
    EInterfaceType.intfIEnumeration,
    EInterfaceType.intfICommand,
}

_INTERFACE_TYPE_LABELS = {
    EInterfaceType.intfIInteger: "integer",
    EInterfaceType.intfIFloat: "float",
    EInterfaceType.intfIString: "string",
    EInterfaceType.intfIBoolean: "boolean",
    EInterfaceType.intfIEnumeration: "enum",
    EInterfaceType.intfICommand: "command",
}

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


def _interface_type_to_label(interface_type):
    return _INTERFACE_TYPE_LABELS.get(interface_type, "unknown")


def _is_supported_interface(interface_type):
    return interface_type in _SUPPORTED_INTERFACE_TYPES


def _safe_call(callable_obj, default=None):
    try:
        return callable_obj()
    except Exception:
        return default


def _safe_getattr(obj, attr_name, default=None):
    if obj is None:
        return default
    try:
        value = getattr(obj, attr_name)
        if callable(value):
            return _safe_call(value, default)
        return value
    except Exception:
        return default


def _normalize_numeric(value):
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return value
    try:
        if hasattr(value, "__float__"):
            value = float(value)
            if value.is_integer():
                return int(value)
            return value
        if isinstance(value, str):
            stripped = value.strip()
            if not stripped:
                return None
            if any(ch in stripped for ch in [".", "e", "E"]):
                numeric = float(stripped)
                if numeric.is_integer():
                    return int(numeric)
                return numeric
            return int(stripped)
        numeric = float(value)
        if numeric.is_integer():
            return int(numeric)
        return numeric
    except Exception:
        return None


def _extract_enum_choices(node_obj):
    choices = []
    if node_obj is None:
        return choices

    symbolics = _safe_getattr(node_obj, "symbolics", None)
    entries = []

    if symbolics:
        try:
            entries = list(symbolics)
        except TypeError:
            try:
                entries = list(symbolics())  # type: ignore[operator]
            except Exception:
                entries = []
        for symbol in entries:
            if symbol is None:
                continue
            choices.append({
                "value": str(symbol),
                "display_name": str(symbol),
            })
        if choices:
            return choices

    entries = _safe_getattr(node_obj, "entries", [])
    try:
        for entry in entries:
            try:
                value = _safe_getattr(entry, "symbolic", None)
                if value is None:
                    continue
                display = _safe_getattr(entry, "display_name", None) or str(value)
                choices.append({
                    "value": str(value),
                    "display_name": str(display),
                })
            except Exception:
                continue
    except Exception:
        pass
    return choices


def _build_node_info(node_map, node):
    interface_type = _safe_getattr(node, "principal_interface_type", None)
    if interface_type is None or not _is_supported_interface(interface_type):
        return None

    node_name = _safe_getattr(node, "name")
    if not node_name:
        return None

    node_obj = _safe_getattr(node_map, node_name, None)
    access_mode_enum = _safe_call(node.get_access_mode, None)
    access_mode = access_mode_enum.name if hasattr(access_mode_enum, "name") else str(access_mode_enum)
    is_readable = access_mode_enum in (EAccessMode.RO, EAccessMode.RW)
    is_writable = access_mode_enum in (EAccessMode.WO, EAccessMode.RW)

    node_type = _interface_type_to_label(interface_type)
    read_error = None
    value = None

    if node_type != "command" and node_obj is not None:
        try:
            raw_value = _safe_getattr(node_obj, "value")
            if raw_value is not None:
                if node_type == "boolean":
                    value = bool(raw_value)
                elif node_type == "integer":
                    normalized = _normalize_numeric(raw_value)
                    value = int(normalized) if normalized is not None else None
                elif node_type == "float":
                    normalized = _normalize_numeric(raw_value)
                    value = float(normalized) if normalized is not None else None
                elif node_type in {"enum", "string"}:
                    value = str(raw_value)
                else:
                    value = raw_value
        except Exception as exc:
            read_error = str(exc)
            value = None

    info = {
        "name": node_name,
        "display_name": _safe_getattr(node, "display_name", node_name),
        "type": node_type,
        "access_mode": access_mode,
        "is_readable": bool(is_readable),
        "is_writable": bool(is_writable) and node_type != "unknown",
        "value": value,
        "read_error": read_error,
        "unit": _safe_getattr(node_obj, "unit", None),
        "min": _normalize_numeric(_safe_getattr(node_obj, "min", None)),
        "max": _normalize_numeric(_safe_getattr(node_obj, "max", None)),
        "inc": _normalize_numeric(_safe_getattr(node_obj, "inc", None)),
        "description": _safe_getattr(node, "description", None),
        "tooltip": _safe_getattr(node, "tooltip", None),
    }

    if node_type == "enum":
        info["choices"] = _extract_enum_choices(node_obj)
    else:
        info["choices"] = []

    return info


def _coerce_value_for_node(node_type, raw_value, node_obj):
    if node_type == "command":
        return None
    if node_type == "boolean":
        if isinstance(raw_value, bool):
            return raw_value
        if isinstance(raw_value, str):
            lowered = raw_value.strip().lower()
            if lowered in {"true", "1", "yes", "on"}:
                return True
            if lowered in {"false", "0", "no", "off"}:
                return False
        if isinstance(raw_value, (int, float)):
            return bool(raw_value)
        raise ValueError("Invalid boolean value.")

    if raw_value is None:
        raise ValueError("A value is required for this node.")

    if node_type == "integer":
        value = int(raw_value)
        minimum = _normalize_numeric(_safe_getattr(node_obj, "min", None))
        maximum = _normalize_numeric(_safe_getattr(node_obj, "max", None))
        if minimum is not None and value < minimum:
            raise ValueError(f"Value must be greater than or equal to {minimum}.")
        if maximum is not None and value > maximum:
            raise ValueError(f"Value must be less than or equal to {maximum}.")
        return value

    if node_type == "float":
        value = float(raw_value)
        minimum = _normalize_numeric(_safe_getattr(node_obj, "min", None))
        maximum = _normalize_numeric(_safe_getattr(node_obj, "max", None))
        if minimum is not None and value < minimum:
            raise ValueError(f"Value must be greater than or equal to {minimum}.")
        if maximum is not None and value > maximum:
            raise ValueError(f"Value must be less than or equal to {maximum}.")
        return value

    if node_type == "enum":
        value = str(raw_value)
        choices = _extract_enum_choices(node_obj)
        if choices:
            valid_values = {choice["value"] for choice in choices}
            if value not in valid_values:
                raise ValueError("Invalid enumeration value provided.")
        return value

    if node_type == "string":
        return str(raw_value)

    return raw_value


def get_genicam_node_map(identifier):
    with harvester_lock:
        try:
            ia = h.create({'serial_number': identifier})
        except Exception as exc:
            return None, f"Unable to access GenICam camera: {exc}"

        try:
            remote_device = ia.remote_device
            node_map = getattr(remote_device, 'node_map', None)
            if not node_map:
                return None, "Node map is not available for this camera."

            nodes = []
            try:
                node_list = list(node_map.nodes)
            except Exception:
                node_list = []

            for node in node_list:
                info = _build_node_info(node_map, node)
                if info:
                    nodes.append(info)

            nodes.sort(key=lambda item: (item.get('display_name') or item['name']).lower())
            return nodes, None
        finally:
            ia.destroy()


def set_genicam_node_value(identifier, node_name, raw_value=None):
    with harvester_lock:
        try:
            ia = h.create({'serial_number': identifier})
        except Exception as exc:
            return None, f"Unable to access GenICam camera: {exc}", 500

        try:
            remote_device = ia.remote_device
            node_map = getattr(remote_device, 'node_map', None)
            if not node_map:
                return None, "Node map is not available for this camera.", 500

            node = _safe_call(lambda: node_map.get_node(node_name), None)
            if node is None:
                return None, f"Node '{node_name}' was not found on the camera.", 404

            interface_type = _safe_getattr(node, "principal_interface_type", None)
            if interface_type is None or not _is_supported_interface(interface_type):
                return None, f"Node '{node_name}' is not supported for updates.", 400

            access_mode = _safe_call(node.get_access_mode, None)
            if access_mode not in (EAccessMode.WO, EAccessMode.RW):
                return None, f"Node '{node_name}' is not writable.", 400

            node_type = _interface_type_to_label(interface_type)
            node_obj = _safe_getattr(node_map, node_name, None)
            if node_obj is None:
                return None, f"Node '{node_name}' is not accessible.", 500

            try:
                if node_type == "command":
                    try:
                        execute = getattr(node_obj, "execute")
                    except Exception as exc:
                        return None, f"Failed to execute node '{node_name}': {exc}", 500
                    execute()
                else:
                    coerced_value = _coerce_value_for_node(node_type, raw_value, node_obj)
                    if node_type == "integer":
                        node_obj.value = int(coerced_value)
                    elif node_type == "float":
                        node_obj.value = float(coerced_value)
                    elif node_type == "boolean":
                        node_obj.value = bool(coerced_value)
                    else:
                        node_obj.value = str(coerced_value)
            except ValueError as exc:
                return None, str(exc), 400
            except Exception as exc:
                return None, f"Failed to update node '{node_name}': {exc}", 500

            updated_info = _build_node_info(node_map, node)
            return updated_info, None, 200
        finally:
            ia.destroy()
