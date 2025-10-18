from abc import ABC, abstractmethod


class BaseDriver(ABC):
    """
    Abstract base class for all camera drivers. Defines the common interface.
    """

    def __init__(self, camera_data):
        """
        Initialize the driver.

        Args:
            camera_data: Either a Camera ORM object or a dict with key 'identifier'
        """
        # Support both ORM objects and dicts for backwards compatibility
        if isinstance(camera_data, dict):
            self.identifier = camera_data["identifier"]
            self.camera_db_data = camera_data  # Store for potential future use
        else:
            # ORM object
            self.identifier = camera_data.identifier
            self.camera_db_data = camera_data

    @abstractmethod
    def connect(self):  # pragma: no cover
        """Establishes a connection to the camera."""
        pass

    @abstractmethod
    def disconnect(self):  # pragma: no cover
        """Closes the connection to the camera."""
        pass

    @abstractmethod
    def get_frame(self):  # pragma: no cover
        """Retrieves a single frame from the camera."""
        pass

    @staticmethod
    @abstractmethod
    def list_devices():  # pragma: no cover
        """Returns a list of available devices for this driver type."""
        pass
