import pytest
import numpy as np
import math
from unittest.mock import MagicMock, patch
from app.pipelines.apriltag_pipeline import AprilTagPipeline


@pytest.fixture
def mock_libs():
    """
    This fixture provides mocks for the C++ backed libraries (robotpy_apriltag, wpimath)
    for a single test function's scope. It uses `patch` to replace the libraries
    where they are imported in the pipeline module.

    The target for patch should be where the object is looked up. In this case,
    'robotpy_apriltag' and 'Transform3d' are both looked up in the
    'app.pipelines.apriltag_pipeline' module's namespace.
    """
    with (
        patch("app.pipelines.apriltag_pipeline.robotpy_apriltag") as mock_rpa,
        patch(
            "app.pipelines.apriltag_pipeline.Transform3d", new_callable=MagicMock
        ) as mock_transform3d,
    ):
        yield mock_rpa, mock_transform3d


@pytest.fixture
def default_config():
    """Provides a default configuration dictionary for the pipeline."""
    return {"family": "tag36h11", "tag_size_m": 0.15, "error_correction": 2}


@pytest.fixture
def default_cam_matrix():
    """Provides a default 3x3 camera intrinsic matrix."""
    return np.array([[1000, 0, 640], [0, 1000, 360], [0, 0, 1]], dtype=np.float32)


def create_mock_detection(tag_id, hamming=0, margin=50.0):
    """Helper function to create a mock AprilTagDetection object."""
    mock_detection = MagicMock()
    mock_detection.getId.return_value = tag_id
    mock_detection.getHamming.return_value = hamming
    mock_detection.getDecisionMargin.return_value = margin

    corners = []
    for i in range(4):
        corner = MagicMock()
        corner.x, corner.y = (100 + i * 10, 200 + i * 10)
        corners.append(corner)

    mock_detection.getCorner.side_effect = lambda index: corners[index]
    return mock_detection


def create_mock_pose_estimate():
    """Helper function to create a mock AprilTagPoseEstimate object with nested mocks."""
    mock_rotation = MagicMock()
    mock_rotation.toMatrix.return_value = np.eye(3)
    # FRC standard: rotation.X()=Roll, rotation.Y()=Pitch, rotation.Z()=Yaw
    mock_rotation.X.return_value = 0.1  # roll_rad = 0.1
    mock_rotation.Y.return_value = 0.2  # pitch_rad = 0.2
    mock_rotation.Z.return_value = 0.3  # yaw_rad = 0.3

    mock_transform = MagicMock()
    mock_transform.rotation.return_value = mock_rotation
    # FRC standard: X=forward, Y=left, Z=up
    mock_transform.X.return_value = 2.0  # x_ui = 2.0
    mock_transform.Y.return_value = 0.5  # y_ui = 0.5
    mock_transform.Z.return_value = 0.8  # z_ui = 0.8

    mock_estimate = MagicMock()
    mock_estimate.pose1 = mock_transform
    mock_estimate.error1 = 0.01

    return mock_estimate


def test_initialization(mock_libs, default_config):
    """Test that the pipeline initializes correctly with a standard config."""
    mock_rpa, _ = mock_libs
    mock_detector_instance = MagicMock()
    mock_rpa.AprilTagDetector.return_value = mock_detector_instance

    pipeline = AprilTagPipeline(default_config)

    mock_rpa.AprilTagDetector.assert_called_once()
    mock_detector_instance.addFamily.assert_called_once_with("tag36h11", 2)

    mock_rpa.AprilTagPoseEstimator.Config.assert_called_once_with(0.15, 0, 0, 0, 0)
    mock_rpa.AprilTagPoseEstimator.assert_not_called()
    assert pipeline.pose_estimator is None


def test_initialization_family_hack(mock_libs):
    """Test the family name 'hack' for adding the 'tag' prefix if it's missing."""
    mock_rpa, _ = mock_libs
    mock_detector_instance = MagicMock()
    mock_rpa.AprilTagDetector.return_value = mock_detector_instance
    config = {"family": "16h5"}

    AprilTagPipeline(config)

    mock_detector_instance.addFamily.assert_called_once_with("tag16h5", 2)


def test_process_frame_no_tags(mock_libs, default_config, default_cam_matrix):
    """Test processing a frame where no tags are detected."""
    mock_rpa, _ = mock_libs
    mock_detector_instance = MagicMock()
    mock_detector_instance.detect.return_value = []
    mock_rpa.AprilTagDetector.return_value = mock_detector_instance

    pipeline = AprilTagPipeline(default_config)
    frame = np.zeros((720, 1280, 3), dtype=np.uint8)
    result = pipeline.process_frame(frame, default_cam_matrix)

    # New format: {"single_tags": [...], "multi_tag": ...}
    assert result["single_tags"] == []
    assert result["multi_tag"] is None
    mock_detector_instance.detect.assert_called_once()


def test_process_frame_with_tags(mock_libs, default_config, default_cam_matrix):
    """Test processing a frame with a valid AprilTag detection."""
    mock_rpa, _ = mock_libs

    mock_detection = create_mock_detection(tag_id=1)
    mock_pose = create_mock_pose_estimate()

    mock_detector_instance = MagicMock()
    mock_detector_instance.detect.return_value = [mock_detection]
    mock_rpa.AprilTagDetector.return_value = mock_detector_instance

    mock_estimator_instance = MagicMock()
    mock_estimator_instance.estimateOrthogonalIteration.return_value = mock_pose
    mock_rpa.AprilTagPoseEstimator.return_value = mock_estimator_instance

    pipeline = AprilTagPipeline(default_config)
    frame = np.zeros((720, 1280, 3), dtype=np.uint8)
    result = pipeline.process_frame(frame, default_cam_matrix)

    # New format: {"single_tags": [...], "multi_tag": ...}
    single_tags = result["single_tags"]
    assert len(single_tags) == 1
    assert result["multi_tag"] is None  # No multi-tag by default

    mock_rpa.AprilTagPoseEstimator.assert_called_once()
    mock_estimator_instance.estimateOrthogonalIteration.assert_called_once_with(
        mock_detection, 40
    )

    ui_data = single_tags[0]["ui_data"]
    assert ui_data["id"] == 1
    assert ui_data["pose_error"] == 0.01
    assert pytest.approx(ui_data["x_m"]) == 2.0
    assert pytest.approx(ui_data["y_m"]) == 0.5
    assert pytest.approx(ui_data["z_m"]) == 0.8
    assert pytest.approx(ui_data["roll_deg"]) == math.degrees(0.1)
    assert pytest.approx(ui_data["pitch_deg"]) == math.degrees(0.2)
    assert pytest.approx(ui_data["yaw_deg"]) == math.degrees(0.3)

    drawing_data = single_tags[0]["drawing_data"]
    assert "rvec" in drawing_data
    assert "tvec" in drawing_data
    assert drawing_data["corners"].shape == (4, 2)
    assert drawing_data["id"] == 1


def test_tag_filtering(mock_libs, default_config, default_cam_matrix):
    """Test that tags are filtered based on hamming distance and decision margin."""
    mock_rpa, _ = mock_libs
    good_tag = create_mock_detection(tag_id=1)
    bad_hamming_tag = create_mock_detection(tag_id=2, hamming=2)
    bad_margin_tag = create_mock_detection(tag_id=3, margin=20.0)

    mock_detector_instance = MagicMock()
    mock_detector_instance.detect.return_value = [
        good_tag,
        bad_hamming_tag,
        bad_margin_tag,
    ]
    mock_rpa.AprilTagDetector.return_value = mock_detector_instance

    mock_estimator_instance = MagicMock()
    mock_estimator_instance.estimateOrthogonalIteration.return_value = (
        create_mock_pose_estimate()
    )
    mock_rpa.AprilTagPoseEstimator.return_value = mock_estimator_instance

    pipeline = AprilTagPipeline(default_config)
    frame = np.zeros((720, 1280, 3), dtype=np.uint8)
    result = pipeline.process_frame(frame, default_cam_matrix)

    # New format: {"single_tags": [...], "multi_tag": ...}
    single_tags = result["single_tags"]
    assert len(single_tags) == 1
    assert single_tags[0]["ui_data"]["id"] == 1
    mock_estimator_instance.estimateOrthogonalIteration.assert_called_once()


def test_pose_estimator_recreation(mock_libs, default_config, default_cam_matrix):
    """Test that the pose estimator is only recreated when camera intrinsics change."""
    mock_rpa, _ = mock_libs
    pipeline = AprilTagPipeline(default_config)
    frame = np.zeros((720, 1280, 3), dtype=np.uint8)

    pipeline.process_frame(frame, default_cam_matrix)
    mock_rpa.AprilTagPoseEstimator.assert_called_once()

    pipeline.process_frame(frame, default_cam_matrix)
    mock_rpa.AprilTagPoseEstimator.assert_called_once()

    new_cam_matrix = default_cam_matrix.copy()
    new_cam_matrix[0, 0] = 1200
    pipeline.process_frame(frame, new_cam_matrix)
    assert mock_rpa.AprilTagPoseEstimator.call_count == 2


@patch("app.pipelines.apriltag_pipeline.cv2.cvtColor")
def test_grayscale_conversion(
    mock_cvt_color, mock_libs, default_config, default_cam_matrix
):
    """Test that frames are correctly converted to grayscale only when necessary."""
    mock_rpa, _ = mock_libs
    pipeline = AprilTagPipeline(default_config)

    bgr_frame = np.zeros((100, 200, 3), dtype=np.uint8)
    pipeline.process_frame(bgr_frame, default_cam_matrix)
    mock_cvt_color.assert_called_once()

    mock_cvt_color.reset_mock()
    gray_frame = np.zeros((100, 200), dtype=np.uint8)
    pipeline.process_frame(gray_frame, default_cam_matrix)
    mock_cvt_color.assert_not_called()
