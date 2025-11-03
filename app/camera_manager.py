import logging
import queue
from sqlalchemy.orm import joinedload

from app.models import Camera
from app.camera_threads import CameraAcquisitionThread, VisionProcessingThread
from app.thread_config import build_camera_thread_config, CameraThreadConfig
from app import thread_state
from app.utils.config import ThreadConfig
from app.utils.camera_config import PipelineManagerConfig

logger = logging.getLogger(__name__)


# --- Centralized Thread Management ---
def start_camera_thread(camera_config: CameraThreadConfig, app):
    """Starts acquisition and processing threads for a single camera."""
    identifier = camera_config.identifier

    # Check if already running
    if thread_state.is_camera_running(identifier):
        logger.warning(f"Camera {identifier} is already running")
        return

    logger.info(f"Starting threads for camera {identifier}")

    # Display frames use higher quality since they're the main view
    acq_thread = CameraAcquisitionThread(
        camera_id=camera_config.id,
        identifier=camera_config.identifier,
        camera_type=camera_config.camera_type,
        orientation=camera_config.orientation,
        app=app,
        jpeg_quality=ThreadConfig.DISPLAY_JPEG_QUALITY,
        depth_enabled=camera_config.depth_enabled,
        resolution_json=camera_config.resolution_json,
        framerate=camera_config.framerate,
        exposure_mode=camera_config.exposure_mode,
        exposure_value=camera_config.exposure_value,
        gain_mode=camera_config.gain_mode,
        gain_value=camera_config.gain_value,
    )

    # Create processing threads for each pipeline
    processing_threads = {}
    for pipeline in camera_config.pipelines:
        frame_queue = queue.Queue(maxsize=ThreadConfig.PIPELINE_QUEUE_SIZE)
        # Pipeline frames use lower quality to save CPU
        proc_thread = VisionProcessingThread(
            identifier=identifier,
            pipeline_id=pipeline.id,
            pipeline_type=pipeline.pipeline_type,
            pipeline_config_json=pipeline.config,
            camera_matrix_json=camera_config.camera_matrix_json,
            dist_coeffs_json=camera_config.dist_coeffs_json,
            frame_queue=frame_queue,
            jpeg_quality=ThreadConfig.PIPELINE_JPEG_QUALITY,
        )

        acq_thread.add_pipeline_queue(pipeline.id, frame_queue)
        processing_threads[pipeline.id] = proc_thread

    # Register the thread group
    thread_state.register_thread_group(identifier, acq_thread, processing_threads)

    # Start all threads
    acq_thread.start()
    for proc_thread in processing_threads.values():
        proc_thread.start()


def stop_camera_thread(identifier):
    """Stops all threads for a single camera."""
    try:
        # Step 1: Mark camera as stopping and get thread references
        with thread_state.safe_thread_access(identifier, mark_stopping=True) as thread_group:
            logger.info(f"Stopping threads for camera {identifier}")

            # Copy thread references while holding lock to avoid TOCTOU race condition
            acq_thread = thread_group["acquisition"]
            proc_threads_list = list(thread_group["processing_threads"].items())
    except thread_state.ThreadNotAccessibleError as e:
        logger.debug(f"Cannot stop camera {identifier}: {e}")
        return

    # Step 2: Signal all threads to stop (outside lock to avoid deadlock)
    for pipeline_id, proc_thread in proc_threads_list:
        proc_thread.stop()
    acq_thread.stop()

    # Step 3: Wait for threads to terminate with timeout
    acq_thread.join(timeout=ThreadConfig.THREAD_STOP_TIMEOUT)

    if acq_thread.is_alive():
        logger.warning(
            f"Acquisition thread for {identifier} did not terminate within {ThreadConfig.THREAD_STOP_TIMEOUT} seconds"
        )

    for pipeline_id, proc_thread in proc_threads_list:
        proc_thread.join(timeout=ThreadConfig.THREAD_STOP_TIMEOUT)
        if proc_thread.is_alive():
            logger.warning(
                f"Processing thread {pipeline_id} for {identifier} did not terminate within {ThreadConfig.THREAD_STOP_TIMEOUT} seconds"
            )

    # Step 4: Remove from active threads
    thread_state.unregister_thread_group(identifier)
    logger.info(f"Successfully stopped and removed threads for camera {identifier}")


def add_pipeline_to_camera(identifier: str, config: PipelineManagerConfig):
    """Starts a new processing thread for a running camera.

    Args:
        identifier: Camera identifier string
        config: PipelineManagerConfig containing pipeline configuration

    Note:
        This function accepts primitive values to avoid database I/O in the hot path.
        Callers should pre-fetch data from the database before calling.
    """
    try:
        with thread_state.safe_thread_access(identifier) as thread_group:
            # Check if pipeline already exists
            if config.pipeline_id in thread_group["processing_threads"]:
                logger.warning(f"Pipeline {config.pipeline_id} already exists for camera {identifier}")
                return

            logger.info(f"Dynamically adding pipeline {config.pipeline_id} to camera {identifier}")

            # Create new processing thread
            frame_queue = queue.Queue(maxsize=ThreadConfig.PIPELINE_QUEUE_SIZE)
            proc_thread = VisionProcessingThread(
                identifier=identifier,
                pipeline_id=config.pipeline_id,
                pipeline_type=config.pipeline_type,
                pipeline_config_json=config.pipeline_config_json,
                camera_matrix_json=config.camera_matrix_json,
                dist_coeffs_json=config.dist_coeffs_json,
                frame_queue=frame_queue,
                jpeg_quality=ThreadConfig.PIPELINE_JPEG_QUALITY,
            )

            # Add to acquisition thread and thread group
            thread_group["acquisition"].add_pipeline_queue(config.pipeline_id, frame_queue)
            thread_state.add_processing_thread(identifier, config.pipeline_id, proc_thread)
            proc_thread.start()
    except thread_state.ThreadNotAccessibleError as e:
        logger.warning(f"Cannot add pipeline to camera {identifier}: {e}")


def remove_pipeline_from_camera(identifier, pipeline_id):
    """Stops a specific processing thread for a running camera.

    Args:
        identifier: Camera identifier string
        pipeline_id: Pipeline database ID to remove

    Note:
        This function accepts primitive values to avoid database I/O in the hot path.
        Callers should pre-fetch the camera identifier before calling.
    """
    try:
        with thread_state.safe_thread_access(identifier) as thread_group:
            if pipeline_id not in thread_group["processing_threads"]:
                logger.warning(
                    f"Pipeline {pipeline_id} not found for camera {identifier}"
                )
                return

            logger.info(
                f"Dynamically removing pipeline {pipeline_id} from camera {identifier}"
            )
            proc_thread = thread_group["processing_threads"][pipeline_id]

            # Signal thread to stop and remove from queues
            proc_thread.stop()
            thread_group["acquisition"].remove_pipeline_queue(pipeline_id)

            # Remove from thread state
            thread_state.remove_processing_thread(identifier, pipeline_id)

        # Wait for thread to terminate (outside lock)
        proc_thread.join(timeout=ThreadConfig.THREAD_STOP_TIMEOUT)
        if proc_thread.is_alive():
            logger.warning(
                f"Processing thread {pipeline_id} did not terminate within {ThreadConfig.THREAD_STOP_TIMEOUT} seconds"
            )
    except thread_state.ThreadNotAccessibleError as e:
        logger.warning(f"Cannot remove pipeline from camera {identifier}: {e}")


def update_pipeline_in_camera(identifier: str, config: PipelineManagerConfig):
    """Stops and restarts a pipeline processing thread to apply new settings.

    Args:
        identifier: Camera identifier string
        config: PipelineManagerConfig containing updated pipeline configuration

    Note:
        This function accepts primitive values to avoid database I/O in the hot path.
        Callers should pre-fetch data from the database before calling.
    """
    try:
        with thread_state.safe_thread_access(identifier) as thread_group:
            # 1. Stop and remove the old thread if it exists
            old_proc_thread = None
            if config.pipeline_id in thread_group["processing_threads"]:
                logger.info(f"Stopping old pipeline thread {config.pipeline_id} for update")
                old_proc_thread = thread_group["processing_threads"][config.pipeline_id]
                old_proc_thread.stop()
                thread_group["acquisition"].remove_pipeline_queue(config.pipeline_id)
                thread_state.remove_processing_thread(identifier, config.pipeline_id)

        # Wait for old thread to terminate (outside lock)
        if old_proc_thread:
            old_proc_thread.join(timeout=ThreadConfig.THREAD_STOP_TIMEOUT)
            if old_proc_thread.is_alive():
                logger.warning(
                    f"Old processing thread {config.pipeline_id} did not terminate within {ThreadConfig.THREAD_STOP_TIMEOUT} seconds"
                )

        # 2. Start a new thread with the updated pipeline config
        with thread_state.safe_thread_access(identifier) as thread_group:
            logger.info(f"Starting new pipeline thread {config.pipeline_id} with updated config")
            frame_queue = queue.Queue(maxsize=ThreadConfig.PIPELINE_QUEUE_SIZE)
            new_proc_thread = VisionProcessingThread(
                identifier=identifier,
                pipeline_id=config.pipeline_id,
                pipeline_type=config.pipeline_type,
                pipeline_config_json=config.pipeline_config_json,
                camera_matrix_json=config.camera_matrix_json,
                dist_coeffs_json=config.dist_coeffs_json,
                frame_queue=frame_queue,
                jpeg_quality=ThreadConfig.PIPELINE_JPEG_QUALITY,
            )

            thread_group["acquisition"].add_pipeline_queue(config.pipeline_id, frame_queue)
            thread_state.add_processing_thread(identifier, config.pipeline_id, new_proc_thread)
            new_proc_thread.start()
    except thread_state.ThreadNotAccessibleError as e:
        logger.warning(f"Cannot update pipeline for camera {identifier}: {e}")


def start_all_camera_threads(app):
    """Initializes all configured cameras at application startup."""
    logger.info("Starting acquisition and processing threads for all configured cameras...")
    with app.app_context():
        camera_configs = [
            build_camera_thread_config(camera)
            for camera in Camera.query.options(joinedload(Camera.pipelines)).all()
        ]
    for camera_config in camera_configs:
        start_camera_thread(camera_config, app)


def stop_all_camera_threads():
    """Gracefully stops all threads at application shutdown."""
    logger.info("Stopping all camera acquisition and processing threads...")
    identifiers_to_stop = thread_state.get_all_active_identifiers()

    for identifier in identifiers_to_stop:
        stop_camera_thread(identifier)

    logger.info("All camera threads stopped")


def get_camera_pipeline_results(identifier):
    """Gets the latest results from all pipelines for a given camera."""
    thread_group = thread_state.get_thread_group(identifier)
    if not thread_group:
        return None

    results = {}
    for pipeline_id, proc_thread in thread_group["processing_threads"].items():
        results[pipeline_id] = proc_thread.get_latest_results()

    return results


def is_camera_thread_running(identifier):
    """Checks if a camera's acquisition thread is active."""
    thread_group = thread_state.get_thread_group(identifier)
    if not thread_group:
        return False
    # Don't report as running if it's being stopped
    if thread_group.get("stopping", False):
        return False
    return thread_group["acquisition"].is_alive()


def notify_camera_config_update(identifier, new_orientation):
    """Notifies a camera thread of configuration changes via event signaling."""
    try:
        with thread_state.safe_thread_access(identifier) as thread_group:
            acq_thread = thread_group["acquisition"]
            acq_thread.update_orientation(new_orientation)
            logger.info(
                f"Notified camera {identifier} of orientation change to {new_orientation}"
            )
    except thread_state.ThreadNotAccessibleError as e:
        logger.debug(f"Cannot notify camera {identifier}: {e}")
