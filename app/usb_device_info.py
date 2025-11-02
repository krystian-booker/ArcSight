"""
USB device information extraction module.

This module provides platform-specific functionality to enumerate USB cameras
and extract stable identifiers (Vendor ID, Product ID, Serial Number, etc.)
that persist across USB port changes.
"""

import logging
import sys
import cv2
from typing import List, Dict, Optional, Tuple

logger = logging.getLogger(__name__)


def get_usb_cameras_with_info() -> List[Dict[str, str]]:
    """
    Enumerate USB cameras and return them with stable unique identifiers.

    Returns a list of dictionaries with keys:
    - 'cv_index': OpenCV camera index (int as string)
    - 'identifier': Stable unique identifier for the camera
    - 'name': Human-readable camera name
    - 'vendor_id': USB Vendor ID (if available)
    - 'product_id': USB Product ID (if available)
    - 'serial_number': USB Serial Number (if available)
    - 'usb_path': USB device path/location (if available)
    """
    if sys.platform == "win32":
        return _get_usb_cameras_windows()
    elif sys.platform.startswith("linux"):
        return _get_usb_cameras_linux()
    elif sys.platform == "darwin":
        return _get_usb_cameras_macos()
    else:
        # Fallback to index-based detection
        return _get_usb_cameras_fallback()


def _get_usb_cameras_windows() -> List[Dict[str, str]]:
    """Windows-specific USB camera enumeration using WMI."""
    try:
        import wmi
    except ImportError:
        logger.warning("wmi module not available. Install with: pip install wmi")
        logger.info("Falling back to index-based camera detection")
        return _get_usb_cameras_fallback()

    cameras = []

    # First, get all available OpenCV camera indices
    cv_cameras = {}  # Maps index to basic camera info
    for i in range(10):
        cap = cv2.VideoCapture(i, cv2.CAP_DSHOW)  # Use DirectShow on Windows
        if cap.isOpened():
            # Try to get the camera backend name
            backend_name = (
                cap.getBackendName() if hasattr(cap, "getBackendName") else "unknown"
            )
            cv_cameras[i] = {"index": i, "backend": backend_name}
            cap.release()

    if not cv_cameras:
        return []

    # Now query WMI for USB device information
    try:
        c = wmi.WMI()

        # Query USB devices that are cameras (imaging devices)
        # We look for PNPEntity devices with specific classes
        usb_devices = []

        # Try to find cameras in imaging devices
        for device in c.Win32_PnPEntity():
            # Check if this is a camera device
            if device.PNPClass in ["Camera", "Image"]:
                device_id = device.DeviceID or ""
                name = device.Name or device.Caption or "Unknown USB Camera"

                # Parse VID/PID from device ID (format: USB\VID_XXXX&PID_XXXX\SERIAL)
                vid, pid, serial = _parse_windows_device_id(device_id)

                if vid and pid:
                    usb_devices.append(
                        {
                            "name": name,
                            "vendor_id": vid,
                            "product_id": pid,
                            "serial_number": serial or "",
                            "device_id": device_id,
                        }
                    )

        # Match USB devices to OpenCV indices
        # This is approximate since Windows doesn't provide direct mapping
        # We'll create identifiers for all found USB cameras
        for idx, (cv_idx, cv_info) in enumerate(cv_cameras.items()):
            if idx < len(usb_devices):
                device = usb_devices[idx]
                identifier = _create_identifier(
                    device["vendor_id"], device["product_id"], device["serial_number"]
                )

                cameras.append(
                    {
                        "cv_index": str(cv_idx),
                        "identifier": identifier,
                        "name": device["name"],
                        "vendor_id": device["vendor_id"],
                        "product_id": device["product_id"],
                        "serial_number": device["serial_number"],
                        "usb_path": device["device_id"],
                    }
                )
            else:
                # More OpenCV cameras than USB devices found via WMI
                # Fall back to index-based identifier
                cameras.append(
                    {
                        "cv_index": str(cv_idx),
                        "identifier": f"usb:index:{cv_idx}",
                        "name": f"USB Camera {cv_idx}",
                        "vendor_id": "",
                        "product_id": "",
                        "serial_number": "",
                        "usb_path": "",
                    }
                )

    except Exception as e:
        logger.error(f"Error querying WMI for USB devices: {e}")
        return _get_usb_cameras_fallback()

    return cameras


def _get_usb_cameras_linux() -> List[Dict[str, str]]:
    """Linux-specific USB camera enumeration using v4l2 and sysfs."""
    try:
        import pyudev
    except ImportError:
        logger.warning("pyudev module not available. Install with: pip install pyudev")
        logger.info("Falling back to index-based camera detection")
        return _get_usb_cameras_fallback()

    cameras = []
    context = pyudev.Context()

    # Find all video4linux devices
    for device in context.list_devices(subsystem="video4linux"):
        # Get the video device path (e.g., /dev/video0)
        device_path = device.device_node
        if not device_path:
            continue

        # Extract index from device path
        try:
            cv_index = int(device_path.replace("/dev/video", ""))
        except ValueError:
            continue

        # Try to open with OpenCV to verify it's accessible
        cap = cv2.VideoCapture(cv_index)
        if not cap.isOpened():
            cap.release()
            continue
        cap.release()

        # Get USB device info by traversing up the device tree
        usb_device = device
        while usb_device and usb_device.subsystem != "usb":
            usb_device = usb_device.parent

        if usb_device:
            vid = usb_device.get("ID_VENDOR_ID", "")
            pid = usb_device.get("ID_MODEL_ID", "")
            serial = usb_device.get("ID_SERIAL_SHORT", "")
            name = usb_device.get("ID_MODEL", f"USB Camera {cv_index}")
            usb_path = usb_device.get("DEVPATH", "")

            identifier = _create_identifier(vid, pid, serial, usb_path)

            cameras.append(
                {
                    "cv_index": str(cv_index),
                    "identifier": identifier,
                    "name": name,
                    "vendor_id": vid,
                    "product_id": pid,
                    "serial_number": serial,
                    "usb_path": usb_path,
                }
            )
        else:
            # Not a USB device, use index-based identifier
            cameras.append(
                {
                    "cv_index": str(cv_index),
                    "identifier": f"usb:index:{cv_index}",
                    "name": f"Camera {cv_index}",
                    "vendor_id": "",
                    "product_id": "",
                    "serial_number": "",
                    "usb_path": device_path,
                }
            )

    return cameras


def _get_usb_cameras_macos() -> List[Dict[str, str]]:
    """macOS-specific USB camera enumeration using system_profiler."""
    import subprocess

    cameras = []

    # First, get all available OpenCV camera indices
    cv_cameras = {}
    for i in range(10):
        cap = cv2.VideoCapture(i)
        if cap.isOpened():
            cv_cameras[i] = {"index": i}
            cap.release()

    if not cv_cameras:
        return []

    # Use system_profiler to get USB device information
    try:
        result = subprocess.run(
            ["system_profiler", "SPCameraDataType", "-json"],
            capture_output=True,
            text=True,
            timeout=10,
        )

        if result.returncode == 0:
            import json

            data = json.loads(result.stdout)
            camera_data = data.get("SPCameraDataType", [])

            # Map cameras to OpenCV indices (best effort)
            for idx, cv_idx in enumerate(cv_cameras.keys()):
                if idx < len(camera_data):
                    cam = camera_data[idx]
                    name = cam.get("_name", f"USB Camera {cv_idx}")

                    # system_profiler doesn't always give us VID/PID easily
                    # We'll try to get it from ioreg as a fallback
                    vid, pid, serial = _get_macos_camera_details(name)

                    identifier = _create_identifier(vid, pid, serial)

                    cameras.append(
                        {
                            "cv_index": str(cv_idx),
                            "identifier": identifier,
                            "name": name,
                            "vendor_id": vid,
                            "product_id": pid,
                            "serial_number": serial,
                            "usb_path": "",
                        }
                    )
                else:
                    # More CV cameras than system_profiler found
                    cameras.append(
                        {
                            "cv_index": str(cv_idx),
                            "identifier": f"usb:index:{cv_idx}",
                            "name": f"USB Camera {cv_idx}",
                            "vendor_id": "",
                            "product_id": "",
                            "serial_number": "",
                            "usb_path": "",
                        }
                    )

        else:
            # system_profiler failed, try ioreg approach
            return _get_usb_cameras_macos_ioreg()

    except (subprocess.TimeoutExpired, json.JSONDecodeError, Exception) as e:
        logger.error(f"Error querying macOS cameras with system_profiler: {e}")
        return _get_usb_cameras_macos_ioreg()

    return cameras


def _get_usb_cameras_macos_ioreg() -> List[Dict[str, str]]:
    """
    Fallback macOS USB camera enumeration using ioreg.
    ioreg provides more detailed USB information.
    """
    import subprocess
    import re

    cameras = []

    # Get all available OpenCV camera indices
    cv_cameras = {}
    for i in range(10):
        cap = cv2.VideoCapture(i)
        if cap.isOpened():
            cv_cameras[i] = {"index": i}
            cap.release()

    if not cv_cameras:
        return []

    try:
        # Query ioreg for USB video devices
        result = subprocess.run(
            ["ioreg", "-r", "-l", "-w", "0"],
            capture_output=True,
            text=True,
            timeout=10,
        )

        if result.returncode != 0:
            return _get_usb_cameras_fallback()

        # Parse ioreg output to find video devices
        usb_devices = []
        lines = result.stdout.split("\n")

        current_device = {}
        in_video_device = False

        for line in lines:
            # Look for USB video class devices or known camera patterns
            if "USB Video" in line or "UVC" in line or "Camera" in line:
                in_video_device = True
                current_device = {}

            if in_video_device:
                # Extract vendor ID
                if "idVendor" in line:
                    match = re.search(r'"idVendor"\s*=\s*(\w+)', line)
                    if match:
                        current_device["vendor_id"] = match.group(1).upper()

                # Extract product ID
                if "idProduct" in line:
                    match = re.search(r'"idProduct"\s*=\s*(\w+)', line)
                    if match:
                        current_device["product_id"] = match.group(1).upper()

                # Extract serial number
                if "USB Serial Number" in line or '"iSerialNumber"' in line:
                    match = re.search(r'".*Serial.*"\s*=\s*"([^"]+)"', line)
                    if match:
                        current_device["serial_number"] = match.group(1)

                # Extract product name
                if '"USB Product Name"' in line:
                    match = re.search(r'"USB Product Name"\s*=\s*"([^"]+)"', line)
                    if match:
                        current_device["name"] = match.group(1)

                # Check if we reached the end of this device entry
                if line.strip() == "" and current_device:
                    if "vendor_id" in current_device and "product_id" in current_device:
                        usb_devices.append(current_device.copy())
                    current_device = {}
                    in_video_device = False

        # Match USB devices to OpenCV indices (best effort, in order)
        for idx, cv_idx in enumerate(cv_cameras.keys()):
            if idx < len(usb_devices):
                device = usb_devices[idx]
                vid = device.get("vendor_id", "")
                pid = device.get("product_id", "")
                serial = device.get("serial_number", "")
                name = device.get("name", f"USB Camera {cv_idx}")

                identifier = _create_identifier(vid, pid, serial)

                cameras.append(
                    {
                        "cv_index": str(cv_idx),
                        "identifier": identifier,
                        "name": name,
                        "vendor_id": vid,
                        "product_id": pid,
                        "serial_number": serial,
                        "usb_path": "",
                    }
                )
            else:
                cameras.append(
                    {
                        "cv_index": str(cv_idx),
                        "identifier": f"usb:index:{cv_idx}",
                        "name": f"USB Camera {cv_idx}",
                        "vendor_id": "",
                        "product_id": "",
                        "serial_number": "",
                        "usb_path": "",
                    }
                )

    except Exception as e:
        logger.error(f"Error querying macOS cameras with ioreg: {e}")
        return _get_usb_cameras_fallback()

    return cameras


def _get_macos_camera_details(camera_name: str) -> tuple[str, str, str]:
    """
    Try to get VID/PID/Serial for a specific camera on macOS.

    Args:
        camera_name: The camera name from system_profiler

    Returns:
        Tuple of (vendor_id, product_id, serial_number)
    """
    import subprocess
    import re

    try:
        # Use ioreg to find this specific camera
        result = subprocess.run(
            ["ioreg", "-r", "-l", "-w", "0", "-n", camera_name],
            capture_output=True,
            text=True,
            timeout=5,
        )

        if result.returncode == 0:
            vid = ""
            pid = ""
            serial = ""

            for line in result.stdout.split("\n"):
                if "idVendor" in line:
                    match = re.search(r'"idVendor"\s*=\s*(\w+)', line)
                    if match:
                        vid = match.group(1).upper()

                if "idProduct" in line:
                    match = re.search(r'"idProduct"\s*=\s*(\w+)', line)
                    if match:
                        pid = match.group(1).upper()

                if "Serial Number" in line:
                    match = re.search(r'".*Serial.*"\s*=\s*"([^"]+)"', line)
                    if match:
                        serial = match.group(1)

            return vid, pid, serial

    except Exception:
        pass

    return "", "", ""


def _get_usb_cameras_fallback() -> List[Dict[str, str]]:
    """
    Fallback method using only OpenCV camera indices.
    This method doesn't provide stable identifiers across USB port changes.
    """
    cameras = []
    for i in range(10):
        cap = cv2.VideoCapture(i)
        if cap.isOpened():
            cameras.append(
                {
                    "cv_index": str(i),
                    "identifier": f"usb:index:{i}",
                    "name": f"USB Camera {i}",
                    "vendor_id": "",
                    "product_id": "",
                    "serial_number": "",
                    "usb_path": "",
                }
            )
            cap.release()
    return cameras


def _parse_windows_device_id(device_id: str) -> Tuple[str, str, str]:
    r"""
    Parse Windows device ID to extract VID, PID, and Serial Number.

    Example format: USB\VID_046D&PID_0825\5&2A8F6F5&0&2

    Returns: (vendor_id, product_id, serial_number)
    """
    vid = ""
    pid = ""
    serial = ""

    if not device_id:
        return vid, pid, serial

    parts = device_id.split("\\")

    # Parse VID and PID from second part
    if len(parts) >= 2:
        id_part = parts[1]
        if "VID_" in id_part:
            vid_start = id_part.find("VID_") + 4
            vid = id_part[vid_start : vid_start + 4]
        if "PID_" in id_part:
            pid_start = id_part.find("PID_") + 4
            pid = id_part[pid_start : pid_start + 4]

    # Parse serial from third part (if it doesn't look like a port path)
    if len(parts) >= 3:
        potential_serial = parts[2]
        # If it contains '&', it's likely a port path, not a serial
        if "&" not in potential_serial:
            serial = potential_serial

    return vid, pid, serial


def _create_identifier(vid: str, pid: str, serial: str, usb_path: str = "") -> str:
    """
    Create a stable unique identifier from USB device information.

    Priority:
    1. VID:PID:SERIAL (best - stable across ports)
    2. VID:PID:PATH (fallback - stable for same port)
    3. index:X (worst - not stable)
    """
    if vid and pid and serial:
        return f"usb:{vid}:{pid}:{serial}"
    elif vid and pid and usb_path:
        # Use a simplified path representation
        path_id = usb_path.replace("/", "_").replace("\\", "_")[-32:]  # Last 32 chars
        return f"usb:{vid}:{pid}:path_{path_id}"
    elif vid and pid:
        return f"usb:{vid}:{pid}"
    else:
        return ""


def find_camera_index_by_identifier(identifier: str) -> Optional[int]:
    """
    Find the current OpenCV camera index for a given stable identifier.

    Args:
        identifier: The stable identifier (e.g., 'usb:046D:0825:SERIAL123')

    Returns:
        The current OpenCV camera index, or None if not found
    """
    cameras = get_usb_cameras_with_info()

    for camera in cameras:
        if camera["identifier"] == identifier:
            return int(camera["cv_index"])

    return None
