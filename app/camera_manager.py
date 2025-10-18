import threading
import queue
from sqlalchemy.orm import joinedload

from .extensions import db
from .models import Camera, Pipeline
from .camera_threads import CameraAcquisitionThread, VisionProcessingThread

# --- Globals & Threading Primitives ---
active_camera_threads = {}
active_camera_threads_lock = threading.Lock()


# --- Centralized Thread Management ---
def start_camera_thread(camera, app):
    """Starts acquisition and processing threads for a single camera."""
    with active_camera_threads_lock:
        identifier = camera.identifier
        if identifier not in active_camera_threads:
            print(f"Starting threads for camera {identifier}")

            # Extract primitive values from ORM object
            # Display frames use higher quality (85) since they're the main view
            acq_thread = CameraAcquisitionThread(
                identifier=camera.identifier,
                camera_type=camera.camera_type,
                orientation=camera.orientation,
                app=app,
                jpeg_quality=85
            )

            # Pipelines are loaded via the relationship
            pipelines = camera.pipelines

            processing_threads = {}
            for pipeline in pipelines:
                frame_queue = queue.Queue(maxsize=2)
                # Pass primitive values instead of ORM objects
                # Pipeline frames use lower quality (75) to save CPU
                proc_thread = VisionProcessingThread(
                    identifier=identifier,
                    pipeline_id=pipeline.id,
                    pipeline_type=pipeline.pipeline_type,
                    pipeline_config_json=pipeline.config,
                    camera_matrix_json=camera.camera_matrix_json,
                    frame_queue=frame_queue,
                    jpeg_quality=75
                )

                acq_thread.add_pipeline_queue(pipeline.id, frame_queue)
                processing_threads[pipeline.id] = proc_thread

            active_camera_threads[identifier] = {
                'acquisition': acq_thread,
                'processing_threads': processing_threads
            }

            acq_thread.start()
            for proc_thread in processing_threads.values():
                proc_thread.start()


def stop_camera_thread(identifier):
    """Stops all threads for a single camera."""
    # Step 1: Mark camera as stopping and get thread references
    with active_camera_threads_lock:
        if identifier not in active_camera_threads:
            return

        thread_group = active_camera_threads[identifier]

        # Mark as stopping to prevent concurrent access issues
        if 'stopping' in thread_group and thread_group['stopping']:
            print(f"Camera {identifier} is already being stopped")
            return

        thread_group['stopping'] = True
        print(f"Stopping threads for camera {identifier}")

    # Step 2: Signal all threads to stop (outside lock to avoid deadlock)
    for proc_thread in thread_group['processing_threads'].values():
        proc_thread.stop()
    thread_group['acquisition'].stop()

    # Step 3: Wait for threads to terminate with timeout
    acq_thread = thread_group['acquisition']
    acq_thread.join(timeout=5)

    if acq_thread.is_alive():
        print(f"WARNING: Acquisition thread for {identifier} did not terminate within 5 seconds")

    for pipeline_id, proc_thread in thread_group['processing_threads'].items():
        proc_thread.join(timeout=5)
        if proc_thread.is_alive():
            print(f"WARNING: Processing thread {pipeline_id} for {identifier} did not terminate within 5 seconds")

    # Step 4: Remove from active threads (with lock)
    with active_camera_threads_lock:
        if identifier in active_camera_threads:
            active_camera_threads.pop(identifier)
            print(f"Successfully stopped and removed threads for camera {identifier}")


def add_pipeline_to_camera(identifier, pipeline_id, pipeline_type, pipeline_config_json, camera_matrix_json):
    """Starts a new processing thread for a running camera.

    Args:
        identifier: Camera identifier string
        pipeline_id: Pipeline database ID
        pipeline_type: Pipeline type string (e.g., 'AprilTag')
        pipeline_config_json: Pipeline configuration as JSON string
        camera_matrix_json: Camera calibration matrix as JSON string

    Note:
        This function accepts primitive values to avoid database I/O in the hot path.
        Callers should pre-fetch data from the database before calling.
    """
    with active_camera_threads_lock:
        if identifier not in active_camera_threads:
            print(f"Cannot add pipeline to camera {identifier}: camera not running")
            return

        thread_group = active_camera_threads[identifier]

        # Don't add pipelines to cameras that are stopping
        if thread_group.get('stopping', False):
            print(f"Cannot add pipeline to camera {identifier}: camera is stopping")
            return

        if pipeline_id not in thread_group['processing_threads']:
            print(f"Dynamically adding pipeline {pipeline_id} to camera {identifier}")
            frame_queue = queue.Queue(maxsize=2)
            # Pass primitive values instead of ORM objects
            # Pipeline frames use lower quality (75) to save CPU
            proc_thread = VisionProcessingThread(
                identifier=identifier,
                pipeline_id=pipeline_id,
                pipeline_type=pipeline_type,
                pipeline_config_json=pipeline_config_json,
                camera_matrix_json=camera_matrix_json,
                frame_queue=frame_queue,
                jpeg_quality=75
            )
            thread_group['acquisition'].add_pipeline_queue(pipeline_id, frame_queue)
            thread_group['processing_threads'][pipeline_id] = proc_thread
            proc_thread.start()


def remove_pipeline_from_camera(identifier, pipeline_id):
    """Stops a specific processing thread for a running camera.

    Args:
        identifier: Camera identifier string
        pipeline_id: Pipeline database ID to remove

    Note:
        This function accepts primitive values to avoid database I/O in the hot path.
        Callers should pre-fetch the camera identifier before calling.
    """
    with active_camera_threads_lock:
        if identifier not in active_camera_threads:
            print(f"Cannot remove pipeline from camera {identifier}: camera not running")
            return

        thread_group = active_camera_threads[identifier]
        if pipeline_id in thread_group['processing_threads']:
            print(f"Dynamically removing pipeline {pipeline_id} from camera {identifier}")
            proc_thread = thread_group['processing_threads'].pop(pipeline_id)

            proc_thread.stop()
            thread_group['acquisition'].remove_pipeline_queue(pipeline_id)
            proc_thread.join(timeout=2)


def update_pipeline_in_camera(identifier, pipeline_id, pipeline_type, pipeline_config_json, camera_matrix_json):
    """Stops and restarts a pipeline processing thread to apply new settings.

    Args:
        identifier: Camera identifier string
        pipeline_id: Pipeline database ID
        pipeline_type: Pipeline type string (e.g., 'AprilTag')
        pipeline_config_json: Updated pipeline configuration as JSON string
        camera_matrix_json: Camera calibration matrix as JSON string

    Note:
        This function accepts primitive values to avoid database I/O in the hot path.
        Callers should pre-fetch data from the database before calling.
    """
    with active_camera_threads_lock:
        if identifier not in active_camera_threads:
            print(f"Cannot update pipeline for camera {identifier}: camera not running")
            return

        thread_group = active_camera_threads[identifier]

        # Don't update pipelines on cameras that are stopping
        if thread_group.get('stopping', False):
            print(f"Cannot update pipeline {pipeline_id}: camera {identifier} is stopping")
            return

        # 1. Stop and remove the old thread if it exists
        if pipeline_id in thread_group['processing_threads']:
            print(f"Stopping old pipeline thread {pipeline_id} for update.")
            old_proc_thread = thread_group['processing_threads'].pop(pipeline_id)
            old_proc_thread.stop()
            thread_group['acquisition'].remove_pipeline_queue(pipeline_id)
            old_proc_thread.join(timeout=2)  # Wait for it to terminate

        # 2. Start a new thread with the updated pipeline config
        print(f"Starting new pipeline thread {pipeline_id} with updated config.")
        frame_queue = queue.Queue(maxsize=2)
        # Pass primitive values instead of ORM objects
        # Pipeline frames use lower quality (75) to save CPU
        new_proc_thread = VisionProcessingThread(
            identifier=identifier,
            pipeline_id=pipeline_id,
            pipeline_type=pipeline_type,
            pipeline_config_json=pipeline_config_json,
            camera_matrix_json=camera_matrix_json,
            frame_queue=frame_queue,
            jpeg_quality=75
        )

        thread_group['acquisition'].add_pipeline_queue(pipeline_id, frame_queue)
        thread_group['processing_threads'][pipeline_id] = new_proc_thread
        new_proc_thread.start()


def start_all_camera_threads(app):
    """Initializes all configured cameras at application startup."""
    print("Starting acquisition and processing threads for all configured cameras...")
    with app.app_context():
        cameras = Camera.query.options(joinedload(Camera.pipelines)).all()
    for camera in cameras:
        start_camera_thread(camera, app)


def stop_all_camera_threads():
    """Gracefully stops all threads at application shutdown."""
    print("Stopping all camera acquisition and processing threads...")
    with active_camera_threads_lock:
        identifiers_to_stop = list(active_camera_threads.keys())
    
    for identifier in identifiers_to_stop:
        stop_camera_thread(identifier)
    
    print("All camera threads stopped.")


def get_camera_pipeline_results(identifier):
    """Gets the latest results from all pipelines for a given camera."""
    with active_camera_threads_lock:
        thread_group = active_camera_threads.get(identifier)
        if not thread_group:
            return None
        
        results = {}
        for pipeline_id, proc_thread in thread_group['processing_threads'].items():
            results[pipeline_id] = proc_thread.get_latest_results()
        
        return results


def is_camera_thread_running(identifier):
    """Checks if a camera's acquisition thread is active."""
    with active_camera_threads_lock:
        thread_group = active_camera_threads.get(identifier)
        if not thread_group:
            return False
        # Don't report as running if it's being stopped
        if thread_group.get('stopping', False):
            return False
        return thread_group['acquisition'].is_alive()


def notify_camera_config_update(identifier, new_orientation):
    """Notifies a camera thread of configuration changes via event signaling."""
    with active_camera_threads_lock:
        thread_group = active_camera_threads.get(identifier)
        if thread_group and not thread_group.get('stopping', False):
            acq_thread = thread_group['acquisition']
            acq_thread.update_orientation(new_orientation)
            print(f"Notified camera {identifier} of orientation change to {new_orientation}")