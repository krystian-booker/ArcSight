"""Frame encoding utilities for video streaming."""

import logging
from typing import Optional

import cv2
import numpy as np

logger = logging.getLogger(__name__)


def encode_frame_to_jpeg(
    frame: np.ndarray, quality: int = 85
) -> Optional[bytes]:
    """
    Encode a frame to JPEG format.

    Args:
        frame: The frame to encode (numpy array in BGR format)
        quality: JPEG quality (0-100, default 85)

    Returns:
        JPEG-encoded bytes, or None if encoding fails
    """
    if frame is None or frame.size == 0:
        logger.warning("Attempted to encode empty or None frame")
        return None

    try:
        ret, buffer = cv2.imencode(
            ".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, quality]
        )
        if not ret:
            logger.error("cv2.imencode returned False")
            return None
        return buffer.tobytes()
    except Exception as e:
        logger.exception(f"Error encoding frame to JPEG: {e}")
        return None
