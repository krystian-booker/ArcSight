from abc import ABC, abstractmethod
from typing import Dict, Any, Union
import numpy as np

from app.utils.camera_config import CameraConfig


class BaseDriver(ABC):
    """
    Abstract base class for all camera drivers. Defines the common interface.
    """

    def __init__(self, camera_data: Union[Dict[str, Any], CameraConfig, Any]):
        """
        Initialize the driver.

        Args:
            camera_data: Either a CameraConfig dataclass, a dict, or a Camera ORM object
        """
        # Support CameraConfig, dicts, and ORM objects for backwards compatibility
        if isinstance(camera_data, CameraConfig):
            self.identifier = camera_data.identifier
            self.camera_db_data = camera_data
        elif isinstance(camera_data, dict):
            self.identifier = camera_data.get("identifier", "")
            self.camera_db_data = camera_data
        else:
            # ORM object
            self.identifier = getattr(camera_data, "identifier", "")
            self.camera_db_data = camera_data

    @abstractmethod
    def connect(self) -> None:  # pragma: no cover
        """Establishes a connection to the camera."""
        pass

    @abstractmethod
    def disconnect(self) -> None:  # pragma: no cover
        """Closes the connection to the camera."""
        pass

    @abstractmethod
    def get_frame(self) -> Union[np.ndarray, tuple, None]:  # pragma: no cover
        """Retrieves a single frame from the camera.

        Returns:
            For standard cameras: numpy array (BGR format) or None if failed
            For depth-capable cameras: tuple (color_frame, depth_frame) where
                                      depth_frame can be None if depth disabled
        """
        pass

    def supports_depth(self) -> bool:
        """Indicates whether this driver supports depth data.

        Returns:
            bool: True if the driver can provide depth frames, False otherwise
        """
        return False

    @staticmethod
    @abstractmethod
    def list_devices() -> list:  # pragma: no cover
        """Returns a list of available devices for this driver type."""
        pass
