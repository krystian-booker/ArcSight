import apriltag
import cv2
import numpy as np
import math

class AprilTagPipeline:
    """
    A pipeline for detecting and estimating the pose of AprilTags.
    """
    def __init__(self, config):
        """
        Initializes the AprilTag detector with given configuration.

        Args:
            config (dict): A dictionary containing configuration for the detector,
                           e.g., {'family': 'tag36h11', 'nthreads': 2, ...}
        """
        # Extract detector options from the config dictionary
        detector_options = {
            'families': config.get('family', 'tag36h11'),
            'nthreads': config.get('threads', 2),
            'quad_decimate': config.get('decimate', 1.0),
            'quad_blur': config.get('blur', 0.0),
            'refine_edges': config.get('refine_edges', True),
            'decode_sharpening': 0.25
        }
        
        # Store other pipeline-specific settings
        self.tag_size_m = config.get('tag_size_m', 0.165) # Default to 6.5 inches in meters

        # Create the detector
        self.detector = apriltag.AprilTagDetector(**detector_options)
        print(f"AprilTag detector initialized with families: {detector_options['families']}")

    def process_frame(self, frame, camera_params):
        """
        Processes a single frame to find AprilTags and estimate their pose.

        Args:
            frame (np.ndarray): The input image frame from the camera.
            camera_params (dict): A dictionary containing camera intrinsic properties,
                                  e.g., {'fx': ..., 'fy': ..., 'cx': ..., 'cy': ...}.

        Returns:
            list: A list of dictionaries, where each dictionary represents a detected tag.
        """
        # Convert frame to grayscale for the detector
        gray_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        
        # Detect tags
        detections = self.detector.detect(gray_frame)
        
        results = []
        for tag in detections:
            # Skip tags with high decision margin (low confidence)
            if tag.decision_margin < 35: # This value can be tuned
                continue

            # --- Pose Estimation ---
            # This requires the camera matrix and distortion coefficients.
            # For now, we assume no distortion.
            pose, e1, e2 = self.detector.detection_pose(
                tag,
                (camera_params['fx'], camera_params['fy'], camera_params['cx'], camera_params['cy']),
                tag_size=self.tag_size_m
            )
            
            # The pose is a 4x4 transformation matrix
            translation = pose[:3, 3] # Translation vector (x, y, z)
            rotation_matrix = pose[:3, :3]

            # FRC convention uses a different coordinate system:
            # X: to the right, Y: up, Z: coming out of the lens
            # AprilTag library uses:
            # X: to the right, Y: down, Z: pointing away from the camera
            x = translation[0]
            y = -translation[1] # Invert Y
            z = translation[2]

            # Calculate yaw (rotation around Y-axis)
            # This is a simplified calculation for Z-up, Y-down, X-right
            yaw = math.atan2(rotation_matrix[0, 2], rotation_matrix[2, 2])

            results.append({
                "id": tag.tag_id,
                "decision_margin": tag.decision_margin,
                "pose_error": e2,
                "x_m": x,
                "y_m": y,
                "z_m": z,
                "yaw_rad": yaw,
                "yaw_deg": math.degrees(yaw)
            })
            
        return results