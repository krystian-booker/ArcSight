import cv2
from .base_driver import BaseDriver


class USBDriver(BaseDriver):
    def __init__(self, camera_db_data):
        super().__init__(camera_db_data)
        self.cap = None

    def connect(self):
        try:
            # The identifier for USB cameras is expected to be a string representing an integer index.
            device_index = int(self.identifier)
        except (ValueError, TypeError):
            raise ConnectionError(
                f"Invalid identifier for USB camera: '{self.identifier}'. Must be an integer index."
            )

        self.cap = cv2.VideoCapture(device_index)
        if not self.cap.isOpened():
            self.cap = None  # Ensure cap is None if connection failed
            raise ConnectionError(
                f"Failed to open USB camera at index {self.identifier}"
            )
        print(f"Successfully connected to USB camera {self.identifier}")

    def disconnect(self):
        if self.cap:
            print(f"Disconnecting USB camera {self.identifier}")
            self.cap.release()
            self.cap = None

    def get_frame(self):
        if not self.cap or not self.cap.isOpened():
            # This indicates a lost connection. Returning None will signal the acquisition loop to reconnect.
            return None

        ret, frame = self.cap.read()

        if not ret or frame is None:
            # A failed read could also mean the camera was disconnected.
            return None

        return frame

    @staticmethod
    def list_devices():
        """
        Scans for available USB cameras by trying to open them.
        This is the logic from the old list_usb_cameras function.
        """
        devices = []
        # Check the first 10 indices, which is a common practice.
        for i in range(10):
            cap = cv2.VideoCapture(i)
            if cap.isOpened():
                # For USB cameras, we use the index as the identifier.
                # A more descriptive name could be fetched if the backend library supports it,
                # but for OpenCV, this is standard.
                devices.append(
                    {
                        "identifier": str(i),
                        "name": f"USB Camera {i}",
                        "camera_type": "USB",
                    }
                )
                cap.release()
        return devices
