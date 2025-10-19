from typing import Optional

from .base_driver import BaseDriver

# Attempt to import depthai
try:
    import depthai as dai
except ImportError:  # pragma: no cover - handled gracefully by connect()
    dai = None


REQUIRED_DAI_VERSION = (3, 1, 0)


class OAKDDriver(BaseDriver):
    """Driver for Luxonis OAK-D series cameras using the DepthAI v3 API."""

    def __init__(self, camera_db_data):
        super().__init__(camera_db_data)
        self.device: Optional["dai.Device"] = None
        self.pipeline: Optional["dai.Pipeline"] = None
        self.output_queue: Optional["dai.DataOutputQueue"] = None
        self._camera_socket = None

    def connect(self):
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

            try:
                self.pipeline = dai.Pipeline(self.device)
            except TypeError:
                self.pipeline = dai.Pipeline()

            camera_builder = self.pipeline.create(dai.node.Camera)
            self._camera_socket = self._select_camera_socket(self.device)
            camera = camera_builder.build(self._camera_socket)

            stream = camera.requestFullResolutionOutput(useHighestResolution=True)
            try:
                self.output_queue = stream.createOutputQueue(maxSize=4, blocking=False)
            except TypeError:
                self.output_queue = stream.createOutputQueue()

            try:
                self.pipeline.start()
            except TypeError:
                self.pipeline.start(self.device)

            print(
                f"Successfully connected to OAK-D camera {self.identifier} at {self._camera_socket}"
            )
        except Exception as exc:  # pragma: no cover - cascades to caller
            self.disconnect()
            raise ConnectionError(
                f"Failed to connect to OAK-D camera {self.identifier}: {exc}"
            ) from exc

    def disconnect(self):
        if self.output_queue is not None:
            self.output_queue = None

        if self.pipeline is not None:
            try:
                if hasattr(self.pipeline, "isRunning") and self.pipeline.isRunning():
                    self.pipeline.stop()
                else:
                    self.pipeline.stop()
            except Exception:
                pass
            self.pipeline = None

        if self.device is not None:
            try:
                self.device.close()
            except Exception:
                pass
            self.device = None

    def get_frame(self):
        if self.output_queue is None:
            return None

        frame = self.output_queue.tryGet()
        if frame is None:
            return None

        return frame.getCvFrame()

    @staticmethod
    def list_devices():
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
            print(f"Error listing OAK-D cameras: {exc}")

        return devices

    def _ensure_supported_depthai_version(self):
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
    def _parse_version(version_str):
        parts = []
        for piece in version_str.split('.'):
            try:
                parts.append(int(piece))
            except ValueError:
                break
        if not parts:
            return None
        while len(parts) < 3:
            parts.append(0)
        return tuple(parts[:3])

    def _select_camera_socket(self, device):
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
