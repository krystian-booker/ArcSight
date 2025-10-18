import time
import cv2
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
    last_frame_id = None

    try:
        while True:
            # Check if there's a new frame available without encoding
            # We use the raw frame object's id to detect changes
            with acq_thread.frame_lock:
                current_frame_raw = acq_thread.latest_display_frame_raw
                current_frame_id = (
                    id(current_frame_raw) if current_frame_raw is not None else None
                )

            # Only encode when we have a new frame to send
            if current_frame_id is not None and current_frame_id != last_frame_id:
                # Encode the frame only now, when we're about to send it
                with acq_thread.frame_lock:
                    if acq_thread.latest_display_frame_raw is not None:
                        ret, buffer = cv2.imencode(
                            ".jpg",
                            acq_thread.latest_display_frame_raw,
                            [cv2.IMWRITE_JPEG_QUALITY, acq_thread.jpeg_quality],
                        )
                        if ret:
                            yield (
                                b"--frame\r\n"
                                b"Content-Type: image/jpeg\r\n\r\n"
                                + buffer.tobytes()
                                + b"\r\n"
                            )
                            last_frame_id = current_frame_id

            if not acq_thread.is_alive():
                print(f"Stopping feed for {identifier} as acquisition thread has died.")
                break
            # Reduced from 100 FPS to ~30 FPS for web streaming (sufficient for display)
            time.sleep(0.033)
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

    last_frame_id = None

    try:
        while True:
            # Check if there's a new frame available without encoding
            # We use the raw frame object's id to detect changes
            with proc_thread.processed_frame_lock:
                current_frame_raw = proc_thread.latest_processed_frame_raw
                current_frame_id = (
                    id(current_frame_raw) if current_frame_raw is not None else None
                )

            # Only encode when we have a new frame to send
            if current_frame_id is not None and current_frame_id != last_frame_id:
                # Encode the frame only now, when we're about to send it
                with proc_thread.processed_frame_lock:
                    if proc_thread.latest_processed_frame_raw is not None:
                        ret, buffer = cv2.imencode(
                            ".jpg",
                            proc_thread.latest_processed_frame_raw,
                            [cv2.IMWRITE_JPEG_QUALITY, proc_thread.jpeg_quality],
                        )
                        if ret:
                            yield (
                                b"--frame\r\n"
                                b"Content-Type: image/jpeg\r\n\r\n"
                                + buffer.tobytes()
                                + b"\r\n"
                            )
                            last_frame_id = current_frame_id

            if not proc_thread.is_alive():
                print(
                    f"Stopping processed feed for {pipeline_id} as its thread has died."
                )
                break
            # Reduced from 100 FPS to ~30 FPS for web streaming (sufficient for display)
            time.sleep(0.033)
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
            # latest_raw_frame is now a RefCountedFrame, get a writable copy
            return acq_thread.latest_raw_frame.get_writable_copy()
    return None
