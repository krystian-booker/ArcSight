import pytest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch, call
import numpy as np

from app.drivers.oakd_driver import OAKDDriver
from app.models import Camera


@pytest.fixture
def mock_camera_data(app):
    """Creates a mock Camera ORM object for the OAK-D driver."""
    with app.app_context():
        camera = MagicMock(spec=Camera)
        camera.identifier = "12345_mxid"
    return camera


@pytest.fixture
def oakd_driver(mock_camera_data):
    """Returns an instance of the OAKDDriver."""
    return OAKDDriver(mock_camera_data)


# --- Test __init__ ---
def test_initialization(oakd_driver, mock_camera_data):
    """Test that the driver initializes correctly."""
    assert oakd_driver.camera_db_data == mock_camera_data
    assert oakd_driver.identifier == "12345_mxid"
    assert oakd_driver.device is None
    assert oakd_driver.pipeline is None
    assert oakd_driver.output_queue is None


# --- Test connect ---
@patch("app.drivers.oakd_driver.dai")
def test_connect_success(mock_dai, oakd_driver):
    """Test a successful connection to an OAK-D camera."""
    # Arrange
    mock_dai.__version__ = "3.1.0"
    mock_device_info = MagicMock()
    mock_dai.DeviceInfo.return_value = mock_device_info

    mock_device = MagicMock()
    mock_socket = MagicMock(name="CAM_A")
    mock_device.getConnectedCameras.return_value = [mock_socket]
    mock_dai.Device.return_value = mock_device

    mock_pipeline = MagicMock()
    mock_dai.Pipeline.return_value = mock_pipeline

    mock_dai.node = MagicMock()
    mock_dai.node.ColorCamera = MagicMock(name="ColorCameraNode")
    mock_dai.node.XLinkOut = MagicMock(name="XLinkOutNode")

    mock_color_camera = MagicMock()
    mock_color_camera.video = MagicMock()
    mock_color_camera.video.link = MagicMock()
    mock_xout = MagicMock()
    mock_xout.input = MagicMock()
    mock_pipeline.create.side_effect = [mock_color_camera, mock_xout]

    mock_dai.CameraBoardSocket = MagicMock()
    mock_dai.CameraBoardSocket.CAM_A = mock_socket

    mock_dai.ColorCameraProperties = SimpleNamespace(
        SensorResolution=SimpleNamespace(THE_1080_P="1080p"),
        ColorOrder=SimpleNamespace(BGR="BGR"),
    )

    mock_queue = MagicMock()
    mock_device.getOutputQueue.return_value = mock_queue

    # Act
    oakd_driver.connect()

    # Assert
    mock_dai.DeviceInfo.assert_called_once_with("12345_mxid")
    mock_dai.Device.assert_called_once_with(mock_device_info)
    mock_dai.Pipeline.assert_called_once()
    assert mock_pipeline.create.call_args_list == [
        call(mock_dai.node.ColorCamera),
        call(mock_dai.node.XLinkOut),
    ]
    mock_color_camera.setBoardSocket.assert_called_once_with(mock_socket)
    mock_color_camera.setResolution.assert_called_once_with("1080p")
    mock_color_camera.setVideoSize.assert_called_once_with(1920, 1080)
    mock_color_camera.setFps.assert_called_once_with(oakd_driver._DEFAULT_FPS)
    mock_color_camera.setColorOrder.assert_called_once_with("BGR")
    mock_color_camera.setInterleaved.assert_called_once_with(False)
    mock_color_camera.setPreviewKeepAspectRatio.assert_called_once_with(False)
    mock_xout.setStreamName.assert_called_once_with(oakd_driver._STREAM_NAME)
    mock_xout.input.setBlocking.assert_called_once_with(False)
    mock_color_camera.video.link.assert_called_once_with(mock_xout.input)
    mock_device.startPipeline.assert_called_once_with(mock_pipeline)
    mock_device.getOutputQueue.assert_called_once_with(
        oakd_driver._STREAM_NAME, maxSize=oakd_driver._OUTPUT_QUEUE_SIZE, blocking=False
    )

    assert oakd_driver.device == mock_device
    assert oakd_driver.pipeline == mock_pipeline
    assert oakd_driver.output_queue == mock_queue


@patch("app.drivers.oakd_driver.dai")
def test_connect_device_raises_exception(mock_dai, oakd_driver):
    """Test that ConnectionError is raised when dai.Device fails."""
    # Arrange
    mock_dai.__version__ = "3.1.0"
    mock_dai.DeviceInfo.return_value = MagicMock()
    mock_device = MagicMock()
    mock_dai.Device.return_value = mock_device
    mock_dai.Pipeline.side_effect = RuntimeError("Pipeline creation failed")

    # Act & Assert
    with pytest.raises(
        ConnectionError,
        match="Failed to connect to OAK-D camera 12345_mxid: Pipeline creation failed",
    ):
        oakd_driver.connect()

    # Ensure cleanup was performed
    mock_device.stopPipeline.assert_called_once()
    mock_device.close.assert_called_once()
    assert oakd_driver.device is None
    assert oakd_driver.pipeline is None
    assert oakd_driver.output_queue is None


@patch("app.drivers.oakd_driver.dai")
def test_connect_retries_pipeline_start_signature(mock_dai, oakd_driver):
    """Test that start(self.device) is attempted when start() TypeErrors."""
    mock_dai.__version__ = "3.1.0"
    mock_device_info = MagicMock()
    mock_dai.DeviceInfo.return_value = mock_device_info

    first_device = MagicMock(name="DeviceWithoutPipeline")
    first_device.getConnectedCameras.return_value = []
    first_device.startPipeline.side_effect = TypeError("needs pipeline")

    second_device = MagicMock(name="DeviceWithPipeline")
    second_device.getOutputQueue.return_value = MagicMock()

    mock_dai.Device.side_effect = [first_device, second_device]

    mock_pipeline = MagicMock()
    mock_dai.Pipeline.return_value = mock_pipeline

    mock_dai.node = MagicMock()
    mock_dai.node.ColorCamera = MagicMock(name="ColorCameraNode")
    mock_dai.node.XLinkOut = MagicMock(name="XLinkOutNode")

    mock_color_camera = MagicMock()
    mock_color_camera.video = MagicMock()
    mock_color_camera.video.link = MagicMock()
    mock_xout = MagicMock()
    mock_xout.input = MagicMock()
    mock_pipeline.create.side_effect = [mock_color_camera, mock_xout]

    mock_dai.ColorCameraProperties = SimpleNamespace(
        SensorResolution=SimpleNamespace(THE_1080_P="1080p"),
        ColorOrder=SimpleNamespace(BGR="BGR"),
    )

    mock_dai.CameraBoardSocket = MagicMock()
    mock_dai.CameraBoardSocket.CAM_A = MagicMock()

    oakd_driver.connect()

    assert mock_dai.Device.call_args_list == [
        call(mock_device_info),
        call(mock_pipeline, mock_device_info),
    ]
    first_device.startPipeline.assert_called_once_with(mock_pipeline)
    first_device.close.assert_called_once()
    second_device.getOutputQueue.assert_called_once_with(
        oakd_driver._STREAM_NAME, maxSize=oakd_driver._OUTPUT_QUEUE_SIZE, blocking=False
    )
    assert oakd_driver.device == second_device
    assert oakd_driver.pipeline == mock_pipeline


@patch("app.drivers.oakd_driver.dai", None)
def test_connect_depthai_not_installed(oakd_driver):
    """Test connect when the depthai library is not installed."""
    # Need to re-import the class to see the patched 'dai' module
    from app.drivers.oakd_driver import OAKDDriver as OAKDDriver_no_dai

    driver = OAKDDriver_no_dai(oakd_driver.camera_db_data)
    with pytest.raises(ConnectionError, match="DepthAI library is not installed"):
        driver.connect()


# --- Test disconnect ---
@patch("app.drivers.oakd_driver.dai")
def test_disconnect_when_connected(mock_dai, oakd_driver):
    """Test disconnecting a connected device."""
    # Arrange
    mock_device = MagicMock()
    oakd_driver.device = mock_device
    oakd_driver.pipeline = MagicMock()
    oakd_driver.output_queue = "dummy_queue"

    # Act
    oakd_driver.disconnect()

    # Assert
    mock_device.stopPipeline.assert_called_once()
    mock_device.close.assert_called_once()
    assert oakd_driver.device is None
    assert oakd_driver.pipeline is None
    assert oakd_driver.output_queue is None


def test_disconnect_when_not_connected(oakd_driver):
    """Test that disconnecting when not connected does nothing and doesn't raise errors."""
    assert oakd_driver.device is None
    oakd_driver.disconnect()
    assert oakd_driver.device is None


# --- Test get_frame ---
def test_get_frame_success(oakd_driver):
    """Test successfully getting a frame."""
    # Arrange
    mock_frame_data = np.zeros((1080, 1920, 3), dtype=np.uint8)
    mock_dai_frame = MagicMock()
    mock_dai_frame.getCvFrame.return_value = mock_frame_data

    mock_queue = MagicMock()
    mock_queue.tryGet.return_value = mock_dai_frame
    oakd_driver.output_queue = mock_queue

    # Act
    frame = oakd_driver.get_frame()

    # Assert
    assert np.array_equal(frame, mock_frame_data)
    mock_queue.tryGet.assert_called_once()
    mock_dai_frame.getCvFrame.assert_called_once()


def test_get_frame_no_frame_available(oakd_driver):
    """Test get_frame when the queue's tryGet returns None."""
    mock_queue = MagicMock()
    mock_queue.tryGet.return_value = None
    mock_queue.get.side_effect = RuntimeError("Queue is closed")
    oakd_driver.output_queue = mock_queue
    frame = oakd_driver.get_frame()
    assert frame is None


def test_get_frame_waits_for_blocking_fetch(oakd_driver, monkeypatch):
    """Test get_frame retrieves a frame via the blocking queue fetch when tryGet is empty."""
    mock_frame_data = np.ones((720, 1280, 3), dtype=np.uint8)
    mock_dai_frame = MagicMock()
    mock_dai_frame.getCvFrame.return_value = mock_frame_data

    mock_queue = MagicMock()
    mock_queue.tryGet.return_value = None
    mock_queue.get.return_value = mock_dai_frame

    # Reduce timeout to keep the test snappy
    monkeypatch.setattr(
        OAKDDriver,
        "_FRAME_ACQUIRE_TIMEOUT_SEC",
        0.1,
        raising=False,
    )
    monkeypatch.setattr(
        OAKDDriver,
        "_FRAME_ACQUIRE_POLL_INTERVAL_SEC",
        0.01,
        raising=False,
    )

    oakd_driver.output_queue = mock_queue
    frame = oakd_driver.get_frame()

    assert np.array_equal(frame, mock_frame_data)
    mock_queue.tryGet.assert_called()
    mock_queue.get.assert_called()


def test_get_frame_not_connected(oakd_driver):
    """Test get_frame when the driver is not connected (no output queue)."""
    assert oakd_driver.output_queue is None
    frame = oakd_driver.get_frame()
    assert frame is None


# --- Test list_devices ---
@patch("app.drivers.oakd_driver.dai")
def test_list_devices_success(mock_dai):
    """Test listing available OAK-D devices."""
    # Arrange
    mock_dev_info1 = MagicMock()
    mock_dev_info1.getDeviceId.return_value = "mxid_1"
    mock_dev_info2 = MagicMock()
    mock_dev_info2.getDeviceId.return_value = "mxid_2"

    mock_devices = [
        mock_dev_info1,
        mock_dev_info2,
    ]
    mock_dai.Device.getAllAvailableDevices.return_value = mock_devices

    # Act
    devices = OAKDDriver.list_devices()

    # Assert
    assert len(devices) == 2
    assert devices[0] == {
        "identifier": "mxid_1",
        "name": "OAK-D mxid_1",
        "camera_type": "OAK-D",
    }
    assert devices[1] == {
        "identifier": "mxid_2",
        "name": "OAK-D mxid_2",
        "camera_type": "OAK-D",
    }


@patch("app.drivers.oakd_driver.dai")
def test_list_devices_raises_exception(mock_dai):
    """Test list_devices when the underlying library call fails."""
    mock_dai.Device.getAllAvailableDevices.side_effect = RuntimeError(
        "Failed to query devices"
    )
    devices = OAKDDriver.list_devices()
    assert devices == []


@patch("app.drivers.oakd_driver.dai")
def test_connect_rejects_old_depthai(mock_dai, oakd_driver):
    mock_dai.__version__ = "2.21.0"
    mock_dai.Device = MagicMock()
    with pytest.raises(ConnectionError, match="DepthAI 3.1.0 or newer is required"):
        oakd_driver.connect()
    mock_dai.Device.assert_not_called()


@patch("app.drivers.oakd_driver.dai", None)
def test_list_devices_depthai_not_installed():
    """Test list_devices when the depthai library is not installed."""
    from app.drivers.oakd_driver import OAKDDriver as OAKDDriver_no_dai

    devices = OAKDDriver_no_dai.list_devices()
    assert devices == []
