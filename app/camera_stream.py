import time
from .camera_manager import active_camera_threads, active_camera_threads_lock


# --- Web Streaming & Camera Utilities ---
def get_camera_feed(camera):
    """A generator that yields JPEG frames from a camera's acquisition thread.

    Uses lazy encoding - frames are only JPEG-compressed when a client requests them,
    avoiding wasteful encoding when no clients are connected.
    """
    identifier = camera.identifier

    with active_camera_threads_lock:
        thread_group = active_camera_threads.get(identifier)

    if not thread_group or not thread_group["acquisition"].is_alive():
        print(
            f"Warning: Attempted to get feed for {identifier}, but its thread is not running."
        )
        return

    acq_thread = thread_group["acquisition"]

    try:
        while True:
            # Lazy encoding: Only encode frame when client requests it
            frame_to_send = acq_thread.get_display_frame()

            if frame_to_send:
                yield (
                    b"--frame\r\n"
                    b"Content-Type: image/jpeg\r\n\r\n" + frame_to_send + b"\r\n"
                )

            if not acq_thread.is_alive():
                print(f"Stopping feed for {identifier} as acquisition thread has died.")
                break
            time.sleep(0.01)
    except GeneratorExit:
        print(f"Client disconnected from camera feed {identifier}.")


def get_processed_camera_feed(pipeline_id):
    """A generator that yields JPEG frames from a vision processing thread.

    Uses lazy encoding - frames are only JPEG-compressed when a client requests them,
    avoiding wasteful encoding when no clients are connected.
    """
    proc_thread = None
    with active_camera_threads_lock:
        for thread_group in active_camera_threads.values():
            if pipeline_id in thread_group["processing_threads"]:
                proc_thread = thread_group["processing_threads"][pipeline_id]
                break

    if not proc_thread or not proc_thread.is_alive():
        print(
            f"Warning: Attempted to get processed feed for pipeline {pipeline_id}, but its thread is not running."
        )
        return

    try:
        while True:
            # Lazy encoding: Only encode frame when client requests it
            frame_to_send = proc_thread.get_processed_frame()

            if frame_to_send:
                yield (
                    b"--frame\r\n"
                    b"Content-Type: image/jpeg\r\n\r\n" + frame_to_send + b"\r\n"
                )

            if not proc_thread.is_alive():
                print(
                    f"Stopping processed feed for {pipeline_id} as its thread has died."
                )
                break
            time.sleep(0.01)
    except GeneratorExit:
        print(f"Client disconnected from processed feed {pipeline_id}.")


def get_latest_raw_frame(identifier):
    """Gets the latest raw, unprocessed frame from a camera's acquisition thread."""
    with active_camera_threads_lock:
        thread_group = active_camera_threads.get(identifier)

    if not thread_group or not thread_group["acquisition"].is_alive():
        return None

    acq_thread = thread_group["acquisition"]
    with acq_thread.raw_frame_lock:
        if acq_thread.latest_raw_frame is not None:
            return acq_thread.latest_raw_frame.copy()
    return None
