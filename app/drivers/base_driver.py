from abc import ABC, abstractmethod

class BaseDriver(ABC):
    """
    Abstract base class for all camera drivers. Defines the common interface.
    """
    def __init__(self, camera_db_data):
        self.camera_db_data = camera_db_data
        self.identifier = camera_db_data['identifier']

    @abstractmethod
    def connect(self):
        """Establishes a connection to the camera."""
        pass

    @abstractmethod
    def disconnect(self):
        """Closes the connection to the camera."""
        pass

    @abstractmethod
    def get_frame(self):
        """Retrieves a single frame from the camera."""
        pass

    @staticmethod
    @abstractmethod
    def list_devices():
        """Returns a list of available devices for this driver type."""
        pass