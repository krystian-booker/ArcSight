import robotpy_apriltag
import cv2
import numpy as np
import math
from wpimath.geometry import Transform3d


class AprilTagPipeline:
    """
    A pipeline for detecting and estimating the pose of AprilTags using robotpy-apriltag.
    """

    def __init__(self, config):
        """
        Initializes the AprilTag detector and pose estimator.

        Args:
            config (dict): A dictionary containing configuration options.
        """
        # --- Detector Setup ---
        self.detector = robotpy_apriltag.AprilTagDetector()

        # Get tag family from config, default to 'tag36h11'
        family = config.get("family", "tag36h11")

        # TODO: Remove this is a hack for now
        # Ensure the family name has the 'tag' prefix
        if not family.startswith("tag"):
            family = f"tag{family}"

        # Add the family to the detector. The second argument is error correction bits.
        self.detector.addFamily(family, config.get("error_correction", 3))

        # --- Pose Estimator Setup ---
        # Get tag size from config, default to 6.5 inches in meters
        tag_size_m = config.get("tag_size_m", 0.1651)

        # Pose Estimator requires camera intrinsics (fx, fy, cx, cy)
        # We will get these from camera_params in process_frame, so we create the estimator there.
        self.pose_estimator_config = robotpy_apriltag.AprilTagPoseEstimator.Config(
            tag_size_m,
            0,  # fx - will be updated per frame
            0,  # fy - will be updated per frame
            0,  # cx - will be updated per frame
            0,  # cy - will be updated per frame
        )
        self.pose_estimator = None

        # --- Reusable Buffers (for optimization) ---
        self.gray_frame = None

        print(f"AprilTag detector initialized with family: {family}")

    def process_frame(self, frame, cam_matrix):
        """
        Processes a single frame to find AprilTags and estimate their pose.

        Args:
            frame (np.ndarray): The input image frame from the camera.
            cam_matrix (np.ndarray): The 3x3 camera intrinsic matrix.

        Returns:
            list: A list of dictionaries, where each dictionary represents a detected tag.
        """
        # --- Update Pose Estimator if needed ---
        fx = cam_matrix[0, 0]
        fy = cam_matrix[1, 1]
        cx = cam_matrix[0, 2]
        cy = cam_matrix[1, 2]

        if (
            self.pose_estimator is None
            or self.pose_estimator_config.fx != fx
            or self.pose_estimator_config.fy != fy
        ):
            self.pose_estimator_config.fx = fx
            self.pose_estimator_config.fy = fy
            self.pose_estimator_config.cx = cx
            self.pose_estimator_config.cy = cy
            self.pose_estimator = robotpy_apriltag.AprilTagPoseEstimator(
                self.pose_estimator_config
            )

        # --- Grayscale Conversion ---
        if frame.ndim == 3:
            if self.gray_frame is None or self.gray_frame.shape != frame.shape[:2]:
                self.gray_frame = np.empty(frame.shape[:2], dtype=np.uint8)
            cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY, dst=self.gray_frame)
            detect_frame = self.gray_frame
        else:
            detect_frame = frame

        # --- Detect Tags ---
        detections = self.detector.detect(detect_frame)

        results = []
        for tag in detections:
            # Reject tags with high hamming distance or low decision margin
            if tag.getHamming() > 1 or tag.getDecisionMargin() < 25.0:
                continue

            # --- Pose Estimation ---
            # Use estimateOrthogonalIteration to get the AprilTagPoseEstimate object
            est_result = self.pose_estimator.estimateOrthogonalIteration(tag, 50)

            pose: Transform3d = est_result.pose1
            pose_error = est_result.error1

            # Extract rotation from the pose
            rotation = pose.rotation()

            # --- Data for Drawing ---
            # Get the raw translation and rotation vectors used by OpenCV
            tvec = np.array([pose.X(), pose.Y(), pose.Z()])
            rvec, _ = cv2.Rodrigues(rotation.toMatrix())

            # Get the corners for drawing the bounding box
            corners = np.array(
                [
                    [tag.getCorner(0).x, tag.getCorner(0).y],
                    [tag.getCorner(1).x, tag.getCorner(1).y],
                    [tag.getCorner(2).x, tag.getCorner(2).y],
                    [tag.getCorner(3).x, tag.getCorner(3).y],
                ]
            )

            # --- Data for UI Table (with coordinate system transformation) ---
            # Transform coordinates for a more intuitive representation if needed
            # For example, Z forward, Y left, X down
            x_ui = pose.Z()
            y_ui = -pose.X()
            z_ui = -pose.Y()

            # For WPILib's Rotation3d: X()=Roll, Y()=Pitch, Z()=Yaw in radians
            pose_rotation = pose.rotation()
            roll_rad = pose_rotation.Z()
            pitch_rad = -pose_rotation.X()
            yaw_rad = -pose_rotation.Y()

            # Convert radians to degrees for the UI
            roll_deg = math.degrees(roll_rad)
            pitch_deg = math.degrees(pitch_rad)
            yaw_deg = math.degrees(yaw_rad)

            results.append(
                {
                    "ui_data": {
                        "id": tag.getId(),
                        "decision_margin": tag.getDecisionMargin(),
                        "pose_error": pose_error,
                        "x_m": x_ui,
                        "y_m": y_ui,
                        "z_m": z_ui,
                        "yaw_rad": yaw_rad,
                        "pitch_rad": pitch_rad,
                        "roll_rad": roll_rad,
                        "yaw_deg": yaw_deg,
                        "pitch_deg": pitch_deg,
                        "roll_deg": roll_deg,
                    },
                    "drawing_data": {
                        "rvec": rvec,
                        "tvec": tvec,
                        "corners": corners,
                        "id": tag.getId(),
                    },
                }
            )

        return results
