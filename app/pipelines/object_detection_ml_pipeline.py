class ObjectDetectionMLPipeline:
    """
    A placeholder pipeline for ML-based object detection.
    This class is intended to allow the UI to save and load configurations
    without requiring a full implementation of the vision processing logic.
    """

    def __init__(self, config):
        """
        Initializes the pipeline.

        Args:
            config (dict): A dictionary containing configuration options.
        """
        self.config = config
        print("Object Detection (ML) pipeline initialized (placeholder).")

    def process_frame(self, frame, cam_matrix):
        """
        Processes a single frame. This is a placeholder and does no actual processing.

        Args:
            frame (np.ndarray): The input image frame from the camera.
            cam_matrix (np.ndarray): The 3x3 camera intrinsic matrix.

        Returns:
            list: An empty list, as no processing is performed.
        """
        return []