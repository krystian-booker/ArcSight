"""Application configuration constants and utilities."""

from appdirs import user_data_dir


# Application metadata
APP_NAME = "VisionTools"
APP_AUTHOR = "User"

# Paths
DATA_DIR = user_data_dir(APP_NAME, APP_AUTHOR)


# Thread configuration
class ThreadConfig:
    """Configuration constants for camera and processing threads."""

    # Queue settings
    PIPELINE_QUEUE_SIZE = 2

    # JPEG quality settings
    DISPLAY_JPEG_QUALITY = 85  # Higher quality for display feeds
    PIPELINE_JPEG_QUALITY = 75  # Lower quality to save CPU for pipelines

    # Timeout settings
    THREAD_STOP_TIMEOUT = 5.0  # Seconds to wait for thread shutdown
    FRAME_PROCESS_TIMEOUT = 0.1  # Seconds to wait for frame from queue

    # Warning throttle
    WARNING_THROTTLE_INTERVAL = 5.0  # Seconds between repeated warnings


# Camera driver configuration
class DriverConfig:
    """Configuration constants for camera drivers."""

    # RealSense
    REALSENSE_FRAME_TIMEOUT_MS = 5000
    REALSENSE_DEFAULT_DEPTH_RESOLUTION = (1280, 720)

    # GenICam
    GENICAM_ENUMERATE_TIMEOUT = 5.0

    # General
    DEFAULT_FRAMERATE = 30
    DEFAULT_EXPOSURE_MODE = "auto"
    DEFAULT_GAIN_MODE = "auto"


# Pipeline configuration
class PipelineConfig:
    """Configuration constants for vision pipelines."""

    # AprilTag
    DEFAULT_TAG_SIZE = 0.16  # meters
    DEFAULT_TAG_FAMILY = "tag36h11"

    # Object Detection
    MAX_MODEL_FILE_SIZE = 100 * 1024 * 1024  # 100 MB
