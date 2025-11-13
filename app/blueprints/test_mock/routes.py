"""
Mock endpoints for E2E testing
Only enabled when E2E_TESTING environment variable is set
"""
import base64
import os

try:
    import cv2  # type: ignore
except ModuleNotFoundError:  # pragma: no cover - OpenCV may not be installed in tests
    cv2 = None  # type: ignore

import numpy as np
from flask import jsonify, Response
from . import test_mock


def is_e2e_testing():
    """Check if E2E testing mode is enabled"""
    return os.getenv("E2E_TESTING", "false").lower() == "true"


@test_mock.route("/mock-cameras")
def mock_cameras():
    """Returns a list of mock camera devices for testing"""
    if not is_e2e_testing():
        return jsonify({"error": "Test endpoints only available in E2E testing mode"}), 403

    mock_devices = [
        {
            "type": "USB",
            "identifier": "test_usb_0",
            "name": "Mock USB Camera",
            "device_info": {"index": 0, "backend": "mock"},
        },
        {
            "type": "USB",
            "identifier": "test_usb_1",
            "name": "Mock USB Camera 2",
            "device_info": {"index": 1, "backend": "mock"},
        },
        {
            "type": "GenICam",
            "identifier": "test_genicam_12345",
            "name": "Mock GenICam Camera",
            "device_info": {"serial": "12345", "model": "MockCam", "vendor": "Test"},
        },
    ]

    return jsonify(mock_devices)


@test_mock.route("/mock-video-feed/<camera_id>")
def mock_video_feed(camera_id):
    """Generates a mock video feed with test patterns"""
    if not is_e2e_testing():
        return jsonify({"error": "Test endpoints only available in E2E testing mode"}), 403

    def generate_frames():
        """Generate test pattern frames"""
        if cv2 is None:
            import time

            while True:
                yield (
                    b"--frame\r\n"
                    b"Content-Type: image/jpeg\r\n\r\n" + _PLACEHOLDER_JPEG + b"\r\n"
                )
                time.sleep(0.1)

        frame_count = 0
        while True:
            # Create a test pattern image
            img = np.zeros((480, 640, 3), dtype=np.uint8)

            # Add colored rectangles
            cv2.rectangle(img, (50, 50), (250, 200), (255, 0, 0), -1)  # Blue
            cv2.rectangle(img, (300, 100), (500, 250), (0, 255, 0), -1)  # Green
            cv2.rectangle(img, (150, 300), (350, 430), (0, 0, 255), -1)  # Red

            # Add frame counter
            text = f"Frame: {frame_count} | Camera: {camera_id}"
            cv2.putText(
                img, text, (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2
            )

            # Encode as JPEG
            ret, jpeg = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, 85])
            if not ret:
                continue

            frame_count += 1

            # Yield frame in multipart format
            yield (
                b"--frame\r\n"
                b"Content-Type: image/jpeg\r\n\r\n" + jpeg.tobytes() + b"\r\n"
            )

            # Simulate ~30 FPS
            import time

            time.sleep(0.033)

    return Response(
        generate_frames(), mimetype="multipart/x-mixed-replace; boundary=frame"
    )


@test_mock.route("/reset-database", methods=["POST"])
def reset_database():
    """Resets the test database to a clean state"""
    if not is_e2e_testing():
        return jsonify({"error": "Test endpoints only available in E2E testing mode"}), 403

    from app.extensions import db
    from app.models import Camera, Pipeline, Setting

    try:
        # Delete all records
        db.session.query(Pipeline).delete()
        db.session.query(Camera).delete()
        db.session.query(Setting).delete()
        db.session.commit()

        return jsonify({"status": "success", "message": "Database reset complete"})
    except Exception as e:
        db.session.rollback()
        return (
            jsonify({"status": "error", "message": str(e)}),
            500,
        )


@test_mock.route("/seed-test-data", methods=["POST"])
def seed_test_data():
    """Seeds the database with test data for E2E tests"""
    if not is_e2e_testing():
        return jsonify({"error": "Test endpoints only available in E2E testing mode"}), 403

    from app.extensions import db
    from app.models import Camera, Pipeline, Setting

    try:
        # Create test cameras
        camera1 = Camera(
            name="Test Camera 1",
            identifier="test_cam_1",
            camera_type="USB",
            device_info_json='{"index": 0}',
        )
        camera2 = Camera(
            name="Test Camera 2",
            identifier="test_cam_2",
            camera_type="USB",
            device_info_json='{"index": 1}',
        )

        db.session.add(camera1)
        db.session.add(camera2)
        db.session.commit()

        # Create test pipeline
        pipeline = Pipeline(
            name="Test AprilTag Pipeline",
            camera_id=camera1.id,
            pipeline_type="AprilTag",
            config_json='{"tag_family": "tag36h11", "threads": 1}',
        )

        db.session.add(pipeline)
        db.session.commit()

        return jsonify(
            {
                "status": "success",
                "message": "Test data seeded",
                "data": {
                    "cameras": [
                        {"id": camera1.id, "name": camera1.name},
                        {"id": camera2.id, "name": camera2.name},
                    ],
                    "pipelines": [{"id": pipeline.id, "name": pipeline.name}],
                },
            }
        )
    except Exception as e:
        db.session.rollback()
        return jsonify({"status": "error", "message": str(e)}), 500


@test_mock.route("/health")
def health():
    """Health check endpoint for E2E tests"""
    return jsonify({"status": "healthy", "e2e_testing": is_e2e_testing()})
_PLACEHOLDER_JPEG = base64.b64decode(
    b'/9j/4AAQSkZJRgABAQEASABIAAD/2wBDABALDA4MChALDg8QEA8QEhASFBcVHRodGR4jLCIjIiYqKSoqKiwtNDY2NjY2ODg4ODg4ODg4ODg4ODg4ODj/2wBDAQQQEhUSEhYVFRYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFj/wAARCAAQABADASIAAhEBAxEB/8QAFQABAQAAAAAAAAAAAAAAAAAAAAf/xAAUEAEAAAAAAAAAAAAAAAAAAAAA/8QAFQEBAQAAAAAAAAAAAAAAAAAAAgP/xAAUEQEAAAAAAAAAAAAAAAAAAAAA/9oADAMBAAIRAxEAPwCfAAf/Z'
)
