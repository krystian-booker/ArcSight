import cv2
from harvesters.core import Harvester
import os
import db
import threading

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
    Generator function that yields JPEG frames from a camera.
    """
    if camera['camera_type'] == 'USB':
        cap = cv2.VideoCapture(int(camera['identifier']))
        if not cap.isOpened():
            print(f"Could not open USB camera {camera['identifier']}")
            return
        
        try:
            while True:
                ret, frame = cap.read()
                if not ret:
                    print(f"Stopping feed for USB camera {camera['identifier']} as it appears to be disconnected.")
                    break
                
                ret, buffer = cv2.imencode('.jpg', frame)
                if ret:
                    yield (b'--frame\r\n'
                           b'Content-Type: image/jpeg\r\n\r\n' + buffer.tobytes() + b'\r\n')
        finally:
            print(f"Releasing USB camera {camera['identifier']}")
            cap.release()

    elif camera['camera_type'] == 'GenICam':
        # Use the global harvester instance. Assumes it's been initialized.
        try:
            with harvester_lock:
                # The 'with' statement ensures the image acquirer is released.
                ia = h.create({'serial_number': camera['identifier']})
            
            if not ia:
                print(f"Failed to create image acquirer for {camera['identifier']}")
                return

            with ia:
                ia.start_acquisition()
                while True:
                    try:
                        with ia.fetch_buffer() as buffer:
                            component = buffer.payload.components[0]
                            img = component.data.reshape(component.height, component.width)
                            
                            if 'Bayer' in component.data_format:
                                img = cv2.cvtColor(img, cv2.COLOR_BayerRG2BGR)

                            ret, jpeg = cv2.imencode('.jpg', img)
                            if ret:
                                yield (b'--frame\r\n'
                                       b'Content-Type: image/jpeg\r\n\r\n' + jpeg.tobytes() + b'\r\n')
                    except Exception as fetch_e:
                        print(f"Error fetching buffer for GenICam {camera['identifier']}: {fetch_e}")
                        break # Exit the loop if fetching fails (e.g., camera disconnected)

        except Exception as e:
            print(f"Error with GenICam feed for {camera['identifier']}: {e}")
        # No h.reset() here, as we are using a global instance.
        # The image acquirer 'ia' is cleaned up by its 'with' statement.
