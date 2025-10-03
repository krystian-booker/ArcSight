import cv2
import numpy as np
import os
from app import db

class ObjectDetectionMLPipeline:
    """
    A pipeline for ML-based object detection using a pre-trained model.
    """

    def __init__(self, config):
        """
        Initializes the pipeline and loads the ML model and labels.

        Args:
            config (dict): A dictionary containing configuration options,
                           including 'model_filename' and 'labels_filename'.
        """
        self.config = config
        self.net = None
        self.classes = []
        self.data_dir = os.path.dirname(db.DB_PATH)

        model_filename = self.config.get('model_filename')
        labels_filename = self.config.get('labels_filename')

        if model_filename and labels_filename:
            model_path = os.path.join(self.data_dir, model_filename)
            labels_path = os.path.join(self.data_dir, labels_filename)

            if os.path.exists(model_path) and os.path.exists(labels_path):
                try:
                    self.net = cv2.dnn.readNet(model_path)
                    with open(labels_path, 'r') as f:
                        self.classes = [line.strip() for line in f.readlines()]
                    print("Object Detection (ML) pipeline initialized successfully.")
                except cv2.error as e:
                    print(f"Error loading model: {e}")
                    self.net = None # Ensure net is None on failure
            else:
                print("Model or labels file not found.")
        else:
            print("Object Detection (ML) pipeline initialized (placeholder - no model/labels).")

    def process_frame(self, frame, cam_matrix):
        """
        Processes a single frame to detect objects.

        Args:
            frame (np.ndarray): The input image frame from the camera.
            cam_matrix (np.ndarray): The 3x3 camera intrinsic matrix.

        Returns:
            list: A list of dictionaries, where each dictionary represents a detected object.
        """
        if self.net is None or not self.classes:
            return []

        (h, w) = frame.shape[:2]
        blob = cv2.dnn.blobFromImage(cv2.resize(frame, (300, 300)), 0.007843, (300, 300), 127.5)

        self.net.setInput(blob)
        detections = self.net.forward()

        results = []
        confidence_threshold = self.config.get('confidence_threshold', 0.5)
        target_classes = self.config.get('target_classes', [])

        for i in np.arange(0, detections.shape[2]):
            confidence = detections[0, 0, i, 2]

            if confidence > confidence_threshold:
                idx = int(detections[0, 0, i, 1])
                
                if target_classes and self.classes[idx] not in target_classes:
                    continue

                box = detections[0, 0, i, 3:7] * np.array([w, h, w, h])
                (startX, startY, endX, endY) = box.astype("int")
                
                results.append({
                    "label": self.classes[idx],
                    "confidence": float(confidence),
                    "box": [int(startX), int(startY), int(endX), int(endY)]
                })

        return results