"""
Video encoding utilities for WebSocket streaming.

Provides H.264 encoding support using OpenCV's VideoWriter for efficient
video streaming to React frontend via WebSocket with MSE support.
"""

import cv2
import numpy as np
import logging
from typing import Optional, Tuple
import time
from enum import Enum

logger = logging.getLogger(__name__)


class EncodingFormat(Enum):
    """Supported video encoding formats"""
    JPEG = "jpeg"
    H264 = "h264"
    H265 = "h265"


class VideoEncoder:
    """
    Video encoder for real-time streaming.

    Supports both JPEG (for MJPEG fallback) and H.264/H.265 encoding.
    For Raspberry Pi, H.264 with hardware acceleration is recommended.
    """

    def __init__(
        self,
        format: EncodingFormat = EncodingFormat.JPEG,
        quality: int = 85,
        target_fps: Optional[int] = None,
        bitrate: Optional[int] = None,
    ):
        """
        Initialize video encoder.

        Args:
            format: Encoding format (JPEG, H264, H265)
            quality: JPEG quality (1-100) when using JPEG format
            target_fps: Target FPS for frame rate limiting
            bitrate: Target bitrate in kbps for H.264/H.265
        """
        self.format = format
        self.quality = quality
        self.target_fps = target_fps
        self.bitrate = bitrate or 2000  # Default 2 Mbps

        # Frame rate limiting
        self.last_encode_time = 0
        self.min_frame_interval = 1.0 / target_fps if target_fps else 0

        # Statistics
        self.frames_encoded = 0
        self.frames_dropped = 0
        self.total_encode_time = 0

    def should_encode_frame(self) -> bool:
        """
        Check if enough time has passed to encode the next frame.

        Returns:
            True if frame should be encoded, False if should be dropped
        """
        if not self.target_fps:
            return True

        current_time = time.time()
        elapsed = current_time - self.last_encode_time

        if elapsed >= self.min_frame_interval:
            self.last_encode_time = current_time
            return True

        self.frames_dropped += 1
        return False

    def encode_frame(self, frame: np.ndarray) -> Optional[bytes]:
        """
        Encode a single frame.

        Args:
            frame: Input frame as numpy array (BGR format)

        Returns:
            Encoded frame bytes or None if frame was dropped
        """
        if not self.should_encode_frame():
            return None

        start_time = time.time()

        try:
            if self.format == EncodingFormat.JPEG:
                encoded = self._encode_jpeg(frame)
            elif self.format == EncodingFormat.H264:
                encoded = self._encode_h264(frame)
            elif self.format == EncodingFormat.H265:
                encoded = self._encode_h265(frame)
            else:
                logger.error(f"Unsupported encoding format: {self.format}")
                return None

            encode_time = time.time() - start_time
            self.total_encode_time += encode_time
            self.frames_encoded += 1

            if encode_time > 0.033:  # Warn if encoding takes > 33ms (30 FPS)
                logger.warning(
                    f"Slow encoding: {encode_time*1000:.1f}ms for {self.format.value}"
                )

            return encoded

        except Exception as e:
            logger.error(f"Error encoding frame: {e}")
            return None

    def _encode_jpeg(self, frame: np.ndarray) -> bytes:
        """
        Encode frame to JPEG.

        Args:
            frame: Input frame

        Returns:
            JPEG encoded bytes
        """
        encode_param = [int(cv2.IMWRITE_JPEG_QUALITY), self.quality]
        _, encoded = cv2.imencode('.jpg', frame, encode_param)
        return encoded.tobytes()

    def _encode_h264(self, frame: np.ndarray) -> bytes:
        """
        Encode frame to H.264.

        Note: This is a placeholder. For production, use ffmpeg-python or
        hardware-accelerated encoders via platform-specific APIs.

        Args:
            frame: Input frame

        Returns:
            H.264 encoded bytes
        """
        # TODO: Implement H.264 encoding using ffmpeg-python
        # For now, fall back to JPEG
        logger.warning("H.264 encoding not fully implemented, using JPEG")
        return self._encode_jpeg(frame)

    def _encode_h265(self, frame: np.ndarray) -> bytes:
        """
        Encode frame to H.265.

        Note: This is a placeholder for future implementation.

        Args:
            frame: Input frame

        Returns:
            H.265 encoded bytes
        """
        # TODO: Implement H.265 encoding
        logger.warning("H.265 encoding not implemented, using JPEG")
        return self._encode_jpeg(frame)

    def get_statistics(self) -> dict:
        """
        Get encoding statistics.

        Returns:
            Dictionary with encoding statistics
        """
        avg_encode_time = (
            self.total_encode_time / self.frames_encoded
            if self.frames_encoded > 0
            else 0
        )

        return {
            'format': self.format.value,
            'frames_encoded': self.frames_encoded,
            'frames_dropped': self.frames_dropped,
            'drop_rate': (
                self.frames_dropped / (self.frames_encoded + self.frames_dropped)
                if (self.frames_encoded + self.frames_dropped) > 0
                else 0
            ),
            'avg_encode_time_ms': avg_encode_time * 1000,
            'target_fps': self.target_fps,
        }

    def reset_statistics(self):
        """Reset encoding statistics"""
        self.frames_encoded = 0
        self.frames_dropped = 0
        self.total_encode_time = 0


def create_encoder(
    format_name: str = "jpeg",
    quality: int = 85,
    target_fps: Optional[int] = 30,
    bitrate: Optional[int] = None,
) -> VideoEncoder:
    """
    Factory function to create a video encoder.

    Args:
        format_name: Encoding format name ("jpeg", "h264", "h265")
        quality: JPEG quality (1-100)
        target_fps: Target FPS for streaming
        bitrate: Target bitrate in kbps

    Returns:
        Configured VideoEncoder instance
    """
    format_map = {
        'jpeg': EncodingFormat.JPEG,
        'h264': EncodingFormat.H264,
        'h265': EncodingFormat.H265,
    }

    format_enum = format_map.get(format_name.lower(), EncodingFormat.JPEG)

    return VideoEncoder(
        format=format_enum,
        quality=quality,
        target_fps=target_fps,
        bitrate=bitrate,
    )
