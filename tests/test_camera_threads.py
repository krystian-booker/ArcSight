import pytest
import numpy as np
import queue
import time
from unittest.mock import MagicMock, patch
import cv2

import json

from app.camera_threads import RefCountedFrame, FrameBufferPool, VisionProcessingThread, CameraAcquisitionThread
from app.models import Camera, Pipeline

# --- Tests for RefCountedFrame ---

def test_ref_counted_frame_initialization():
    """Verify that the frame is initialized with a reference count of zero."""
    frame_buffer = np.zeros((10, 10), dtype=np.uint8)
    release_callback = MagicMock()
    rc_frame = RefCountedFrame(frame_buffer, release_callback)
    assert rc_frame._ref_count == 0
    assert np.array_equal(rc_frame.data, frame_buffer)

def test_ref_counted_frame_acquire():
    """Test that acquiring the frame increments the reference count."""
    rc_frame = RefCountedFrame(np.zeros(1), MagicMock())
    rc_frame.acquire()
    assert rc_frame._ref_count == 1
    rc_frame.acquire()
    assert rc_frame._ref_count == 2

def test_ref_counted_frame_release():
    """Test that releasing the frame decrements the count and calls the callback at zero."""
    release_callback = MagicMock()
    rc_frame = RefCountedFrame(np.zeros(1), release_callback)

    rc_frame.acquire()
    rc_frame.acquire()
    assert rc_frame._ref_count == 2

    rc_frame.release()
    assert rc_frame._ref_count == 1
    release_callback.assert_not_called()

    rc_frame.release()
    assert rc_frame._ref_count == 0
    release_callback.assert_called_once_with(rc_frame.frame_buffer)

def test_ref_counted_frame_release_does_not_go_below_zero():
    """Test that the reference count does not become negative."""
    release_callback = MagicMock()
    rc_frame = RefCountedFrame(np.zeros(1), release_callback)
    rc_frame.release()
    assert rc_frame._ref_count == 0
    release_callback.assert_not_called()

def test_ref_counted_frame_get_writable_copy():
    """Test that get_writable_copy returns a new, independent numpy array."""
    original_frame = np.array([[1, 2], [3, 4]])
    rc_frame = RefCountedFrame(original_frame, MagicMock())
    
    frame_copy = rc_frame.get_writable_copy()
    
    # Check that the data is the same
    assert np.array_equal(frame_copy, original_frame)
    # Check that they are different objects in memory
    assert id(frame_copy) != id(original_frame)
    
    # Modify the copy and ensure the original is unchanged
    frame_copy[0, 0] = 99
    assert original_frame[0, 0] == 1

# --- Tests for FrameBufferPool ---

def test_frame_buffer_pool_initialization():
    """Verify that the pool is empty upon creation."""
    pool = FrameBufferPool()
    assert pool._pool.empty()
    assert pool._buffer_shape is None
    assert pool._allocated == 0

def test_frame_buffer_pool_initialize():
    """Test the initialization of the buffer pool with a sample frame."""
    pool = FrameBufferPool()
    sample_frame = np.zeros((480, 640, 3), dtype=np.uint8)
    pool.initialize(sample_frame, num_buffers=5)

    assert pool._pool.qsize() == 5
    assert pool._allocated == 5
    assert pool._buffer_shape == sample_frame.shape
    assert pool._buffer_dtype == sample_frame.dtype

def test_frame_buffer_pool_initialize_reinitializes_on_shape_change():
    """Test that the pool is re-created if a frame with a different shape is provided."""
    pool = FrameBufferPool()
    # Initial setup
    pool.initialize(np.zeros((10, 10)), num_buffers=3)
    assert pool._pool.qsize() == 3
    assert pool._buffer_shape == (10, 10)

    # Re-initialize with a different shape
    pool.initialize(np.zeros((20, 20)), num_buffers=5)
    assert pool._pool.qsize() == 5
    assert pool._buffer_shape == (20, 20)
    assert pool._allocated == 5 # Should be reset

def test_frame_buffer_pool_initialize_does_not_reinitialize_on_same_shape():
    """Test that the pool is not re-created if the shape is the same."""
    pool = FrameBufferPool()
    pool.initialize(np.zeros((10, 10)), num_buffers=3)
    first_buffer = pool.get_buffer() # Get one buffer to change state

    # Calling initialize again with the same shape should do nothing
    pool.initialize(np.zeros((10, 10)), num_buffers=3)
    assert pool._pool.qsize() == 2 # Should not have been reset to 3
    assert pool._allocated == 3

def test_frame_buffer_pool_get_buffer_from_pool():
    """Test retrieving a pre-allocated buffer from the pool."""
    pool = FrameBufferPool()
    sample_frame = np.zeros((10, 10), dtype=np.uint8)
    pool.initialize(sample_frame, num_buffers=1)

    buffer = pool.get_buffer()
    assert pool._pool.empty()
    assert buffer.shape == sample_frame.shape
    assert buffer.dtype == sample_frame.dtype

def test_frame_buffer_pool_get_buffer_allocates_new():
    """Test that a new buffer is allocated when the pool is empty."""
    pool = FrameBufferPool()
    sample_frame = np.zeros((10, 10), dtype=np.uint8)
    pool.initialize(sample_frame, num_buffers=1)

    # Empty the pool
    _ = pool.get_buffer()
    assert pool._pool.empty()

    # Get another one, which should be newly allocated
    new_buffer = pool.get_buffer()
    assert pool._allocated == 2
    assert new_buffer is not None

def test_frame_buffer_pool_get_buffer_uninitialized():
    """Test that getting a buffer from an uninitialized pool returns None."""
    pool = FrameBufferPool()
    assert pool.get_buffer() is None

def test_frame_buffer_pool_release_buffer():
    """Test returning a buffer to the pool."""
    pool = FrameBufferPool()
    sample_frame = np.zeros((10, 10))
    pool.initialize(sample_frame, num_buffers=1)

    # Empty the pool
    buffer = pool.get_buffer()
    assert pool._pool.empty()

    # Return it
    pool.release_buffer(buffer)
    assert pool._pool.qsize() == 1


# --- Mocks and Fixtures for Thread Tests ---

@pytest.fixture
def mock_pipeline_instances():
    """Provides a dictionary of mocked pipeline implementation instances."""
    with patch('app.camera_threads.AprilTagPipeline') as mock_at, \
         patch('app.camera_threads.ColouredShapePipeline') as mock_cs, \
         patch('app.camera_threads.ObjectDetectionMLPipeline') as mock_ml:
        
        # Provide valid numpy arrays for rvec and tvec to prevent cv2.error
        rvec = np.array([1.0, 0.0, 0.0], dtype=np.float32)
        tvec = np.array([0.0, 0.0, 1.0], dtype=np.float32)
        mock_at.return_value.process_frame.return_value = [{
            'ui_data': 'apriltag_data', 
            'drawing_data': {'rvec': rvec, 'tvec': tvec, 'corners': np.array([[0,0]]), 'id': 1}
        }]
        mock_cs.return_value.process_frame.return_value = "coloured_shape_data"
        mock_ml.return_value.process_frame.return_value = "ml_data"
        
        yield {
            'AprilTag': mock_at,
            'Coloured Shape': mock_cs,
            'Object Detection (ML)': mock_ml
        }

@pytest.fixture
def mock_camera(mock_app):
    """Creates a mock Camera object."""
    with mock_app.app_context():
        camera = MagicMock(spec=Camera)
        camera.id = 1
        camera.identifier = "0"  # Must be a valid integer index for USBDriver
        camera.camera_matrix_json = json.dumps(np.eye(3).tolist())
        camera.dist_coeffs_json = json.dumps(np.zeros(5).tolist())
        camera.orientation = 0
        camera.camera_type = 'USB' # Needed for get_driver to succeed
    return camera

@pytest.fixture
def mock_pipeline(mock_app):
    """Creates a mock Pipeline object."""
    with mock_app.app_context():
        pipeline = MagicMock(spec=Pipeline)
        pipeline.id = 101
        pipeline.pipeline_type = 'AprilTag'
        pipeline.config = json.dumps({'family': 'tag36h11', 'tag_size_m': 0.1})
    return pipeline


# --- Tests for VisionProcessingThread ---

def test_vision_processing_thread_initialization(mock_camera, mock_pipeline, mock_pipeline_instances):
    """Test the thread's constructor and initialization of pipeline instances."""
    thread = VisionProcessingThread(
        identifier=mock_camera.identifier,
        pipeline_id=mock_pipeline.id,
        pipeline_type=mock_pipeline.pipeline_type,
        pipeline_config_json=mock_pipeline.config,
        camera_matrix_json=mock_camera.camera_matrix_json,
        frame_queue=queue.Queue()
    )

    assert thread.pipeline_type == 'AprilTag'
    mock_pipeline_instances['AprilTag'].assert_called_once()
    assert thread.latest_results == {"status": "Starting..."}
    assert thread.cam_matrix is not None


@pytest.mark.parametrize("pipeline_type", [
    "AprilTag",
    "Coloured Shape",
    "Object Detection (ML)"
])
def test_vision_processing_thread_initialization_all_types(pipeline_type, mock_camera, mock_pipeline, mock_pipeline_instances):
    """Test that the correct pipeline class is instantiated based on pipeline_type."""
    mock_pipeline.pipeline_type = pipeline_type
    thread = VisionProcessingThread(
        identifier=mock_camera.identifier,
        pipeline_id=mock_pipeline.id,
        pipeline_type=mock_pipeline.pipeline_type,
        pipeline_config_json=mock_pipeline.config,
        camera_matrix_json=mock_camera.camera_matrix_json,
        frame_queue=queue.Queue()
    )

    assert thread.pipeline_instance is not None
    mock_pipeline_instances[pipeline_type].assert_called_once()


def test_vision_processing_thread_init_invalid_pipeline_type(mock_camera, mock_pipeline, mock_pipeline_instances):
    """Test initialization with an unknown pipeline type."""
    mock_pipeline.pipeline_type = "Unknown Type"
    thread = VisionProcessingThread(
        identifier=mock_camera.identifier,
        pipeline_id=mock_pipeline.id,
        pipeline_type=mock_pipeline.pipeline_type,
        pipeline_config_json=mock_pipeline.config,
        camera_matrix_json=mock_camera.camera_matrix_json,
        frame_queue=queue.Queue()
    )
    assert thread.pipeline_instance is None


def test_vision_processing_thread_init_bad_json_config(mock_camera, mock_pipeline, mock_pipeline_instances):
    """Test that initialization falls back to defaults with invalid JSON in pipeline config."""
    mock_pipeline.config = "{'bad json"
    thread = VisionProcessingThread(
        identifier=mock_camera.identifier,
        pipeline_id=mock_pipeline.id,
        pipeline_type=mock_pipeline.pipeline_type,
        pipeline_config_json=mock_pipeline.config,
        camera_matrix_json=mock_camera.camera_matrix_json,
        frame_queue=queue.Queue()
    )

    # It should still initialize with the default config
    mock_pipeline_instances['AprilTag'].assert_called_once()
    # The config passed to the constructor should be the default merged with the (empty) parsed one
    final_config = mock_pipeline_instances['AprilTag'].call_args[0][0]
    assert final_config['family'] == 'tag36h11' # Check a default value


def test_vision_processing_thread_init_no_camera_matrix(mock_camera, mock_pipeline, mock_pipeline_instances):
    """Test that a default camera matrix is created if none is in the DB."""
    mock_camera.camera_matrix_json = None
    thread = VisionProcessingThread(
        identifier=mock_camera.identifier,
        pipeline_id=mock_pipeline.id,
        pipeline_type=mock_pipeline.pipeline_type,
        pipeline_config_json=mock_pipeline.config,
        camera_matrix_json=mock_camera.camera_matrix_json,
        frame_queue=queue.Queue()
    )

    # The run method will create the default matrix
    thread.start()
    time.sleep(0.1) # Give thread time to start and check for matrix
    thread.stop()
    thread.join()

    assert thread.cam_matrix is not None
    assert thread.cam_matrix[0, 0] == 600.0 # Check a default value


def test_vision_processing_thread_run_loop(mock_camera, mock_pipeline, mock_pipeline_instances):
    """Test the main run loop: processing a frame from the queue."""
    frame_queue = queue.Queue()
    thread = VisionProcessingThread(
        identifier=mock_camera.identifier,
        pipeline_id=mock_pipeline.id,
        pipeline_type=mock_pipeline.pipeline_type,
        pipeline_config_json=mock_pipeline.config,
        camera_matrix_json=mock_camera.camera_matrix_json,
        frame_queue=frame_queue
    )

    # Mock the frame
    frame_data = np.zeros((100, 100, 3), dtype=np.uint8)
    mock_rc_frame = MagicMock(spec=RefCountedFrame)
    mock_rc_frame.data = frame_data

    # Put frame in queue and start thread
    frame_queue.put(mock_rc_frame)
    thread.start()
    time.sleep(0.2) # Allow thread to process

    # Check results
    results = thread.get_latest_results()
    assert results['tags_found'] is True
    assert results['detections'] == ['apriltag_data']
    assert 'processing_time_ms' in results

    # Check that frame was released
    mock_rc_frame.release.assert_called_once()

    # Check that processed frame was generated
    with thread.processed_frame_lock:
        assert thread.latest_processed_frame is not None

    # Stop the thread
    thread.stop()
    thread.join(timeout=1)
    assert not thread.is_alive()


def test_vision_processing_thread_run_loop_empty_queue(mock_camera, mock_pipeline):
    """Test that the run loop handles an empty queue without crashing."""
    frame_queue = queue.Queue()
    thread = VisionProcessingThread(
        identifier=mock_camera.identifier,
        pipeline_id=mock_pipeline.id,
        pipeline_type=mock_pipeline.pipeline_type,
        pipeline_config_json=mock_pipeline.config,
        camera_matrix_json=mock_camera.camera_matrix_json,
        frame_queue=frame_queue
    )

    thread.start()
    time.sleep(0.1) # Let it run on an empty queue

    thread.stop()
    thread.join(timeout=1)
    assert not thread.is_alive()
    # No frames processed, results should be the initial ones
    assert thread.latest_results == {"status": "Starting..."}


def test_vision_processing_thread_stop_method(mock_camera, mock_pipeline):
    """Verify the stop event terminates the run loop."""
    thread = VisionProcessingThread(
        identifier=mock_camera.identifier,
        pipeline_id=mock_pipeline.id,
        pipeline_type=mock_pipeline.pipeline_type,
        pipeline_config_json=mock_pipeline.config,
        camera_matrix_json=mock_camera.camera_matrix_json,
        frame_queue=queue.Queue()
    )
    thread.start()
    assert thread.is_alive()

    thread.stop()
    # Increase timeout to account for the queue.get(timeout=1) in the loop
    thread.join(timeout=2)

    assert not thread.is_alive()
    assert thread.stop_event.is_set()

def test_vision_processing_thread_draw_3d_box(mock_camera, mock_pipeline):
    """Test the drawing function logic."""
    with patch('cv2.projectPoints') as mock_project, \
         patch('cv2.drawContours'), \
         patch('cv2.line'), \
         patch('cv2.putText'):

        # Mock projectPoints to return predictable screen coordinates
        mock_project.return_value = (np.zeros((8, 1, 2)), None)

        thread = VisionProcessingThread(
            identifier=mock_camera.identifier,
            pipeline_id=mock_pipeline.id,
            pipeline_type=mock_pipeline.pipeline_type,
            pipeline_config_json=mock_pipeline.config,
            camera_matrix_json=mock_camera.camera_matrix_json,
            frame_queue=queue.Queue()
        )
        # Manually set a valid camera matrix
        thread.cam_matrix = np.eye(3)

        frame = np.zeros((100, 100, 3))
        detections = [{'rvec': 1, 'tvec': 2, 'corners': [[0,0]], 'id': 1}]

        thread._draw_3d_box_on_frame(frame, detections)

        mock_project.assert_called_once()


def test_vision_processing_thread_run_loop_ml_pipeline(mock_camera, mock_pipeline, mock_pipeline_instances):
    """Test the main run loop with an ML pipeline."""
    mock_pipeline.pipeline_type = 'Object Detection (ML)'
    mock_pipeline_instances['Object Detection (ML)'].return_value.process_frame.return_value = [
        {'box': [10, 20, 30, 40], 'label': 'test', 'confidence': 0.99}
    ]
    frame_queue = queue.Queue()
    thread = VisionProcessingThread(
        identifier=mock_camera.identifier,
        pipeline_id=mock_pipeline.id,
        pipeline_type=mock_pipeline.pipeline_type,
        pipeline_config_json=mock_pipeline.config,
        camera_matrix_json=mock_camera.camera_matrix_json,
        frame_queue=frame_queue
    )

    frame_data = np.zeros((100, 100, 3), dtype=np.uint8)
    mock_rc_frame = MagicMock(spec=RefCountedFrame)
    mock_rc_frame.data = frame_data
    frame_queue.put(mock_rc_frame)

    with patch('cv2.rectangle'), patch('cv2.putText'):
        thread.start()
        time.sleep(0.2)

        results = thread.get_latest_results()
        assert 'detections' in results
        assert len(results['detections']) == 1

        thread.stop()
        thread.join()

def test_vision_processing_thread_run_loop_coloured_shape_pipeline(mock_camera, mock_pipeline, mock_pipeline_instances):
    """Test the main run loop with a coloured shape pipeline."""
    mock_pipeline.pipeline_type = 'Coloured Shape'
    frame_queue = queue.Queue()
    thread = VisionProcessingThread(
        identifier=mock_camera.identifier,
        pipeline_id=mock_pipeline.id,
        pipeline_type=mock_pipeline.pipeline_type,
        pipeline_config_json=mock_pipeline.config,
        camera_matrix_json=mock_camera.camera_matrix_json,
        frame_queue=frame_queue
    )

    frame_data = np.zeros((100, 100, 3), dtype=np.uint8)
    mock_rc_frame = MagicMock(spec=RefCountedFrame)
    mock_rc_frame.data = frame_data
    frame_queue.put(mock_rc_frame)

    thread.start()
    time.sleep(0.2)

    results = thread.get_latest_results()
    assert results['detections'] == "coloured_shape_data"

    thread.stop()
    thread.join()


def test_vision_processing_thread_run_exits_if_no_pipeline(mock_camera, mock_pipeline):
    """Test that the run method exits immediately if the pipeline instance is None."""
    mock_pipeline.pipeline_type = "Invalid"
    thread = VisionProcessingThread(
        identifier=mock_camera.identifier,
        pipeline_id=mock_pipeline.id,
        pipeline_type=mock_pipeline.pipeline_type,
        pipeline_config_json=mock_pipeline.config,
        camera_matrix_json=mock_camera.camera_matrix_json,
        frame_queue=queue.Queue()
    )

    thread.start()
    thread.join(timeout=0.5) # Should exit very quickly

    assert not thread.is_alive()


def test_vision_processing_thread_imencode_failure(mock_camera, mock_pipeline):
    """Test that the loop continues gracefully if cv2.imencode fails."""
    frame_queue = queue.Queue()
    thread = VisionProcessingThread(
        identifier=mock_camera.identifier,
        pipeline_id=mock_pipeline.id,
        pipeline_type=mock_pipeline.pipeline_type,
        pipeline_config_json=mock_pipeline.config,
        camera_matrix_json=mock_camera.camera_matrix_json,
        frame_queue=frame_queue
    )

    frame_data = np.zeros((100, 100, 3), dtype=np.uint8)
    mock_rc_frame = MagicMock(spec=RefCountedFrame)
    mock_rc_frame.data = frame_data
    frame_queue.put(mock_rc_frame)

    with patch('cv2.imencode', return_value=(False, None)):
        thread.start()
        time.sleep(0.2)

        # The frame should not have been set
        with thread.processed_frame_lock:
            assert thread.latest_processed_frame is None

        thread.stop()
        thread.join()


def test_vision_processing_thread_init_bad_camera_matrix_json(mock_camera, mock_pipeline, mock_pipeline_instances):
    """Test that a bad camera_matrix_json from the DB is handled correctly."""
    mock_camera.camera_matrix_json = "this is not json"

    # The thread should still initialize
    thread = VisionProcessingThread(
        identifier=mock_camera.identifier,
        pipeline_id=mock_pipeline.id,
        pipeline_type=mock_pipeline.pipeline_type,
        pipeline_config_json=mock_pipeline.config,
        camera_matrix_json=mock_camera.camera_matrix_json,
        frame_queue=queue.Queue()
    )
    assert thread.cam_matrix is None

    # And the run loop should create a default one
    thread.start()
    time.sleep(0.1)
    thread.stop()
    thread.join()
    assert thread.cam_matrix is not None
    assert thread.cam_matrix[0, 0] == 600.0


# --- Tests for CameraAcquisitionThread ---

@pytest.fixture
def mock_driver():
    """Creates a mock camera driver instance."""
    driver = MagicMock()
    # Simulate getting enough good frames to trigger FPS calculation, then None to break loop
    # (1 for pool init + 6 for loop iterations where 6th triggers FPS calc + 1 None to break)
    frames = [np.zeros((10, 10, 3), dtype=np.uint8) for _ in range(7)] + [None]
    driver.get_frame.side_effect = frames
    return driver

@pytest.fixture
def mock_app(app):
    """Creates a mock Flask app object for the thread."""
    # We use the actual test app fixture to get a valid context
    mock_app_obj = app
    return mock_app_obj

def test_camera_acquisition_thread_init(mock_camera, mock_app):
    """Test the thread's constructor."""
    thread = CameraAcquisitionThread(
        identifier=mock_camera.identifier,
        camera_type=mock_camera.camera_type,
        orientation=mock_camera.orientation,
        app=mock_app
    )
    assert thread.identifier == mock_camera.identifier
    assert thread.daemon is True
    assert not thread.stop_event.is_set()

def test_camera_acquisition_thread_add_remove_queues(mock_camera, mock_app):
    """Test adding and removing pipeline queues."""
    thread = CameraAcquisitionThread(
        identifier=mock_camera.identifier,
        camera_type=mock_camera.camera_type,
        orientation=mock_camera.orientation,
        app=mock_app
    )

    # Add a queue
    q1 = queue.Queue()
    thread.add_pipeline_queue(101, q1)
    assert 101 in thread.processing_queues
    assert thread.processing_queues[101] == q1

    # Remove the queue
    thread.remove_pipeline_queue(101)
    assert 101 not in thread.processing_queues

@patch('app.camera_threads.get_driver')
@patch('app.camera_threads.CameraAcquisitionThread._acquisition_loop')
def test_camera_acquisition_thread_run_connect_disconnect(mock_acq_loop, mock_get_driver, mock_driver, mock_camera, mock_app):
    """Test the main run loop's connect/disconnect and loop call logic."""
    mock_get_driver.return_value = mock_driver
    thread = CameraAcquisitionThread(
        identifier=mock_camera.identifier,
        camera_type=mock_camera.camera_type,
        orientation=mock_camera.orientation,
        app=mock_app
    )

    # Make the loop run once then stop the thread
    mock_acq_loop.side_effect = lambda: thread.stop()

    thread.start()
    thread.join(timeout=1)

    mock_get_driver.assert_called_once_with({'camera_type': mock_camera.camera_type, 'identifier': mock_camera.identifier})
    mock_driver.connect.assert_called_once()
    mock_acq_loop.assert_called_once()
    mock_driver.disconnect.assert_called_once()

@patch('app.camera_threads.get_driver')
def test_camera_acquisition_thread_run_reconnection_on_error(mock_get_driver, mock_camera, mock_app):
    """Test that the thread attempts to reconnect after a driver error."""
    mock_successful_driver = MagicMock()
    mock_get_driver.side_effect = [Exception("Driver init failed"), mock_successful_driver]

    thread = CameraAcquisitionThread(
        identifier=mock_camera.identifier,
        camera_type=mock_camera.camera_type,
        orientation=mock_camera.orientation,
        app=mock_app
    )

    # The thread's main loop uses stop_event.wait(), which is basically time.sleep().
    # We patch the instance's event wait and the class's acquisition loop.
    with patch.object(thread.stop_event, 'wait') as mock_wait, \
         patch.object(CameraAcquisitionThread, '_acquisition_loop', side_effect=lambda: thread.stop()) as mock_acq_loop:

        thread.start()
        thread.join(timeout=2) # Should not time out now

        assert mock_get_driver.call_count == 2
        mock_successful_driver.connect.assert_called_once()
        mock_acq_loop.assert_called_once()
        mock_wait.assert_called_once_with(5.0)
        mock_successful_driver.disconnect.assert_called_once()


@patch('app.camera_threads.get_driver')
def test_acquisition_loop(mock_get_driver, mock_driver, mock_camera, mock_app):
    """Test the inner frame acquisition loop."""
    mock_get_driver.return_value = mock_driver
    thread = CameraAcquisitionThread(
        identifier=mock_camera.identifier,
        camera_type=mock_camera.camera_type,
        orientation=mock_camera.orientation,
        app=mock_app
    )
    thread.driver = mock_driver # Manually set driver since we're not calling run()

    # Add a consumer queue and mock its put method to check calls
    proc_q = MagicMock(spec=queue.Queue)
    thread.add_pipeline_queue(101, proc_q)

    # Manually call the loop, mocking time to ensure FPS gets calculated
    # Provide time values that create elapsed_time >= 1.0 to trigger FPS calculation
    # FPS is calculated when elapsed_time >= 1.0, so we need start_time=0, then times that eventually exceed 1.0
    time_side_effects = [0, 0.1, 0.2, 0.3, 0.4, 0.5, 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 1.7, 1.8, 1.9, 2.0, 2.1]
    with patch('time.time', side_effect=time_side_effects):
        thread._acquisition_loop()

    # get_frame was called 8 times (1 for init + 6 good frames + 1 None which breaks the loop)
    assert mock_driver.get_frame.call_count == 8

    # The first frame is consumed by pool initialization, the next 6 are queued
    assert proc_q.put_nowait.call_count == 6

    # Check latest frames
    with thread.raw_frame_lock:
        assert thread.latest_raw_frame is not None
    with thread.frame_lock:
        assert thread.latest_frame_for_display is not None

    # Check FPS calculation
    assert thread.fps > 0

def test_acquisition_loop_fails_first_frame():
    """Test that the acquisition loop exits if the first frame cannot be retrieved."""
    # Create a fresh driver mock for this specific test
    driver = MagicMock()
    driver.get_frame.return_value = None

    mock_camera = MagicMock()
    mock_camera.identifier = "test_cam"
    mock_camera.camera_type = "USB"
    mock_camera.orientation = 0
    thread = CameraAcquisitionThread(
        identifier=mock_camera.identifier,
        camera_type=mock_camera.camera_type,
        orientation=mock_camera.orientation,
        app=MagicMock()
    )
    thread.driver = driver

    thread._acquisition_loop()

    # The loop should return immediately, and no frames should be processed
    assert thread.latest_raw_frame is None
    assert thread.latest_frame_for_display is None


@pytest.mark.parametrize("orientation, cv2_rotate_code", [
    (90, cv2.ROTATE_90_CLOCKWISE),
    (180, cv2.ROTATE_180),
    (270, cv2.ROTATE_90_COUNTERCLOCKWISE)
])
@patch('cv2.rotate')
def test_apply_orientation(mock_rotate, orientation, cv2_rotate_code):
    """Test applying different rotation orientations."""
    thread = CameraAcquisitionThread(
        identifier="test",
        camera_type="USB",
        orientation=0,
        app=MagicMock()
    )
    frame = np.zeros((10, 10))
    thread._apply_orientation(frame, orientation)
    mock_rotate.assert_called_once_with(frame, cv2_rotate_code)

def test_apply_orientation_none():
    """Test that 0 or None orientation does not call rotate."""
    thread = CameraAcquisitionThread(
        identifier="test",
        camera_type="USB",
        orientation=0,
        app=MagicMock()
    )
    frame = np.zeros((10, 10))

    with patch('cv2.rotate') as mock_rotate:
        result = thread._apply_orientation(frame, 0)
        mock_rotate.assert_not_called()
        assert np.array_equal(result, frame)

@patch('app.camera_threads.get_driver')
def test_acquisition_loop_orientation_change(mock_get_driver, mock_driver, mock_camera, mock_app):
    """Test that the acquisition loop detects orientation changes and reconfigures."""
    mock_get_driver.return_value = mock_driver

    thread = CameraAcquisitionThread(
        identifier=mock_camera.identifier,
        camera_type=mock_camera.camera_type,
        orientation=0,  # Start with 0 orientation
        app=mock_app
    )
    thread.driver = mock_driver # Manually set driver since we're not calling run()

    with patch.object(thread.buffer_pool, 'initialize') as mock_pool_init:
        # Simulate the orientation changing mid-loop by using update_orientation
        # We'll use a side effect on get_frame to trigger the orientation change after a few frames
        frame_count = [0]
        def get_frame_side_effect():
            frame_count[0] += 1
            # After 3 frames, trigger orientation change
            if frame_count[0] == 3:
                thread.update_orientation(90)
            # Return frames for the first 5 calls, then None to break the loop
            if frame_count[0] <= 5:
                return np.zeros((10, 10, 3), dtype=np.uint8)
            return None

        mock_driver.get_frame.side_effect = get_frame_side_effect

        # Provide time values to prevent StopIteration
        time_side_effects = [0] + [0.1 * i for i in range(1, 20)]
        with patch('time.time', side_effect=time_side_effects):
             thread._acquisition_loop()

        # The pool should be initialized once at the start, and once after the config change
        assert mock_pool_init.call_count == 2


def test_acquisition_loop_handles_full_queue(mock_driver):
    """Test that a full consumer queue doesn't crash the acquisition thread."""
    thread = CameraAcquisitionThread(
        identifier="test",
        camera_type="USB",
        orientation=0,
        app=MagicMock()
    )
    thread.driver = mock_driver
    thread.buffer_pool.initialize(np.zeros((10, 10, 3)))

    # Add a full queue
    full_q = queue.Queue(maxsize=1)
    full_q.put("dummy")
    thread.add_pipeline_queue(1, full_q)

    with patch('app.camera_threads.RefCountedFrame.release') as mock_release:
        # This should run without raising a queue.Full exception
        thread._acquisition_loop()
        # The frame that failed to be put should have been released immediately
        assert mock_release.call_count > 0

def test_acquisition_loop_empty_buffer_pool(mock_driver, mock_camera, mock_app):
    """Test that the loop continues if the buffer pool is temporarily empty."""
    thread = CameraAcquisitionThread(
        identifier=mock_camera.identifier,
        camera_type=mock_camera.camera_type,
        orientation=mock_camera.orientation,
        app=mock_app
    )
    thread.driver = mock_driver
    thread.buffer_pool.initialize(np.zeros((10, 10, 3), dtype=np.uint8))

    # Temporarily make the pool return None
    with patch.object(thread.buffer_pool, 'get_buffer', return_value=None):
        thread._acquisition_loop()
        # Loop should complete
        assert mock_driver.get_frame.call_count > 0
        # The raw frame should be set
        assert thread.latest_raw_frame is not None
        # But the display frame and pipeline queues should not get anything
        assert thread.latest_frame_for_display is None


def test_prepare_display_frame():
    """Test that the FPS overlay is added to the frame."""
    thread = CameraAcquisitionThread(
        identifier="test",
        camera_type="USB",
        orientation=0,
        app=MagicMock()
    )
    thread.fps = 30.0
    frame = np.zeros((100, 100, 3), dtype=np.uint8)

    with patch('cv2.putText') as mock_put_text:
        processed_frame = thread._prepare_display_frame(frame)
        mock_put_text.assert_called_once()
        # Check that the text contains the FPS
        text_arg = mock_put_text.call_args[0][1]
        assert "FPS: 30.00" in text_arg
        # Ensure the original frame is modified and returned
        assert id(processed_frame) == id(frame)