"""Thread state management and querying."""

import logging
import threading
from contextlib import contextmanager
from typing import Any, Dict, Iterator, Optional

logger = logging.getLogger(__name__)


class ThreadNotAccessibleError(Exception):
    """Raised when a thread cannot be accessed (not running or stopping)."""
    pass


# Global thread state
active_camera_threads: Dict[str, Dict[str, Any]] = {}
active_camera_threads_lock = threading.Lock()


def is_camera_running(identifier: str) -> bool:
    """
    Check if a camera thread is currently active.

    Args:
        identifier: Camera identifier

    Returns:
        True if camera thread exists and is not stopping
    """
    with active_camera_threads_lock:
        thread_group = active_camera_threads.get(identifier)
        if not thread_group:
            return False
        return not thread_group.get("stopping", False)


def get_thread_group(identifier: str) -> Optional[Dict[str, Any]]:
    """
    Get the thread group for a camera (thread-safe).

    Args:
        identifier: Camera identifier

    Returns:
        Thread group dictionary or None if not found
    """
    with active_camera_threads_lock:
        return active_camera_threads.get(identifier)


def get_all_active_identifiers() -> list[str]:
    """
    Get list of all active camera identifiers.

    Returns:
        List of camera identifiers that have active threads
    """
    with active_camera_threads_lock:
        return list(active_camera_threads.keys())


@contextmanager
def safe_thread_access(identifier: str, mark_stopping: bool = False) -> Iterator[Dict[str, Any]]:
    """
    Context manager for safe thread access with optional stopping flag.

    This ensures thread-safe access to thread groups and optionally marks
    them as stopping to prevent concurrent access during shutdown.

    Args:
        identifier: Camera identifier
        mark_stopping: If True, mark thread group as stopping

    Yields:
        Thread group dictionary

    Raises:
        ThreadNotAccessibleError: If thread doesn't exist or is already stopping
    """
    with active_camera_threads_lock:
        thread_group = active_camera_threads.get(identifier)

        if not thread_group:
            raise ThreadNotAccessibleError(
                f"No active thread for camera {identifier}"
            )

        if thread_group.get("stopping", False):
            raise ThreadNotAccessibleError(
                f"Camera {identifier} is already stopping"
            )

        if mark_stopping:
            thread_group["stopping"] = True
            logger.debug(f"Marked thread group {identifier} as stopping")

        try:
            yield thread_group
        finally:
            # Cleanup happens outside the context manager
            pass


def register_thread_group(
    identifier: str,
    acq_thread: Any,
    processing_threads: Dict[int, Any]
) -> None:
    """
    Register a new thread group.

    Args:
        identifier: Camera identifier
        acq_thread: Acquisition thread instance
        processing_threads: Dictionary of pipeline_id -> processing thread
    """
    with active_camera_threads_lock:
        active_camera_threads[identifier] = {
            "acquisition": acq_thread,
            "processing_threads": processing_threads,
            "stopping": False,
        }
        logger.debug(
            f"Registered thread group for {identifier} "
            f"with {len(processing_threads)} processing threads"
        )


def unregister_thread_group(identifier: str) -> None:
    """
    Remove a thread group from active threads.

    Args:
        identifier: Camera identifier
    """
    with active_camera_threads_lock:
        if identifier in active_camera_threads:
            del active_camera_threads[identifier]
            logger.debug(f"Unregistered thread group for {identifier}")


def get_processing_thread(identifier: str, pipeline_id: int) -> Optional[Any]:
    """
    Get a specific processing thread.

    Args:
        identifier: Camera identifier
        pipeline_id: Pipeline ID

    Returns:
        Processing thread instance or None if not found
    """
    with active_camera_threads_lock:
        thread_group = active_camera_threads.get(identifier)
        if not thread_group:
            return None
        return thread_group.get("processing_threads", {}).get(pipeline_id)


def add_processing_thread(
    identifier: str,
    pipeline_id: int,
    thread: Any
) -> bool:
    """
    Add a processing thread to an existing thread group.

    Args:
        identifier: Camera identifier
        pipeline_id: Pipeline ID
        thread: Processing thread instance

    Returns:
        True if successful, False if thread group doesn't exist
    """
    with active_camera_threads_lock:
        thread_group = active_camera_threads.get(identifier)
        if not thread_group:
            logger.warning(
                f"Cannot add processing thread: no thread group for {identifier}"
            )
            return False

        thread_group["processing_threads"][pipeline_id] = thread
        logger.debug(f"Added processing thread {pipeline_id} to {identifier}")
        return True


def remove_processing_thread(identifier: str, pipeline_id: int) -> bool:
    """
    Remove a processing thread from a thread group.

    Args:
        identifier: Camera identifier
        pipeline_id: Pipeline ID

    Returns:
        True if successful, False if not found
    """
    with active_camera_threads_lock:
        thread_group = active_camera_threads.get(identifier)
        if not thread_group:
            return False

        processing = thread_group.get("processing_threads", {})
        if pipeline_id in processing:
            del processing[pipeline_id]
            logger.debug(f"Removed processing thread {pipeline_id} from {identifier}")
            return True

        return False
