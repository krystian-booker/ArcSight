import cv2
import numpy as np
import pytest
from unittest.mock import patch

pytest.importorskip("robotpy_apriltag")
pytest.importorskip("wpimath.geometry")

from wpimath.geometry import Quaternion, Rotation3d, Transform3d, Translation3d

from app.pipelines.apriltag_pipeline import (
    AprilTagPipeline,
    _matrix_to_quaternion,
    _rotation3d_to_matrix,
    _scale_tag_corners,
    _transform_to_rvec_tvec,
)


def _close_matrix(a: np.ndarray, b: np.ndarray, atol: float = 1e-6) -> bool:
    return np.allclose(a, b, atol=atol)


def test_rotation_conversion_roundtrip():
    quaternion = Quaternion(0.9238795325, 0.0, 0.3826834324, 0.0)
    rotation = Rotation3d(quaternion)
    matrix = _rotation3d_to_matrix(rotation)
    recovered_quaternion = _matrix_to_quaternion(matrix)
    assert pytest.approx(recovered_quaternion.W(), rel=1e-6) == quaternion.W()
    assert pytest.approx(recovered_quaternion.X(), rel=1e-6) == quaternion.X()
    assert pytest.approx(recovered_quaternion.Y(), rel=1e-6) == quaternion.Y()
    assert pytest.approx(recovered_quaternion.Z(), rel=1e-6) == quaternion.Z()


def test_transform_to_rvec_tvec_matches_cv2():
    rotation = Rotation3d(Quaternion(0.965925826, 0.129409523, 0.224143868, 0.0))
    translation = Translation3d(0.5, -0.25, 1.2)
    transform = Transform3d(translation, rotation)

    rvec, tvec = _transform_to_rvec_tvec(transform)
    matrix_cv, _ = cv2.Rodrigues(rvec)
    matrix_wpimath = _rotation3d_to_matrix(rotation)

    assert _close_matrix(matrix_cv, matrix_wpimath)
    assert np.allclose(
        tvec.reshape(-1), [translation.X(), translation.Y(), translation.Z()], atol=1e-6
    )


def test_scale_tag_corners_ordering():
    corners = _scale_tag_corners(2.0)
    expected = np.array(
        [
            [-1.0, -1.0, 0.0],
            [1.0, -1.0, 0.0],
            [1.0, 1.0, 0.0],
            [-1.0, 1.0, 0.0],
        ],
        dtype=np.float32,
    )
    assert np.array_equal(corners, expected)


class DummyCorner:
    def __init__(self, x: float, y: float) -> None:
        self.x = x
        self.y = y


class DummyDetection:
    def __init__(self, tag_id: int, corners):
        self._tag_id = tag_id
        self._corners = corners

    def getId(self):
        return self._tag_id

    def getCorner(self, idx: int):
        return self._corners[idx]

    def getHamming(self):
        return 0

    def getDecisionMargin(self):
        return 100.0


def test_field_layout_corner_projection():
    layout = {
        "tags": [
            {
                "ID": 1,
                "pose": {
                    "translation": {"x": 0.0, "y": 0.0, "z": 0.0},
                    "rotation": {
                        "quaternion": {"W": 1.0, "X": 0.0, "Y": 0.0, "Z": 0.0}
                    },
                },
            }
        ]
    }
    with (
        patch(
            "app.pipelines.apriltag_pipeline.get_selected_field_name",
            return_value="test.json",
        ),
        patch(
            "app.pipelines.apriltag_pipeline.load_field_layout_by_name",
            return_value=layout,
        ),
    ):
        pipeline = AprilTagPipeline(
            {
                "family": "tag36h11",
                "tag_size_m": 1.0,
                "multi_tag_enabled": True,
            }
        )

    corners_image = [
        DummyCorner(100.0, 100.0),
        DummyCorner(200.0, 100.0),
        DummyCorner(200.0, 200.0),
        DummyCorner(100.0, 200.0),
    ]
    detection = DummyDetection(1, corners_image)

    correspondences = pipeline._build_correspondences([detection])
    assert len(correspondences) == 1

    expected_field_corners = _scale_tag_corners(1.0)
    np.testing.assert_allclose(
        correspondences[0].corners_field,
        expected_field_corners,
        atol=1e-9,
    )
