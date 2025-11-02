"""Service for camera calibration business logic."""

import logging
import json
from typing import List, Optional, Tuple

import cv2
import numpy as np

from app.extensions import db
from app.models import Camera

logger = logging.getLogger(__name__)


class CalibrationService:
    """Service for camera calibration operations."""

    @staticmethod
    def find_chessboard_corners(
        image: np.ndarray,
        pattern_size: Tuple[int, int],
        refine_corners: bool = True
    ) -> Tuple[bool, Optional[np.ndarray]]:
        """
        Find chessboard corners in an image.

        Args:
            image: Input image (color or grayscale)
            pattern_size: Tuple of (columns, rows) of inner corners
            refine_corners: Whether to refine corner positions

        Returns:
            Tuple of (found, corners) where found is bool and corners is numpy array
        """
        # Convert to grayscale if needed
        if len(image.shape) == 3:
            gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        else:
            gray = image

        # Find chessboard corners
        ret, corners = cv2.findChessboardCorners(gray, pattern_size, None)

        if ret and refine_corners:
            # Refine corner positions to sub-pixel accuracy
            criteria = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 30, 0.001)
            corners = cv2.cornerSubPix(gray, corners, (11, 11), (-1, -1), criteria)

        return ret, corners if ret else None

    @staticmethod
    def compute_calibration(
        object_points: List[np.ndarray],
        image_points: List[np.ndarray],
        image_size: Tuple[int, int]
    ) -> Tuple[bool, Optional[np.ndarray], Optional[np.ndarray], Optional[float]]:
        """
        Compute camera calibration from object and image points.

        Args:
            object_points: List of 3D object point arrays
            image_points: List of 2D image point arrays
            image_size: Image dimensions (width, height)

        Returns:
            Tuple of (success, camera_matrix, dist_coeffs, reprojection_error)
        """
        if not object_points or not image_points:
            logger.warning("No calibration points provided")
            return False, None, None, None

        if len(object_points) != len(image_points):
            logger.error(
                f"Mismatch: {len(object_points)} object point sets vs "
                f"{len(image_points)} image point sets"
            )
            return False, None, None, None

        try:
            ret, camera_matrix, dist_coeffs, rvecs, tvecs = cv2.calibrateCamera(
                object_points,
                image_points,
                image_size,
                None,
                None
            )

            if not ret:
                logger.error("Camera calibration failed")
                return False, None, None, None

            # Compute reprojection error
            total_error = 0.0
            total_points = 0

            for i in range(len(object_points)):
                projected_points, _ = cv2.projectPoints(
                    object_points[i],
                    rvecs[i],
                    tvecs[i],
                    camera_matrix,
                    dist_coeffs
                )
                error = cv2.norm(image_points[i], projected_points, cv2.NORM_L2)
                total_error += error
                total_points += len(object_points[i])

            mean_error = total_error / total_points if total_points > 0 else 0.0

            logger.info(
                f"Calibration successful: {len(object_points)} images, "
                f"reprojection error: {mean_error:.4f}"
            )

            return True, camera_matrix, dist_coeffs, mean_error

        except Exception as e:
            logger.exception(f"Error during camera calibration: {e}")
            return False, None, None, None

    @staticmethod
    def save_calibration_to_camera(
        camera: Camera,
        camera_matrix: np.ndarray,
        dist_coeffs: np.ndarray,
        reprojection_error: float
    ) -> None:
        """
        Save calibration results to a camera in the database.

        Args:
            camera: Camera object to update
            camera_matrix: 3x3 camera matrix
            dist_coeffs: Distortion coefficients array
            reprojection_error: Mean reprojection error

        Raises:
            Exception: If database operation fails
        """
        camera.camera_matrix_json = json.dumps(camera_matrix.tolist())
        camera.dist_coeffs_json = json.dumps(dist_coeffs.tolist())
        camera.reprojection_error = reprojection_error

        db.session.commit()

        logger.info(
            f"Saved calibration to camera {camera.id}: "
            f"error={reprojection_error:.4f}"
        )

    @staticmethod
    def clear_calibration_from_camera(camera: Camera) -> None:
        """
        Remove calibration data from a camera.

        Args:
            camera: Camera object to update

        Raises:
            Exception: If database operation fails
        """
        camera.camera_matrix_json = None
        camera.dist_coeffs_json = None
        camera.reprojection_error = None

        db.session.commit()

        logger.info(f"Cleared calibration from camera {camera.id}")

    @staticmethod
    def generate_object_points(
        pattern_size: Tuple[int, int],
        square_size: float
    ) -> np.ndarray:
        """
        Generate 3D object points for a chessboard pattern.

        Args:
            pattern_size: Tuple of (columns, rows) of inner corners
            square_size: Size of each square in meters

        Returns:
            Numpy array of 3D object points
        """
        objp = np.zeros((pattern_size[0] * pattern_size[1], 3), np.float32)
        objp[:, :2] = np.mgrid[
            0:pattern_size[0], 0:pattern_size[1]
        ].T.reshape(-1, 2)
        objp *= square_size

        return objp

    @staticmethod
    def undistort_image(
        image: np.ndarray,
        camera_matrix: np.ndarray,
        dist_coeffs: np.ndarray
    ) -> np.ndarray:
        """
        Undistort an image using calibration parameters.

        Args:
            image: Input distorted image
            camera_matrix: 3x3 camera matrix
            dist_coeffs: Distortion coefficients

        Returns:
            Undistorted image
        """
        h, w = image.shape[:2]
        new_camera_matrix, roi = cv2.getOptimalNewCameraMatrix(
            camera_matrix, dist_coeffs, (w, h), 1, (w, h)
        )

        undistorted = cv2.undistort(
            image, camera_matrix, dist_coeffs, None, new_camera_matrix
        )

        return undistorted

    @staticmethod
    def load_calibration_from_camera(
        camera: Camera
    ) -> Tuple[Optional[np.ndarray], Optional[np.ndarray]]:
        """
        Load calibration data from a camera.

        Args:
            camera: Camera object

        Returns:
            Tuple of (camera_matrix, dist_coeffs) or (None, None) if not calibrated
        """
        if not camera.camera_matrix_json or not camera.dist_coeffs_json:
            return None, None

        try:
            camera_matrix = np.array(
                json.loads(camera.camera_matrix_json), dtype=np.float64
            )
            dist_coeffs = np.array(
                json.loads(camera.dist_coeffs_json), dtype=np.float64
            )
            return camera_matrix, dist_coeffs
        except (json.JSONDecodeError, ValueError) as e:
            logger.error(f"Error loading calibration for camera {camera.id}: {e}")
            return None, None
