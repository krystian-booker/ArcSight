import logging
import time
from typing import Any, Dict, List, Optional, Union

import numpy as np

from .base_driver import BaseDriver

logger = logging.getLogger(__name__)

# Attempt to import depthai
try:
    import depthai as dai
except ImportError:  # pragma: no cover - handled gracefully by connect()
    dai = None


REQUIRED_DAI_VERSION = (3, 1, 0)


class OAKDDriver(BaseDriver):
    """Driver for Luxonis OAK-D series cameras using the DepthAI v3 API."""

    _FRAME_ACQUIRE_TIMEOUT_SEC = 5.0
    _FRAME_ACQUIRE_POLL_INTERVAL_SEC = 0.05

    def __init__(self, camera_db_data: Union[Dict[str, Any], Any]):
        super().__init__(camera_db_data)
        self.device: Optional["dai.Device"] = None
        self.pipeline: Optional["dai.Pipeline"] = None
        self.output_queue: Optional["dai.DataOutputQueue"] = None
        self._camera_socket: Optional[Any] = None

    _STREAM_NAME = "oakd_rgb"
    _OUTPUT_QUEUE_SIZE = 4
    _DEFAULT_FPS = 30
    _DEFAULT_RESOLUTION = "THE_1080_P"

    def connect(self) -> None:
        if dai is None:
            raise ConnectionError(
                "DepthAI library is not installed or failed to import."
            )

        try:
            self._ensure_supported_depthai_version()

            device_info = None
            if self.identifier:
                device_info = dai.DeviceInfo(self.identifier)

            self.device = dai.Device(device_info) if device_info else dai.Device()

            self.pipeline = dai.Pipeline()

            color_camera = self.pipeline.create(dai.node.ColorCamera)
            self._camera_socket = self._select_camera_socket(self.device)
            self._configure_camera_socket(color_camera, self._camera_socket)
            self._configure_color_camera(color_camera)

            xlink_out = self.pipeline.create(dai.node.XLinkOut)
            xlink_out.setStreamName(self._STREAM_NAME)
            xlink_input = getattr(xlink_out, "input", None)
            if xlink_input is None:
                raise RuntimeError("XLinkOut node is missing an input interface.")
            if hasattr(xlink_input, "setBlocking"):
                xlink_input.setBlocking(False)

            stream_source = getattr(color_camera, "video", None)
            if stream_source is None:
                stream_source = getattr(color_camera, "isp", None)
            if stream_source is None:
                raise RuntimeError("ColorCamera node does not expose a video/isp output.")
            stream_source.link(xlink_input)

            try:
                self.device.startPipeline(self.pipeline)
            except TypeError:
                # Older DepthAI releases expect the pipeline to be passed at construction time.
                # Recreate the device with the pipeline if startPipeline signature mismatches.
                self.device.close()
                self.device = (
                    dai.Device(self.pipeline, device_info)
                    if device_info
                    else dai.Device(self.pipeline)
                )

            try:
                self.output_queue = self.device.getOutputQueue(
                    self._STREAM_NAME,
                    maxSize=self._OUTPUT_QUEUE_SIZE,
                    blocking=False,
                )
            except TypeError:
                self.output_queue = self.device.getOutputQueue(self._STREAM_NAME)
                if hasattr(self.output_queue, "setBlocking"):
                    self.output_queue.setBlocking(False)

            logger.info(
                f"Successfully connected to OAK-D camera {self.identifier} at {self._camera_socket}"
            )
        except Exception as exc:  # pragma: no cover - cascades to caller
            self.disconnect()
            raise ConnectionError(
                f"Failed to connect to OAK-D camera {self.identifier}: {exc}"
            ) from exc

    def disconnect(self) -> None:
        if self.output_queue is not None:
            self.output_queue = None

        if self.device is not None:
            try:
                if hasattr(self.device, "stopPipeline"):
                    self.device.stopPipeline()
                self.device.close()
            except Exception:
                pass
            self.device = None

        self.pipeline = None

    def _configure_camera_socket(self, color_camera: Any, socket: Any) -> None:
        if socket is None or color_camera is None:
            return

        for setter_name in ("setBoardSocket", "setSocket", "setCameraSocket"):
            setter = getattr(color_camera, setter_name, None)
            if callable(setter):
                setter(socket)
                return

    def _configure_color_camera(self, color_camera: Any) -> None:
        if color_camera is None:
            return

        color_props = getattr(dai, "ColorCameraProperties", None)
        if color_props is None:
            return

        sensor_resolution = getattr(color_props, "SensorResolution", None)
        if sensor_resolution is not None and hasattr(color_camera, "setResolution"):
            resolution_enum = getattr(sensor_resolution, self._DEFAULT_RESOLUTION, None)
            if resolution_enum is not None:
                color_camera.setResolution(resolution_enum)
                if hasattr(color_camera, "setVideoSize"):
                    color_camera.setVideoSize(1920, 1080)

        if hasattr(color_camera, "setFps"):
            color_camera.setFps(self._DEFAULT_FPS)

        color_order = getattr(color_props, "ColorOrder", None)
        if color_order is not None and hasattr(color_camera, "setColorOrder"):
            bgr_order = getattr(color_order, "BGR", None)
            if bgr_order is not None:
                color_camera.setColorOrder(bgr_order)

        if hasattr(color_camera, "setInterleaved"):
            color_camera.setInterleaved(False)

        if hasattr(color_camera, "setPreviewKeepAspectRatio"):
            color_camera.setPreviewKeepAspectRatio(False)

    def get_frame(self) -> Optional[np.ndarray]:
        if self.output_queue is None:
            return None

        deadline = time.monotonic() + self._FRAME_ACQUIRE_TIMEOUT_SEC

        while True:
            try:
                frame_packet = self.output_queue.tryGet()
                if frame_packet is None:
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        return None
                    timeout = min(
                        self._FRAME_ACQUIRE_POLL_INTERVAL_SEC,
                        remaining,
                    )
                    frame_packet = self.output_queue.get(timeout=timeout)

                if frame_packet is None:
                    if time.monotonic() >= deadline:
                        return None
                    time.sleep(self._FRAME_ACQUIRE_POLL_INTERVAL_SEC)
                    continue

                return frame_packet.getCvFrame()
            except RuntimeError:
                return None

    @staticmethod
    def list_devices() -> List[Dict[str, str]]:
        if dai is None:
            return []

        devices = []
        try:
            get_devices = getattr(dai.Device, "getAllAvailableDevices", None)
            if not callable(get_devices):
                raise RuntimeError(
                    "DepthAI SDK does not provide a device enumeration API."
                )

            for device_info in get_devices():
                identifier = None
                for attr_name in ("getDeviceId", "getMxId", "getMxID"):
                    getter = getattr(device_info, attr_name, None)
                    if callable(getter):
                        identifier = getter()
                        break

                if identifier is None:
                    identifier = str(device_info)

                devices.append(
                    {
                        "identifier": identifier,
                        "name": f"OAK-D {identifier}",
                        "camera_type": "OAK-D",
                    }
                )
        except Exception as exc:
            logger.error(f"Error listing OAK-D cameras: {exc}")

        return devices

    def _ensure_supported_depthai_version(self) -> None:
        version_str = getattr(dai, "__version__", "")
        if not version_str:
            return

        parsed_version = self._parse_version(version_str)
        if parsed_version is None:
            return

        if parsed_version < REQUIRED_DAI_VERSION:
            raise ConnectionError(
                "DepthAI 3.1.0 or newer is required for OAK-D cameras. "
                f"Detected version: {version_str}"
            )

    @staticmethod
    def _parse_version(version_str: str) -> Optional[tuple]:
        parts = []
        for piece in version_str.split("."):
            try:
                parts.append(int(piece))
            except ValueError:
                break
        if not parts:
            return None
        while len(parts) < 3:
            parts.append(0)
        return tuple(parts[:3])

    def _select_camera_socket(self, device: Any) -> Any:
        default_socket = getattr(dai.CameraBoardSocket, "CAM_A", None)
        try:
            sockets = list(device.getConnectedCameras())
        except Exception:
            sockets = []

        if sockets:
            preferred_order = [
                getattr(dai.CameraBoardSocket, name, None)
                for name in ("CAM_A", "CAM_C", "CAM_B", "CAM_D")
            ]
            for preferred in preferred_order:
                if preferred in sockets:
                    return preferred
            return sockets[0]

        if default_socket is not None:
            return default_socket

        raise ConnectionError("No camera sockets available on the connected device.")
