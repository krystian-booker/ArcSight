import math
from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

import cv2
import numpy as np
import robotpy_apriltag
from app.apriltag_fields import get_selected_field_name, load_field_layout_by_name
from wpimath.geometry import (
    Pose3d,
    Quaternion,
    Rotation3d,
    Transform3d,
    Translation3d,
)

try:
    from wpimath.units import units
except ImportError:  # pragma: no-cover - optional dependency in older robotpy builds
    units = None  # type: ignore[assignment]


FRC_AXIS_SWAP = np.array(
    [
        [0.0, 0.0, 1.0],  # X_frc = Z_cv
        [-1.0, 0.0, 0.0],  # Y_frc = -X_cv
        [0.0, -1.0, 0.0],  # Z_frc = -Y_cv
    ],
    dtype=np.float64,
)


def _translation_to_dict(translation: Translation3d) -> Dict[str, float]:
    return {
        "x": float(translation.X()),
        "y": float(translation.Y()),
        "z": float(translation.Z()),
    }


def _rotation_to_dict(rotation: Rotation3d) -> Dict[str, Dict[str, float]]:
    roll = float(rotation.X())
    pitch = float(rotation.Y())
    yaw = float(rotation.Z())
    quaternion = _extract_quaternion(rotation)
    return {
        "euler_deg": {
            "roll": math.degrees(roll),
            "pitch": math.degrees(pitch),
            "yaw": math.degrees(yaw),
        },
        "euler_rad": {
            "roll": roll,
            "pitch": pitch,
            "yaw": yaw,
        },
        "quaternion": {
            "w": float(quaternion.W()),
            "x": float(quaternion.X()),
            "y": float(quaternion.Y()),
            "z": float(quaternion.Z()),
        },
    }


def _transform_to_dict(transform: Transform3d) -> Dict[str, Dict[str, float]]:
    return {
        "translation": _translation_to_dict(transform.translation()),
        "rotation": _rotation_to_dict(transform.rotation()),
    }


def _pose_to_dict(pose: Pose3d) -> Dict[str, Dict[str, float]]:
    return {
        "translation": _translation_to_dict(pose.translation()),
        "rotation": _rotation_to_dict(pose.rotation()),
    }


def _extract_quaternion(rotation: Rotation3d) -> Quaternion:
    for attr in ("getQuaternion", "toQuaternion", "Quaternion"):
        handler = getattr(rotation, attr, None)
        if handler is None:
            continue
        quaternion = handler() if callable(handler) else handler
        if isinstance(quaternion, Quaternion):
            return quaternion
    raise AttributeError("Rotation3d does not expose a quaternion accessor")


def _quaternion_to_matrix(quaternion: Quaternion) -> np.ndarray:
    w = quaternion.W()
    x = quaternion.X()
    y = quaternion.Y()
    z = quaternion.Z()

    xx = x * x
    yy = y * y
    zz = z * z
    xy = x * y
    xz = x * z
    yz = y * z
    wx = w * x
    wy = w * y
    wz = w * z

    return np.array(
        [
            [1 - 2 * (yy + zz), 2 * (xy - wz), 2 * (xz + wy)],
            [2 * (xy + wz), 1 - 2 * (xx + zz), 2 * (yz - wx)],
            [2 * (xz - wy), 2 * (yz + wx), 1 - 2 * (xx + yy)],
        ],
        dtype=np.float64,
    )


def _rotation3d_to_matrix(rotation: Rotation3d) -> np.ndarray:
    matrix_method = getattr(rotation, "toMatrix", None)
    if callable(matrix_method):
        matrix = matrix_method()
        return np.array(matrix, dtype=np.float64)

    quaternion = _extract_quaternion(rotation)
    return _quaternion_to_matrix(quaternion)


def _matrix_to_quaternion(matrix: np.ndarray) -> Quaternion:
    m = matrix
    trace = m[0, 0] + m[1, 1] + m[2, 2]
    if trace > 0:
        s = math.sqrt(trace + 1.0) * 2.0
        w = 0.25 * s
        x = (m[2, 1] - m[1, 2]) / s
        y = (m[0, 2] - m[2, 0]) / s
        z = (m[1, 0] - m[0, 1]) / s
    elif m[0, 0] > m[1, 1] and m[0, 0] > m[2, 2]:
        s = math.sqrt(1.0 + m[0, 0] - m[1, 1] - m[2, 2]) * 2.0
        w = (m[2, 1] - m[1, 2]) / s
        x = 0.25 * s
        y = (m[0, 1] + m[1, 0]) / s
        z = (m[0, 2] + m[2, 0]) / s
    elif m[1, 1] > m[2, 2]:
        s = math.sqrt(1.0 + m[1, 1] - m[0, 0] - m[2, 2]) * 2.0
        w = (m[0, 2] - m[2, 0]) / s
        x = (m[0, 1] + m[1, 0]) / s
        y = 0.25 * s
        z = (m[1, 2] + m[2, 1]) / s
    else:
        s = math.sqrt(1.0 + m[2, 2] - m[0, 0] - m[1, 1]) * 2.0
        w = (m[1, 0] - m[0, 1]) / s
        x = (m[0, 2] + m[2, 0]) / s
        y = (m[1, 2] + m[2, 1]) / s
        z = 0.25 * s

    return Quaternion(w, x, y, z)


def _transform_to_rvec_tvec(transform: Transform3d) -> Tuple[np.ndarray, np.ndarray]:
    rotation_matrix = _rotation3d_to_matrix(transform.rotation())
    rvec, _ = cv2.Rodrigues(rotation_matrix)

    translation = transform.translation()
    tvec = np.array(
        [[translation.X()], [translation.Y()], [translation.Z()]],
        dtype=np.float64,
    )
    return rvec, tvec


def _project_error(
    object_points: np.ndarray,
    image_points: np.ndarray,
    rvec: np.ndarray,
    tvec: np.ndarray,
    cam_matrix: np.ndarray,
    dist_coeffs: np.ndarray,
) -> float:
    projected, _ = cv2.projectPoints(object_points, rvec, tvec, cam_matrix, dist_coeffs)
    projected = projected.reshape(-1, 2)
    residual = image_points - projected
    return float(np.mean(np.linalg.norm(residual, axis=1)))


def _scale_tag_corners(tag_size: float) -> np.ndarray:
    half = tag_size / 2.0
    return np.array(
        [
            [-half, -half, 0.0],
            [half, -half, 0.0],
            [half, half, 0.0],
            [-half, half, 0.0],
        ],
        dtype=np.float32,
    )


def _compute_frc_pose(
    rvec: np.ndarray, tvec: np.ndarray
) -> Tuple[
    np.ndarray, Tuple[float, float, float], Tuple[float, float, float], np.ndarray
]:
    rmat_opencv, _ = cv2.Rodrigues(rvec)
    rmat_frc = FRC_AXIS_SWAP @ rmat_opencv @ FRC_AXIS_SWAP.T

    tvec_frc = np.array(
        [tvec[2, 0], -tvec[0, 0], -tvec[1, 0]],
        dtype=np.float64,
    )

    pitch = math.asin(-rmat_frc[2, 0])
    if abs(math.cos(pitch)) > 1e-6:
        yaw = math.atan2(rmat_frc[1, 0], rmat_frc[0, 0])
        roll = math.atan2(rmat_frc[2, 1], rmat_frc[2, 2])
    else:
        yaw = math.atan2(-rmat_frc[0, 1], rmat_frc[1, 1])
        roll = 0.0

    euler_deg = (math.degrees(roll), math.degrees(pitch), math.degrees(yaw))
    return tvec_frc, (roll, pitch, yaw), euler_deg, rmat_frc


@dataclass
class SingleTagResult:
    ui_data: Dict[str, float]
    drawing_data: Dict[str, object]
    detection: Dict[str, object]


@dataclass
class TagCorrespondence:
    tag_id: int
    corners_field: np.ndarray
    corners_image: np.ndarray


class AprilTagPipeline:
    """AprilTag pipeline supporting both WPILib pose estimator and OpenCV fallbacks."""

    def __init__(self, config: Dict):
        self.detector = robotpy_apriltag.AprilTagDetector()

        family = config.get("family", "tag36h11")
        if not family.startswith("tag"):
            family = f"tag{family}"
        self.detector.addFamily(family, config.get("error_correction", 2))

        detector_config = self.detector.getConfig()
        detector_config.numThreads = config.get("threads", 1)
        detector_config.quadDecimate = config.get("decimate", 1.0)
        detector_config.quadSigma = config.get("blur", 0.0)
        detector_config.refineEdges = config.get("refine_edges", True)
        detector_config.decodeSharpening = config.get("decode_sharpening", 0.25)
        self.detector.setConfig(detector_config)

        self.decision_margin_threshold = config.get("decision_margin", 35.0)
        self.pose_iterations = int(config.get("pose_iterations", 50))

        self.multi_tag_enabled = bool(config.get("multi_tag_enabled", False))
        self.ransac_reproj_threshold = float(config.get("ransac_reproj_threshold", 1.2))
        self.ransac_confidence = float(config.get("ransac_confidence", 0.999))
        self.ransac_min_inliers = int(config.get("min_inliers", 12))
        self.use_prev_guess = bool(config.get("use_prev_guess", True))
        self.multi_tag_error_threshold = float(
            config.get("multi_tag_error_threshold", 6.0)
        )
        self.publish_field_pose = bool(config.get("publish_field_pose", True))
        self.output_quaternion = bool(config.get("output_quaternion", True))

        self.field_layout_name: Optional[str] = None
        self.field_layout_data: Optional[Dict[int, Pose3d]] = None
        self._load_selected_layout()

        self.tag_size_m = float(config.get("tag_size_m", 0.1651))
        self.single_tag_obj_points = _scale_tag_corners(self.tag_size_m)

        self.gray_frame: Optional[np.ndarray] = None

        self._pose_estimator = None
        self._pose_estimator_intrinsics: Optional[Tuple[float, float, float, float]] = (
            None
        )
        self._use_pose_estimator = False

        self._previous_rvec: Optional[np.ndarray] = None
        self._previous_tvec: Optional[np.ndarray] = None

        print(
            "AprilTag detector configured",
            f"family={family}",
            f"threads={detector_config.numThreads}",
            f"decimate={detector_config.quadDecimate}",
            f"blur={detector_config.quadSigma}",
            f"refine_edges={detector_config.refineEdges}",
            f"multi_tag={self.multi_tag_enabled}",
        )

    def _load_selected_layout(self) -> None:
        if not self.multi_tag_enabled:
            return

        selected = get_selected_field_name()
        if not selected:
            print("Multi-tag enabled, but no AprilTag field layout selected")
            return

        layout = load_field_layout_by_name(selected)
        if not layout:
            print(f"Failed to load AprilTag field layout '{selected}'")
            return

        self._apply_layout(selected, layout)

    def _apply_layout(self, name: str, layout: Dict) -> None:
        tag_map: Dict[int, Pose3d] = {}
        for tag in layout.get("tags", []):
            try:
                tag_id = int(tag["ID"])
                pose = tag["pose"]
                translation = pose["translation"]
                rotation = pose["rotation"]["quaternion"]

                def _q(key: str) -> float:
                    return float(rotation.get(key, rotation.get(key.lower())))

                pose3d = Pose3d(
                    Translation3d(
                        float(translation["x"]),
                        float(translation["y"]),
                        float(translation["z"]),
                    ),
                    Rotation3d(
                        Quaternion(
                            _q("W"),
                            _q("X"),
                            _q("Y"),
                            _q("Z"),
                        )
                    ),
                )
            except (KeyError, TypeError, ValueError):
                continue
            tag_map[tag_id] = pose3d

        if tag_map:
            self.field_layout_name = name
            self.field_layout_data = tag_map
            print(
                f"Loaded AprilTag field '{name}' with {len(tag_map)} tags",
            )
        else:
            self.field_layout_name = None
            self.field_layout_data = None
            print(f"AprilTag field '{name}' contained no valid tags")

    def _ensure_pose_estimator(self, cam_matrix: np.ndarray) -> None:
        estimator_cls = getattr(robotpy_apriltag, "AprilTagPoseEstimator", None)
        if estimator_cls is None or not isinstance(estimator_cls, type):
            self._pose_estimator = None
            self._use_pose_estimator = False
            return

        fx = float(cam_matrix[0, 0])
        fy = float(cam_matrix[1, 1])
        cx = float(cam_matrix[0, 2])
        cy = float(cam_matrix[1, 2])
        intrinsics = (fx, fy, cx, cy)

        if self._pose_estimator and self._pose_estimator_intrinsics == intrinsics:
            self._use_pose_estimator = True
            return

        config_cls = getattr(estimator_cls, "Config", None)
        if config_cls is None or not isinstance(config_cls, type):
            self._pose_estimator = None
            self._use_pose_estimator = False
            return

        tag_size = (
            units.meters(self.tag_size_m) if units is not None else self.tag_size_m
        )
        try:
            config = config_cls(tag_size, fx, fy, cx, cy)
        except TypeError:
            try:
                config = config_cls(self.tag_size_m, fx, fy, cx, cy)
            except TypeError as exc:
                print(f"Failed to configure AprilTagPoseEstimator: {exc}")
                self._pose_estimator = None
                self._use_pose_estimator = False
                return

        try:
            self._pose_estimator = estimator_cls(config)
        except TypeError as exc:
            print(f"Failed to instantiate AprilTagPoseEstimator: {exc}")
            self._pose_estimator = None
            self._use_pose_estimator = False
            return

        self._pose_estimator_intrinsics = intrinsics
        self._use_pose_estimator = True

    def _filter_detections(
        self, detections: Sequence[robotpy_apriltag.AprilTagDetection]
    ) -> List[robotpy_apriltag.AprilTagDetection]:
        valid: List[robotpy_apriltag.AprilTagDetection] = []
        for tag in detections:
            if (
                tag.getHamming() <= 1
                and tag.getDecisionMargin() >= self.decision_margin_threshold
            ):
                valid.append(tag)
        return valid

    def _build_correspondences(
        self,
        detections: Iterable[robotpy_apriltag.AprilTagDetection],
    ) -> List[TagCorrespondence]:
        correspondences: List[TagCorrespondence] = []
        if not self.field_layout_data:
            return correspondences

        for tag in detections:
            tag_id = int(tag.getId())
            tag_pose_field = self.field_layout_data.get(tag_id)
            if tag_pose_field is None:
                continue

            corners_image = np.array(
                [
                    [tag.getCorner(0).x, tag.getCorner(0).y],
                    [tag.getCorner(1).x, tag.getCorner(1).y],
                    [tag.getCorner(2).x, tag.getCorner(2).y],
                    [tag.getCorner(3).x, tag.getCorner(3).y],
                ],
                dtype=np.float32,
            )

            corners_field: List[List[float]] = []
            for corner in self.single_tag_obj_points:
                offset = Translation3d(
                    float(corner[0]), float(corner[1]), float(corner[2])
                )
                corner_pose = tag_pose_field.transformBy(
                    Transform3d(offset, Rotation3d())
                )
                trans = corner_pose.translation()
                corners_field.append(
                    [float(trans.X()), float(trans.Y()), float(trans.Z())]
                )

            correspondences.append(
                TagCorrespondence(
                    tag_id=tag_id,
                    corners_field=np.array(corners_field, dtype=np.float32),
                    corners_image=corners_image,
                )
            )

        return correspondences

    def _build_single_tag_result(
        self,
        tag_id: int,
        decision_margin: float,
        hamming: int,
        pose_error: float,
        ambiguity: float,
        reprojection_error: float,
        rvec: np.ndarray,
        tvec: np.ndarray,
        img_points: np.ndarray,
        camera_to_tag_transform: Transform3d,
        field_pose: Optional[Pose3d],
    ) -> SingleTagResult:
        tvec_frc, euler_rad, euler_deg, rmat_frc = _compute_frc_pose(rvec, tvec)

        ui_data = {
            "id": tag_id,
            "decision_margin": decision_margin,
            "pose_error": pose_error,
            "ambiguity": ambiguity,
            "reprojection_error": reprojection_error,
            "x_m": float(tvec_frc[0]),
            "y_m": float(tvec_frc[1]),
            "z_m": float(tvec_frc[2]),
            "roll_rad": euler_rad[0],
            "pitch_rad": euler_rad[1],
            "yaw_rad": euler_rad[2],
            "roll_deg": euler_deg[0],
            "pitch_deg": euler_deg[1],
            "yaw_deg": euler_deg[2],
        }

        drawing_data = {
            "rvec": rvec,
            "tvec": tvec,
            "corners": img_points,
            "id": tag_id,
        }

        detection_payload = {
            "id": tag_id,
            "decision_margin": decision_margin,
            "hamming": hamming,
            "pose_error": pose_error,
            "ambiguity": ambiguity,
            "reprojection_error": reprojection_error,
            "camera_to_tag": self._transform_payload(camera_to_tag_transform),
        }

        if field_pose is not None:
            detection_payload["camera_pose_field"] = self._pose_payload(field_pose)

        return SingleTagResult(ui_data, drawing_data, detection_payload)

    def _solve_single_tag_with_estimator(
        self,
        detection: robotpy_apriltag.AprilTagDetection,
        cam_matrix: np.ndarray,
        dist_coeffs: np.ndarray,
    ) -> Optional[SingleTagResult]:
        if not self._use_pose_estimator or self._pose_estimator is None:
            return None

        try:
            estimate = self._pose_estimator.estimateOrthogonalIteration(
                detection, self.pose_iterations
            )
        except TypeError:
            estimate = self._pose_estimator.estimateOrthogonalIteration(detection)

        if estimate is None:
            return None

        candidates: List[Tuple[Transform3d, float]] = []
        ambiguity = float(getattr(estimate, "ambiguity", math.nan))

        for attr in ("bestPose", "pose1", "pose2", "pose"):
            pose = getattr(estimate, attr, None)
            if pose is None:
                continue
            error_attr_variants = (
                f"{attr}Error",
                f"{attr}error",
                "bestError",
                "error",
            )
            error_value = math.inf
            for error_attr in error_attr_variants:
                if hasattr(estimate, error_attr):
                    error_value = getattr(estimate, error_attr)
                    break

            candidates.append((pose, float(error_value)))

        if not candidates:
            return None

        camera_to_tag_transform, best_error = min(candidates, key=lambda item: item[1])

        rvec, tvec = _transform_to_rvec_tvec(camera_to_tag_transform)
        img_points = np.array(
            [
                [detection.getCorner(0).x, detection.getCorner(0).y],
                [detection.getCorner(1).x, detection.getCorner(1).y],
                [detection.getCorner(2).x, detection.getCorner(2).y],
                [detection.getCorner(3).x, detection.getCorner(3).y],
            ],
            dtype=np.float32,
        )
        reprojection_error = _project_error(
            self.single_tag_obj_points, img_points, rvec, tvec, cam_matrix, dist_coeffs
        )

        field_pose = None
        if (
            self.publish_field_pose
            and self.field_layout_data
            and detection.getId() in self.field_layout_data
        ):
            tag_pose_field = self.field_layout_data[detection.getId()]
            field_pose = tag_pose_field.transformBy(camera_to_tag_transform.inverse())

        return self._build_single_tag_result(
            detection.getId(),
            float(detection.getDecisionMargin()),
            int(detection.getHamming()),
            float(best_error),
            ambiguity,
            reprojection_error,
            rvec,
            tvec,
            img_points,
            camera_to_tag_transform,
            field_pose,
        )

    def _solve_single_tag_with_opencv(
        self,
        detection: robotpy_apriltag.AprilTagDetection,
        cam_matrix: np.ndarray,
        dist_coeffs: np.ndarray,
    ) -> Optional[SingleTagResult]:
        img_points = np.array(
            [
                [detection.getCorner(0).x, detection.getCorner(0).y],
                [detection.getCorner(1).x, detection.getCorner(1).y],
                [detection.getCorner(2).x, detection.getCorner(2).y],
                [detection.getCorner(3).x, detection.getCorner(3).y],
            ],
            dtype=np.float32,
        )

        success, rvec, tvec = cv2.solvePnP(
            self.single_tag_obj_points,
            img_points,
            cam_matrix,
            dist_coeffs,
            flags=cv2.SOLVEPNP_IPPE,
        )

        if not success:
            return None

        reprojection_error = _project_error(
            self.single_tag_obj_points, img_points, rvec, tvec, cam_matrix, dist_coeffs
        )

        tvec_frc, _, _, rmat_frc = _compute_frc_pose(rvec, tvec)

        rotation = Rotation3d(_matrix_to_quaternion(rmat_frc))
        translation = Translation3d(
            float(tvec_frc[0]),
            float(tvec_frc[1]),
            float(tvec_frc[2]),
        )
        camera_to_tag_transform = Transform3d(translation, rotation)

        field_pose = None
        if (
            self.publish_field_pose
            and self.field_layout_data
            and detection.getId() in self.field_layout_data
        ):
            tag_pose_field = self.field_layout_data[detection.getId()]
            field_pose = tag_pose_field.transformBy(camera_to_tag_transform.inverse())

        return self._build_single_tag_result(
            detection.getId(),
            float(detection.getDecisionMargin()),
            int(detection.getHamming()),
            float(reprojection_error),
            math.nan,
            reprojection_error,
            rvec,
            tvec,
            img_points,
            camera_to_tag_transform,
            field_pose,
        )

    def _modern_multi_to_legacy(self, modern: Dict[str, object]) -> Dict[str, object]:
        if modern is None:
            return {}
        translation = modern["camera_to_field"]["translation"]  # type: ignore[index]
        rotation = modern["camera_to_field"]["rotation"]  # type: ignore[index]
        euler_deg = rotation.get("euler_deg", {})
        euler_rad = rotation.get("euler_rad", {})
        return {
            "pose_error": modern.get("projected_error"),
            "x_m": translation.get("x"),
            "y_m": translation.get("y"),
            "z_m": translation.get("z"),
            "roll_deg": euler_deg.get("roll"),
            "pitch_deg": euler_deg.get("pitch"),
            "yaw_deg": euler_deg.get("yaw"),
            "roll_rad": euler_rad.get("roll"),
            "pitch_rad": euler_rad.get("pitch"),
            "yaw_rad": euler_rad.get("yaw"),
            "num_tags": len(modern.get("tag_ids_used", [])),
            "tag_ids": modern.get("tag_ids_used", []),
        }

    def _solve_multi_tag_opencv(
        self,
        correspondences: List[TagCorrespondence],
        cam_matrix: np.ndarray,
        dist_coeffs: np.ndarray,
    ) -> Tuple[Optional[Dict[str, object]], Optional[Dict[str, object]]]:
        if len(correspondences) < 2:
            return None, None

        object_points = []
        image_points = []
        tag_ranges: List[Tuple[int, Tuple[int, int]]] = []

        for corr in correspondences:
            start_index = len(object_points)
            object_points.extend(corr.corners_field)
            image_points.extend(corr.corners_image)
            tag_ranges.append((corr.tag_id, (start_index, start_index + 4)))

        obj = np.asarray(object_points, dtype=np.float32)
        img = np.asarray(image_points, dtype=np.float32)

        success, rvec, tvec = cv2.solvePnP(
            obj,
            img,
            cam_matrix,
            dist_coeffs,
            flags=cv2.SOLVEPNP_SQPNP,
        )

        if not success:
            return None, None

        projected, _ = cv2.projectPoints(obj, rvec, tvec, cam_matrix, dist_coeffs)
        residuals = img - projected.reshape(-1, 2)
        residual_norms = np.linalg.norm(residuals, axis=1)
        mean_error = float(np.mean(residual_norms))

        tvec_frc, _, _, rmat_frc = _compute_frc_pose(rvec, tvec)
        rotation = Rotation3d(_matrix_to_quaternion(rmat_frc))
        translation = Translation3d(
            float(tvec_frc[0]),
            float(tvec_frc[1]),
            float(tvec_frc[2]),
        )
        camera_to_field = Transform3d(translation, rotation)
        field_to_camera = camera_to_field.inverse()

        per_tag_errors: Dict[int, Dict[str, float]] = {}
        for tag_id, (start, end) in tag_ranges:
            tag_residuals = residual_norms[start:end]
            per_tag_errors[tag_id] = {
                "mean_reproj_error": float(np.mean(tag_residuals)),
                "max_reproj_error": float(np.max(tag_residuals)),
            }

        modern = {
            "tag_ids_used": [tag_id for tag_id, _ in tag_ranges],
            "num_inliers": int(len(obj)),
            "mean_reproj_error": mean_error,
            "max_reproj_error": float(np.max(residual_norms)),
            "camera_to_field": self._transform_payload(camera_to_field),
            "field_to_camera": self._transform_payload(field_to_camera),
            "per_tag_error": per_tag_errors,
            "projected_error": mean_error,
        }
        legacy = self._modern_multi_to_legacy(modern)
        return modern, legacy

    def _solve_multi_tag_ransac(
        self,
        correspondences: List[TagCorrespondence],
        cam_matrix: np.ndarray,
        dist_coeffs: np.ndarray,
    ) -> Tuple[Optional[Dict[str, object]], Optional[Dict[str, object]]]:
        if len(correspondences) < 2:
            return None, None

        object_points = []
        image_points = []
        tag_ranges: List[Tuple[int, Tuple[int, int]]] = []

        for corr in correspondences:
            start_index = len(object_points)
            object_points.extend(corr.corners_field)
            image_points.extend(corr.corners_image)
            tag_ranges.append((corr.tag_id, (start_index, start_index + 4)))

        obj = np.asarray(object_points, dtype=np.float32)
        img = np.asarray(image_points, dtype=np.float32)

        use_guess = self.use_prev_guess and self._previous_rvec is not None
        initial_rvec = self._previous_rvec if use_guess else None
        initial_tvec = self._previous_tvec if use_guess else None

        success, rvec, tvec, inliers = cv2.solvePnPRansac(
            obj,
            img,
            cam_matrix,
            dist_coeffs,
            useExtrinsicGuess=use_guess,
            rvec=initial_rvec,
            tvec=initial_tvec,
            reprojectionError=self.ransac_reproj_threshold,
            confidence=self.ransac_confidence,
            iterationsCount=max(self.pose_iterations, 25),
            flags=cv2.SOLVEPNP_ITERATIVE,
        )

        if not success or inliers is None:
            return None, None

        inlier_indices = set(int(idx[0]) for idx in inliers)
        if len(inlier_indices) < self.ransac_min_inliers:
            return None, None

        projected_error = _project_error(
            obj[inliers.flatten()],
            img[inliers.flatten()],
            rvec,
            tvec,
            cam_matrix,
            dist_coeffs,
        )

        tvec_frc, _, _, rmat_frc = _compute_frc_pose(rvec, tvec)
        rotation = Rotation3d(_matrix_to_quaternion(rmat_frc))
        translation = Translation3d(
            float(tvec_frc[0]),
            float(tvec_frc[1]),
            float(tvec_frc[2]),
        )

        camera_to_field = Transform3d(translation, rotation)
        field_to_camera = camera_to_field.inverse()

        field_pose = Pose3d(
            field_to_camera.translation(),
            field_to_camera.rotation(),
        )

        per_tag_errors: Dict[int, Dict[str, float]] = {}
        residuals = []
        projected_all, _ = cv2.projectPoints(obj, rvec, tvec, cam_matrix, dist_coeffs)
        projected_all = projected_all.reshape(-1, 2)

        for tag_id, (start, end) in tag_ranges:
            indices = list(range(start, end))
            inlier_mask = [idx for idx in indices if idx in inlier_indices]
            if not inlier_mask:
                continue
            residual = img[inlier_mask] - projected_all[inlier_mask]
            l2 = np.linalg.norm(residual, axis=1)
            per_tag_errors[tag_id] = {
                "mean_reproj_error": float(np.mean(l2)),
                "max_reproj_error": float(np.max(l2)),
            }
            residuals.extend(l2.tolist())

        mean_error = float(np.mean(residuals)) if residuals else float("nan")
        max_error = float(np.max(residuals)) if residuals else float("nan")

        modern = {
            "tag_ids_used": [
                tag_id for tag_id, _ in tag_ranges if per_tag_errors.get(tag_id)
            ],
            "num_inliers": int(len(inlier_indices)),
            "mean_reproj_error": mean_error,
            "max_reproj_error": max_error,
            "camera_to_field": self._transform_payload(camera_to_field),
            "field_to_camera": self._transform_payload(field_to_camera),
            "field_pose": self._pose_payload(field_pose),
            "per_tag_error": per_tag_errors,
            "projected_error": projected_error,
        }

        legacy = self._modern_multi_to_legacy(modern)
        self._previous_rvec = rvec
        self._previous_tvec = tvec

        if (
            modern["per_tag_error"]
            and self.multi_tag_error_threshold > 0
            and len(modern["tag_ids_used"]) > 1
        ):
            outlier_tags = [
                tag_id
                for tag_id, metrics in modern["per_tag_error"].items()
                if metrics["mean_reproj_error"] > self.multi_tag_error_threshold
            ]
            if outlier_tags and len(modern["tag_ids_used"]) - len(outlier_tags) >= 2:
                filtered = [
                    corr for corr in correspondences if corr.tag_id not in outlier_tags
                ]
                return self._solve_multi_tag_ransac(filtered, cam_matrix, dist_coeffs)

        return modern, legacy

    def _transform_payload(self, transform: Transform3d) -> Dict[str, Dict[str, float]]:
        payload = _transform_to_dict(transform)
        if not self.output_quaternion:
            payload.get("rotation", {}).pop("quaternion", None)
        return payload

    def _pose_payload(self, pose: Pose3d) -> Dict[str, Dict[str, float]]:
        payload = _pose_to_dict(pose)
        if not self.output_quaternion:
            payload.get("rotation", {}).pop("quaternion", None)
        return payload

    def process_frame(
        self,
        frame: np.ndarray,
        cam_matrix: np.ndarray,
        dist_coeffs: Optional[np.ndarray] = None,
    ) -> Dict[str, object]:
        if dist_coeffs is None:
            dist_coeffs = np.zeros((4, 1), dtype=np.float32)

        if frame.ndim == 3:
            if self.gray_frame is None or self.gray_frame.shape != frame.shape[:2]:
                self.gray_frame = np.empty(frame.shape[:2], dtype=np.uint8)
            cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY, dst=self.gray_frame)
            detect_frame = self.gray_frame
        else:
            detect_frame = frame

        detections = self.detector.detect(detect_frame)
        valid_detections = self._filter_detections(detections)

        self._ensure_pose_estimator(cam_matrix)

        single_tag_results: List[SingleTagResult] = []
        for tag in valid_detections:
            result = None
            if self._use_pose_estimator:
                result = self._solve_single_tag_with_estimator(
                    tag, cam_matrix, dist_coeffs
                )
            if result is None:
                result = self._solve_single_tag_with_opencv(
                    tag, cam_matrix, dist_coeffs
                )
            if result is not None:
                single_tag_results.append(result)

        multi_tag_modern = None
        multi_tag_legacy = None
        if self.multi_tag_enabled and self.field_layout_data:
            correspondences = self._build_correspondences(valid_detections)
            if correspondences:
                if self._use_pose_estimator:
                    multi_tag_modern, multi_tag_legacy = self._solve_multi_tag_ransac(
                        correspondences, cam_matrix, dist_coeffs
                    )
                if multi_tag_modern is None and multi_tag_legacy is None:
                    multi_tag_modern, multi_tag_legacy = self._solve_multi_tag_opencv(
                        correspondences, cam_matrix, dist_coeffs
                    )

        legacy_single_tags = [
            {"ui_data": result.ui_data, "drawing_data": result.drawing_data}
            for result in single_tag_results
        ]
        overlays = [result.drawing_data for result in single_tag_results]
        modern_detections = [result.detection for result in single_tag_results]

        return {
            "detections": modern_detections,
            "overlays": overlays,
            "multi_tag_pose": multi_tag_modern,
            "single_tags": legacy_single_tags,
            "multi_tag": multi_tag_legacy,
        }
