import pytest
from unittest.mock import MagicMock, patch
import numpy as np

from app.drivers.usb_driver import USBDriver
from app.models import Camera


@pytest.fixture
def mock_camera_data(app):
    """Creates a mock Camera ORM object for the USB driver."""
    with app.app_context():
        camera = MagicMock(spec=Camera)
        camera.identifier = "0"  # A valid USB camera index
    return camera


@pytest.fixture
def usb_driver(mock_camera_data):
    """Returns an instance of the USBDriver."""
    return USBDriver(mock_camera_data)


@patch("cv2.VideoCapture")
def test_connect_success(mock_video_capture, usb_driver):
    """Test successful connection to a USB camera."""
    # Arrange
    mock_cap_instance = MagicMock()
    mock_cap_instance.isOpened.return_value = True
    mock_video_capture.return_value = mock_cap_instance

    # Act
    usb_driver.connect()

    # Assert
    mock_video_capture.assert_called_once_with(0)
    assert usb_driver.cap is mock_cap_instance


@patch("cv2.VideoCapture")
def test_connect_failure(mock_video_capture, usb_driver):
    """Test failed connection if camera cannot be opened."""
    # Arrange
    mock_cap_instance = MagicMock()
    mock_cap_instance.isOpened.return_value = False
    mock_video_capture.return_value = mock_cap_instance

    # Act & Assert
    with pytest.raises(ConnectionError, match="Failed to open USB camera at index 0"):
        usb_driver.connect()
    assert usb_driver.cap is None


def test_connect_invalid_identifier(mock_camera_data):
    """Test connection failure with a non-integer identifier."""
    # Arrange
    mock_camera_data.identifier = "not-a-number"
    driver = USBDriver(mock_camera_data)

    # Act & Assert
    with pytest.raises(
        ConnectionError, match="Invalid identifier for USB camera: 'not-a-number'"
    ):
        driver.connect()


def test_disconnect(usb_driver):
    """Test disconnecting from a camera."""
    # Arrange
    mock_cap = MagicMock()
    usb_driver.cap = mock_cap

    # Act
    usb_driver.disconnect()

    # Assert
    mock_cap.release.assert_called_once()
    assert usb_driver.cap is None


def test_disconnect_when_not_connected(usb_driver):
    """Test that disconnecting when not connected does nothing."""
    # Arrange
    assert usb_driver.cap is None

    # Act
    usb_driver.disconnect()

    # Assert
    assert usb_driver.cap is None


def test_get_frame_success(usb_driver):
    """Test successfully getting a frame."""
    # Arrange
    mock_frame = np.zeros((480, 640, 3), dtype=np.uint8)
    usb_driver.cap = MagicMock()
    usb_driver.cap.isOpened.return_value = True
    usb_driver.cap.read.return_value = (True, mock_frame)

    # Act
    frame = usb_driver.get_frame()

    # Assert
    assert np.array_equal(frame, mock_frame)


def test_get_frame_read_failure(usb_driver):
    """Test getting a frame when the read fails."""
    # Arrange
    usb_driver.cap = MagicMock()
    usb_driver.cap.isOpened.return_value = True
    usb_driver.cap.read.return_value = (False, None)

    # Act
    frame = usb_driver.get_frame()

    # Assert
    assert frame is None


def test_get_frame_not_connected(usb_driver):
    """Test getting a frame when not connected."""
    # Arrange
    assert usb_driver.cap is None

    # Act
    frame = usb_driver.get_frame()

    # Assert
    assert frame is None


def test_get_frame_lost_connection(usb_driver):
    """Test getting a frame when the connection is lost (isOpened returns False)."""
    # Arrange
    usb_driver.cap = MagicMock()
    usb_driver.cap.isOpened.return_value = False

    # Act
    frame = usb_driver.get_frame()

    # Assert
    assert frame is None


@patch("cv2.VideoCapture")
def test_list_devices(mock_video_capture):
    """Test listing available USB devices."""
    # Arrange
    # Simulate that cameras at index 0 and 2 are available, but 1 is not.
    mock_caps = {
        0: MagicMock(isOpened=MagicMock(return_value=True)),
        1: MagicMock(isOpened=MagicMock(return_value=False)),
        2: MagicMock(isOpened=MagicMock(return_value=True)),
    }

    def side_effect(index):
        # Default mock for indices we don't care about
        if index not in mock_caps:
            return MagicMock(isOpened=MagicMock(return_value=False))
        return mock_caps[index]

    mock_video_capture.side_effect = side_effect

    # Act
    devices = USBDriver.list_devices()

    # Assert
    assert len(devices) == 2
    assert devices[0] == {
        "identifier": "0",
        "name": "USB Camera 0",
        "camera_type": "USB",
    }
    assert devices[1] == {
        "identifier": "2",
        "name": "USB Camera 2",
        "camera_type": "USB",
    }

    # Check that release was called on the opened cameras
    mock_caps[0].release.assert_called_once()
    mock_caps[1].release.assert_not_called()  # Should not be called if not opened
    mock_caps[2].release.assert_called_once()
