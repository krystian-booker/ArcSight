import pytest
from unittest.mock import MagicMock, patch, call
import numpy as np
import json

from app.drivers.realsense_driver import RealSenseDriver
from app.models import Camera


@pytest.fixture
def mock_camera_data(app):
    """Creates a mock Camera ORM object for the RealSense driver."""
    with app.app_context():
        camera = MagicMock(spec=Camera)
        camera.identifier = "123456789"
        camera.resolution_json = json.dumps({"width": 1920, "height": 1080})
        camera.framerate = 30
        camera.depth_enabled = True
        camera.exposure_mode = "auto"
        camera.exposure_value = 500
        camera.gain_mode = "auto"
        camera.gain_value = 50
    return camera


@pytest.fixture
def mock_camera_data_dict():
    """Creates a mock camera data dict for the RealSense driver."""
    return {
        "identifier": "123456789",
        "camera_type": "RealSense",
        "resolution_json": json.dumps({"width": 1280, "height": 720}),
        "framerate": 60,
        "depth_enabled": False,
        "exposure_mode": "manual",
        "exposure_value": 1000,
        "gain_mode": "manual",
        "gain_value": 64,
    }


@pytest.fixture
def realsense_driver(mock_camera_data):
    """Returns an instance of the RealSenseDriver."""
    return RealSenseDriver(mock_camera_data)


# --- Test __init__ ---
def test_initialization_with_orm_object(realsense_driver, mock_camera_data):
    """Test that the driver initializes correctly with ORM object."""
    assert realsense_driver.camera_db_data == mock_camera_data
    assert realsense_driver.identifier == "123456789"
    assert realsense_driver.pipeline is None
    assert realsense_driver.config is None
    assert realsense_driver.align is None
    assert realsense_driver.color_sensor is None
    assert realsense_driver.width == 1920
    assert realsense_driver.height == 1080
    assert realsense_driver.fps == 30
    assert realsense_driver.depth_enabled == True
    assert realsense_driver.exposure_mode == "auto"
    assert realsense_driver.exposure_value == 500
    assert realsense_driver.gain_mode == "auto"
    assert realsense_driver.gain_value == 50


def test_initialization_with_dict(mock_camera_data_dict):
    """Test that the driver initializes correctly with dict."""
    driver = RealSenseDriver(mock_camera_data_dict)
    assert driver.identifier == "123456789"
    assert driver.width == 1280
    assert driver.height == 720
    assert driver.fps == 60
    assert driver.depth_enabled == False
    assert driver.exposure_mode == "manual"
    assert driver.exposure_value == 1000
    assert driver.gain_mode == "manual"
    assert driver.gain_value == 64


def test_initialization_with_defaults(app):
    """Test that the driver uses defaults when fields are missing."""
    with app.app_context():
        camera = MagicMock(spec=Camera)
        camera.identifier = "test123"
        # All optional fields are None
        camera.resolution_json = None
        camera.framerate = None
        camera.depth_enabled = None
        camera.exposure_mode = None
        camera.exposure_value = None
        camera.gain_mode = None
        camera.gain_value = None

    driver = RealSenseDriver(camera)
    assert driver.width == driver._DEFAULT_WIDTH
    assert driver.height == driver._DEFAULT_HEIGHT
    assert driver.fps == driver._DEFAULT_FPS
    assert driver.depth_enabled == False
    assert driver.exposure_mode == "auto"
    assert driver.exposure_value == 500
    assert driver.gain_mode == "auto"
    assert driver.gain_value == 50


# --- Test connect ---
@patch("app.drivers.realsense_driver.rs")
def test_connect_success_with_depth(mock_rs, realsense_driver):
    """Test a successful connection to a RealSense camera with depth enabled."""
    # Arrange
    mock_pipeline = MagicMock()
    mock_config = MagicMock()
    mock_align = MagicMock()
    mock_profile = MagicMock()
    mock_device = MagicMock()
    mock_sensor = MagicMock()

    mock_rs.pipeline.return_value = mock_pipeline
    mock_rs.config.return_value = mock_config
    mock_rs.align.return_value = mock_align
    mock_pipeline.start.return_value = mock_profile
    mock_profile.get_device.return_value = mock_device
    mock_sensor.is_color_sensor.return_value = True
    mock_device.query_sensors.return_value = [mock_sensor]

    # Act
    realsense_driver.connect()

    # Assert
    mock_rs.pipeline.assert_called_once()
    mock_rs.config.assert_called_once()
    mock_config.enable_device.assert_called_once_with("123456789")
    mock_config.enable_stream.assert_any_call(
        mock_rs.stream.color, 1920, 1080, mock_rs.format.bgr8, 30
    )
    mock_config.enable_stream.assert_any_call(
        mock_rs.stream.depth,
        realsense_driver._DEFAULT_DEPTH_WIDTH,
        realsense_driver._DEFAULT_DEPTH_HEIGHT,
        mock_rs.format.z16,
        30,
    )
    mock_rs.align.assert_called_once_with(mock_rs.stream.color)
    mock_pipeline.start.assert_called_once_with(mock_config)
    assert realsense_driver.pipeline == mock_pipeline
    assert realsense_driver.config == mock_config
    assert realsense_driver.align == mock_align
    assert realsense_driver.color_sensor == mock_sensor


@patch("app.drivers.realsense_driver.rs")
def test_connect_success_without_depth(mock_rs, mock_camera_data):
    """Test a successful connection to a RealSense camera with depth disabled."""
    # Arrange
    mock_camera_data.depth_enabled = False
    driver = RealSenseDriver(mock_camera_data)

    mock_pipeline = MagicMock()
    mock_config = MagicMock()
    mock_profile = MagicMock()
    mock_device = MagicMock()
    mock_sensor = MagicMock()

    mock_rs.pipeline.return_value = mock_pipeline
    mock_rs.config.return_value = mock_config
    mock_pipeline.start.return_value = mock_profile
    mock_profile.get_device.return_value = mock_device
    mock_sensor.is_color_sensor.return_value = True
    mock_device.query_sensors.return_value = [mock_sensor]

    # Act
    driver.connect()

    # Assert
    # Should only enable color stream, not depth
    assert mock_config.enable_stream.call_count == 1
    mock_config.enable_stream.assert_called_once_with(
        mock_rs.stream.color, 1920, 1080, mock_rs.format.bgr8, 30
    )
    # align should not be created
    assert driver.align is None


@patch("app.drivers.realsense_driver.rs", None)
def test_connect_library_not_installed(realsense_driver):
    """Test that connection raises error when pyrealsense2 is not installed."""
    with pytest.raises(ConnectionError, match="pyrealsense2 library is not installed"):
        realsense_driver.connect()


@patch("app.drivers.realsense_driver.rs")
def test_connect_failure_calls_disconnect(mock_rs, realsense_driver):
    """Test that connection failure calls disconnect to cleanup."""
    # Arrange
    mock_rs.pipeline.side_effect = Exception("Connection failed")

    # Act & Assert
    with pytest.raises(ConnectionError, match="Failed to connect to RealSense camera"):
        realsense_driver.connect()

    # Verify pipeline is reset to None
    assert realsense_driver.pipeline is None


# --- Test disconnect ---
def test_disconnect_when_connected(realsense_driver):
    """Test disconnecting a connected camera."""
    # Arrange
    mock_pipeline = MagicMock()
    realsense_driver.pipeline = mock_pipeline
    realsense_driver.config = MagicMock()
    realsense_driver.align = MagicMock()
    realsense_driver.color_sensor = MagicMock()

    # Act
    realsense_driver.disconnect()

    # Assert
    mock_pipeline.stop.assert_called_once()
    assert realsense_driver.pipeline is None
    assert realsense_driver.config is None
    assert realsense_driver.align is None
    assert realsense_driver.color_sensor is None


def test_disconnect_when_not_connected(realsense_driver):
    """Test disconnecting when no connection exists."""
    # Should not raise an error
    realsense_driver.disconnect()
    assert realsense_driver.pipeline is None


def test_disconnect_with_error(realsense_driver):
    """Test disconnect handles errors gracefully."""
    # Arrange
    mock_pipeline = MagicMock()
    mock_pipeline.stop.side_effect = Exception("Stop failed")
    realsense_driver.pipeline = mock_pipeline

    # Act - should not raise exception
    realsense_driver.disconnect()

    # Assert - pipeline should still be reset
    assert realsense_driver.pipeline is None


# --- Test get_frame ---
@patch("app.drivers.realsense_driver.rs")
@patch("app.drivers.realsense_driver.np")
def test_get_frame_success_with_depth(mock_np, mock_rs, realsense_driver):
    """Test getting a frame with depth data."""
    # Arrange
    mock_pipeline = MagicMock()
    mock_align = MagicMock()
    realsense_driver.pipeline = mock_pipeline
    realsense_driver.align = mock_align

    mock_frames = MagicMock()
    mock_aligned_frames = MagicMock()
    mock_color_frame = MagicMock()
    mock_depth_frame = MagicMock()

    mock_pipeline.wait_for_frames.return_value = mock_frames
    mock_align.process.return_value = mock_aligned_frames
    mock_aligned_frames.get_color_frame.return_value = mock_color_frame
    mock_aligned_frames.get_depth_frame.return_value = mock_depth_frame

    color_array = np.zeros((1080, 1920, 3), dtype=np.uint8)
    depth_array = np.zeros((720, 1280), dtype=np.uint16)
    mock_np.asanyarray.side_effect = [color_array, depth_array]

    # Act
    result = realsense_driver.get_frame()

    # Assert
    mock_pipeline.wait_for_frames.assert_called_once_with(timeout_ms=5000)
    mock_align.process.assert_called_once_with(mock_frames)
    mock_aligned_frames.get_color_frame.assert_called_once()
    mock_aligned_frames.get_depth_frame.assert_called_once()
    assert len(result) == 2
    assert isinstance(result[0], np.ndarray)  # color
    assert isinstance(result[1], np.ndarray)  # depth


@patch("app.drivers.realsense_driver.rs")
@patch("app.drivers.realsense_driver.np")
def test_get_frame_success_without_depth(mock_np, mock_rs, mock_camera_data):
    """Test getting a frame without depth data."""
    # Arrange
    mock_camera_data.depth_enabled = False
    driver = RealSenseDriver(mock_camera_data)

    mock_pipeline = MagicMock()
    driver.pipeline = mock_pipeline
    driver.align = None  # No align when depth disabled

    mock_frames = MagicMock()
    mock_color_frame = MagicMock()

    mock_pipeline.wait_for_frames.return_value = mock_frames
    mock_frames.get_color_frame.return_value = mock_color_frame

    color_array = np.zeros((1080, 1920, 3), dtype=np.uint8)
    mock_np.asanyarray.return_value = color_array

    # Act
    result = driver.get_frame()

    # Assert
    assert len(result) == 2
    assert isinstance(result[0], np.ndarray)  # color
    assert result[1] is None  # no depth


def test_get_frame_not_connected(realsense_driver):
    """Test get_frame returns None when not connected."""
    result = realsense_driver.get_frame()
    assert result == (None, None)


@patch("app.drivers.realsense_driver.rs")
def test_get_frame_no_color_frame(mock_rs, realsense_driver):
    """Test get_frame returns None when color frame is missing."""
    # Arrange
    mock_pipeline = MagicMock()
    mock_align = MagicMock()
    realsense_driver.pipeline = mock_pipeline
    realsense_driver.align = mock_align

    mock_frames = MagicMock()
    mock_aligned_frames = MagicMock()
    mock_aligned_frames.get_color_frame.return_value = None

    mock_pipeline.wait_for_frames.return_value = mock_frames
    mock_align.process.return_value = mock_aligned_frames

    # Act
    result = realsense_driver.get_frame()

    # Assert
    assert result == (None, None)


@patch("app.drivers.realsense_driver.rs")
def test_get_frame_exception(mock_rs, realsense_driver):
    """Test get_frame handles exceptions gracefully."""
    # Arrange
    mock_pipeline = MagicMock()
    realsense_driver.pipeline = mock_pipeline
    mock_pipeline.wait_for_frames.side_effect = Exception("Frame error")

    # Act
    result = realsense_driver.get_frame()

    # Assert
    assert result == (None, None)


# --- Test supports_depth ---
def test_supports_depth(realsense_driver):
    """Test that RealSense driver reports depth support."""
    assert realsense_driver.supports_depth() == True


# --- Test list_devices ---
@patch("app.drivers.realsense_driver.rs")
def test_list_devices_success(mock_rs):
    """Test listing available RealSense devices."""
    # Arrange
    mock_ctx = MagicMock()
    mock_rs.context.return_value = mock_ctx

    mock_device1 = MagicMock()
    mock_device1.get_info.side_effect = lambda x: "f123456" if x == mock_rs.camera_info.serial_number else "D435i"

    mock_device2 = MagicMock()
    mock_device2.get_info.side_effect = lambda x: "f789012" if x == mock_rs.camera_info.serial_number else "D455"

    mock_ctx.query_devices.return_value = [mock_device1, mock_device2]

    # Act
    devices = RealSenseDriver.list_devices()

    # Assert
    assert len(devices) == 2
    assert devices[0]["identifier"] == "f123456"
    assert devices[0]["name"] == "D435i (f123456)"
    assert devices[0]["camera_type"] == "RealSense"
    assert devices[1]["identifier"] == "f789012"
    assert devices[1]["name"] == "D455 (f789012)"


@patch("app.drivers.realsense_driver.rs", None)
def test_list_devices_library_not_installed():
    """Test list_devices returns empty list when library not installed."""
    devices = RealSenseDriver.list_devices()
    assert devices == []


@patch("app.drivers.realsense_driver.rs")
def test_list_devices_exception(mock_rs):
    """Test list_devices handles exceptions gracefully."""
    # Arrange
    mock_rs.context.side_effect = Exception("Discovery error")

    # Act
    devices = RealSenseDriver.list_devices()

    # Assert
    assert devices == []


# --- Test _apply_exposure_gain ---
@patch("app.drivers.realsense_driver.rs")
def test_apply_exposure_gain_manual_mode(mock_rs, realsense_driver):
    """Test applying manual exposure and gain settings."""
    # Arrange
    mock_sensor = MagicMock()
    mock_sensor.supports.return_value = True
    realsense_driver.color_sensor = mock_sensor
    realsense_driver.exposure_mode = "manual"
    realsense_driver.exposure_value = 100
    realsense_driver.gain_mode = "manual"
    realsense_driver.gain_value = 64

    # Act
    realsense_driver._apply_exposure_gain()

    # Assert
    # Check that auto exposure was disabled
    mock_sensor.set_option.assert_any_call(mock_rs.option.enable_auto_exposure, 0)
    # Check that exposure was set (scaled by 10)
    mock_sensor.set_option.assert_any_call(mock_rs.option.exposure, 1000)
    # Check that auto white balance was disabled
    mock_sensor.set_option.assert_any_call(mock_rs.option.enable_auto_white_balance, 0)
    # Check that gain was set
    mock_sensor.set_option.assert_any_call(mock_rs.option.gain, 64)


@patch("app.drivers.realsense_driver.rs")
def test_apply_exposure_gain_auto_mode(mock_rs, realsense_driver):
    """Test applying auto exposure and gain settings."""
    # Arrange
    mock_sensor = MagicMock()
    mock_sensor.supports.return_value = True
    realsense_driver.color_sensor = mock_sensor
    realsense_driver.exposure_mode = "auto"
    realsense_driver.gain_mode = "auto"

    # Act
    realsense_driver._apply_exposure_gain()

    # Assert
    mock_sensor.set_option.assert_any_call(mock_rs.option.enable_auto_exposure, 1)
    mock_sensor.set_option.assert_any_call(mock_rs.option.enable_auto_white_balance, 1)


def test_apply_exposure_gain_no_sensor(realsense_driver):
    """Test _apply_exposure_gain when no color sensor available."""
    # Arrange
    realsense_driver.color_sensor = None

    # Act - should not raise exception
    realsense_driver._apply_exposure_gain()


@patch("app.drivers.realsense_driver.rs")
def test_apply_exposure_gain_exception(mock_rs, realsense_driver):
    """Test _apply_exposure_gain handles exceptions gracefully."""
    # Arrange
    mock_sensor = MagicMock()
    mock_sensor.supports.side_effect = Exception("Sensor error")
    realsense_driver.color_sensor = mock_sensor

    # Act - should not raise exception
    realsense_driver._apply_exposure_gain()


# --- Test Resolution Query Methods ---
def test_get_supported_resolutions_success():
    """Test getting supported resolutions from a RealSense camera."""
    with patch("app.drivers.realsense_driver.rs") as mock_rs:
        # Setup mock objects
        mock_ctx = MagicMock()
        mock_device = MagicMock()
        mock_sensor = MagicMock()
        mock_profile_1 = MagicMock()
        mock_profile_2 = MagicMock()
        mock_profile_3 = MagicMock()
        mock_video_1 = MagicMock()
        mock_video_2 = MagicMock()
        mock_video_3 = MagicMock()

        # Configure mocks
        mock_rs.context.return_value = mock_ctx
        mock_ctx.query_devices.return_value = [mock_device]
        mock_device.get_info.return_value = "123456"
        mock_device.query_sensors.return_value = [mock_sensor]
        mock_sensor.is_color_sensor.return_value = True
        mock_sensor.get_stream_profiles.return_value = [mock_profile_1, mock_profile_2, mock_profile_3]

        # Configure profiles
        mock_rs.stream.color = "color_stream"
        mock_rs.format.bgr8 = "bgr8_format"

        mock_profile_1.stream_type.return_value = "color_stream"
        mock_profile_1.format.return_value = "bgr8_format"
        mock_profile_1.as_video_stream_profile.return_value = mock_video_1
        mock_video_1.width.return_value = 1920
        mock_video_1.height.return_value = 1080
        mock_video_1.fps.return_value = 30

        mock_profile_2.stream_type.return_value = "color_stream"
        mock_profile_2.format.return_value = "bgr8_format"
        mock_profile_2.as_video_stream_profile.return_value = mock_video_2
        mock_video_2.width.return_value = 1280
        mock_video_2.height.return_value = 720
        mock_video_2.fps.return_value = 30

        mock_profile_3.stream_type.return_value = "color_stream"
        mock_profile_3.format.return_value = "bgr8_format"
        mock_profile_3.as_video_stream_profile.return_value = mock_video_3
        mock_video_3.width.return_value = 640
        mock_video_3.height.return_value = 480
        mock_video_3.fps.return_value = 60

        # Act
        resolutions = RealSenseDriver.get_supported_resolutions("123456")

        # Assert
        assert len(resolutions) == 3
        assert resolutions[0]["width"] == 1920
        assert resolutions[0]["height"] == 1080
        assert resolutions[1]["width"] == 1280
        assert resolutions[1]["height"] == 720
        assert resolutions[2]["width"] == 640
        assert resolutions[2]["height"] == 480


def test_get_supported_resolutions_camera_not_found():
    """Test getting resolutions when camera is not found."""
    with patch("app.drivers.realsense_driver.rs") as mock_rs:
        mock_ctx = MagicMock()
        mock_device = MagicMock()

        mock_rs.context.return_value = mock_ctx
        mock_ctx.query_devices.return_value = [mock_device]
        mock_device.get_info.return_value = "different_serial"

        # Act
        resolutions = RealSenseDriver.get_supported_resolutions("123456")

        # Assert - should return defaults
        assert len(resolutions) > 0
        assert any(r["width"] == 640 and r["height"] == 480 for r in resolutions)


def test_get_supported_resolutions_no_pyrealsense2():
    """Test getting resolutions when pyrealsense2 is not installed."""
    with patch("app.drivers.realsense_driver.rs", None):
        # Act
        resolutions = RealSenseDriver.get_supported_resolutions("123456")

        # Assert - should return defaults
        assert len(resolutions) > 0
        assert any(r["width"] == 640 and r["height"] == 480 for r in resolutions)


def test_get_supported_resolutions_exception():
    """Test getting resolutions when an exception occurs."""
    with patch("app.drivers.realsense_driver.rs") as mock_rs:
        mock_rs.context.side_effect = Exception("Connection error")

        # Act
        resolutions = RealSenseDriver.get_supported_resolutions("123456")

        # Assert - should return defaults
        assert len(resolutions) > 0
        assert any(r["width"] == 640 and r["height"] == 480 for r in resolutions)


def test_get_default_resolutions():
    """Test that default resolutions are returned in correct format."""
    # Act
    defaults = RealSenseDriver._get_default_resolutions()

    # Assert
    assert len(defaults) > 0
    assert all("width" in r and "height" in r and "fps" in r for r in defaults)
    assert any(r["width"] == 640 and r["height"] == 480 for r in defaults)
    assert any(r["width"] == 1280 and r["height"] == 720 for r in defaults)
    assert any(r["width"] == 1920 and r["height"] == 1080 for r in defaults)


def test_detect_best_resolution_success():
    """Test detecting best resolution for a camera."""
    with patch.object(RealSenseDriver, "get_supported_resolutions") as mock_get_res:
        mock_get_res.return_value = [
            {"width": 1920, "height": 1080, "fps": 30, "format": "bgr8"},
            {"width": 1280, "height": 720, "fps": 30, "format": "bgr8"},
            {"width": 640, "height": 480, "fps": 60, "format": "bgr8"},
        ]

        # Act
        best = RealSenseDriver.detect_best_resolution("123456")

        # Assert - should return highest resolution
        assert best["width"] == 1920
        assert best["height"] == 1080
        assert best["fps"] == 30


def test_detect_best_resolution_fallback():
    """Test detecting best resolution falls back to safe default."""
    with patch.object(RealSenseDriver, "get_supported_resolutions") as mock_get_res:
        mock_get_res.side_effect = Exception("Error")

        # Act
        best = RealSenseDriver.detect_best_resolution("123456")

        # Assert - should return safe fallback
        assert best["width"] == 640
        assert best["height"] == 480
        assert best["fps"] == 30


def test_detect_best_resolution_empty_list():
    """Test detecting best resolution with empty resolution list."""
    with patch.object(RealSenseDriver, "get_supported_resolutions") as mock_get_res:
        mock_get_res.return_value = []

        # Act
        best = RealSenseDriver.detect_best_resolution("123456")

        # Assert - should return safe fallback
        assert best["width"] == 640
        assert best["height"] == 480
        assert best["fps"] == 30
