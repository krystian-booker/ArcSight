"""Camera configuration utilities and data structures."""

import json
import logging
from dataclasses import dataclass
from typing import Any, Dict, Optional, Tuple, Union

import numpy as np

logger = logging.getLogger(__name__)


@dataclass
class CameraConfig:
    """
    Unified camera configuration data structure.

    This dataclass provides a consistent interface for accessing camera
    configuration whether it comes from a database ORM object or a dictionary.
    """

    identifier: str
    camera_type: str = "usb"
    name: Optional[str] = None
    orientation: int = 0
    exposure_mode: str = "auto"
    exposure_value: Optional[int] = None
    gain_mode: str = "auto"
    gain_value: Optional[int] = None
    resolution_json: Optional[str] = None
    framerate: Optional[int] = None
    depth_enabled: bool = False
    camera_matrix_json: Optional[str] = None
    dist_coeffs_json: Optional[str] = None
    device_info_json: Optional[str] = None

    @classmethod
    def from_camera_data(cls, camera_data: Union[Dict[str, Any], Any]) -> "CameraConfig":
        """
        Create a CameraConfig from either a dictionary or ORM object.

        Args:
            camera_data: Either a dict or an ORM model instance (like Camera model)

        Returns:
            CameraConfig instance with all fields populated
        """
        def get_value(key: str, default: Any = None) -> Any:
            """Helper to get value from either dict or ORM object."""
            if isinstance(camera_data, dict):
                return camera_data.get(key, default)
            return getattr(camera_data, key, default)

        return cls(
            identifier=get_value("identifier", ""),
            camera_type=get_value("camera_type", get_value("type", "USB")),
            name=get_value("name"),
            orientation=get_value("orientation", 0) or 0,
            exposure_mode=get_value("exposure_mode", "auto") or "auto",
            exposure_value=get_value("exposure_value"),
            gain_mode=get_value("gain_mode", "auto") or "auto",
            gain_value=get_value("gain_value"),
            resolution_json=get_value("resolution_json"),
            framerate=get_value("framerate"),
            depth_enabled=get_value("depth_enabled", False) or False,
            camera_matrix_json=get_value("camera_matrix_json"),
            dist_coeffs_json=get_value("dist_coeffs_json"),
            device_info_json=get_value("device_info_json"),
        )

    def get_resolution(self) -> Optional[Tuple[int, int]]:
        """
        Parse and return resolution as (width, height) tuple.

        Returns:
            (width, height) tuple or None if not set or invalid
        """
        if not self.resolution_json:
            return None

        try:
            res = json.loads(self.resolution_json)
            width = res.get("width")
            height = res.get("height")
            if width and height:
                return (int(width), int(height))
        except (json.JSONDecodeError, ValueError, TypeError) as e:
            logger.warning(f"Invalid resolution_json: {self.resolution_json}, error: {e}")

        return None

    def get_camera_matrix(self) -> Optional[np.ndarray]:
        """
        Parse and return camera calibration matrix.

        Returns:
            3x3 numpy array or None if not set or invalid
        """
        if not self.camera_matrix_json:
            return None

        try:
            matrix = json.loads(self.camera_matrix_json)
            return np.array(matrix, dtype=np.float64)
        except (json.JSONDecodeError, ValueError, TypeError) as e:
            logger.warning(f"Invalid camera_matrix_json: {e}")
            return None

    def get_dist_coeffs(self) -> Optional[np.ndarray]:
        """
        Parse and return distortion coefficients.

        Returns:
            Numpy array of distortion coefficients or None if not set or invalid
        """
        if not self.dist_coeffs_json:
            return None

        try:
            coeffs = json.loads(self.dist_coeffs_json)
            return np.array(coeffs, dtype=np.float64)
        except (json.JSONDecodeError, ValueError, TypeError) as e:
            logger.warning(f"Invalid dist_coeffs_json: {e}")
            return None

    def get_device_info(self) -> Dict[str, Any]:
        """
        Parse and return device info dictionary.

        Returns:
            Dictionary of device information or empty dict if not set or invalid
        """
        if not self.device_info_json:
            return {}

        try:
            return json.loads(self.device_info_json)
        except (json.JSONDecodeError, TypeError) as e:
            logger.warning(f"Invalid device_info_json: {e}")
            return {}


def get_config_value(
    camera_data: Union[Dict[str, Any], Any],
    key: str,
    default: Any = None
) -> Any:
    """
    Get a configuration value from either a dict or ORM object.

    This is a standalone utility function for cases where you don't need
    the full CameraConfig dataclass.

    Args:
        camera_data: Either a dict or an ORM model instance
        key: The configuration key to retrieve
        default: Default value if key not found

    Returns:
        The configuration value or default
    """
    if isinstance(camera_data, dict):
        value = camera_data.get(key, default)
    else:
        value = getattr(camera_data, key, default)

    # Handle None values by returning default
    return value if value is not None else default


@dataclass
class PipelineManagerConfig:
    """
    Configuration for pipeline operations in camera manager.

    Encapsulates all the data needed to add/update a pipeline in the
    camera manager, avoiding long parameter lists.
    """

    pipeline_id: int
    pipeline_type: str
    pipeline_config_json: str
    camera_matrix_json: Optional[str] = None
    dist_coeffs_json: Optional[str] = None
