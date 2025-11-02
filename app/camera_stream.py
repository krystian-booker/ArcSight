import logging
import time
from typing import Generator, Optional

from app import thread_state
from app.utils.encoding import encode_frame_to_jpeg

logger = logging.getLogger(__name__)


def _generate_mjpeg_stream(
    thread_obj,
    frame_lock_attr: str,
    frame_seq_attr: str,
    frame_data_attr: str,
    feed_name: str
) -> Generator[bytes, None, None]:
    """
    Generic MJPEG stream generator for camera or pipeline feeds.

    Args:
        thread_obj: Thread object containing frame data
        frame_lock_attr: Name of the lock attribute (e.g., 'frame_lock')
        frame_seq_attr: Name of the sequence number attribute (e.g., 'display_frame_seq')
        frame_data_attr: Name of the frame data attribute (e.g., 'latest_display_frame_raw')
        feed_name: Name for logging purposes

    Yields:
        MJPEG frame chunks as bytes
    """
    last_frame_seq = -1
    frame_lock = getattr(thread_obj, frame_lock_attr)
    jpeg_quality = getattr(thread_obj, "jpeg_quality", 85)

    try:
        while True:
            frame_bytes = None

            with frame_lock:
                current_frame_seq = getattr(thread_obj, frame_seq_attr, -1)
                latest_frame = getattr(thread_obj, frame_data_attr, None)

                if latest_frame is not None and current_frame_seq != last_frame_seq:
                    frame_bytes = encode_frame_to_jpeg(latest_frame, jpeg_quality)
                    if frame_bytes:
                        last_frame_seq = current_frame_seq

            if frame_bytes is not None:
                yield (
                    b"--frame\r\n"
                    b"Content-Type: image/jpeg\r\n\r\n" + frame_bytes + b"\r\n"
                )
                continue

            if not thread_obj.is_alive():
                logger.info(f"Stopping feed for {feed_name} as thread has died")
                break

            time.sleep(0.001)
    except GeneratorExit:
        logger.debug(f"Client disconnected from {feed_name} feed")


def get_camera_feed(camera) -> Generator[bytes, None, None]:
    """
    Generator that yields MJPEG frames from a camera's acquisition thread.

    Uses lazy encoding - frames are only JPEG-compressed when a client requests them,
    avoiding wasteful encoding when no clients are connected.

    Args:
        camera: Camera ORM object

    Yields:
        MJPEG frame chunks as bytes
    """
    identifier = camera.identifier
    thread_group = thread_state.get_thread_group(identifier)

    if not thread_group or not thread_group["acquisition"].is_alive():
        logger.warning(
            f"Attempted to get feed for {identifier}, but its thread is not running"
        )
        return

    acq_thread = thread_group["acquisition"]
    yield from _generate_mjpeg_stream(
        thread_obj=acq_thread,
        frame_lock_attr="frame_lock",
        frame_seq_attr="display_frame_seq",
        frame_data_attr="latest_display_frame_raw",
        feed_name=identifier
    )


def get_processed_camera_feed(pipeline_id: int) -> Generator[bytes, None, None]:
    """
    Generator that yields MJPEG frames from a vision processing thread.

    Uses lazy encoding - frames are only JPEG-compressed when a client requests them,
    avoiding wasteful encoding when no clients are connected.

    Args:
        pipeline_id: Pipeline database ID

    Yields:
        MJPEG frame chunks as bytes
    """
    # Find the processing thread across all cameras
    proc_thread = None
    for thread_group in thread_state.active_camera_threads.values():
        if pipeline_id in thread_group.get("processing_threads", {}):
            proc_thread = thread_group["processing_threads"][pipeline_id]
            break

    if not proc_thread or not proc_thread.is_alive():
        logger.warning(
            f"Attempted to get processed feed for pipeline {pipeline_id}, but its thread is not running"
        )
        return

    yield from _generate_mjpeg_stream(
        thread_obj=proc_thread,
        frame_lock_attr="processed_frame_lock",
        frame_seq_attr="processed_frame_seq",
        frame_data_attr="latest_processed_frame_raw",
        feed_name=f"pipeline_{pipeline_id}"
    )


def get_latest_raw_frame(identifier: str) -> Optional[bytes]:
    """
    Gets the latest raw, unprocessed frame from a camera's acquisition thread.

    Args:
        identifier: Camera identifier

    Returns:
        Writable copy of the latest frame, or None if not available
    """
    thread_group = thread_state.get_thread_group(identifier)

    if not thread_group or not thread_group["acquisition"].is_alive():
        return None

    acq_thread = thread_group["acquisition"]
    with acq_thread.raw_frame_lock:
        if acq_thread.latest_raw_frame is not None:
            # latest_raw_frame is now a RefCountedFrame, get a writable copy
            return acq_thread.latest_raw_frame.get_writable_copy()
    return None
