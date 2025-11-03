import json
import logging
from typing import Any, Dict, List, Optional, Tuple, Union

import numpy as np

from .base_driver import BaseDriver
from .exceptions import (
    DriverConnectionError,
    DriverFrameAcquisitionError,
    DriverNotAvailableError,
)
from app.enums import CameraType
from app.utils.camera_config import get_config_value
from app.utils.config import DriverConfig

logger = logging.getLogger(__name__)

# Graceful import handling - pyrealsense2 may not be installed
try:
    import pyrealsense2 as rs
except ImportError:
    rs = None


class RealSenseDriver(BaseDriver):
    """Driver for Intel RealSense depth cameras.

    Supports RGB color stream and optional depth stream for models like D435, D435i, D455, etc.
    Provides configurable resolution, framerate, exposure, and gain settings.
    """

    # Default configuration constants
    _DEFAULT_WIDTH = 640
    _DEFAULT_HEIGHT = 480
    _DEFAULT_FPS = 30

    def __init__(self, camera_data: Union[Dict[str, Any], Any]):
        super().__init__(camera_data)
        self.pipeline = None
        self.config = None
        self.align = None  # For aligning depth to color frame
        self.color_sensor = None  # For exposure/gain control
        self.pipeline_started = False  # Track if pipeline.start() succeeded

        # Get configuration values using helper function
        resolution_json = get_config_value(camera_data, "resolution_json")
        framerate = get_config_value(camera_data, "framerate")
        depth_enabled = get_config_value(camera_data, "depth_enabled", False)
        exposure_mode = get_config_value(camera_data, "exposure_mode", "auto")
        exposure_value = get_config_value(camera_data, "exposure_value", 500)
        gain_mode = get_config_value(camera_data, "gain_mode", "auto")
        gain_value = get_config_value(camera_data, "gain_value", 50)

        # Parse resolution settings from JSON
        if resolution_json:
            try:
                res_data = json.loads(resolution_json) if isinstance(resolution_json, str) else resolution_json
                self.width = res_data.get("width", self._DEFAULT_WIDTH)
                self.height = res_data.get("height", self._DEFAULT_HEIGHT)
            except (json.JSONDecodeError, AttributeError, TypeError):
                self.width = self._DEFAULT_WIDTH
                self.height = self._DEFAULT_HEIGHT
        else:
            self.width = self._DEFAULT_WIDTH
            self.height = self._DEFAULT_HEIGHT

        # Get framerate setting
        self.fps = framerate or self._DEFAULT_FPS

        # Get depth enabled flag
        self.depth_enabled = depth_enabled

        # Get exposure and gain settings
        self.exposure_mode = exposure_mode
        self.exposure_value = exposure_value
        self.gain_mode = gain_mode
        self.gain_value = gain_value

    def connect(self) -> None:
        """Establishes connection to the RealSense camera."""
        if rs is None:
            raise DriverNotAvailableError(
                "pyrealsense2 library is not installed. "
                "Install with: pip install pyrealsense2"
            )

        try:
            # Create pipeline and config
            self.pipeline = rs.pipeline()
            self.config = rs.config()

            # Enable specific device by serial number
            self.config.enable_device(self.identifier)

            # Enable color stream
            logger.info(f"[{self.identifier}] Attempting to start RealSense pipeline with:")
            logger.info(f"  Color: {self.width}x{self.height} @ {self.fps} FPS")

            self.config.enable_stream(
                rs.stream.color,
                self.width,
                self.height,
                rs.format.bgr8,
                self.fps
            )

            # Enable depth stream if requested
            if self.depth_enabled:
                depth_width, depth_height = DriverConfig.REALSENSE_DEFAULT_DEPTH_RESOLUTION
                logger.info(f"  Depth: {depth_width}x{depth_height} @ {self.fps} FPS")
                # Use smaller resolution for depth to improve performance
                self.config.enable_stream(
                    rs.stream.depth,
                    depth_width,
                    depth_height,
                    rs.format.z16,
                    self.fps
                )
                # Create alignment object to align depth to color
                self.align = rs.align(rs.stream.color)

            # Start pipeline
            pipeline_profile = self.pipeline.start(self.config)
            self.pipeline_started = True  # Mark pipeline as successfully started

            # Get color sensor for exposure/gain control
            device = pipeline_profile.get_device()
            for sensor in device.query_sensors():
                if sensor.is_color_sensor():
                    self.color_sensor = sensor
                    break

            # Apply exposure and gain settings
            self._apply_exposure_gain()

            logger.info(f"Successfully connected to RealSense camera {self.identifier}")
            logger.info(f"  Resolution: {self.width}x{self.height} @ {self.fps} FPS")
            logger.info(f"  Depth enabled: {self.depth_enabled}")

        except RuntimeError as e:
            # Handle specific RealSense errors with helpful messages
            self.disconnect()
            error_msg = str(e)
            if "Couldn't resolve requests" in error_msg:
                raise DriverConnectionError(
                    f"RealSense camera {self.identifier}: Unsupported resolution/framerate combination. "
                    f"Requested {self.width}x{self.height} @ {self.fps} FPS. "
                    f"This may be caused by: (1) USB 2.0 connection (USB 3.0 required for high resolutions), "
                    f"(2) Unsupported FPS for this resolution, or (3) Camera model limitations. "
                    f"Try a lower resolution like 1280x720 or 640x480. Original error: {e}"
                )
            else:
                raise DriverConnectionError(f"Failed to connect to RealSense camera {self.identifier}: {e}")
        except Exception as e:
            self.disconnect()
            raise DriverConnectionError(
                f"Failed to connect to RealSense camera {self.identifier}: {e}"
            )

    def disconnect(self) -> None:
        """Closes the connection to the camera."""
        if self.pipeline:
            logger.info(f"Disconnecting RealSense camera {self.identifier}")
            try:
                # Only stop the pipeline if it was successfully started
                if self.pipeline_started:
                    self.pipeline.stop()
                    self.pipeline_started = False
            except Exception as e:
                logger.error(f"Error stopping RealSense pipeline: {e}")
            finally:
                self.pipeline = None
                self.config = None
                self.align = None
                self.color_sensor = None

    def get_frame(self) -> Union[None, np.ndarray, Tuple[Optional[np.ndarray], Optional[np.ndarray]]]:
        """Retrieves a single frame from the camera.

        Returns:
            - If depth_enabled=True: tuple (color_frame, depth_frame) where both are numpy arrays
            - If depth_enabled=False: single numpy array (color frame only)
            - Returns None (or (None, None) if depth enabled) if frame acquisition fails
        """
        if self.pipeline is None:
            return (None, None) if self.depth_enabled else None

        try:
            # Wait for frames with timeout
            frames = self.pipeline.wait_for_frames(timeout_ms=DriverConfig.REALSENSE_FRAME_TIMEOUT_MS)

            # Align depth to color if depth is enabled
            if self.depth_enabled and self.align:
                frames = self.align.process(frames)

            # Get color frame
            color_frame = frames.get_color_frame()
            if not color_frame:
                return (None, None) if self.depth_enabled else None

            # Convert to numpy array (already in BGR8 format)
            color_image = np.asanyarray(color_frame.get_data())

            # Get depth frame if enabled
            if self.depth_enabled:
                depth_frame = frames.get_depth_frame()
                if depth_frame:
                    # Convert to numpy array (uint16, values in mm)
                    depth_image = np.asanyarray(depth_frame.get_data())
                    return (color_image, depth_image)
                else:
                    # Depth enabled but no depth frame available
                    return (color_image, None)
            else:
                # Depth not enabled - return single frame
                return color_image

        except Exception as e:
            logger.error(f"Error getting frame from RealSense camera {self.identifier}: {e}")
            return (None, None) if self.depth_enabled else None

    def supports_depth(self) -> bool:
        """Indicates that RealSense cameras have depth capability.

        Note: This returns True to indicate hardware capability, but actual depth
        data is only returned from get_frame() when depth_enabled=True.
        """
        return True

    def _apply_exposure_gain(self) -> None:
        """Applies exposure and gain settings to the color sensor."""
        if not self.color_sensor:
            return

        try:
            # Set exposure mode
            if self.exposure_mode == "manual":
                # Disable auto exposure
                if self.color_sensor.supports(rs.option.enable_auto_exposure):
                    self.color_sensor.set_option(rs.option.enable_auto_exposure, 0)

                # Set manual exposure value
                if self.color_sensor.supports(rs.option.exposure):
                    # RealSense exposure is in microseconds
                    # Scale our value (typically 100-10000) appropriately
                    exposure_us = self.exposure_value * 10  # Simple scaling
                    self.color_sensor.set_option(rs.option.exposure, exposure_us)
            else:
                # Enable auto exposure
                if self.color_sensor.supports(rs.option.enable_auto_exposure):
                    self.color_sensor.set_option(rs.option.enable_auto_exposure, 1)

            # Set gain mode
            if self.gain_mode == "manual":
                # Disable auto gain (white balance)
                if self.color_sensor.supports(rs.option.enable_auto_white_balance):
                    self.color_sensor.set_option(rs.option.enable_auto_white_balance, 0)

                # Set manual gain value
                if self.color_sensor.supports(rs.option.gain):
                    # RealSense gain is typically 0-128
                    gain_value = min(128, max(0, self.gain_value))
                    self.color_sensor.set_option(rs.option.gain, gain_value)
            else:
                # Enable auto white balance
                if self.color_sensor.supports(rs.option.enable_auto_white_balance):
                    self.color_sensor.set_option(rs.option.enable_auto_white_balance, 1)

        except Exception as e:
            logger.error(f"Error applying exposure/gain settings: {e}")

    @staticmethod
    def list_devices() -> List[Dict[str, str]]:
        """Returns a list of available RealSense devices.

        Returns:
            List of dicts with keys 'identifier', 'name', 'camera_type'
        """
        if rs is None:
            # Library not installed, return empty list
            return []

        devices = []
        try:
            ctx = rs.context()
            device_list = ctx.query_devices()

            for device in device_list:
                # Get serial number (stable identifier)
                serial = device.get_info(rs.camera_info.serial_number)

                # Get model name
                name = device.get_info(rs.camera_info.name)

                # Create display name: "Model (serial)"
                display_name = f"{name} ({serial})"

                devices.append({
                    "identifier": serial,
                    "name": display_name,
                    "camera_type": CameraType.REALSENSE.value,
                })

        except Exception as e:
            logger.error(f"Error discovering RealSense cameras: {e}")
            return []

        return devices

    @staticmethod
    def get_supported_resolutions(serial_number: str) -> List[Dict[str, Any]]:
        """Query supported resolutions and framerates for a specific RealSense camera.

        Args:
            serial_number: Camera serial number (identifier)

        Returns:
            List of dicts with keys 'width', 'height', 'fps', 'format'
            Sorted by resolution (highest first) and FPS.
            Returns safe defaults if query fails.
        """
        if rs is None:
            logger.warning("pyrealsense2 not available, returning default resolutions")
            return RealSenseDriver._get_default_resolutions()

        try:
            ctx = rs.context()
            devices = ctx.query_devices()

            # Find device by serial number
            target_device = None
            for device in devices:
                if device.get_info(rs.camera_info.serial_number) == serial_number:
                    target_device = device
                    break

            if not target_device:
                logger.warning(f"RealSense camera {serial_number} not found, returning defaults")
                return RealSenseDriver._get_default_resolutions()

            # Get color sensor
            color_sensor = None
            for sensor in target_device.query_sensors():
                if sensor.is_color_sensor():
                    color_sensor = sensor
                    break

            if not color_sensor:
                logger.warning(f"No color sensor found for {serial_number}, returning defaults")
                return RealSenseDriver._get_default_resolutions()

            # Query all stream profiles
            stream_profiles = color_sensor.get_stream_profiles()

            # Extract unique resolution/FPS combinations for BGR8 format
            resolutions = []
            seen = set()

            for profile in stream_profiles:
                # Filter for video streams only
                if profile.stream_type() != rs.stream.color:
                    continue

                # Cast to video stream profile to access resolution
                video_profile = profile.as_video_stream_profile()

                # We want BGR8 format (native for color stream)
                if profile.format() != rs.format.bgr8:
                    continue

                width = video_profile.width()
                height = video_profile.height()
                fps = video_profile.fps()

                # Create unique key
                key = (width, height, fps)
                if key not in seen:
                    seen.add(key)
                    resolutions.append({
                        "width": width,
                        "height": height,
                        "fps": fps,
                        "format": "bgr8"
                    })

            # Sort by resolution (area) descending, then by FPS descending
            resolutions.sort(key=lambda x: (x["width"] * x["height"], x["fps"]), reverse=True)

            if not resolutions:
                logger.warning(f"No BGR8 color profiles found for {serial_number}, returning defaults")
                return RealSenseDriver._get_default_resolutions()

            logger.info(f"Found {len(resolutions)} supported resolutions for RealSense {serial_number}")
            return resolutions

        except Exception as e:
            logger.error(f"Error querying resolutions for RealSense {serial_number}: {e}")
            return RealSenseDriver._get_default_resolutions()

    @staticmethod
    def _get_default_resolutions() -> List[Dict[str, Any]]:
        """Returns a safe list of common resolutions supported by most RealSense cameras.

        These are fallback values when actual resolution query fails.
        """
        return [
            {"width": 1920, "height": 1080, "fps": 30, "format": "bgr8"},
            {"width": 1920, "height": 1080, "fps": 15, "format": "bgr8"},
            {"width": 1280, "height": 720, "fps": 30, "format": "bgr8"},
            {"width": 1280, "height": 720, "fps": 15, "format": "bgr8"},
            {"width": 640, "height": 480, "fps": 60, "format": "bgr8"},
            {"width": 640, "height": 480, "fps": 30, "format": "bgr8"},
            {"width": 640, "height": 480, "fps": 15, "format": "bgr8"},
        ]

    @staticmethod
    def detect_best_resolution(serial_number: str) -> Dict[str, Any]:
        """Automatically detect and return the best supported resolution for a camera.

        Args:
            serial_number: Camera serial number (identifier)

        Returns:
            Dict with 'width', 'height', 'fps' for the highest supported resolution.
            Falls back to 640x480@30 if detection fails.
        """
        try:
            resolutions = RealSenseDriver.get_supported_resolutions(serial_number)
            if resolutions:
                # Return the first one (highest resolution/FPS due to sorting)
                best = resolutions[0]
                logger.info(
                    f"Detected best resolution for {serial_number}: "
                    f"{best['width']}x{best['height']}@{best['fps']}fps"
                )
                return {
                    "width": best["width"],
                    "height": best["height"],
                    "fps": best["fps"]
                }
        except Exception as e:
            logger.error(f"Error detecting best resolution for {serial_number}: {e}")

        # Safe fallback
        logger.info(f"Using safe fallback resolution for {serial_number}: 640x480@30fps")
        return {
            "width": RealSenseDriver._DEFAULT_WIDTH,
            "height": RealSenseDriver._DEFAULT_HEIGHT,
            "fps": RealSenseDriver._DEFAULT_FPS
        }
