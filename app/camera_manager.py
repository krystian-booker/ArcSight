import threading
import queue

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
            
            acq_thread = CameraAcquisitionThread(camera, app)
            
            # Pipelines are loaded via the relationship
            pipelines = camera.pipelines
            
            processing_threads = {}
            for pipeline in pipelines:
                frame_queue = queue.Queue(maxsize=2)
                # Pass the ORM objects directly
                proc_thread = VisionProcessingThread(identifier, pipeline, camera, frame_queue)
                
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
    with active_camera_threads_lock:
        if identifier in active_camera_threads:
            print(f"Stopping threads for camera {identifier}")
            thread_group = active_camera_threads.pop(identifier)
            
            for proc_thread in thread_group['processing_threads'].values():
                proc_thread.stop()
            thread_group['acquisition'].stop()

            thread_group['acquisition'].join(timeout=2)
            for proc_thread in thread_group['processing_threads'].values():
                proc_thread.join(timeout=2)


def add_pipeline_to_camera(camera_id, pipeline, app):
    """Starts a new processing thread for a running camera."""
    with app.app_context():
        camera = Camera.query.get(camera_id)
    if not camera:
        return

    identifier = camera.identifier
    with active_camera_threads_lock:
        if identifier in active_camera_threads:
            thread_group = active_camera_threads[identifier]
            pipeline_id = pipeline.id

            if pipeline_id not in thread_group['processing_threads']:
                print(f"Dynamically adding pipeline {pipeline_id} to camera {identifier}")
                frame_queue = queue.Queue(maxsize=2)
                proc_thread = VisionProcessingThread(identifier, pipeline, camera, frame_queue)
                thread_group['acquisition'].add_pipeline_queue(pipeline_id, frame_queue)
                thread_group['processing_threads'][pipeline_id] = proc_thread
                proc_thread.start()


def remove_pipeline_from_camera(camera_id, pipeline_id, app):
    """Stops a specific processing thread for a running camera."""
    with app.app_context():
        camera = Camera.query.get(camera_id)
    if not camera:
        return

    identifier = camera.identifier
    with active_camera_threads_lock:
        if identifier in active_camera_threads:
            thread_group = active_camera_threads[identifier]
            if pipeline_id in thread_group['processing_threads']:
                print(f"Dynamically removing pipeline {pipeline_id} from camera {identifier}")
                proc_thread = thread_group['processing_threads'].pop(pipeline_id)
                
                proc_thread.stop()
                thread_group['acquisition'].remove_pipeline_queue(pipeline_id)
                proc_thread.join(timeout=2)


def update_pipeline_in_camera(camera_id, pipeline_id, app):
    """Stops and restarts a pipeline processing thread to apply new settings."""
    with app.app_context():
        camera = Camera.query.get(camera_id)
        pipeline = Pipeline.query.get(pipeline_id)
    
    if not camera or not pipeline:
        print(f"Error: Could not find camera or pipeline for update.")
        return

    identifier = camera.identifier
    with active_camera_threads_lock:
        if identifier in active_camera_threads:
            thread_group = active_camera_threads[identifier]
            
            # 1. Stop and remove the old thread if it exists
            if pipeline_id in thread_group['processing_threads']:
                print(f"Stopping old pipeline thread {pipeline_id} for update.")
                old_proc_thread = thread_group['processing_threads'].pop(pipeline_id)
                old_proc_thread.stop()
                thread_group['acquisition'].remove_pipeline_queue(pipeline_id)
                old_proc_thread.join(timeout=2) # Wait for it to terminate

            # 2. Start a new thread with the updated pipeline_info
            print(f"Starting new pipeline thread {pipeline_id} with updated config.")
            frame_queue = queue.Queue(maxsize=2)
            new_proc_thread = VisionProcessingThread(identifier, pipeline, camera, frame_queue)
            
            thread_group['acquisition'].add_pipeline_queue(pipeline_id, frame_queue)
            thread_group['processing_threads'][pipeline_id] = new_proc_thread
            new_proc_thread.start()


def start_all_camera_threads(app):
    """Initializes all configured cameras at application startup."""
    print("Starting acquisition and processing threads for all configured cameras...")
    with app.app_context():
        cameras = Camera.query.all()
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
        return thread_group and thread_group['acquisition'].is_alive()