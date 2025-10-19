from .base_driver import BaseDriver

# Attempt to import depthai
try:
    # As per memory, import depthai before cv2 to avoid C++ conflicts.
    # While cv2 is already imported in this file, the critical part is the
    # initial application load order. This import is for functionality.
    import depthai as dai
except ImportError:  # pragma: no cover
    dai = None


class OAKDDriver(BaseDriver):
    """
    Driver for Luxonis OAK-D series cameras using the depthai library.
    """

    def __init__(self, camera_db_data):
        super().__init__(camera_db_data)
        self.device = None
        self.pipeline = None
        self.q_rgb = None

    def connect(self):
        if not dai:
            raise ConnectionError(
                "DepthAI library is not installed or failed to import."
            )

        try:
            # The identifier for OAK-D is the device ID (MXID).
            device_info = dai.DeviceInfo(self.identifier)

            # Define a pipeline for color camera output.
            self.pipeline = dai.Pipeline()
            cam_rgb = self.pipeline.create(dai.node.ColorCamera)
            xout_rgb = self.pipeline.create(dai.node.XLinkOut)

            xout_rgb.setStreamName("rgb")
            cam_rgb.setBoardSocket(dai.CameraBoardSocket.CAM_A)
            # It's better to configure resolution/fps from DB data if available,
            # but we'll use a sensible default for now.
            cam_rgb.setResolution(dai.ColorCameraProperties.SensorResolution.THE_1080_P)
            cam_rgb.setInterleaved(False)
            cam_rgb.setColorOrder(dai.ColorCameraProperties.ColorOrder.BGR)

            # Link nodes
            cam_rgb.video.link(xout_rgb.input)

            # Connect to the device and start the pipeline
            self.device = dai.Device(self.pipeline, device_info)

            # Get the output queue
            self.q_rgb = self.device.getOutputQueue(
                name="rgb", maxSize=4, blocking=False
            )

            print(f"Successfully connected to OAK-D camera {self.identifier}")

        except Exception as e:
            self.disconnect()  # Ensure cleanup on failed connection
            raise ConnectionError(
                f"Failed to connect to OAK-D camera {self.identifier}: {e}"
            )

    def disconnect(self):
        # The 'device' object in depthai handles closing the connection when it's destroyed.
        if self.device:
            print(f"Disconnecting OAK-D camera {self.identifier}")
            self.device.close()
        self.device = None
        self.pipeline = None
        self.q_rgb = None

    def get_frame(self):
        if not self.q_rgb:
            return None

        in_rgb = self.q_rgb.tryGet()

        if in_rgb is not None:
            # The getCvFrame() method returns a numpy array in BGR format.
            return in_rgb.getCvFrame()

        # If no frame is available, return None. The acquisition loop will handle it.
        return None

    @staticmethod
    def list_devices():
        """
        Returns a list of available OAK-D devices.
        """
        if not dai:
            return []

        devices = []
        try:
            # This returns a list of all connected OAK devices.
            for device_info in dai.Device.getAllAvailableDevices():
                devices.append(
                    {
                        "identifier": device_info.getDeviceId(),  # The unique identifier for OAK-D
                        "name": f"OAK-D {device_info.getDeviceId()}",
                        "camera_type": "OAK-D",
                    }
                )
        except Exception as e:
            print(f"Error listing OAK-D cameras: {e}")

        return devices
