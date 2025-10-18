import pytest
from unittest.mock import MagicMock

from app.drivers.base_driver import BaseDriver
from app.models import Camera


# A concrete implementation of the abstract BaseDriver for testing purposes
class ConcreteDriver(BaseDriver):
    def connect(self):
        pass

    def disconnect(self):
        pass

    def get_frame(self):
        return None

    @staticmethod
    def list_devices():
        return []


@pytest.fixture
def mock_camera_data(app):
    """Creates a mock Camera ORM object for driver initialization."""
    with app.app_context():
        camera = MagicMock(spec=Camera)
        camera.identifier = "test_concrete_cam"
    return camera


def test_base_driver_initialization(mock_camera_data):
    """
    Tests that the BaseDriver's __init__ method correctly sets attributes.
    """
    # When
    driver = ConcreteDriver(mock_camera_data)

    # Then
    assert driver.camera_db_data == mock_camera_data
    assert driver.identifier == "test_concrete_cam"


def test_cannot_instantiate_abstract_base_driver(mock_camera_data):
    """
    Tests that the BaseDriver ABC cannot be instantiated directly
    without implementing the abstract methods.
    """
    with pytest.raises(TypeError) as excinfo:
        # This is expected to fail because the abstract methods are not implemented.
        # We are creating a class on the fly here that doesn't implement them.
        class IncompleteDriver(BaseDriver):
            pass

        IncompleteDriver(mock_camera_data)

    # Check that the error message contains information about the missing methods.
    # The exact message can vary slightly between Python versions.
    error_str = str(excinfo.value)
    assert "Can't instantiate abstract class" in error_str
    assert "connect" in error_str
    assert "disconnect" in error_str
    assert "get_frame" in error_str
    assert "list_devices" in error_str
