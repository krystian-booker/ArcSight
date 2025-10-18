import robotpy_apriltag
import cv2
import numpy as np
import math
import json


class AprilTagPipeline:
    """
    A pipeline for detecting and estimating the pose of AprilTags using robotpy-apriltag
    for detection and OpenCV for pose estimation.
    """

    def __init__(self, config):
        """
        Initializes the AprilTag detector.

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
        # tag36h11 typically uses 2 error correction bits
        self.detector.addFamily(family, config.get("error_correction", 2))

        # --- Configure Detector Parameters ---
        detector_config = self.detector.getConfig()
        detector_config.numThreads = config.get("threads", 1)
        detector_config.quadDecimate = config.get("decimate", 1.0)
        detector_config.quadSigma = config.get("blur", 0.0)
        detector_config.refineEdges = config.get("refine_edges", True)
        detector_config.decodeSharpening = config.get("decode_sharpening", 0.25)
        self.detector.setConfig(detector_config)

        # Store filtering parameters
        self.decision_margin_threshold = config.get("decision_margin", 35.0)

        # --- Multi-tag Configuration ---
        self.multi_tag_enabled = config.get("multi_tag_enabled", False)
        self.field_layout_data = None

        # Load field layout if provided and multi-tag is enabled
        field_layout_json = config.get("field_layout", "")
        if self.multi_tag_enabled and field_layout_json:
            try:
                self.field_layout_data = self._load_field_layout(field_layout_json)
                print(f"Loaded field layout with {len(self.field_layout_data)} tags")
            except Exception as e:
                print(f"Failed to load field layout: {e}")
                self.multi_tag_enabled = False

        # --- Tag Size for 3D Object Points ---
        # Get tag size from config, default to 6.5 inches in meters
        self.tag_size_m = config.get("tag_size_m", 0.1651)

        # Create 3D object points for a single tag (tag-local coordinate system)
        # Tag corners in counter-clockwise order starting from bottom-left
        # Origin at tag center, X-right, Y-up, Z-out (right-handed)
        half_size = self.tag_size_m / 2.0
        self.single_tag_obj_points = np.array(
            [
                [-half_size, -half_size, 0],  # bottom-left
                [half_size, -half_size, 0],  # bottom-right
                [half_size, half_size, 0],  # top-right
                [-half_size, half_size, 0],  # top-left
            ],
            dtype=np.float32,
        )

        # --- Reusable Buffers (for optimization) ---
        self.gray_frame = None

        print(
            f"AprilTag detector initialized with family: {family}, "
            f"threads: {detector_config.numThreads}, "
            f"decimate: {detector_config.quadDecimate}, "
            f"blur: {detector_config.quadSigma}, "
            f"refine_edges: {detector_config.refineEdges}, "
            f"multi_tag: {self.multi_tag_enabled}"
        )

    def _load_field_layout(self, field_layout_json):
        """
        Load AprilTag field layout from JSON string.

        Args:
            field_layout_json (str): JSON string containing field layout

        Returns:
            dict: Dictionary mapping tag IDs to their 3D poses (center position + rotation)
        """
        layout_data = json.loads(field_layout_json)

        # Create dictionary mapping tag ID to pose information
        field_layout = {}
        for tag_data in layout_data["tags"]:
            tag_id = tag_data["ID"]
            pose_data = tag_data["pose"]

            # Extract translation (tag center in field coordinates)
            trans = pose_data["translation"]
            center_pos = np.array(
                [trans["x"], trans["y"], trans["z"]], dtype=np.float32
            )

            # Extract quaternion rotation and convert to rotation matrix
            quat = pose_data["rotation"]["quaternion"]
            # Quaternion format: W, X, Y, Z
            q_w, q_x, q_y, q_z = quat["W"], quat["X"], quat["Y"], quat["Z"]

            # Convert quaternion to rotation matrix
            # https://en.wikipedia.org/wiki/Rotation_matrix#Quaternion
            rotation_matrix = np.array(
                [
                    [
                        1 - 2 * (q_y**2 + q_z**2),
                        2 * (q_x * q_y - q_w * q_z),
                        2 * (q_x * q_z + q_w * q_y),
                    ],
                    [
                        2 * (q_x * q_y + q_w * q_z),
                        1 - 2 * (q_x**2 + q_z**2),
                        2 * (q_y * q_z - q_w * q_x),
                    ],
                    [
                        2 * (q_x * q_z - q_w * q_y),
                        2 * (q_y * q_z + q_w * q_x),
                        1 - 2 * (q_x**2 + q_y**2),
                    ],
                ],
                dtype=np.float32,
            )

            field_layout[tag_id] = {"center": center_pos, "rotation": rotation_matrix}

        return field_layout

    def process_frame(self, frame, cam_matrix, dist_coeffs=None):
        """
        Processes a single frame to find AprilTags and estimate their pose using OpenCV.

        Args:
            frame (np.ndarray): The input image frame from the camera.
            cam_matrix (np.ndarray): The 3x3 camera intrinsic matrix.
            dist_coeffs (np.ndarray, optional): Camera distortion coefficients. Defaults to zero distortion.

        Returns:
            dict: {"single_tags": [...], "multi_tag": {...} or None}
        """
        # Default to zero distortion if not provided
        if dist_coeffs is None:
            dist_coeffs = np.zeros((4, 1), dtype=np.float32)

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

        # Filter detections based on quality
        valid_detections = []
        for tag in detections:
            if (
                tag.getHamming() <= 1
                and tag.getDecisionMargin() >= self.decision_margin_threshold
            ):
                valid_detections.append(tag)

        # --- Single Tag Processing ---
        single_tag_results = []
        for tag in valid_detections:
            # Get the corners for the image points
            img_points = np.array(
                [
                    [tag.getCorner(0).x, tag.getCorner(0).y],
                    [tag.getCorner(1).x, tag.getCorner(1).y],
                    [tag.getCorner(2).x, tag.getCorner(2).y],
                    [tag.getCorner(3).x, tag.getCorner(3).y],
                ],
                dtype=np.float32,
            )

            # --- Pose Estimation using OpenCV solvePnP with IPPE method ---
            success, rvec, tvec = cv2.solvePnP(
                self.single_tag_obj_points,
                img_points,
                cam_matrix,
                dist_coeffs,
                flags=cv2.SOLVEPNP_IPPE,
            )

            if not success:
                continue

            # Calculate reprojection error
            projected_points, _ = cv2.projectPoints(
                self.single_tag_obj_points, rvec, tvec, cam_matrix, dist_coeffs
            )
            pose_error = np.mean(
                np.linalg.norm(img_points - projected_points.reshape(-1, 2), axis=1)
            )

            # Convert rvec/tvec to FRC coordinate system
            # OpenCV: X=right, Y=down, Z=forward
            # FRC: X=forward, Y=left, Z=up
            # Transformation: FRC_X = OpenCV_Z, FRC_Y = -OpenCV_X, FRC_Z = -OpenCV_Y
            tvec_frc = np.array([tvec[2, 0], -tvec[0, 0], -tvec[1, 0]])

            # Convert rotation vector to rotation matrix
            rmat_opencv, _ = cv2.Rodrigues(rvec)

            # Transform rotation matrix to FRC coordinates
            # Rotation matrix to swap axes: OpenCV -> FRC
            transform_matrix = np.array(
                [
                    [0, 0, 1],  # FRC X = OpenCV Z
                    [-1, 0, 0],  # FRC Y = -OpenCV X
                    [0, -1, 0],  # FRC Z = -OpenCV Y
                ],
                dtype=np.float32,
            )
            rmat_frc = transform_matrix @ rmat_opencv @ transform_matrix.T

            # Convert FRC rotation matrix to Euler angles (Roll, Pitch, Yaw)
            # Using convention: Yaw (Z) -> Pitch (Y) -> Roll (X)
            # https://en.wikipedia.org/wiki/Conversion_between_quaternions_and_Euler_angles
            pitch_rad = np.arcsin(-rmat_frc[2, 0])
            if np.cos(pitch_rad) > 1e-6:
                yaw_rad = np.arctan2(rmat_frc[1, 0], rmat_frc[0, 0])
                roll_rad = np.arctan2(rmat_frc[2, 1], rmat_frc[2, 2])
            else:
                # Gimbal lock case
                yaw_rad = np.arctan2(-rmat_frc[0, 1], rmat_frc[1, 1])
                roll_rad = 0

            single_tag_results.append(
                {
                    "ui_data": {
                        "id": tag.getId(),
                        "decision_margin": tag.getDecisionMargin(),
                        "pose_error": pose_error,
                        "x_m": tvec_frc[0],
                        "y_m": tvec_frc[1],
                        "z_m": tvec_frc[2],
                        "yaw_rad": yaw_rad,
                        "pitch_rad": pitch_rad,
                        "roll_rad": roll_rad,
                        "yaw_deg": math.degrees(yaw_rad),
                        "pitch_deg": math.degrees(pitch_rad),
                        "roll_deg": math.degrees(roll_rad),
                    },
                    "drawing_data": {
                        "rvec": rvec,
                        "tvec": tvec,
                        "corners": img_points,
                        "id": tag.getId(),
                    },
                }
            )

        # --- Multi-Tag Processing ---
        multi_tag_result = None
        if (
            self.multi_tag_enabled
            and self.field_layout_data is not None
            and len(valid_detections) > 1
        ):
            try:
                # Build 3D object points and 2D image points for all detected tags
                obj_points_list = []
                img_points_list = []

                for tag in valid_detections:
                    tag_id = tag.getId()
                    if tag_id not in self.field_layout_data:
                        continue

                    # Get tag pose from field layout
                    tag_info = self.field_layout_data[tag_id]
                    tag_center = tag_info["center"]
                    tag_rotation = tag_info["rotation"]

                    # Calculate 3D positions of tag corners in field coordinates
                    # Tag corners in tag-local coordinates
                    half_size = self.tag_size_m / 2.0
                    tag_corners_local = np.array(
                        [
                            [-half_size, -half_size, 0],
                            [half_size, -half_size, 0],
                            [half_size, half_size, 0],
                            [-half_size, half_size, 0],
                        ],
                        dtype=np.float32,
                    )

                    # Transform to field coordinates
                    tag_corners_field = (
                        tag_rotation @ tag_corners_local.T
                    ).T + tag_center

                    # Get 2D image points
                    img_corners = np.array(
                        [
                            [tag.getCorner(0).x, tag.getCorner(0).y],
                            [tag.getCorner(1).x, tag.getCorner(1).y],
                            [tag.getCorner(2).x, tag.getCorner(2).y],
                            [tag.getCorner(3).x, tag.getCorner(3).y],
                        ],
                        dtype=np.float32,
                    )

                    obj_points_list.append(tag_corners_field)
                    img_points_list.append(img_corners)

                if len(obj_points_list) >= 2:
                    # Concatenate all points
                    obj_points_multi = np.vstack(obj_points_list)
                    img_points_multi = np.vstack(img_points_list)

                    # Use SQPNP for multi-tag pose estimation
                    success, rvec_multi, tvec_multi = cv2.solvePnP(
                        obj_points_multi,
                        img_points_multi,
                        cam_matrix,
                        dist_coeffs,
                        flags=cv2.SOLVEPNP_SQPNP,
                    )

                    if success:
                        # Calculate reprojection error
                        projected_multi, _ = cv2.projectPoints(
                            obj_points_multi,
                            rvec_multi,
                            tvec_multi,
                            cam_matrix,
                            dist_coeffs,
                        )
                        multi_error = np.mean(
                            np.linalg.norm(
                                img_points_multi - projected_multi.reshape(-1, 2),
                                axis=1,
                            )
                        )

                        # Convert to FRC coordinate system
                        tvec_multi_frc = np.array(
                            [tvec_multi[2, 0], -tvec_multi[0, 0], -tvec_multi[1, 0]]
                        )

                        # Convert rotation matrix to FRC coordinates
                        rmat_multi_opencv, _ = cv2.Rodrigues(rvec_multi)
                        transform_matrix = np.array(
                            [[0, 0, 1], [-1, 0, 0], [0, -1, 0]], dtype=np.float32
                        )
                        rmat_multi_frc = (
                            transform_matrix @ rmat_multi_opencv @ transform_matrix.T
                        )

                        # Convert to Euler angles
                        multi_pitch_rad = np.arcsin(-rmat_multi_frc[2, 0])
                        if np.cos(multi_pitch_rad) > 1e-6:
                            multi_yaw_rad = np.arctan2(
                                rmat_multi_frc[1, 0], rmat_multi_frc[0, 0]
                            )
                            multi_roll_rad = np.arctan2(
                                rmat_multi_frc[2, 1], rmat_multi_frc[2, 2]
                            )
                        else:
                            multi_yaw_rad = np.arctan2(
                                -rmat_multi_frc[0, 1], rmat_multi_frc[1, 1]
                            )
                            multi_roll_rad = 0

                        multi_tag_result = {
                            "pose_error": multi_error,
                            "x_m": tvec_multi_frc[0],
                            "y_m": tvec_multi_frc[1],
                            "z_m": tvec_multi_frc[2],
                            "roll_rad": multi_roll_rad,
                            "pitch_rad": multi_pitch_rad,
                            "yaw_rad": multi_yaw_rad,
                            "roll_deg": math.degrees(multi_roll_rad),
                            "pitch_deg": math.degrees(multi_pitch_rad),
                            "yaw_deg": math.degrees(multi_yaw_rad),
                            "num_tags": len(obj_points_list),
                        }
            except Exception as e:
                print(f"Multi-tag estimation failed: {e}")

        # Return both single and multi-tag results
        return {"single_tags": single_tag_results, "multi_tag": multi_tag_result}
