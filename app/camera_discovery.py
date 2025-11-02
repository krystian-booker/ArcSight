import logging

from .drivers.usb_driver import USBDriver
from .drivers.genicam_driver import GenICamDriver
from .drivers.oakd_driver import OAKDDriver
from .drivers.realsense_driver import RealSenseDriver

logger = logging.getLogger(__name__)


# --- Driver Factory ---
def get_driver(camera_data):
    """
    Factory function to get the correct driver instance.

    Args:
        camera_data: Either a Camera ORM object or a dict with keys 'camera_type' and 'identifier'
    """
    # Support both ORM objects and dicts for backwards compatibility
    if isinstance(camera_data, dict):
        camera_type = camera_data["camera_type"]
    else:
        # ORM object
        camera_type = camera_data.camera_type

    if camera_type == "USB":
        return USBDriver(camera_data)
    elif camera_type == "GenICam":
        return GenICamDriver(camera_data)
    elif camera_type == "OAK-D":
        return OAKDDriver(camera_data)
    elif camera_type == "RealSense":
        return RealSenseDriver(camera_data)
    else:
        raise ValueError(f"Unknown camera type: {camera_type}")


# --- Camera Discovery ---
def discover_cameras(existing_identifiers):
    """Discovers all available cameras by polling the drivers."""
    logger.info("Discovering cameras...")
    usb_cams = [
        c
        for c in USBDriver.list_devices()
        if c["identifier"] not in existing_identifiers
    ]
    genicam_cams = [
        c
        for c in GenICamDriver.list_devices()
        if c["identifier"] not in existing_identifiers
    ]
    oakd_cams = [
        c
        for c in OAKDDriver.list_devices()
        if c["identifier"] not in existing_identifiers
    ]
    realsense_cams = [
        c
        for c in RealSenseDriver.list_devices()
        if c["identifier"] not in existing_identifiers
    ]

    logger.info(
        f"Found {len(usb_cams)} new USB, {len(genicam_cams)} new GenICam, "
        f"{len(oakd_cams)} new OAK-D, {len(realsense_cams)} new RealSense cameras"
    )
    return {
        "usb": usb_cams,
        "genicam": genicam_cams,
        "oakd": oakd_cams,
        "realsense": realsense_cams,
    }
