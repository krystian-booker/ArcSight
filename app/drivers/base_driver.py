from abc import ABC, abstractmethod
from typing import Union
import numpy as np

from app.utils.camera_config import CameraConfig


class BaseDriver(ABC):
    """
    Abstract base class for all camera drivers. Defines the common interface.

    Drivers may raise the following exceptions from app.drivers.exceptions:
    - DriverConnectionError: When connect() fails
    - DriverDisconnectionError: When disconnect() fails
    - DriverFrameAcquisitionError: When get_frame() fails
    - DriverConfigurationError: When configuration is invalid
    - DriverNotAvailableError: When driver dependencies are not installed
    - DriverDiscoveryError: When list_devices() fails
    - DriverNodeError: When GenICam node operations fail (GenICam only)
    """

    def __init__(self, camera_config: CameraConfig):
        """
        Initialize the driver.

        Args:
            camera_config: CameraConfig dataclass containing camera configuration
        """
        self.identifier = camera_config.identifier
        self.camera_config = camera_config

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
