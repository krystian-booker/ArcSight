import json
import numpy as np

from .base_driver import BaseDriver

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
    _FRAME_ACQUIRE_TIMEOUT_MS = 5000  # 5 second timeout
    _DEFAULT_WIDTH = 1920
    _DEFAULT_HEIGHT = 1080
    _DEFAULT_FPS = 30
    _DEFAULT_DEPTH_WIDTH = 1280
    _DEFAULT_DEPTH_HEIGHT = 720

    def __init__(self, camera_data):
        super().__init__(camera_data)
        self.pipeline = None
        self.config = None
        self.align = None  # For aligning depth to color frame
        self.color_sensor = None  # For exposure/gain control

        # Parse resolution settings from JSON
        resolution_json = getattr(camera_data, "resolution_json", None)
        if resolution_json:
            try:
                res_data = json.loads(resolution_json)
                self.width = res_data.get("width", self._DEFAULT_WIDTH)
                self.height = res_data.get("height", self._DEFAULT_HEIGHT)
            except (json.JSONDecodeError, AttributeError):
                self.width = self._DEFAULT_WIDTH
                self.height = self._DEFAULT_HEIGHT
        else:
            self.width = self._DEFAULT_WIDTH
            self.height = self._DEFAULT_HEIGHT

        # Get framerate setting
        self.fps = getattr(camera_data, "framerate", None) or self._DEFAULT_FPS

        # Get depth enabled flag
        self.depth_enabled = getattr(camera_data, "depth_enabled", False)

        # Get exposure and gain settings
        self.exposure_mode = getattr(camera_data, "exposure_mode", "auto")
        self.exposure_value = getattr(camera_data, "exposure_value", 500)
        self.gain_mode = getattr(camera_data, "gain_mode", "auto")
        self.gain_value = getattr(camera_data, "gain_value", 50)

    def connect(self):
        """Establishes connection to the RealSense camera."""
        if rs is None:
            raise ConnectionError(
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
            self.config.enable_stream(
                rs.stream.color,
                self.width,
                self.height,
                rs.format.bgr8,
                self.fps
            )

            # Enable depth stream if requested
            if self.depth_enabled:
                # Use smaller resolution for depth to improve performance
                self.config.enable_stream(
                    rs.stream.depth,
                    self._DEFAULT_DEPTH_WIDTH,
                    self._DEFAULT_DEPTH_HEIGHT,
                    rs.format.z16,
                    self.fps
                )
                # Create alignment object to align depth to color
                self.align = rs.align(rs.stream.color)

            # Start pipeline
            pipeline_profile = self.pipeline.start(self.config)

            # Get color sensor for exposure/gain control
            device = pipeline_profile.get_device()
            for sensor in device.query_sensors():
                if sensor.is_color_sensor():
                    self.color_sensor = sensor
                    break

            # Apply exposure and gain settings
            self._apply_exposure_gain()

            print(f"Successfully connected to RealSense camera {self.identifier}")
            print(f"  Resolution: {self.width}x{self.height} @ {self.fps} FPS")
            print(f"  Depth enabled: {self.depth_enabled}")

        except Exception as e:
            self.disconnect()
            raise ConnectionError(
                f"Failed to connect to RealSense camera {self.identifier}: {e}"
            )

    def disconnect(self):
        """Closes the connection to the camera."""
        if self.pipeline:
            print(f"Disconnecting RealSense camera {self.identifier}")
            try:
                self.pipeline.stop()
            except Exception as e:
                print(f"Error stopping RealSense pipeline: {e}")
            finally:
                self.pipeline = None
                self.config = None
                self.align = None
                self.color_sensor = None

    def get_frame(self):
        """Retrieves a single frame from the camera.

        Returns:
            tuple: (color_frame, depth_frame) where:
                - color_frame is numpy array in BGR format
                - depth_frame is numpy array with uint16 depth values in mm
                - depth_frame is None if depth_enabled=False
            Returns (None, None) if frame acquisition fails.
        """
        if self.pipeline is None:
            return (None, None)

        try:
            # Wait for frames with timeout
            frames = self.pipeline.wait_for_frames(timeout_ms=self._FRAME_ACQUIRE_TIMEOUT_MS)

            # Align depth to color if depth is enabled
            if self.depth_enabled and self.align:
                frames = self.align.process(frames)

            # Get color frame
            color_frame = frames.get_color_frame()
            if not color_frame:
                return (None, None)

            # Convert to numpy array (already in BGR8 format)
            color_image = np.asanyarray(color_frame.get_data())

            # Get depth frame if enabled
            depth_image = None
            if self.depth_enabled:
                depth_frame = frames.get_depth_frame()
                if depth_frame:
                    # Convert to numpy array (uint16, values in mm)
                    depth_image = np.asanyarray(depth_frame.get_data())

            return (color_image, depth_image)

        except Exception as e:
            print(f"Error getting frame from RealSense camera {self.identifier}: {e}")
            return (None, None)

    def supports_depth(self):
        """RealSense cameras support depth."""
        return True

    def _apply_exposure_gain(self):
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
            print(f"Error applying exposure/gain settings: {e}")

    @staticmethod
    def list_devices():
        """Returns a list of available RealSense devices.

        Returns:
            list: List of dicts with keys 'identifier', 'name', 'camera_type'
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
                    "camera_type": "RealSense",
                })

        except Exception as e:
            print(f"Error discovering RealSense cameras: {e}")
            return []

        return devices
