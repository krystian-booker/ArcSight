import cv2
from harvesters.core import Harvester
import os
import db # This assumes db.py is in the same directory

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
