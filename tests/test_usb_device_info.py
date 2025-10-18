from unittest.mock import patch
from app.usb_device_info import (
    find_camera_index_by_identifier,
    _create_identifier,
    _parse_windows_device_id,
)


def test_create_identifier():
    """Test creation of stable identifiers from USB device info."""
    # Best case: VID + PID + Serial
    identifier = _create_identifier("046D", "0825", "ABC123")
    assert identifier == "usb:046D:0825:ABC123"

    # Fallback: VID + PID + Path (no serial)
    identifier = _create_identifier(
        "046D", "0825", "", "/devices/pci0000:00/0000:00:14.0/usb1/1-2"
    )
    assert identifier.startswith("usb:046D:0825:path_")
    assert "1-2" in identifier

    # Just VID + PID
    identifier = _create_identifier("046D", "0825", "")
    assert identifier == "usb:046D:0825"

    # Missing info
    identifier = _create_identifier("", "", "")
    assert identifier == ""


def test_parse_windows_device_id():
    """Test parsing Windows device IDs."""
    # Standard format with port path (has &, so won't be treated as serial)
    device_id = r"USB\VID_046D&PID_0825\5&2A8F6F5"
    vid, pid, serial = _parse_windows_device_id(device_id)
    assert vid == "046D"
    assert pid == "0825"
    assert serial == ""  # Contains '&', so not treated as serial

    # Format with actual serial (no & in third part)
    device_id = r"USB\VID_046D&PID_0825\ABC123DEF456"
    vid, pid, serial = _parse_windows_device_id(device_id)
    assert vid == "046D"
    assert pid == "0825"
    assert serial == "ABC123DEF456"

    # Missing parts
    device_id = r"USB\VID_046D&PID_0825"
    vid, pid, serial = _parse_windows_device_id(device_id)
    assert vid == "046D"
    assert pid == "0825"
    assert serial == ""

    # Empty device ID
    vid, pid, serial = _parse_windows_device_id("")
    assert vid == ""
    assert pid == ""
    assert serial == ""


@patch("app.usb_device_info.get_usb_cameras_with_info")
def test_find_camera_index_by_identifier(mock_get_cameras):
    """Test finding camera index by stable identifier."""
    # Mock camera list
    mock_get_cameras.return_value = [
        {
            "cv_index": "0",
            "identifier": "usb:046D:0825:ABC123",
            "name": "Logitech Webcam",
        },
        {
            "cv_index": "2",
            "identifier": "usb:1234:5678:XYZ789",
            "name": "Generic Camera",
        },
    ]

    # Find existing camera
    index = find_camera_index_by_identifier("usb:046D:0825:ABC123")
    assert index == 0

    index = find_camera_index_by_identifier("usb:1234:5678:XYZ789")
    assert index == 2

    # Try to find non-existent camera
    index = find_camera_index_by_identifier("usb:0000:0000:NOTFOUND")
    assert index is None


@patch("app.usb_device_info.sys.platform", "win32")
@patch("app.usb_device_info._get_usb_cameras_windows")
def test_get_usb_cameras_with_info_windows(mock_windows):
    """Test that Windows platform calls the Windows-specific function."""
    mock_windows.return_value = [
        {
            "cv_index": "0",
            "identifier": "usb:046D:0825:ABC123",
            "name": "Test Camera",
            "vendor_id": "046D",
            "product_id": "0825",
            "serial_number": "ABC123",
            "usb_path": "",
        }
    ]

    from app.usb_device_info import get_usb_cameras_with_info

    cameras = get_usb_cameras_with_info()
    assert len(cameras) == 1
    assert cameras[0]["identifier"] == "usb:046D:0825:ABC123"
    mock_windows.assert_called_once()


@patch("app.usb_device_info.sys.platform", "linux")
@patch("app.usb_device_info._get_usb_cameras_linux")
def test_get_usb_cameras_with_info_linux(mock_linux):
    """Test that Linux platform calls the Linux-specific function."""
    mock_linux.return_value = []

    from app.usb_device_info import get_usb_cameras_with_info

    get_usb_cameras_with_info()
    mock_linux.assert_called_once()
