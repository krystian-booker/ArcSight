import logging

from .drivers.usb_driver import USBDriver
from .drivers.genicam_driver import GenICamDriver
from .drivers.oakd_driver import OAKDDriver
from .drivers.realsense_driver import RealSenseDriver
from .enums import CameraType
from .utils.camera_config import CameraConfig

logger = logging.getLogger(__name__)


# --- Driver Factory ---
def get_driver(camera_data):
    """
    Factory function to get the correct driver instance.

    Args:
        camera_data: CameraConfig object, dict, or Camera ORM object.
                    Non-CameraConfig inputs will be automatically converted.

    Returns:
        An instance of the appropriate camera driver.
    """
    # Convert to CameraConfig if not already
    if not isinstance(camera_data, CameraConfig):
        camera_config = CameraConfig.from_camera_data(camera_data)
    else:
        camera_config = camera_data

    camera_type = camera_config.camera_type

    if camera_type == CameraType.USB.value:
        return USBDriver(camera_config)
    elif camera_type == CameraType.GENICAM.value:
        return GenICamDriver(camera_config)
    elif camera_type == CameraType.OAKD.value:
        return OAKDDriver(camera_config)
    elif camera_type == CameraType.REALSENSE.value:
        return RealSenseDriver(camera_config)
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
        CameraType.USB.value: usb_cams,
        CameraType.GENICAM.value: genicam_cams,
        CameraType.OAKD.value: oakd_cams,
        CameraType.REALSENSE.value: realsense_cams,
    }
