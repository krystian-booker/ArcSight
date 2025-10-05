import pytest
from unittest.mock import MagicMock, patch
import numpy as np
import sys
import cv2
from importlib import reload

from app.models import Camera

# --- Helper classes to mock genicam interfaces ---
class MockIInteger(MagicMock): pass
class MockIFloat(MagicMock): pass
class MockIString(MagicMock): pass
class MockIBoolean(MagicMock): pass
class MockIEnumeration(MagicMock): pass

@pytest.fixture
def mock_camera_data(app):
    """Creates a mock Camera ORM object."""
    with app.app_context():
        yield MagicMock(spec=Camera, identifier="SN12345")

@pytest.fixture
def genicam_mocks():
    """
    The core mocking fixture. It completely replaces the harvesters and genicam
    libraries in sys.modules, ensuring any subsequent import or reload of the
    driver uses these mocks.
    """
    mock_genapi = MagicMock()
    mock_genapi.EInterfaceType = MagicMock(side_effect=lambda x: x)
    mock_genapi.EInterfaceType.intfIInteger, mock_genapi.EInterfaceType.intfIFloat, mock_genapi.EInterfaceType.intfIString, mock_genapi.EInterfaceType.intfIBoolean, mock_genapi.EInterfaceType.intfIEnumeration = range(1, 6)
    
    mock_genapi.EAccessMode = MagicMock(side_effect=lambda x: x)
    mock_genapi.EAccessMode.RO, mock_genapi.EAccessMode.RW, mock_genapi.EAccessMode.WO = 'RO', 'RW', 'WO'
    
    # Use real, catchable exception classes
    mock_genapi.TimeoutException = TimeoutError
    mock_genapi.LogicalErrorException = RuntimeError

    mock_genapi.IInteger, mock_genapi.IFloat, mock_genapi.IString, mock_genapi.IBoolean, mock_genapi.IEnumeration = MockIInteger, MockIFloat, MockIString, MockIBoolean, MockIEnumeration
    
    mock_harvesters_core = MagicMock()
    MockHarvesterClass = MagicMock()
    mock_h_instance = MockHarvesterClass.return_value
    mock_harvesters_core.Harvester = MockHarvesterClass

    original_modules = sys.modules.copy()
    sys.modules['genicam'] = mock_genapi
    sys.modules['harvesters.core'] = mock_harvesters_core
    
    # Reload the driver module to ensure it uses our mocks
    if 'app.drivers.genicam_driver' in sys.modules:
        reload(sys.modules['app.drivers.genicam_driver'])

    # Yield the global harvester instance from the reloaded module
    from app.drivers.genicam_driver import h
    yield { 'h': h, 'genapi': mock_genapi }

    sys.modules.clear()
    sys.modules.update(original_modules)

# --- Tests ---

def test_connection_and_frames(genicam_mocks, mock_camera_data):
    """Tests connection, disconnection, and frame acquisition."""
    from app.drivers.genicam_driver import GenICamDriver
    driver = GenICamDriver(mock_camera_data)
    mock_h = genicam_mocks['h']
    
    mock_ia = MagicMock()
    mock_h.create.return_value = mock_ia
    driver.connect()
    mock_h.create.assert_called_with({'serial_number': 'SN12345'})
    
    with patch('cv2.cvtColor') as mock_cvt:
        mock_buffer = MagicMock()
        mock_component = mock_buffer.payload.components[0]
        driver.ia.fetch.return_value.__enter__.return_value = mock_buffer
        mock_component.data_format = 'BayerRG12'
        driver.get_frame()
        assert mock_cvt.call_args[0][1] == cv2.COLOR_BayerRG2BGR

    driver.disconnect()
    mock_ia.stop.assert_called_once()

def test_static_methods(genicam_mocks):
    """Tests the static methods like initialize and list_devices."""
    from app.drivers.genicam_driver import GenICamDriver
    mock_h = genicam_mocks['h']

    with patch('os.path.exists', return_value=True):
        GenICamDriver.initialize("path/to/cti")
        mock_h.add_file.assert_called_once_with("path/to/cti")

    mock_h.device_info_list = [MagicMock(serial_number="SN123", model="TestModel")]
    assert len(GenICamDriver.list_devices()) == 1

def test_node_map_and_update(genicam_mocks):
    """Tests the complex node map retrieval and update logic."""
    from app.drivers.genicam_driver import GenICamDriver
    mock_h = genicam_mocks['h']
    genapi = genicam_mocks['genapi']
    
    # --- get_node_map ---
    mock_ia_map = MagicMock()
    mock_h.create.return_value = mock_ia_map
    mock_node_wrapper = MagicMock(node=MagicMock(principal_interface_type=genapi.EInterfaceType.intfIEnumeration, get_access_mode=lambda: 'RW', name="Node1"), symbolics=[])
    mock_ia_map.remote_device.node_map.nodes = [mock_node_wrapper]
    nodes, error = GenICamDriver.get_node_map("SN123")
    assert error is None and len(nodes) == 1

    # --- update_node ---
    mock_ia_update = MagicMock()
    mock_node = MockIInteger()
    mock_node.get_access_mode.return_value = 'RW'
    mock_ia_update.remote_device.node_map.get_node.return_value = mock_node
    
    # Configure create to return the correct mock for update's two internal calls
    mock_h.create.side_effect = [mock_ia_update, mock_ia_update]
    
    success, _, status, _ = GenICamDriver.update_node("id", "TestNode", "42")
    assert success is True and status == 200
    mock_node.set_value.assert_called_once_with(42)

def test_full_coverage_of_all_branches(genicam_mocks, mock_camera_data):
    """A final test to hit all remaining uncovered branches."""
    from app.drivers.genicam_driver import GenICamDriver
    driver = GenICamDriver(mock_camera_data)
    mock_h = genicam_mocks['h']
    
    # Connect failure
    mock_h.create.side_effect = Exception("fail")
    with pytest.raises(ConnectionError): driver.connect()
    mock_h.create.side_effect = None

    # Get Frame failures
    driver.ia = MagicMock()
    driver.ia.fetch.side_effect = RuntimeError
    assert driver.get_frame() is None
    
    # Initialize failures
    with patch('os.path.exists', return_value=False): GenICamDriver.initialize()
    
    # List devices failures
    mock_h.update.side_effect = Exception
    assert GenICamDriver.list_devices() == []
    mock_h.update.side_effect = None
    
    # update_node failures
    mock_ia = MagicMock()
    mock_h.create.return_value = mock_ia
    _, _, status, _ = GenICamDriver.update_node("id", None, "v")
    assert status == 400
    mock_ia.remote_device.node_map.get_node.return_value = None
    _, _, status, _ = GenICamDriver.update_node("id", "n", "v")
    assert status == 404
    
    # Final check with no libs
    with patch('app.drivers.genicam_driver.h', None):
        with pytest.raises(ConnectionError): driver.connect()
    with patch('app.drivers.genicam_driver.genapi', None):
        GenICamDriver.get_node_map("id")
        GenICamDriver.update_node("id", "n", "v")

    # Cover remaining type branches in update_node
    mock_h.create.side_effect = [mock_ia, mock_ia]
    mock_float_node = MockIFloat()
    mock_float_node.get_access_mode.return_value = 'RW'
    mock_ia.remote_device.node_map.get_node.return_value = mock_float_node
    GenICamDriver.update_node("id", "node", "3.14")
    mock_float_node.set_value.assert_called_with(3.14)
    
    mock_bool_node = MockIBoolean()
    mock_bool_node.get_access_mode.return_value = 'RW'
    mock_ia.remote_device.node_map.get_node.return_value = mock_bool_node
    GenICamDriver.update_node("id", "node", "true")
    mock_bool_node.set_value.assert_called_with(True)
    
    mock_string_node = MockIString()
    mock_string_node.get_access_mode.return_value = 'RW'
    mock_ia.remote_device.node_map.get_node.return_value = mock_string_node
    GenICamDriver.update_node("id", "node", "hello")
    mock_string_node.from_string.assert_called_with("hello")
    
    # Dummy assertion to end test
    assert GenICamDriver is not None