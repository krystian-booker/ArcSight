import logging
from typing import Any, Dict, List, Optional, Union
import cv2
import numpy as np

from .base_driver import BaseDriver
from .exceptions import DriverConnectionError, DriverConfigurationError
from app.usb_device_info import find_camera_index_by_identifier
from app.utils.camera_config import CameraConfig, get_config_value
from app.enums import CameraType, ExposureMode, GainMode

logger = logging.getLogger(__name__)


class USBDriver(BaseDriver):
    def __init__(self, camera_config: CameraConfig):
        super().__init__(camera_config)
        self.cap: Optional[cv2.VideoCapture] = None
        self.resolved_index: Optional[int] = None  # Stores the actual OpenCV index after resolution

        # Extract exposure and gain settings
        self.exposure_mode = get_config_value(camera_config, "exposure_mode", "auto")
        self.exposure_value = get_config_value(camera_config, "exposure_value", 500)
        self.gain_mode = get_config_value(camera_config, "gain_mode", "auto")
        self.gain_value = get_config_value(camera_config, "gain_value", 50)

    def connect(self) -> None:
        """Establishes connection to the USB camera."""
        # Resolve stable identifier to current index
        device_index = find_camera_index_by_identifier(self.identifier)
        if device_index is None:
            raise DriverConnectionError(
                f"USB camera with identifier '{self.identifier}' not found. "
                f"Please check that the camera is connected."
            )

        logger.info(f"Resolved camera identifier '{self.identifier}' to index {device_index}")

        self.resolved_index = device_index
        self.cap = cv2.VideoCapture(device_index)
        if not self.cap.isOpened():
            self.cap = None
            self.resolved_index = None
            raise DriverConnectionError(
                f"Failed to open USB camera at index {device_index} (identifier: {self.identifier})"
            )

        # Apply exposure and gain settings if in manual mode
        self._apply_camera_settings()

        logger.info(
            f"Successfully connected to USB camera {self.identifier} at index {device_index}"
        )

    def disconnect(self) -> None:
        """Closes the connection to the USB camera."""
        if self.cap:
            logger.info(f"Disconnecting USB camera {self.identifier}")
            self.cap.release()
            self.cap = None

    def get_frame(self) -> Optional[np.ndarray]:
        """Retrieves a single frame from the camera.

        Returns:
            numpy array (BGR format) or None if failed
        """
        if not self.cap or not self.cap.isOpened():
            # This indicates a lost connection. Returning None will signal the acquisition loop to reconnect.
            return None

        ret, frame = self.cap.read()

        if not ret or frame is None:
            # A failed read could also mean the camera was disconnected.
            return None

        return frame

    def _apply_camera_settings(self) -> None:
        """Apply exposure and gain settings to the camera."""
        if not self.cap:
            return

        try:
            # Handle exposure mode
            if self.exposure_mode == ExposureMode.MANUAL.value or self.exposure_mode == "manual":
                # Disable auto exposure
                self.cap.set(cv2.CAP_PROP_AUTO_EXPOSURE, 0.25)  # 0.25 = manual mode
                # Set manual exposure value
                if self.exposure_value is not None:
                    self.cap.set(cv2.CAP_PROP_EXPOSURE, self.exposure_value)
            else:
                # Enable auto exposure
                self.cap.set(cv2.CAP_PROP_AUTO_EXPOSURE, 0.75)  # 0.75 = auto mode

            # Handle gain mode
            if self.gain_mode == GainMode.MANUAL.value or self.gain_mode == "manual":
                # Set manual gain value
                if self.gain_value is not None:
                    self.cap.set(cv2.CAP_PROP_GAIN, self.gain_value)
            # Note: OpenCV doesn't have explicit auto-gain control for USB cameras
        except Exception as e:
            logger.warning(f"Failed to apply camera settings for {self.identifier}: {e}")
            # Don't raise - settings application is non-critical

    @staticmethod
    def list_devices() -> List[Dict[str, Any]]:
        """
        Scans for available USB cameras with stable unique identifiers.

        Uses platform-specific methods to extract USB device information
        (Vendor ID, Product ID, Serial Number) to create stable identifiers
        that persist across USB port changes.

        Returns:
            List of dictionaries with camera information
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
                    "camera_type": CameraType.USB.value,
                    # Include metadata for UI display (optional)
                    "vendor_id": cam_info.get("vendor_id", ""),
                    "product_id": cam_info.get("product_id", ""),
                    "serial_number": cam_info.get("serial_number", ""),
                    "cv_index": cam_info["cv_index"],
                }
            )

        return devices
