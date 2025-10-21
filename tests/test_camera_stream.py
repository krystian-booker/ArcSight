import pytest
from unittest.mock import MagicMock, patch
import numpy as np

from app import camera_stream
from app.models import Camera


@pytest.fixture
def mock_camera(app):
    """Creates a mock Camera ORM object."""
    with app.app_context():
        camera = MagicMock(spec=Camera)
        camera.id = 1
        camera.identifier = "test_cam_123"
    return camera


@pytest.fixture
def mock_active_threads(mock_camera):
    """
    Mocks the active_camera_threads global dictionary and provides mock thread objects.
    This fixture patches the dictionary where it's looked up (in the camera_stream module).
    """
    mock_acq_thread = MagicMock()
    mock_acq_thread.is_alive.return_value = True
    # Mock the raw frame for lazy encoding (must be a numpy array for cv2.imencode)
    mock_acq_thread.latest_display_frame_raw = np.zeros((10, 10, 3), dtype=np.uint8)
    mock_acq_thread.jpeg_quality = 85
    # latest_raw_frame is now a RefCountedFrame, create a mock for it
    mock_ref_frame = MagicMock()
    mock_ref_frame.get_writable_copy.return_value = np.zeros((10, 10), dtype=np.uint8)
    mock_acq_thread.latest_raw_frame = mock_ref_frame

    mock_proc_thread = MagicMock()
    mock_proc_thread.is_alive.return_value = True
    # Mock the raw processed frame for lazy encoding (must be a numpy array for cv2.imencode)
    mock_proc_thread.latest_processed_frame_raw = np.zeros((10, 10, 3), dtype=np.uint8)
    mock_proc_thread.jpeg_quality = 75

    threads_dict = {
        mock_camera.identifier: {
            "acquisition": mock_acq_thread,
            "processing_threads": {101: mock_proc_thread},
        }
    }

    with patch.dict(
        camera_stream.active_camera_threads, threads_dict, clear=True
    ) as mocked_dict:
        yield {"dict": mocked_dict, "acq": mock_acq_thread, "proc": mock_proc_thread}


# --- Tests for get_camera_feed ---


def test_get_camera_feed_success(mock_camera, mock_active_threads):
    """Test successfully getting a frame from the raw camera feed generator."""
    feed_generator = camera_stream.get_camera_feed(mock_camera)

    # Get the first frame successfully
    frame = next(feed_generator)

    # Now, simulate the thread dying to prevent an infinite loop in the test
    mock_active_threads["acq"].is_alive.return_value = False

    # The frame should be a JPEG-encoded image with proper MIME boundaries
    assert b"--frame" in frame
    assert b"Content-Type: image/jpeg" in frame


def test_get_camera_feed_thread_not_running(mock_camera):
    """Test the feed generator when the camera thread is not active."""
    # The mock_active_threads fixture is not used, so the dict is empty
    feed_generator = camera_stream.get_camera_feed(mock_camera)

    # The generator should yield nothing and exit gracefully
    with pytest.raises(StopIteration):
        next(feed_generator)


def test_get_camera_feed_thread_dies(mock_camera, mock_active_threads):
    """Test the feed generator when the thread dies during streaming."""
    feed_generator = camera_stream.get_camera_feed(mock_camera)

    # The first yield should work fine
    frame = next(feed_generator)
    assert b"--frame" in frame

    # Now, we simulate the thread dying
    mock_active_threads["acq"].is_alive.return_value = False

    # The next iteration of the loop should see the dead thread and break,
    # causing the generator to raise StopIteration.
    with pytest.raises(StopIteration):
        next(feed_generator)


def test_get_camera_feed_generator_exit(mock_camera, mock_active_threads):
    """Test that the generator handles client disconnection (GeneratorExit)."""
    feed_generator = camera_stream.get_camera_feed(mock_camera)

    try:
        # This will run until the generator yields, then we close it
        next(feed_generator)
        feed_generator.close()  # This raises GeneratorExit inside the generator
    except Exception as e:
        pytest.fail(f"GeneratorExit was not handled correctly: {e}")


def test_get_camera_feed_no_frame(mock_camera, mock_active_threads):
    """Test the camera feed generator when the thread is alive but there's no frame."""
    mock_active_threads["acq"].latest_display_frame_raw = None
    # Let the thread die after the first check to prevent an infinite loop
    mock_active_threads["acq"].is_alive.side_effect = [True, False]

    feed_generator = camera_stream.get_camera_feed(mock_camera)

    # The generator should not yield anything and just exit
    with pytest.raises(StopIteration):
        next(feed_generator)


# --- Tests for get_processed_camera_feed ---


def test_get_processed_camera_feed_success(mock_active_threads):
    """Test successfully getting a frame from the processed feed generator."""
    pipeline_id = 101
    feed_generator = camera_stream.get_processed_camera_feed(pipeline_id)

    # Get the first frame successfully
    frame = next(feed_generator)

    # Simulate the thread dying after the first frame
    mock_active_threads["proc"].is_alive.return_value = False

    assert b"--frame" in frame
    assert b"Content-Type: image/jpeg" in frame


def test_get_processed_camera_feed_thread_not_found():
    """Test the feed generator when the pipeline ID does not exist."""
    feed_generator = camera_stream.get_processed_camera_feed(999)

    with pytest.raises(StopIteration):
        next(feed_generator)


def test_get_processed_camera_feed_thread_dies(mock_active_threads):
    """Test the processed feed generator when the thread dies during streaming."""
    pipeline_id = 101
    feed_generator = camera_stream.get_processed_camera_feed(pipeline_id)

    # The first yield should work fine
    frame = next(feed_generator)
    assert b"--frame" in frame

    # Now, we simulate the thread dying
    mock_active_threads["proc"].is_alive.return_value = False

    # The next iteration of the loop should see the dead thread and break,
    # causing the generator to raise StopIteration.
    with pytest.raises(StopIteration):
        next(feed_generator)


def test_get_processed_camera_feed_generator_exit(mock_active_threads):
    """Test that the processed feed generator handles client disconnection."""
    pipeline_id = 101
    feed_generator = camera_stream.get_processed_camera_feed(pipeline_id)

    try:
        next(feed_generator)
        feed_generator.close()
    except Exception as e:
        pytest.fail(f"GeneratorExit was not handled correctly: {e}")


def test_get_processed_camera_feed_no_frame(mock_active_threads):
    """Test the processed feed generator when the thread is alive but there's no frame."""
    pipeline_id = 101
    mock_active_threads["proc"].latest_processed_frame_raw = None
    # Let the thread die after the first check to prevent an infinite loop
    mock_active_threads["proc"].is_alive.side_effect = [True, False]

    feed_generator = camera_stream.get_processed_camera_feed(pipeline_id)

    # The generator should not yield anything and just exit
    with pytest.raises(StopIteration):
        next(feed_generator)


# --- Tests for get_latest_raw_frame ---


def test_get_latest_raw_frame_success(mock_camera, mock_active_threads):
    """Test successfully getting the latest raw frame."""
    # latest_raw_frame is now a RefCountedFrame mock
    ref_frame_mock = mock_active_threads["acq"].latest_raw_frame
    expected_frame = ref_frame_mock.get_writable_copy.return_value

    frame_copy = camera_stream.get_latest_raw_frame(mock_camera.identifier)

    # Check that get_writable_copy was called
    ref_frame_mock.get_writable_copy.assert_called_once()
    # Check that the returned frame matches
    assert np.array_equal(frame_copy, expected_frame)


def test_get_latest_raw_frame_thread_not_running(mock_camera):
    """Test getting a raw frame when the camera thread is not active."""
    frame = camera_stream.get_latest_raw_frame(mock_camera.identifier)
    assert frame is None


def test_get_latest_raw_frame_is_none(mock_camera, mock_active_threads):
    """Test getting a raw frame when the thread is running but the frame is None."""
    mock_active_threads["acq"].latest_raw_frame = None

    frame = camera_stream.get_latest_raw_frame(mock_camera.identifier)
    assert frame is None


def test_get_camera_feed_waits_for_frame(mock_camera, mock_active_threads):
    """
    Test the camera feed generator when it has to wait for a frame to become available.
    This ensures the time.sleep line is covered.
    """
    # The thread is alive for two loops, then dies.
    mock_active_threads["acq"].is_alive.side_effect = [True, True, False]

    # The frame is not available on the first loop (latest_display_frame_raw is None).
    mock_active_threads["acq"].latest_display_frame_raw = None

    feed_generator = camera_stream.get_camera_feed(mock_camera)

    with patch("time.sleep") as mock_sleep:
        # This side effect runs when time.sleep is called after the first empty loop.
        def make_frame_available(duration):
            # Set a new raw frame (numpy array) that will be encoded
            mock_active_threads["acq"].latest_display_frame_raw = np.zeros(
                (10, 10, 3), dtype=np.uint8
            )

        mock_sleep.side_effect = make_frame_available

        # The generator should loop once, find no frame, sleep (and trigger the side effect),
        # then loop again, find the new frame, and yield it.
        frame = next(feed_generator)

        assert b"--frame" in frame
        mock_sleep.assert_called_once_with(0.001)


def test_get_processed_camera_feed_waits_for_frame(mock_active_threads):
    """
    Test the processed feed generator when it has to wait for a frame.
    This ensures the time.sleep line is covered.
    """
    pipeline_id = 101
    # The thread is alive for two loops, then dies.
    mock_active_threads["proc"].is_alive.side_effect = [True, True, False]

    # The frame is not available on the first loop (latest_processed_frame_raw is None).
    mock_active_threads["proc"].latest_processed_frame_raw = None

    feed_generator = camera_stream.get_processed_camera_feed(pipeline_id)

    with patch("time.sleep") as mock_sleep:
        # This side effect runs when time.sleep is called after the first empty loop.
        def make_frame_available(duration):
            # Set a new raw processed frame (numpy array) that will be encoded
            mock_active_threads["proc"].latest_processed_frame_raw = np.zeros(
                (10, 10, 3), dtype=np.uint8
            )

        mock_sleep.side_effect = make_frame_available

        # The generator should loop once, find no frame, sleep (and trigger the side effect),
        # then loop again, find the new frame, and yield it.
        frame = next(feed_generator)

        assert b"--frame" in frame
        mock_sleep.assert_called_once_with(0.001)
