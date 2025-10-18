import robotpy_apriltag
import cv2
import numpy as np
import math
import json
from wpimath.geometry import Transform3d, Pose3d, Rotation3d, Quaternion


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
        self.pose_iterations = config.get("pose_iterations", 40)

        # --- Multi-tag Configuration ---
        self.multi_tag_enabled = config.get("multi_tag_enabled", False)
        self.field_layout = None

        # Load field layout if provided and multi-tag is enabled
        field_layout_json = config.get("field_layout", "")
        if self.multi_tag_enabled and field_layout_json:
            try:
                self.field_layout = self._load_field_layout(field_layout_json)
                print(
                    f"Loaded field layout with {len(self.field_layout.getTags())} tags"
                )
            except Exception as e:
                print(f"Failed to load field layout: {e}")
                self.multi_tag_enabled = False

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
            AprilTagFieldLayout: The loaded field layout
        """
        layout_data = json.loads(field_layout_json)

        # Create list of AprilTag objects with their 3D poses
        tags = []
        for tag_data in layout_data["tags"]:
            tag_id = tag_data["ID"]
            pose_data = tag_data["pose"]

            # Extract translation
            trans = pose_data["translation"]
            translation = (trans["x"], trans["y"], trans["z"])

            # Extract quaternion rotation
            quat = pose_data["rotation"]["quaternion"]
            rotation = Rotation3d(
                Quaternion(quat["W"], quat["X"], quat["Y"], quat["Z"])
            )

            # Create Pose3d for this tag
            pose = Pose3d(*translation, rotation)

            # Create AprilTag with ID and pose
            tag = robotpy_apriltag.AprilTag()
            tag.ID = tag_id
            tag.pose = pose
            tags.append(tag)

        # Create field layout
        field_length = layout_data["field"]["length"]
        field_width = layout_data["field"]["width"]

        return robotpy_apriltag.AprilTagFieldLayout(tags, field_length, field_width)

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

        # --- Single Tag Processing ---
        single_tag_results = []
        for tag in detections:
            # Reject tags with high hamming distance or low decision margin
            if (
                tag.getHamming() > 1
                or tag.getDecisionMargin() < self.decision_margin_threshold
            ):
                continue

            # --- Pose Estimation ---
            # Use estimateOrthogonalIteration to get the AprilTagPoseEstimate object
            est_result = self.pose_estimator.estimateOrthogonalIteration(
                tag, self.pose_iterations
            )

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

            # --- Data for UI Table (FRC standard coordinate system) ---
            # FRC coordinate system:
            # X: forward/back (positive = forward)
            # Y: left/right (positive = left)
            # Z: up/down (positive = up)
            # WPILib's Transform3d already uses this standard, so use values directly
            x_ui = pose.X()
            y_ui = pose.Y()
            z_ui = pose.Z()

            # FRC rotation conventions (Roll, Pitch, Yaw):
            # Roll: rotation around X axis (forward/back)
            # Pitch: rotation around Y axis (left/right)
            # Yaw: rotation around Z axis (up/down)
            # WPILib's Rotation3d: X()=Roll, Y()=Pitch, Z()=Yaw in radians
            pose_rotation = pose.rotation()
            roll_rad = pose_rotation.X()
            pitch_rad = pose_rotation.Y()
            yaw_rad = pose_rotation.Z()

            # Convert radians to degrees for the UI
            roll_deg = math.degrees(roll_rad)
            pitch_deg = math.degrees(pitch_rad)
            yaw_deg = math.degrees(yaw_rad)

            single_tag_results.append(
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

        # --- Multi-Tag Processing ---
        multi_tag_result = None
        if (
            self.multi_tag_enabled
            and self.field_layout is not None
            and len(detections) > 1
        ):
            try:
                # Use multiple tags simultaneously for better pose estimation
                multi_tag_estimate = self.pose_estimator.estimateMultiTag(
                    detections, self.field_layout, self.pose_iterations
                )

                # Extract pose from multi-tag result
                multi_pose = multi_tag_estimate.pose1
                multi_error = multi_tag_estimate.error1

                # Extract coordinates and rotation (FRC standard)
                multi_x = multi_pose.X()
                multi_y = multi_pose.Y()
                multi_z = multi_pose.Z()

                multi_rotation = multi_pose.rotation()
                multi_roll = multi_rotation.X()
                multi_pitch = multi_rotation.Y()
                multi_yaw = multi_rotation.Z()

                multi_tag_result = {
                    "pose_error": multi_error,
                    "x_m": multi_x,
                    "y_m": multi_y,
                    "z_m": multi_z,
                    "roll_rad": multi_roll,
                    "pitch_rad": multi_pitch,
                    "yaw_rad": multi_yaw,
                    "roll_deg": math.degrees(multi_roll),
                    "pitch_deg": math.degrees(multi_pitch),
                    "yaw_deg": math.degrees(multi_yaw),
                    "num_tags": len(detections),
                }
            except Exception as e:
                print(f"Multi-tag estimation failed: {e}")

        # Return both single and multi-tag results
        return {"single_tags": single_tag_results, "multi_tag": multi_tag_result}
