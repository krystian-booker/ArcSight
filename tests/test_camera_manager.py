import pytest
from unittest.mock import ANY, MagicMock, patch, call

from app import camera_manager, thread_state
from app.thread_config import build_camera_thread_config
from app.models import Camera, Pipeline


@pytest.fixture
def mock_app(app):
    """Provides a mock Flask app with a context."""
    return app


@pytest.fixture
def orm_camera(mock_app):
    """Creates a mock Camera ORM object with associated pipelines."""
    with mock_app.app_context():
        camera = MagicMock(spec=Camera)
        camera.id = 1
        camera.identifier = "test_cam_123"
        camera.camera_type = "USB"
        camera.orientation = 0
        camera.camera_matrix_json = None
        camera.dist_coeffs_json = None

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
def camera_config(orm_camera):
    """Builds a thread-safe primitive configuration for a camera."""
    return build_camera_thread_config(orm_camera)


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
    thread_state.active_camera_threads.clear()
    yield
    thread_state.active_camera_threads.clear()


@pytest.fixture
def mock_threads():
    """Patches the thread classes used by the camera manager."""
    with (
        patch("app.camera_manager.CameraAcquisitionThread") as mock_acq,
        patch("app.camera_manager.VisionProcessingThread") as mock_proc,
    ):
        mock_acq.return_value.is_alive.return_value = True
        yield {"acquisition": mock_acq, "processing": mock_proc}


def test_build_camera_thread_config(orm_camera):
    """Conversions should strip ORM state and fill defaults."""
    orm_camera.orientation = None  # ensure fallback logic
    config = build_camera_thread_config(orm_camera)

    assert config.id == orm_camera.id
    assert config.identifier == orm_camera.identifier
    assert config.camera_type == orm_camera.camera_type
    assert config.orientation == 0  # default orientation
    assert config.pipelines[0].id == orm_camera.pipelines[0].id
    assert (
        config.pipelines[1].pipeline_type == orm_camera.pipelines[1].pipeline_type
    )


def test_start_camera_thread(camera_config, mock_app, mock_threads):
    """Starting threads should rely solely on primitive config values."""
    camera_manager.start_camera_thread(camera_config, mock_app)

    mock_threads["acquisition"].assert_called_once_with(
        camera_id=camera_config.id,
        identifier=camera_config.identifier,
        camera_type=camera_config.camera_type,
        orientation=camera_config.orientation,
        app=mock_app,
        jpeg_quality=85,
        depth_enabled=camera_config.depth_enabled,
        resolution_json=camera_config.resolution_json,
        framerate=camera_config.framerate,
        exposure_mode=camera_config.exposure_mode,
        exposure_value=camera_config.exposure_value,
        gain_mode=camera_config.gain_mode,
        gain_value=camera_config.gain_value,
    )
    mock_threads["acquisition"].return_value.start.assert_called_once()

    assert mock_threads["processing"].call_count == len(camera_config.pipelines)
    for proc_call in mock_threads["processing"].call_args_list:
        kwargs = proc_call.kwargs
        assert kwargs["identifier"] == camera_config.identifier
        assert kwargs["frame_queue"] is not None

    thread_group = thread_state.active_camera_threads[camera_config.identifier]
    assert thread_group["acquisition"] == mock_threads["acquisition"].return_value
    assert len(thread_group["processing_threads"]) == len(camera_config.pipelines)


def test_start_camera_thread_already_running(camera_config, mock_app, mock_threads):
    """No threads should start if the camera is already tracked."""
    thread_state.active_camera_threads[camera_config.identifier] = {"stopping": False}
    camera_manager.start_camera_thread(camera_config, mock_app)

    mock_threads["acquisition"].assert_not_called()
    mock_threads["processing"].assert_not_called()


def test_stop_camera_thread(camera_config):
    """Thread teardown should stop and join all worker threads."""
    mock_acq_thread = MagicMock()
    mock_proc_thread1 = MagicMock()
    mock_proc_thread2 = MagicMock()

    thread_state.active_camera_threads[camera_config.identifier] = {
        "acquisition": mock_acq_thread,
        "processing_threads": {101: mock_proc_thread1, 102: mock_proc_thread2},
        "stopping": False,
    }

    camera_manager.stop_camera_thread(camera_config.identifier)

    mock_acq_thread.stop.assert_called_once()
    mock_acq_thread.join.assert_called_once()
    mock_proc_thread1.stop.assert_called_once()
    mock_proc_thread1.join.assert_called_once()
    mock_proc_thread2.stop.assert_called_once()
    mock_proc_thread2.join.assert_called_once()
    assert camera_config.identifier not in thread_state.active_camera_threads


def test_stop_camera_thread_not_running(camera_config):
    """Stopping an unknown camera should be a no-op."""
    camera_manager.stop_camera_thread(camera_config.identifier)
    assert not thread_state.active_camera_threads


def test_add_pipeline_to_camera(camera_config, mock_pipeline, mock_threads):
    """Adding a pipeline should spin up a new processing thread."""
    mock_acq_thread = MagicMock()
    mock_proc_thread1 = MagicMock()
    thread_state.active_camera_threads[camera_config.identifier] = {
        "acquisition": mock_acq_thread,
        "processing_threads": {101: mock_proc_thread1},
        "stopping": False,
    }

    camera_manager.add_pipeline_to_camera(
        identifier=camera_config.identifier,
        pipeline_id=mock_pipeline.id,
        pipeline_type=mock_pipeline.pipeline_type,
        pipeline_config_json=mock_pipeline.config,
        camera_matrix_json=camera_config.camera_matrix_json,
        dist_coeffs_json=camera_config.dist_coeffs_json,
    )

    mock_threads["processing"].assert_called_once()
    mock_threads["processing"].return_value.start.assert_called_once()
    mock_acq_thread.add_pipeline_queue.assert_called_once_with(mock_pipeline.id, ANY)
    thread_group = thread_state.active_camera_threads[camera_config.identifier]
    assert mock_pipeline.id in thread_group["processing_threads"]


def test_remove_pipeline_from_camera(camera_config):
    """Removing a pipeline should stop the associated processing thread."""
    pipeline_to_remove_id = 101
    mock_acq_thread = MagicMock()
    mock_proc_thread1 = MagicMock()
    mock_proc_thread2 = MagicMock()
    thread_state.active_camera_threads[camera_config.identifier] = {
        "acquisition": mock_acq_thread,
        "processing_threads": {
            pipeline_to_remove_id: mock_proc_thread1,
            102: mock_proc_thread2,
        },
        "stopping": False,
    }

    camera_manager.remove_pipeline_from_camera(
        identifier=camera_config.identifier, pipeline_id=pipeline_to_remove_id
    )

    mock_proc_thread1.stop.assert_called_once()
    mock_proc_thread1.join.assert_called_once()
    mock_acq_thread.remove_pipeline_queue.assert_called_once_with(pipeline_to_remove_id)
    thread_group = thread_state.active_camera_threads[camera_config.identifier]
    assert pipeline_to_remove_id not in thread_group["processing_threads"]
    assert 102 in thread_group["processing_threads"]


def test_update_pipeline_in_camera(camera_config, mock_pipeline, mock_threads):
    """Updating a pipeline should replace its processing thread."""
    pipeline_to_update_id = mock_pipeline.id
    mock_acq_thread = MagicMock()
    mock_old_proc_thread = MagicMock()
    thread_state.active_camera_threads[camera_config.identifier] = {
        "acquisition": mock_acq_thread,
        "processing_threads": {pipeline_to_update_id: mock_old_proc_thread},
        "stopping": False,
    }

    camera_manager.update_pipeline_in_camera(
        identifier=camera_config.identifier,
        pipeline_id=pipeline_to_update_id,
        pipeline_type=mock_pipeline.pipeline_type,
        pipeline_config_json=mock_pipeline.config,
        camera_matrix_json=camera_config.camera_matrix_json,
        dist_coeffs_json=camera_config.dist_coeffs_json,
    )

    mock_old_proc_thread.stop.assert_called_once()
    mock_old_proc_thread.join.assert_called_once()
    mock_acq_thread.remove_pipeline_queue.assert_called_once_with(pipeline_to_update_id)
    mock_threads["processing"].assert_called_once()
    mock_threads["processing"].return_value.start.assert_called_once()
    mock_acq_thread.add_pipeline_queue.assert_called_with(pipeline_to_update_id, ANY)
    thread_group = thread_state.active_camera_threads[camera_config.identifier]
    assert (
        thread_group["processing_threads"][pipeline_to_update_id]
        == mock_threads["processing"].return_value
    )


@patch("app.camera_manager.build_camera_thread_config")
@patch("app.camera_manager.Camera.query")
@patch("app.camera_manager.start_camera_thread")
def test_start_all_camera_threads(
    mock_start_single, mock_query, mock_build_config, mock_app
):
    """Global startup should convert ORM rows before spawning threads."""
    cam1 = MagicMock()
    cam2 = MagicMock()
    mock_query.options.return_value.all.return_value = [cam1, cam2]
    config1 = {"identifier": "cam1"}
    config2 = {"identifier": "cam2"}
    mock_build_config.side_effect = [config1, config2]

    camera_manager.start_all_camera_threads(mock_app)

    mock_build_config.assert_has_calls([call(cam1), call(cam2)])
    mock_start_single.assert_has_calls(
        [call(config1, mock_app), call(config2, mock_app)]
    )


@patch("app.camera_manager.stop_camera_thread")
def test_stop_all_camera_threads(mock_stop_single):
    """Global shutdown should iterate over tracked cameras."""
    thread_state.active_camera_threads = {"cam1": 1, "cam2": 2, "cam3": 3}

    camera_manager.stop_all_camera_threads()

    mock_stop_single.assert_has_calls(
        [call("cam1"), call("cam2"), call("cam3")], any_order=True
    )


def test_get_camera_pipeline_results(camera_config):
    """Fetching pipeline results should aggregate per pipeline."""
    mock_proc_thread1 = MagicMock()
    mock_proc_thread1.get_latest_results.return_value = "results1"
    mock_proc_thread2 = MagicMock()
    mock_proc_thread2.get_latest_results.return_value = "results2"

    thread_state.active_camera_threads[camera_config.identifier] = {
        "acquisition": MagicMock(),
        "processing_threads": {101: mock_proc_thread1, 102: mock_proc_thread2},
        "stopping": False,
    }

    results = camera_manager.get_camera_pipeline_results(camera_config.identifier)

    assert results == {101: "results1", 102: "results2"}
    mock_proc_thread1.get_latest_results.assert_called_once()
    mock_proc_thread2.get_latest_results.assert_called_once()


def test_get_camera_pipeline_results_not_running():
    """Fetching results should return None for unknown cameras."""
    assert camera_manager.get_camera_pipeline_results("missing") is None


def test_is_camera_thread_running(camera_config, mock_threads):
    """Status checks should respect thread liveness."""
    thread_state.active_camera_threads[camera_config.identifier] = {
        "acquisition": mock_threads["acquisition"].return_value,
        "processing_threads": {},
        "stopping": False,
    }

    assert camera_manager.is_camera_thread_running(camera_config.identifier) is True

    mock_threads["acquisition"].return_value.is_alive.return_value = False
    assert camera_manager.is_camera_thread_running(camera_config.identifier) is False


def test_is_camera_thread_running_not_present():
    """Status checks should return False for unknown cameras."""
    assert camera_manager.is_camera_thread_running("non_existent_cam") is False


def test_add_pipeline_to_camera_not_found(mock_pipeline):
    """Adding a pipeline to an unknown camera should be safe."""
    camera_manager.add_pipeline_to_camera(
        identifier="non_existent_camera",
        pipeline_id=mock_pipeline.id,
        pipeline_type=mock_pipeline.pipeline_type,
        pipeline_config_json=mock_pipeline.config,
        camera_matrix_json="{}",
        dist_coeffs_json="{}",
    )
    assert not thread_state.active_camera_threads


def test_remove_pipeline_from_camera_not_found():
    """Removing a pipeline from an unknown camera should be a no-op."""
    camera_manager.remove_pipeline_from_camera(
        identifier="non_existent_camera", pipeline_id=101
    )
    assert not thread_state.active_camera_threads


def test_update_pipeline_in_camera_not_found():
    """Updating a pipeline on an unknown camera should be a no-op."""
    camera_manager.update_pipeline_in_camera(
        identifier="non_existent_camera",
        pipeline_id=101,
        pipeline_type="AprilTag",
        pipeline_config_json="{}",
        camera_matrix_json="{}",
        dist_coeffs_json="{}",
    )
    assert not thread_state.active_camera_threads
