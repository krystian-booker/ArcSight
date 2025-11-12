import pytest
from unittest.mock import MagicMock, patch

from app.camera_discovery import discover_cameras, get_driver
from app.drivers.usb_driver import USBDriver
from app.drivers.genicam_driver import GenICamDriver
from app.drivers.oakd_driver import OAKDDriver


# --- Mock Data ---
MOCK_USB_DEVICES = [{"identifier": "0", "name": "USB Camera 0", "camera_type": "USB"}]
MOCK_GENICAM_DEVICES = [
    {
        "identifier": "SERIAL123",
        "name": "Test GenICam (SERIAL123)",
        "camera_type": "GenICam",
    }
]
MOCK_OAKD_DEVICES = [
    {"identifier": "MXID456", "name": "OAK-D MXID456", "camera_type": "OAK-D"}
]


# --- Tests for discover_cameras ---


@patch("app.camera_discovery.OAKDDriver.list_devices", return_value=MOCK_OAKD_DEVICES)
@patch(
    "app.camera_discovery.GenICamDriver.list_devices", return_value=MOCK_GENICAM_DEVICES
)
@patch("app.camera_discovery.USBDriver.list_devices", return_value=MOCK_USB_DEVICES)
def test_discover_cameras_all_new(mock_usb, mock_genicam, mock_oakd):
    """Test discovering all new cameras when no cameras exist yet."""
    result = discover_cameras(existing_identifiers=[])

    assert result["usb"] == MOCK_USB_DEVICES
    assert result["genicam"] == MOCK_GENICAM_DEVICES
    assert result["oakd"] == MOCK_OAKD_DEVICES
    mock_usb.assert_called_once()
    mock_genicam.assert_called_once()
    mock_oakd.assert_called_once()


@patch("app.camera_discovery.OAKDDriver.list_devices", return_value=MOCK_OAKD_DEVICES)
@patch(
    "app.camera_discovery.GenICamDriver.list_devices", return_value=MOCK_GENICAM_DEVICES
)
@patch("app.camera_discovery.USBDriver.list_devices", return_value=MOCK_USB_DEVICES)
def test_discover_cameras_some_exist(mock_usb, mock_genicam, mock_oakd):
    """Test that existing cameras are correctly filtered out."""
    existing = ["0", "MXID456"]  # One USB and one OAK-D exist

    result = discover_cameras(existing_identifiers=existing)

    assert result["usb"] == []  # This one should be filtered
    assert result["genicam"] == MOCK_GENICAM_DEVICES  # This one is new
    assert result["oakd"] == []  # This one should be filtered


@patch("app.camera_discovery.OAKDDriver.list_devices", return_value=[])
@patch("app.camera_discovery.GenICamDriver.list_devices", return_value=[])
@patch("app.camera_discovery.USBDriver.list_devices", return_value=[])
def test_discover_cameras_none_found(mock_usb, mock_genicam, mock_oakd):
    """Test the case where no new cameras are found by any driver."""
    result = discover_cameras(existing_identifiers=["0", "SERIAL123"])

    assert result["usb"] == []
    assert result["genicam"] == []
    assert result["oakd"] == []


@patch(
    "app.camera_discovery.USBDriver.list_devices",
    side_effect=RuntimeError("Driver failed"),
)
def test_discover_cameras_driver_exception(mock_usb):
    """Test that an exception from a driver's list_devices call propagates."""
    # We expect the exception to propagate up.
    # To test this thoroughly, you might want to test each driver independently
    # and ensure the others are still called if one fails, but for now, we assume
    # any exception from a list_devices call is a critical failure.
    with pytest.raises(RuntimeError, match="Driver failed"):
        discover_cameras(existing_identifiers=[])


def test_get_driver_usb():
    """Test that get_driver returns a USBDriver instance for 'USB' type."""
    mock_cam_data = MagicMock()
    mock_cam_data.camera_type = "USB"
    driver = get_driver(mock_cam_data)
    assert isinstance(driver, USBDriver)


def test_get_driver_genicam():
    """Test that get_driver returns a GenICamDriver instance for 'GenICam' type."""
    mock_cam_data = MagicMock()
    mock_cam_data.camera_type = "GenICam"
    driver = get_driver(mock_cam_data)
    assert isinstance(driver, GenICamDriver)


def test_get_driver_oakd():
    """Test that get_driver returns an OAKDDriver instance for 'OAK-D' type."""
    mock_cam_data = MagicMock()
    mock_cam_data.camera_type = "OAK-D"
    driver = get_driver(mock_cam_data)
    assert isinstance(driver, OAKDDriver)


def test_get_driver_unknown_type():
    """Test that get_driver raises a ValueError for an unknown camera type."""
    mock_cam_data = MagicMock()
    mock_cam_data.camera_type = "UnknownType"
    with pytest.raises(ValueError, match="Unknown camera type: UnknownType"):
        get_driver(mock_cam_data)
