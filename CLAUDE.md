# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

ArcSight (formerly vision-tools) is a Flask-based web application for industrial computer vision. It provides real-time video streaming, camera management, and configurable vision pipelines for AprilTag detection, colored shape detection, and ML-based object detection. Supports multiple camera types: USB, GenICam, and OAK-D.

## Development Commands

### Environment Setup
```bash
# Create and activate conda environment
conda env create -f environment.yml
conda activate ArcSight
```

### Running the Application
```bash
# Development server (with debug mode)
python run.py

# Or set environment variables for development
# FLASK_ENV=development python run.py
# FLASK_DEBUG=1 python run.py
```

The web server runs on `http://0.0.0.0:8080` by default.

### Testing
```bash
# Run all tests with coverage
pytest

# Run verbose output
pytest -v

# Run without coverage (faster)
pytest --no-cov

# Run specific test file
pytest tests/test_camera_manager.py

# Run specific test function
pytest tests/test_camera_manager.py::test_function_name
```

### Code Quality
```bash
# Format code
ruff format app tests

# Check code quality
ruff check app tests
```

## Architecture

### Threading Model
The application uses a producer-consumer threading model with separate threads per camera:

1. **CameraAcquisitionThread** (Producer): Captures frames from camera drivers and distributes them to multiple pipeline queues. Handles automatic reconnection and frame buffer pooling.

2. **VisionProcessingThread** (Consumer): Processes frames from queues through vision pipelines. Each pipeline runs in its own thread.

Thread lifecycle is managed in `app/camera_manager.py` through functions like `start_camera_thread()`, `stop_camera_thread()`, `add_pipeline_to_camera()`, etc.

### Frame Buffer Management
- **FrameBufferPool**: Pre-allocates numpy arrays to avoid repeated memory allocation. Supports optional depth buffers for depth-capable cameras (e.g., Intel RealSense).
- **RefCountedFrame**: Thread-safe wrapper with reference counting for safe sharing across multiple pipelines. Can hold both color and depth frames simultaneously.
- **Lazy JPEG Encoding**: Frames are encoded only when clients request them, saving CPU when no clients are connected
- **Water-mark Shrinking**: Pool automatically shrinks during idle periods to prevent memory bloat

### Camera Driver System
All drivers inherit from `BaseDriver` (app/drivers/base_driver.py) and must implement:
- `connect()`: Establish camera connection
- `disconnect()`: Close camera connection
- `get_frame()`: Retrieve frame(s) - returns numpy array for standard cameras, or (color_frame, depth_frame) tuple for depth-capable cameras
- `list_devices()`: Static method to discover available devices
- `supports_depth()`: Optional method to indicate depth capability (default: False)

Implemented drivers:
- **USBDriver** (app/drivers/usb_driver.py): OpenCV-based driver for USB cameras
- **GenICamDriver** (app/drivers/genicam_driver.py): Harvesters-based driver for industrial cameras
- **OAKDDriver** (app/drivers/oakd_driver.py): DepthAI-based driver for OAK-D cameras
- **RealSenseDriver** (app/drivers/realsense_driver.py): pyrealsense2-based driver for Intel RealSense depth cameras (D435, D435i, D455, etc.). Supports both color and depth streams with configurable resolution/framerate.

Driver selection happens in `app/camera_discovery.py` via `get_driver()`.

### Vision Pipelines
All pipelines follow a common interface with a `process_frame()` method:

- **AprilTagPipeline** (app/pipelines/apriltag_pipeline.py): Detects AprilTags, computes pose estimation, supports multi-tag localization
- **ColouredShapePipeline** (app/pipelines/coloured_shape_pipeline.py): HSV-based color filtering and contour detection
- **ObjectDetectionMLPipeline** (app/pipelines/object_detection_ml_pipeline.py): ONNX-based ML inference

**Depth-Aware Pipelines**: Pipelines can optionally accept a `ref_frame` parameter to access depth data from depth-capable cameras:
```python
def process_frame(self, frame: np.ndarray, cam_matrix, ref_frame=None):
    # Standard color processing
    detections = self.detect_objects(frame)

    # Optionally use depth data if available
    if ref_frame and ref_frame.has_depth():
        depth_frame = ref_frame.depth_data
        for detection in detections:
            # Calculate distance to detected object
            x, y = detection['center']
            distance_mm = depth_frame[y, x]
            detection['distance_mm'] = distance_mm

    return detections
```

The VisionProcessingThread uses signature inspection to automatically detect depth-aware pipelines and pass the `ref_frame` parameter. Legacy pipelines without this parameter continue to work unchanged.

Pipeline configuration is stored as JSON in the database and validated by `app/pipeline_validators.py`.

### Database Models
SQLAlchemy models in `app/models.py`:

- **Camera**: Stores camera configuration including:
  - Basic: type, identifier, name, orientation
  - Image settings: exposure_value, gain_value, exposure_mode, gain_mode
  - Calibration: camera_matrix_json, dist_coeffs_json, reprojection_error
  - RealSense/advanced: resolution_json, framerate, depth_enabled
  - Metadata: device_info_json
- **Pipeline**: Associated with a camera via foreign key, stores pipeline type and JSON config
- **Setting**: Key-value store for application-wide settings (e.g., GenICam CTI path)

Database is SQLite by default, stored in user data directory (managed by `appdirs`).

### Flask Blueprint Structure
Application is modularized using Flask blueprints:

- **dashboard** (app/blueprints/dashboard): Main UI with live camera feeds
- **cameras** (app/blueprints/cameras): Camera configuration and discovery APIs
- **pipelines** (app/blueprints/pipelines): Pipeline CRUD operations
- **calibration** (app/blueprints/calibration): Camera calibration workflows
- **settings** (app/blueprints/settings): Application settings management
- **monitoring** (app/blueprints/monitoring): Metrics and health monitoring UI

### Metrics System
The metrics system (app/metrics/) collects real-time performance data:

- **Pipeline Metrics**: Latency (average, p95, max), FPS, queue depth, dropped frames
- **System Metrics**: CPU usage, RAM usage, temperature (platform-specific)
- **Configuration**: Thresholds and sampling rates controlled via environment variables

Metrics are exposed at `/api/metrics/summary` and displayed on `/monitoring`.

### AprilTag Field Layouts
Field layouts for FRC games are stored as JSON in `data/` directory. Custom fields can be uploaded via the web UI and are stored in the user data directory. Field management is in `app/apriltag_fields.py`.

## Key Implementation Details

### Thread Safety
- Camera threads are managed with locks (`active_camera_threads_lock`)
- Stopping state prevents concurrent access during shutdown
- Database queries are performed in Flask app context before passing primitive values to threads (avoids ORM session issues)

### Configuration Updates
Camera threads use event-based signaling for configuration updates:
- `notify_camera_config_update()` sets `config_update_event` to signal orientation changes
- Acquisition thread checks event non-blocking every frame
- Pipelines must be stopped and restarted to apply config changes

### Frame Drops and Warnings
When pipelines can't keep up:
- Old frames are dropped from queues (keeps newest frames)
- Throttled warnings logged every 5 seconds with queue utilization stats
- Metrics track drop counts and rates per pipeline

### Calibration Workflow
Camera calibration uses OpenCV's checkerboard pattern:
1. Capture multiple frames via web UI (stored in `CalibrationManager`)
2. Server processes images to find checkerboard corners
3. Computes camera matrix and distortion coefficients
4. Stores results in database (camera.camera_matrix_json, camera.dist_coeffs_json)

## Testing Notes

- Tests use in-memory SQLite database (`SQLALCHEMY_DATABASE_URI = 'sqlite:///:memory:'`)
- Camera threads are disabled in tests (`CAMERA_THREADS_ENABLED = False`)
- Metrics are disabled in tests (`METRICS_ENABLED = False`)
- Test configuration is in `config.py` (`TestingConfig` class)
- Use `pytest-mock` for mocking camera drivers and external dependencies

## Configuration Priority

Application configuration follows this priority order:
1. Environment variables (highest priority)
2. `.env` file (copy from `.env.example`)
3. `config.py` defaults (lowest priority)

Flask config loaded via `get_config()` in config.py:
- Checks `FLASK_ENV` first (development/production/testing)
- Falls back to `FLASK_DEBUG` (0/1)
- Defaults to production (safe default)

## Common Gotchas

- **Camera thread stopping**: Must handle both ORM detachment and TOCTOU race conditions. Always copy thread references under lock before joining.
- **Orientation changes**: Require buffer pool re-initialization if frame dimensions change
- **Pipeline config**: Always merge with defaults before instantiation (see `VisionProcessingThread.__init__`)
- **AprilTag auto-threading**: `recommended_apriltag_threads()` scales detector threads based on CPU cores
- **JPEG quality**: Display frames use quality=85, pipeline frames use quality=75 to save CPU
- **Depth frame handling**: Drivers that support depth return (color, depth) tuples from get_frame(). Non-depth drivers return single frames. CameraAcquisitionThread handles both cases automatically.

## Intel RealSense Camera Support

### Overview
The RealSense driver provides support for Intel RealSense depth cameras (D435, D435i, D455, etc.) with both color and optional depth streams.

### Installation
```bash
pip install pyrealsense2
```

### Driver Configuration
RealSense cameras support the following configuration options (stored in Camera model):
- **resolution_json**: JSON string with width/height (e.g., `{"width": 1920, "height": 1080}`)
- **framerate**: FPS setting (e.g., 30, 60)
- **depth_enabled**: Boolean to enable/disable depth stream
- **exposure_mode** / **exposure_value**: Auto or manual exposure control
- **gain_mode** / **gain_value**: Auto or manual gain control

### Implementation Details
- **Depth Alignment**: Depth frames are automatically aligned to the color frame coordinate system
- **Frame Return**: Returns `(color_bgr, depth_uint16)` tuple where depth values are in millimeters
- **Depth Resolution**: Uses 1280x720 for depth stream (optimized for performance) regardless of color resolution
- **Identifier**: Uses camera serial number as stable identifier
- **Device Name**: Formatted as "Model (serial)" for easy identification (e.g., "D435i (f123456)")

### Memory Management
When depth is enabled:
- **Dual Buffer Pools**: Separate pools for color and depth frames
- **Memory Usage**: For 640x480 - RGB=900KB, Depth=600KB per buffer. With 10 buffers ≈15MB total
- **Reference Counting**: Both color and depth buffers share the same RefCountedFrame lifecycle
- **Automatic Cleanup**: Buffers released together when reference count reaches zero

### Creating Depth-Aware Pipelines
Pipelines can access depth data by adding an optional `ref_frame` parameter:

```python
class MyDepthAwarePipeline:
    def process_frame(self, frame: np.ndarray, cam_matrix, ref_frame=None):
        # Process color frame normally
        detections = self.detect_objects(frame)

        # Add depth information to detections if available
        if ref_frame and ref_frame.has_depth():
            depth = ref_frame.depth_data  # uint16 numpy array in mm
            for det in detections:
                x, y = int(det['center_x']), int(det['center_y'])
                if 0 <= y < depth.shape[0] and 0 <= x < depth.shape[1]:
                    det['distance_mm'] = int(depth[y, x])

        return detections
```

The signature inspection in `VisionProcessingThread._call_pipeline_process_frame()` automatically detects the `ref_frame` parameter and passes the RefCountedFrame object. Existing pipelines without this parameter continue to work unchanged.

### Testing RealSense Driver
Comprehensive tests are in `tests/test_realsense_driver.py`:
- Mock pyrealsense2 library for all tests (library may not be installed in test environment)
- Test both depth-enabled and depth-disabled modes
- Test exposure/gain configuration
- Test graceful failure when library not available
- Verify proper cleanup on disconnect
