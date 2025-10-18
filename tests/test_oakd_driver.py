import pytest
from unittest.mock import MagicMock, patch
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
    assert oakd_driver.q_rgb is None


# --- Test connect ---
@patch("app.drivers.oakd_driver.dai")
def test_connect_success(mock_dai, oakd_driver):
    """Test a successful connection to an OAK-D camera."""
    # Arrange
    mock_device_info = MagicMock()
    mock_dai.DeviceInfo.return_value = mock_device_info

    mock_pipeline = MagicMock()
    mock_dai.Pipeline.return_value = mock_pipeline

    mock_device = MagicMock()
    mock_dai.Device.return_value = mock_device

    mock_queue = MagicMock()
    mock_device.getOutputQueue.return_value = mock_queue

    # Act
    oakd_driver.connect()

    # Assert
    mock_dai.DeviceInfo.assert_called_once_with("12345_mxid")
    mock_dai.Pipeline.assert_called_once()
    mock_dai.Device.assert_called_once_with(mock_pipeline, mock_device_info)
    mock_device.getOutputQueue.assert_called_once_with(
        name="rgb", maxSize=4, blocking=False
    )

    assert oakd_driver.device == mock_device
    assert oakd_driver.pipeline == mock_pipeline
    assert oakd_driver.q_rgb == mock_queue


@patch("app.drivers.oakd_driver.dai")
def test_connect_device_raises_exception(mock_dai, oakd_driver):
    """Test that ConnectionError is raised when dai.Device fails."""
    # Arrange
    mock_dai.DeviceInfo.return_value = MagicMock()
    mock_dai.Pipeline.return_value = MagicMock()
    mock_dai.Device.side_effect = RuntimeError("Device not found")

    # Act & Assert
    with pytest.raises(
        ConnectionError,
        match="Failed to connect to OAK-D camera 12345_mxid: Device not found",
    ):
        oakd_driver.connect()

    # Ensure cleanup was performed
    assert oakd_driver.device is None
    assert oakd_driver.pipeline is None
    assert oakd_driver.q_rgb is None


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
    oakd_driver.pipeline = "dummy_pipeline"
    oakd_driver.q_rgb = "dummy_queue"

    # Act
    oakd_driver.disconnect()

    # Assert
    mock_device.close.assert_called_once()
    assert oakd_driver.device is None
    assert oakd_driver.pipeline is None
    assert oakd_driver.q_rgb is None


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
    oakd_driver.q_rgb = mock_queue

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
    oakd_driver.q_rgb = mock_queue
    frame = oakd_driver.get_frame()
    assert frame is None


def test_get_frame_not_connected(oakd_driver):
    """Test get_frame when the driver is not connected (q_rgb is None)."""
    assert oakd_driver.q_rgb is None
    frame = oakd_driver.get_frame()
    assert frame is None


# --- Test list_devices ---
@patch("app.drivers.oakd_driver.dai")
def test_list_devices_success(mock_dai):
    """Test listing available OAK-D devices."""
    # Arrange
    mock_dev_info1 = MagicMock()
    mock_dev_info1.getMxId.return_value = "mxid_1"
    mock_dev_info2 = MagicMock()
    mock_dev_info2.getMxId.return_value = "mxid_2"

    mock_dai.Device.getAllAvailableDevices.return_value = [
        mock_dev_info1,
        mock_dev_info2,
    ]

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


@patch("app.drivers.oakd_driver.dai", None)
def test_list_devices_depthai_not_installed():
    """Test list_devices when the depthai library is not installed."""
    from app.drivers.oakd_driver import OAKDDriver as OAKDDriver_no_dai

    devices = OAKDDriver_no_dai.list_devices()
    assert devices == []
