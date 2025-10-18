import pytest
import unittest
from unittest.mock import MagicMock, patch, call

from app import camera_manager
from app.models import Camera, Pipeline


@pytest.fixture
def mock_app(app):
    """Provides a mock Flask app with a context."""
    return app


@pytest.fixture
def mock_camera(mock_app):
    """Creates a mock Camera ORM object with associated pipelines."""
    with mock_app.app_context():
        camera = MagicMock(spec=Camera)
        camera.id = 1
        camera.identifier = "test_cam_123"
        camera.camera_type = "USB"
        camera.orientation = 0
        camera.camera_matrix_json = None

        # Simulate the joinedload of pipelines
        p1 = MagicMock(spec=Pipeline)
        p1.id = 101
        p1.pipeline_type = "AprilTag"
        p1.config = "{}"
        p2 = MagicMock(spec=Pipeline)
        p2.id = 102
        p2.pipeline_type = "AprilTag"
        p2.config = "{}"
        camera.pipelines = [p1, p2]

    return camera


@pytest.fixture
def mock_pipeline(mock_app):
    """Creates a mock Pipeline ORM object."""
    with mock_app.app_context():
        pipeline = MagicMock(spec=Pipeline)
        pipeline.id = 103
        pipeline.pipeline_type = "Test"
        pipeline.config = "{}"
    return pipeline


@pytest.fixture(autouse=True)
def manage_active_threads():
    """Fixture to clear the active_camera_threads global before and after each test."""
    # Setup: clear the dictionary
    camera_manager.active_camera_threads.clear()

    yield

    # Teardown: clear it again to be safe
    camera_manager.active_camera_threads.clear()


@pytest.fixture
def mock_threads():
    """Patches the thread classes used by the camera manager."""
    with (
        patch("app.camera_manager.CameraAcquisitionThread") as mock_acq,
        patch("app.camera_manager.VisionProcessingThread") as mock_proc,
    ):
        # Make mock threads appear "alive" for certain checks
        mock_acq.return_value.is_alive.return_value = True

        yield {"acquisition": mock_acq, "processing": mock_proc}


def test_start_camera_thread(mock_camera, mock_app, mock_threads):
    """Test starting threads for a single camera."""
    camera_manager.start_camera_thread(mock_camera, mock_app)

    # Check that acquisition thread was created with primitives and JPEG quality
    mock_threads["acquisition"].assert_called_once_with(
        identifier=mock_camera.identifier,
        camera_type=mock_camera.camera_type,
        orientation=mock_camera.orientation,
        app=mock_app,
        jpeg_quality=85,
    )
    mock_threads["acquisition"].return_value.start.assert_called_once()

    assert mock_threads["processing"].call_count == 2  # For the two pipelines
    for p_thread in (mock_threads["processing"].return_value,):
        p_thread.start.assert_called()

    # Check that the thread group was added to the global dict
    assert mock_camera.identifier in camera_manager.active_camera_threads
    thread_group = camera_manager.active_camera_threads[mock_camera.identifier]
    assert thread_group["acquisition"] == mock_threads["acquisition"].return_value
    assert len(thread_group["processing_threads"]) == 2


def test_start_camera_thread_already_running(mock_camera, mock_app, mock_threads):
    """Test that starting a thread for an already running camera does nothing."""
    # Manually add to the dict to simulate it running
    camera_manager.active_camera_threads[mock_camera.identifier] = "dummy_thread"

    camera_manager.start_camera_thread(mock_camera, mock_app)

    # No threads should be created or started
    mock_threads["acquisition"].assert_not_called()
    mock_threads["processing"].assert_not_called()


def test_stop_camera_thread(mock_camera):
    """Test stopping threads for a single camera."""
    # Manually create mock threads and add them to the dict
    mock_acq_thread = MagicMock()
    mock_proc_thread1 = MagicMock()
    mock_proc_thread2 = MagicMock()

    camera_manager.active_camera_threads[mock_camera.identifier] = {
        "acquisition": mock_acq_thread,
        "processing_threads": {101: mock_proc_thread1, 102: mock_proc_thread2},
    }

    camera_manager.stop_camera_thread(mock_camera.identifier)

    # Check that stop and join were called on all threads
    mock_acq_thread.stop.assert_called_once()
    mock_acq_thread.join.assert_called_once()
    mock_proc_thread1.stop.assert_called_once()
    mock_proc_thread1.join.assert_called_once()
    mock_proc_thread2.stop.assert_called_once()
    mock_proc_thread2.join.assert_called_once()

    # Check that the camera was removed from the active dict
    assert mock_camera.identifier not in camera_manager.active_camera_threads


def test_stop_camera_thread_not_running(mock_camera):
    """Test that stopping a non-existent camera thread does nothing."""
    # This should run without error
    camera_manager.stop_camera_thread(mock_camera.identifier)
    assert not camera_manager.active_camera_threads


def test_add_pipeline_to_camera(mock_camera, mock_pipeline, mock_app, mock_threads):
    """Test dynamically adding a new pipeline to a running camera."""
    # Simulate a running camera with one pipeline
    mock_acq_thread = MagicMock()
    mock_proc_thread1 = MagicMock()
    camera_manager.active_camera_threads[mock_camera.identifier] = {
        "acquisition": mock_acq_thread,
        "processing_threads": {101: mock_proc_thread1},
    }

    # Call with primitive data (no DB I/O)
    camera_manager.add_pipeline_to_camera(
        identifier=mock_camera.identifier,
        pipeline_id=mock_pipeline.id,
        pipeline_type=mock_pipeline.pipeline_type,
        pipeline_config_json=mock_pipeline.config,
        camera_matrix_json=mock_camera.camera_matrix_json,
        dist_coeffs_json=mock_camera.dist_coeffs_json,
    )

    # A new processing thread should be created and started
    mock_threads["processing"].assert_called_once()
    mock_threads["processing"].return_value.start.assert_called_once()

    # The new thread should be added to the acquisition thread's queues
    mock_acq_thread.add_pipeline_queue.assert_called_once()

    # The new thread should be in the manager's dict
    thread_group = camera_manager.active_camera_threads[mock_camera.identifier]
    assert mock_pipeline.id in thread_group["processing_threads"]


def test_remove_pipeline_from_camera(mock_camera, mock_app):
    """Test dynamically removing a pipeline from a running camera."""
    pipeline_to_remove_id = 101

    # Simulate a running camera with two pipelines
    mock_acq_thread = MagicMock()
    mock_proc_thread1 = MagicMock()
    mock_proc_thread2 = MagicMock()
    camera_manager.active_camera_threads[mock_camera.identifier] = {
        "acquisition": mock_acq_thread,
        "processing_threads": {
            pipeline_to_remove_id: mock_proc_thread1,
            102: mock_proc_thread2,
        },
    }

    # Call with primitive data (no DB I/O)
    camera_manager.remove_pipeline_from_camera(
        identifier=mock_camera.identifier, pipeline_id=pipeline_to_remove_id
    )

    # The target thread should be stopped and joined
    mock_proc_thread1.stop.assert_called_once()
    mock_proc_thread1.join.assert_called_once()

    # Its queue should be removed from the acquisition thread
    mock_acq_thread.remove_pipeline_queue.assert_called_once_with(pipeline_to_remove_id)

    # It should be removed from the manager's dict
    thread_group = camera_manager.active_camera_threads[mock_camera.identifier]
    assert pipeline_to_remove_id not in thread_group["processing_threads"]
    assert 102 in thread_group["processing_threads"]  # The other one should remain


def test_update_pipeline_in_camera(mock_camera, mock_pipeline, mock_app, mock_threads):
    """Test updating a pipeline, which should stop the old and start a new thread."""
    pipeline_to_update_id = mock_pipeline.id

    # Simulate a running camera
    mock_acq_thread = MagicMock()
    mock_old_proc_thread = MagicMock()
    camera_manager.active_camera_threads[mock_camera.identifier] = {
        "acquisition": mock_acq_thread,
        "processing_threads": {pipeline_to_update_id: mock_old_proc_thread},
    }

    # Call with primitive data (no DB I/O)
    camera_manager.update_pipeline_in_camera(
        identifier=mock_camera.identifier,
        pipeline_id=pipeline_to_update_id,
        pipeline_type=mock_pipeline.pipeline_type,
        pipeline_config_json=mock_pipeline.config,
        camera_matrix_json=mock_camera.camera_matrix_json,
        dist_coeffs_json=mock_camera.dist_coeffs_json,
    )

    # 1. Stop the old thread
    mock_old_proc_thread.stop.assert_called_once()
    mock_old_proc_thread.join.assert_called_once()

    # 2. Remove its queue
    mock_acq_thread.remove_pipeline_queue.assert_called_once_with(pipeline_to_update_id)

    # 3. Create and start a new processing thread
    mock_threads["processing"].assert_called_once()
    mock_threads["processing"].return_value.start.assert_called_once()

    # 4. Add the new queue
    mock_acq_thread.add_pipeline_queue.assert_called_with(
        pipeline_to_update_id, unittest.mock.ANY
    )

    # 5. The new thread should be in the dict
    thread_group = camera_manager.active_camera_threads[mock_camera.identifier]
    assert (
        thread_group["processing_threads"][pipeline_to_update_id]
        == mock_threads["processing"].return_value
    )


@patch("app.camera_manager.Camera.query")
@patch("app.camera_manager.start_camera_thread")
def test_start_all_camera_threads(mock_start_single, mock_query, mock_app):
    """Test the global startup function."""
    # Simulate finding two cameras in the DB
    cam1 = MagicMock()
    cam2 = MagicMock()
    mock_query.options.return_value.all.return_value = [cam1, cam2]

    camera_manager.start_all_camera_threads(mock_app)

    # Check that start_camera_thread was called for each camera
    mock_start_single.assert_has_calls([call(cam1, mock_app), call(cam2, mock_app)])


@patch("app.camera_manager.stop_camera_thread")
def test_stop_all_camera_threads(mock_stop_single):
    """Test the global shutdown function."""
    # Simulate three running cameras
    camera_manager.active_camera_threads = {"cam1": 1, "cam2": 2, "cam3": 3}

    camera_manager.stop_all_camera_threads()

    # Check that stop_camera_thread was called for each identifier
    mock_stop_single.assert_has_calls(
        [call("cam1"), call("cam2"), call("cam3")], any_order=True
    )


def test_get_camera_pipeline_results(mock_camera):
    """Test retrieving latest results from all pipelines for a camera."""
    # Simulate a running camera with two pipelines
    mock_proc_thread1 = MagicMock()
    mock_proc_thread1.get_latest_results.return_value = "results1"
    mock_proc_thread2 = MagicMock()
    mock_proc_thread2.get_latest_results.return_value = "results2"

    camera_manager.active_camera_threads[mock_camera.identifier] = {
        "acquisition": MagicMock(),
        "processing_threads": {101: mock_proc_thread1, 102: mock_proc_thread2},
    }

    results = camera_manager.get_camera_pipeline_results(mock_camera.identifier)

    assert results == {101: "results1", 102: "results2"}
    mock_proc_thread1.get_latest_results.assert_called_once()
    mock_proc_thread2.get_latest_results.assert_called_once()


def test_get_camera_pipeline_results_not_running():
    """Test getting results for a non-existent camera."""
    results = camera_manager.get_camera_pipeline_results("non_existent_cam")
    assert results is None


def test_is_camera_thread_running(mock_camera, mock_threads):
    """Test the status check for a running camera."""
    # Simulate a running camera
    camera_manager.active_camera_threads[mock_camera.identifier] = {
        "acquisition": mock_threads["acquisition"].return_value,
        "processing_threads": {},
    }

    # The mock is_alive returns True by default
    assert camera_manager.is_camera_thread_running(mock_camera.identifier) is True

    # Simulate a dead thread
    mock_threads["acquisition"].return_value.is_alive.return_value = False
    assert camera_manager.is_camera_thread_running(mock_camera.identifier) is False


def test_is_camera_thread_running_not_present():
    """Test the status check for a non-existent camera."""
    assert camera_manager.is_camera_thread_running("non_existent_cam") is False


def test_add_pipeline_to_camera_not_found(mock_pipeline, mock_app):
    """Test add_pipeline_to_camera when the camera is not running."""
    # No threads are running
    camera_manager.add_pipeline_to_camera(
        identifier="non_existent_camera",
        pipeline_id=mock_pipeline.id,
        pipeline_type=mock_pipeline.pipeline_type,
        pipeline_config_json=mock_pipeline.config,
        camera_matrix_json="{}",
        dist_coeffs_json="{}",
    )
    assert not camera_manager.active_camera_threads  # Should not have changed


def test_remove_pipeline_from_camera_not_found(mock_app):
    """Test remove_pipeline_from_camera when the camera is not running."""
    # No threads are running
    camera_manager.remove_pipeline_from_camera(
        identifier="non_existent_camera", pipeline_id=101
    )
    assert not camera_manager.active_camera_threads  # Should not have changed


def test_update_pipeline_in_camera_not_found(mock_app):
    """Test update_pipeline_in_camera when the camera is not running."""
    # No threads are running
    camera_manager.update_pipeline_in_camera(
        identifier="non_existent_camera",
        pipeline_id=101,
        pipeline_type="AprilTag",
        pipeline_config_json="{}",
        camera_matrix_json="{}",
        dist_coeffs_json="{}",
    )
    assert not camera_manager.active_camera_threads  # Should not have changed
