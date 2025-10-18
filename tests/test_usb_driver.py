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
        camera.identifier = "usb:046D:0825:ABC123"  # A stable USB identifier
    return camera


@pytest.fixture
def usb_driver(mock_camera_data):
    """Returns an instance of the USBDriver."""
    return USBDriver(mock_camera_data)


@patch("app.drivers.usb_driver.find_camera_index_by_identifier")
@patch("cv2.VideoCapture")
def test_connect_success(mock_video_capture, mock_find_index, usb_driver):
    """Test successful connection to a USB camera."""
    # Arrange
    mock_find_index.return_value = 0  # Camera found at index 0
    mock_cap_instance = MagicMock()
    mock_cap_instance.isOpened.return_value = True
    mock_video_capture.return_value = mock_cap_instance

    # Act
    usb_driver.connect()

    # Assert
    mock_find_index.assert_called_once_with("usb:046D:0825:ABC123")
    mock_video_capture.assert_called_once_with(0)
    assert usb_driver.cap is mock_cap_instance
    assert usb_driver.resolved_index == 0


@patch("app.drivers.usb_driver.find_camera_index_by_identifier")
@patch("cv2.VideoCapture")
def test_connect_failure(mock_video_capture, mock_find_index, usb_driver):
    """Test failed connection if camera cannot be opened."""
    # Arrange
    mock_find_index.return_value = 0
    mock_cap_instance = MagicMock()
    mock_cap_instance.isOpened.return_value = False
    mock_video_capture.return_value = mock_cap_instance

    # Act & Assert
    with pytest.raises(ConnectionError, match="Failed to open USB camera at index 0"):
        usb_driver.connect()
    assert usb_driver.cap is None
    assert usb_driver.resolved_index is None


@patch("app.drivers.usb_driver.find_camera_index_by_identifier")
def test_connect_camera_not_found(mock_find_index, mock_camera_data):
    """Test connection failure when camera identifier is not found."""
    # Arrange
    mock_camera_data.identifier = "usb:046D:0825:NOTFOUND"
    driver = USBDriver(mock_camera_data)
    mock_find_index.return_value = None  # Camera not found

    # Act & Assert
    with pytest.raises(
        ConnectionError,
        match="USB camera with identifier 'usb:046D:0825:NOTFOUND' not found",
    ):
        driver.connect()


@patch("app.drivers.usb_driver.find_camera_index_by_identifier")
@patch("cv2.VideoCapture")
def test_connect_with_stable_identifier_success(
    mock_video_capture, mock_find_index, mock_camera_data
):
    """Test successful connection using a stable identifier."""
    # Arrange
    mock_camera_data.identifier = "usb:046D:0825:ABC123"
    driver = USBDriver(mock_camera_data)
    mock_find_index.return_value = 2  # Camera is at index 2

    mock_cap_instance = MagicMock()
    mock_cap_instance.isOpened.return_value = True
    mock_video_capture.return_value = mock_cap_instance

    # Act
    driver.connect()

    # Assert
    mock_find_index.assert_called_once_with("usb:046D:0825:ABC123")
    mock_video_capture.assert_called_once_with(2)
    assert driver.cap is mock_cap_instance
    assert driver.resolved_index == 2


@patch("app.drivers.usb_driver.find_camera_index_by_identifier")
def test_connect_with_stable_identifier_not_found(mock_find_index, mock_camera_data):
    """Test connection failure when stable identifier is not found."""
    # Arrange
    mock_camera_data.identifier = "usb:046D:0825:NOTFOUND"
    driver = USBDriver(mock_camera_data)
    mock_find_index.return_value = None  # Camera not found

    # Act & Assert
    with pytest.raises(
        ConnectionError,
        match="USB camera with identifier 'usb:046D:0825:NOTFOUND' not found",
    ):
        driver.connect()
    mock_find_index.assert_called_once_with("usb:046D:0825:NOTFOUND")


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


@patch("app.usb_device_info.get_usb_cameras_with_info")
def test_list_devices(mock_get_cameras):
    """Test listing available USB devices with stable identifiers."""
    # Arrange
    mock_get_cameras.return_value = [
        {
            "cv_index": "0",
            "identifier": "usb:046D:0825:ABC123",
            "name": "Logitech Webcam",
            "vendor_id": "046D",
            "product_id": "0825",
            "serial_number": "ABC123",
            "usb_path": "",
        },
        {
            "cv_index": "2",
            "identifier": "usb:1234:5678:XYZ789",
            "name": "Generic USB Camera",
            "vendor_id": "1234",
            "product_id": "5678",
            "serial_number": "XYZ789",
            "usb_path": "",
        },
    ]

    # Act
    devices = USBDriver.list_devices()

    # Assert
    assert len(devices) == 2

    # Check first device
    assert devices[0]["identifier"] == "usb:046D:0825:ABC123"
    assert devices[0]["camera_type"] == "USB"
    assert "046D:0825" in devices[0]["name"]  # VID:PID should be in name
    assert "ABC123" in devices[0]["name"]  # Serial should be in name

    # Check second device
    assert devices[1]["identifier"] == "usb:1234:5678:XYZ789"
    assert devices[1]["camera_type"] == "USB"
    assert "1234:5678" in devices[1]["name"]

    mock_get_cameras.assert_called_once()


@patch("app.usb_device_info.get_usb_cameras_with_info")
def test_list_devices_fallback_format(mock_get_cameras):
    """Test listing devices that use fallback identifiers (no serial)."""
    # Arrange
    mock_get_cameras.return_value = [
        {
            "cv_index": "0",
            "identifier": "usb:index:0",
            "name": "USB Camera 0",
            "vendor_id": "",
            "product_id": "",
            "serial_number": "",
            "usb_path": "",
        }
    ]

    # Act
    devices = USBDriver.list_devices()

    # Assert
    assert len(devices) == 1
    assert devices[0]["identifier"] == "usb:index:0"
    assert devices[0]["name"] == "USB Camera 0"
    mock_get_cameras.assert_called_once()
