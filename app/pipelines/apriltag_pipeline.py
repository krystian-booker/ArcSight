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
        family = config.get('family', 'tag36h11')
        
        # Add the family to the detector. The second argument is error correction bits.
        self.detector.addFamily(family, config.get('error_correction', 3))

        # --- Pose Estimator Setup ---
        # Get tag size from config, default to 6.5 inches in meters
        tag_size_m = config.get('tag_size_m', 0.1651)

        # Pose Estimator requires camera intrinsics (fx, fy, cx, cy)
        # We will get these from camera_params in process_frame, so we create the estimator there.
        self.pose_estimator_config = robotpy_apriltag.AprilTagPoseEstimator.Config(
            tag_size_m,
            0, # fx - will be updated per frame
            0, # fy - will be updated per frame
            0, # cx - will be updated per frame
            0  # cy - will be updated per frame
        )
        self.pose_estimator = None

        # --- Reusable Buffers (for optimization) ---
        self.gray_frame = None

        print(f"AprilTag detector initialized with family: {family}")

    def process_frame(self, frame, camera_params):
        """
        Processes a single frame to find AprilTags and estimate their pose.

        Args:
            frame (np.ndarray): The input image frame from the camera.
            camera_params (dict): Dict with camera intrinsics {'fx': ..., 'fy': ..., 'cx': ..., 'cy': ...}.

        Returns:
            list: A list of dictionaries, where each dictionary represents a detected tag.
        """
        # --- Update Pose Estimator if needed ---
        # The pose estimator needs to be created with the correct camera intrinsics.
        if (self.pose_estimator is None or 
            self.pose_estimator_config.fx != camera_params['fx'] or
            self.pose_estimator_config.fy != camera_params['fy']):
            
            self.pose_estimator_config.fx = camera_params['fx']
            self.pose_estimator_config.fy = camera_params['fy']
            self.pose_estimator_config.cx = camera_params['cx']
            self.pose_estimator_config.cy = camera_params['cy']
            self.pose_estimator = robotpy_apriltag.AprilTagPoseEstimator(self.pose_estimator_config)

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
            # The estimate method returns a Transform3d object
            pose: Transform3d = self.pose_estimator.estimate(tag)

            # Extract translation and rotation
            translation = pose.translation()
            rotation = pose.rotation()

            # The RobotPy coordinate system is already in the FRC convention (X away, Y left, Z up from camera)
            # We will convert it to a more standard robotics view (X right, Y up, Z out of lens)
            # This matches what we had before.
            x = -translation.y
            y = -translation.z
            z = translation.x

            # Get Yaw, Pitch, Roll in degrees
            yaw = rotation.z_degrees
            pitch = rotation.y_degrees
            roll = rotation.x_degrees

            results.append({
                "id": tag.getId(),
                "decision_margin": tag.getDecisionMargin(),
                "hamming": tag.getHamming(),
                "x_m": x,
                "y_m": y,
                "z_m": z,
                "roll_deg": roll,
                "pitch_deg": pitch,
                "yaw_deg": yaw
            })
            
        return results