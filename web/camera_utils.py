import cv2
from harvesters.core import Harvester
import os
import threading
import time

import numpy as np

import db  # This assumes db.py is in the same directory


_usb_capture_lock = threading.Lock()
_active_usb_captures = {}

def list_usb_cameras():
    """
    Lists available USB cameras by trying to open them.
    Returns a list of dictionaries, each with 'identifier' and 'name'.
    """
    usb_cameras = []
    # Check up to 10 indices. A more robust solution might be needed
    # on systems with many devices, but this is a common approach.
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
    Lists available GenICam cameras using the harvesters library.
    Returns a list of dictionaries, each with 'identifier' and 'name'.
    """
    genicam_cameras = []
    cti_path = db.get_setting('genicam_cti_path')

    if not cti_path or not os.path.exists(cti_path):
        print(f"GenICam CTI file not found or not configured: {cti_path}")
        return genicam_cameras

    h = Harvester()
    try:
        h.add_file(cti_path)
        h.update()
        for device_info in h.device_info_list:
            identifier = device_info.serial_number
            name = device_info.model
            genicam_cameras.append({
                'identifier': identifier,
                'name': f"{name} ({identifier})"
            })
    except Exception as e:
        print(f"Error listing GenICam cameras: {e}")
    finally:
        if h is not None:
            h.reset()
    
    return genicam_cameras

def check_camera_connection(camera):
    """
    Checks if a given camera is currently connected.
    'camera' is a dictionary-like object from the database.
    """
    if camera['camera_type'] == 'USB':
        try:
            index = int(camera['identifier'])
        except (ValueError, TypeError):
            return False

        with _usb_capture_lock:
            cap = _active_usb_captures.get(index)
            if cap is not None and cap.isOpened():
                return True

        temp_cap = cv2.VideoCapture(index)
        try:
            return temp_cap.isOpened()
        finally:
            temp_cap.release()

    elif camera['camera_type'] == 'GenICam':
        connected_genicams = list_genicam_cameras()
        return any(cam['identifier'] == camera['identifier'] for cam in connected_genicams)

    return False

def get_camera_feed(camera):
    """
    Generator function that yields JPEG frames from a camera.
    """
    if camera['camera_type'] == 'USB':
        try:
            index = int(camera['identifier'])
        except (ValueError, TypeError):
            print(f"Invalid USB camera identifier: {camera['identifier']}")
            return

        error_frame = _build_error_frame_chunk("Camera disconnected")

        try:
            while True:
                cap = cv2.VideoCapture(index)
                if not cap.isOpened():
                    cap.release()
                    if error_frame:
                        yield error_frame
                    time.sleep(1)
                    continue

                with _usb_capture_lock:
                    _active_usb_captures[index] = cap

                try:
                    while True:
                        ret, frame = cap.read()
                        if not ret:
                            break

                        ret, buffer = cv2.imencode('.jpg', frame)
                        if not ret:
                            break

                        yield (b'--frame\r\n'
                               b'Content-Type: image/jpeg\r\n\r\n' + buffer.tobytes() + b'\r\n')
                except GeneratorExit:
                    raise
                except Exception as exc:
                    print(f"Error streaming USB camera {camera['identifier']}: {exc}")
                finally:
                    with _usb_capture_lock:
                        if _active_usb_captures.get(index) is cap:
                            _active_usb_captures.pop(index, None)
                    cap.release()

                if error_frame:
                    yield error_frame
                time.sleep(1)
        except GeneratorExit:
            return

    elif camera['camera_type'] == 'GenICam':
        h = Harvester()
        cti_path = db.get_setting('genicam_cti_path')
        if not cti_path or not os.path.exists(cti_path):
            print(f"GenICam CTI file not found or not configured: {cti_path}")
            return

        h.add_file(cti_path)
        h.update()

        try:
            with h.create({'serial_number': camera['identifier']}) as ia:
                ia.start_acquisition()
                while True:
                    with ia.fetch_buffer() as buffer:
                        # This assumes a mono or bayer image, which is common.
                        # For color, more complex handling is needed.
                        component = buffer.payload.components[0]
                        img = component.data.reshape(component.height, component.width)
                        
                        # Convert to 3-channel BGR for color display if needed,
                        # assuming bayer pattern. This is a simplification.
                        # For a real application, you'd check component.data_format
                        if 'Bayer' in component.data_format:
                            # This is a basic conversion, might need adjustment
                            # based on the specific Bayer pattern (RG, GB, etc.)
                            img = cv2.cvtColor(img, cv2.COLOR_BayerRG2BGR)

                        ret, jpeg = cv2.imencode('.jpg', img)
                        if ret:
                            yield (b'--frame\r\n'
                                   b'Content-Type: image/jpeg\r\n\r\n' + jpeg.tobytes() + b'\r\n')
        except Exception as e:
            print(f"Error with GenICam feed: {e}")
        finally:
            h.reset()


def _build_error_frame_chunk(message, width=640, height=480):
    """Create a single multipart frame representing an error message."""
    img = np.zeros((height, width, 3), np.uint8)
    font = cv2.FONT_HERSHEY_SIMPLEX
    text_size = cv2.getTextSize(message, font, 1, 2)[0]
    text_x = (width - text_size[0]) // 2
    text_y = (height + text_size[1]) // 2
    cv2.putText(img, message, (text_x, text_y), font, 1, (255, 255, 255), 2)
    ret, jpeg = cv2.imencode('.jpg', img)
    if not ret:
        return None
    return (b'--frame\r\n'
            b'Content-Type: image/jpeg\r\n\r\n' + jpeg.tobytes() + b'\r\n')
