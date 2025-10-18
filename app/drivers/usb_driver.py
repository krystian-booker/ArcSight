import cv2
from .base_driver import BaseDriver
from app.usb_device_info import find_camera_index_by_identifier


class USBDriver(BaseDriver):
    def __init__(self, camera_db_data):
        super().__init__(camera_db_data)
        self.cap = None
        self.resolved_index = None  # Stores the actual OpenCV index after resolution

    def connect(self):
        # Resolve stable identifier to current index
        device_index = find_camera_index_by_identifier(self.identifier)
        if device_index is None:
            raise ConnectionError(
                f"USB camera with identifier '{self.identifier}' not found. "
                f"Please check that the camera is connected."
            )

        print(
            f"Resolved camera identifier '{self.identifier}' to index {device_index}"
        )

        self.resolved_index = device_index
        self.cap = cv2.VideoCapture(device_index)
        if not self.cap.isOpened():
            self.cap = None
            self.resolved_index = None
            raise ConnectionError(
                f"Failed to open USB camera at index {device_index} (identifier: {self.identifier})"
            )
        print(
            f"Successfully connected to USB camera {self.identifier} at index {device_index}"
        )

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
        Scans for available USB cameras with stable unique identifiers.

        Uses platform-specific methods to extract USB device information
        (Vendor ID, Product ID, Serial Number) to create stable identifiers
        that persist across USB port changes.
        """
        from app.usb_device_info import get_usb_cameras_with_info

        devices = []
        cameras_info = get_usb_cameras_with_info()

        for cam_info in cameras_info:
            # Build a descriptive name
            name_parts = []
            if (
                cam_info.get("name")
                and cam_info["name"] != f"USB Camera {cam_info['cv_index']}"
            ):
                name_parts.append(cam_info["name"])
            else:
                name_parts.append(f"USB Camera {cam_info['cv_index']}")

            # Add VID:PID if available for clarity
            if cam_info.get("vendor_id") and cam_info.get("product_id"):
                name_parts.append(f"[{cam_info['vendor_id']}:{cam_info['product_id']}]")

            # Add serial if available
            if cam_info.get("serial_number"):
                name_parts.append(f"S/N: {cam_info['serial_number']}")

            full_name = " ".join(name_parts)

            devices.append(
                {
                    "identifier": cam_info["identifier"],
                    "name": full_name,
                    "camera_type": "USB",
                    # Include metadata for UI display (optional)
                    "vendor_id": cam_info.get("vendor_id", ""),
                    "product_id": cam_info.get("product_id", ""),
                    "serial_number": cam_info.get("serial_number", ""),
                    "cv_index": cam_info["cv_index"],
                }
            )

        return devices
