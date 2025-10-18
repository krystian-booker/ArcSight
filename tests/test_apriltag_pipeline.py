import pytest
import numpy as np
import math
from unittest.mock import MagicMock, patch
from app.pipelines.apriltag_pipeline import AprilTagPipeline


@pytest.fixture
def mock_detector():
    """Provides a mock robotpy-apriltag detector (detection only, not pose)."""
    with patch("app.pipelines.apriltag_pipeline.robotpy_apriltag") as mock_rpa:
        yield mock_rpa


@pytest.fixture
def default_config():
    """Provides a default configuration dictionary for the pipeline."""
    return {"family": "tag36h11", "tag_size_m": 0.15, "error_correction": 2}


@pytest.fixture
def default_cam_matrix():
    """Provides a default 3x3 camera intrinsic matrix."""
    return np.array([[1000, 0, 640], [0, 1000, 360], [0, 0, 1]], dtype=np.float32)


@pytest.fixture
def default_dist_coeffs():
    """Provides default distortion coefficients (zero distortion)."""
    return np.zeros((4, 1), dtype=np.float32)


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


def test_initialization(mock_detector, default_config):
    """Test that the pipeline initializes correctly with a standard config."""
    mock_detector_instance = MagicMock()
    mock_detector.AprilTagDetector.return_value = mock_detector_instance

    pipeline = AprilTagPipeline(default_config)

    mock_detector.AprilTagDetector.assert_called_once()
    mock_detector_instance.addFamily.assert_called_once_with("tag36h11", 2)
    assert pipeline.tag_size_m == 0.15
    assert pipeline.single_tag_obj_points.shape == (4, 3)


def test_initialization_family_hack(mock_detector):
    """Test the family name 'hack' for adding the 'tag' prefix if it's missing."""
    mock_detector_instance = MagicMock()
    mock_detector.AprilTagDetector.return_value = mock_detector_instance
    config = {"family": "16h5"}

    AprilTagPipeline(config)

    mock_detector_instance.addFamily.assert_called_once_with("tag16h5", 2)


def test_process_frame_no_tags(mock_detector, default_config, default_cam_matrix, default_dist_coeffs):
    """Test processing a frame where no tags are detected."""
    mock_detector_instance = MagicMock()
    mock_detector_instance.detect.return_value = []
    mock_detector.AprilTagDetector.return_value = mock_detector_instance

    pipeline = AprilTagPipeline(default_config)
    frame = np.zeros((720, 1280, 3), dtype=np.uint8)
    result = pipeline.process_frame(frame, default_cam_matrix, default_dist_coeffs)

    assert result["single_tags"] == []
    assert result["multi_tag"] is None
    mock_detector_instance.detect.assert_called_once()


@patch("app.pipelines.apriltag_pipeline.cv2.solvePnP")
@patch("app.pipelines.apriltag_pipeline.cv2.projectPoints")
def test_process_frame_with_tags(
    mock_project, mock_solve, mock_detector, default_config, default_cam_matrix, default_dist_coeffs
):
    """Test processing a frame with a valid AprilTag detection using OpenCV solvePnP."""
    mock_detection = create_mock_detection(tag_id=1)

    mock_detector_instance = MagicMock()
    mock_detector_instance.detect.return_value = [mock_detection]
    mock_detector.AprilTagDetector.return_value = mock_detector_instance

    # Mock solvePnP to return success and some rvec/tvec in OpenCV coordinates
    # OpenCV: X=right, Y=down, Z=forward
    mock_rvec = np.array([[0.1], [0.2], [0.3]], dtype=np.float32)
    mock_tvec = np.array([[0.5], [0.3], [2.0]], dtype=np.float32)  # X=right, Y=down, Z=forward
    mock_solve.return_value = (True, mock_rvec, mock_tvec)

    # Mock projectPoints for reprojection error calculation
    mock_project.return_value = (
        np.array([[[100, 200]], [[110, 210]], [[120, 220]], [[130, 230]]], dtype=np.float32),
        None
    )

    pipeline = AprilTagPipeline(default_config)
    frame = np.zeros((720, 1280, 3), dtype=np.uint8)
    result = pipeline.process_frame(frame, default_cam_matrix, default_dist_coeffs)

    single_tags = result["single_tags"]
    assert len(single_tags) == 1
    assert result["multi_tag"] is None

    mock_solve.assert_called_once()
    args = mock_solve.call_args[0]
    assert args[2] is default_cam_matrix
    assert np.array_equal(args[3], default_dist_coeffs)

    ui_data = single_tags[0]["ui_data"]
    assert ui_data["id"] == 1
    # FRC transformation: FRC_X = OpenCV_Z, FRC_Y = -OpenCV_X, FRC_Z = -OpenCV_Y
    # OpenCV tvec: [0.5, 0.3, 2.0]
    # FRC tvec: [2.0, -0.5, -0.3]
    assert pytest.approx(ui_data["x_m"], abs=0.01) == 2.0
    assert pytest.approx(ui_data["y_m"], abs=0.01) == -0.5
    assert pytest.approx(ui_data["z_m"], abs=0.01) == -0.3

    drawing_data = single_tags[0]["drawing_data"]
    assert "rvec" in drawing_data
    assert "tvec" in drawing_data
    assert drawing_data["corners"].shape == (4, 2)
    assert drawing_data["id"] == 1


def test_tag_filtering(mock_detector, default_config, default_cam_matrix, default_dist_coeffs):
    """Test that tags are filtered based on hamming distance and decision margin."""
    good_tag = create_mock_detection(tag_id=1)
    bad_hamming_tag = create_mock_detection(tag_id=2, hamming=2)
    bad_margin_tag = create_mock_detection(tag_id=3, margin=20.0)

    mock_detector_instance = MagicMock()
    mock_detector_instance.detect.return_value = [
        good_tag,
        bad_hamming_tag,
        bad_margin_tag,
    ]
    mock_detector.AprilTagDetector.return_value = mock_detector_instance

    with patch("app.pipelines.apriltag_pipeline.cv2.solvePnP") as mock_solve:
        mock_solve.return_value = (True, np.zeros((3, 1)), np.ones((3, 1)))

        with patch("app.pipelines.apriltag_pipeline.cv2.projectPoints") as mock_project:
            mock_project.return_value = (np.zeros((4, 1, 2)), None)

            pipeline = AprilTagPipeline(default_config)
            frame = np.zeros((720, 1280, 3), dtype=np.uint8)
            result = pipeline.process_frame(frame, default_cam_matrix, default_dist_coeffs)

            single_tags = result["single_tags"]
            assert len(single_tags) == 1
            assert single_tags[0]["ui_data"]["id"] == 1
            mock_solve.assert_called_once()


@patch("app.pipelines.apriltag_pipeline.cv2.cvtColor")
def test_grayscale_conversion(
    mock_cvt_color, mock_detector, default_config, default_cam_matrix, default_dist_coeffs
):
    """Test that frames are correctly converted to grayscale only when necessary."""
    pipeline = AprilTagPipeline(default_config)

    bgr_frame = np.zeros((100, 200, 3), dtype=np.uint8)
    pipeline.process_frame(bgr_frame, default_cam_matrix, default_dist_coeffs)
    mock_cvt_color.assert_called_once()

    mock_cvt_color.reset_mock()
    gray_frame = np.zeros((100, 200), dtype=np.uint8)
    pipeline.process_frame(gray_frame, default_cam_matrix, default_dist_coeffs)
    mock_cvt_color.assert_not_called()


@patch("app.pipelines.apriltag_pipeline.cv2.solvePnP")
@patch("app.pipelines.apriltag_pipeline.cv2.projectPoints")
def test_multi_tag_sqpnp(
    mock_project, mock_solve, mock_detector, default_cam_matrix, default_dist_coeffs
):
    """Test multi-tag pose estimation using SQPNP with field layout."""
    # Create config with multi-tag enabled and field layout
    field_layout_json = """
    {
        "field": {"length": 16.54, "width": 8.21},
        "tags": [
            {
                "ID": 1,
                "pose": {
                    "translation": {"x": 1.0, "y": 0.0, "z": 0.5},
                    "rotation": {
                        "quaternion": {"W": 1.0, "X": 0.0, "Y": 0.0, "Z": 0.0}
                    }
                }
            },
            {
                "ID": 2,
                "pose": {
                    "translation": {"x": 2.0, "y": 0.0, "z": 0.5},
                    "rotation": {
                        "quaternion": {"W": 1.0, "X": 0.0, "Y": 0.0, "Z": 0.0}
                    }
                }
            }
        ]
    }
    """
    config = {
        "family": "tag36h11",
        "tag_size_m": 0.15,
        "multi_tag_enabled": True,
        "field_layout": field_layout_json
    }

    mock_detection1 = create_mock_detection(tag_id=1)
    mock_detection2 = create_mock_detection(tag_id=2)

    mock_detector_instance = MagicMock()
    mock_detector_instance.detect.return_value = [mock_detection1, mock_detection2]
    mock_detector.AprilTagDetector.return_value = mock_detector_instance

    # Mock solvePnP to return success for both single tags and multi-tag
    def solvepnp_side_effect(obj_pts, img_pts, cam_mat, dist, flags=0):
        # Return appropriate success based on number of points
        return (True, np.zeros((3, 1)), np.ones((3, 1)))

    mock_solve.side_effect = solvepnp_side_effect

    # Mock projectPoints to return the same number of points as input
    def projectpoints_side_effect(obj_pts, rvec, tvec, cam_mat, dist):
        num_points = obj_pts.shape[0]
        return (np.zeros((num_points, 1, 2)), None)

    mock_project.side_effect = projectpoints_side_effect

    pipeline = AprilTagPipeline(config)
    frame = np.zeros((720, 1280, 3), dtype=np.uint8)
    result = pipeline.process_frame(frame, default_cam_matrix, default_dist_coeffs)

    # Should have 2 single tag results
    assert len(result["single_tags"]) == 2

    # Should have multi-tag result
    assert result["multi_tag"] is not None
    assert result["multi_tag"]["num_tags"] == 2

    # Verify SQPNP was called (last call should be SQPNP for multi-tag)
    assert mock_solve.call_count >= 3  # 2 single tags + 1 multi-tag
    last_call_kwargs = mock_solve.call_args[1]
    assert last_call_kwargs["flags"] == 8  # cv2.SOLVEPNP_SQPNP = 8


@patch("app.pipelines.apriltag_pipeline.cv2.solvePnP")
def test_single_tag_uses_ippe(mock_solve, mock_detector, default_config, default_cam_matrix, default_dist_coeffs):
    """Test that single tags use SOLVEPNP_IPPE method."""
    mock_detection = create_mock_detection(tag_id=1)
    mock_detector_instance = MagicMock()
    mock_detector_instance.detect.return_value = [mock_detection]
    mock_detector.AprilTagDetector.return_value = mock_detector_instance

    mock_solve.return_value = (True, np.zeros((3, 1)), np.ones((3, 1)))

    with patch("app.pipelines.apriltag_pipeline.cv2.projectPoints") as mock_project:
        mock_project.return_value = (np.zeros((4, 1, 2)), None)

        pipeline = AprilTagPipeline(default_config)
        frame = np.zeros((720, 1280, 3), dtype=np.uint8)
        pipeline.process_frame(frame, default_cam_matrix, default_dist_coeffs)

        # Verify IPPE flag was used
        call_kwargs = mock_solve.call_args[1]
        assert call_kwargs["flags"] == 6  # cv2.SOLVEPNP_IPPE = 6
