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
    last_frame_seq = -1

    try:
        while True:
            frame_bytes = None
            with acq_thread.frame_lock:
                current_frame_seq = getattr(acq_thread, "display_frame_seq", -1)
                latest_frame = acq_thread.latest_display_frame_raw
                if latest_frame is not None and current_frame_seq != last_frame_seq:
                    ret, buffer = cv2.imencode(
                        ".jpg",
                        latest_frame,
                        [cv2.IMWRITE_JPEG_QUALITY, acq_thread.jpeg_quality],
                    )
                    if ret:
                        frame_bytes = buffer.tobytes()
                        last_frame_seq = current_frame_seq

            if frame_bytes is not None:
                yield (
                    b"--frame\r\n"
                    b"Content-Type: image/jpeg\r\n\r\n" + frame_bytes + b"\r\n"
                )
                continue

            if not acq_thread.is_alive():
                print(f"Stopping feed for {identifier} as acquisition thread has died.")
                break
            time.sleep(0.001)
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

    last_frame_seq = -1

    try:
        while True:
            frame_bytes = None
            with proc_thread.processed_frame_lock:
                current_frame_seq = getattr(proc_thread, "processed_frame_seq", -1)
                latest_frame = proc_thread.latest_processed_frame_raw
                if latest_frame is not None and current_frame_seq != last_frame_seq:
                    ret, buffer = cv2.imencode(
                        ".jpg",
                        latest_frame,
                        [cv2.IMWRITE_JPEG_QUALITY, proc_thread.jpeg_quality],
                    )
                    if ret:
                        frame_bytes = buffer.tobytes()
                        last_frame_seq = current_frame_seq

            if frame_bytes is not None:
                yield (
                    b"--frame\r\n"
                    b"Content-Type: image/jpeg\r\n\r\n" + frame_bytes + b"\r\n"
                )
                continue

            if not proc_thread.is_alive():
                print(
                    f"Stopping processed feed for {pipeline_id} as its thread has died."
                )
                break
            time.sleep(0.001)
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
