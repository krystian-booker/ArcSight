from flask import render_template, Response
from app import db, camera_manager, camera_stream
import cv2
import numpy as np
from . import dashboard

def create_error_image(message, width=640, height=480):
    """Creates a black image with white text for error display."""
    img = np.zeros((height, width, 3), np.uint8)
    font = cv2.FONT_HERSHEY_SIMPLEX
    text_size = cv2.getTextSize(message, font, 1, 2)[0]
    text_x = (width - text_size[0]) // 2
    text_y = (height + text_size[1]) // 2
    cv2.putText(img, message, (text_x, text_y), font, 1, (255, 255, 255), 2)
    ret, jpeg = cv2.imencode('.jpg', img)
    return jpeg.tobytes()


@dashboard.route('/')
def dashboard_page():
    """Renders the main dashboard."""
    cameras = db.get_cameras()
    return render_template('index.html', cameras=cameras)


@dashboard.route('/video_feed/<int:camera_id>')
def video_feed(camera_id):
    """Streams the video feed for a given camera."""
    camera = db.get_camera(camera_id)
    if not camera:
        return "Camera not found", 404

    if not camera_manager.is_camera_thread_running(camera['identifier']):
        error_img = create_error_image("Camera not connected")
        return Response(error_img, mimetype='image/jpeg')

    return Response(camera_stream.get_camera_feed(dict(camera)),
                    mimetype='multipart/x-mixed-replace; boundary=frame')


@dashboard.route('/processed_video_feed/<int:pipeline_id>')
def processed_video_feed(pipeline_id):
    """Streams the processed video feed for a given pipeline."""
    pipeline = db.get_pipeline(pipeline_id)
    if not pipeline:
        error_img = create_error_image("Pipeline not found")
        return Response(error_img, mimetype='image/jpeg', status=404)

    return Response(camera_stream.get_processed_camera_feed(pipeline_id),
                    mimetype='multipart/x-mixed-replace; boundary=frame')