from flask import (
    render_template,
    request,
    jsonify,
    Response,
    current_app,
    make_response,
)
import json
from app.extensions import db
from app import camera_manager, camera_stream
from app.models import Camera
from app.calibration_utils import generate_chessboard_pdf, generate_charuco_board_pdf
import cv2
import io
import numpy as np
from . import calibration


def create_error_image(message, width=640, height=480):
    """Creates a black image with white text for error display."""
    img = np.zeros((height, width, 3), np.uint8)
    font = cv2.FONT_HERSHEY_SIMPLEX
    text_size = cv2.getTextSize(message, font, 1, 2)[0]
    text_x = (width - text_size[0]) // 2
    text_y = (height + text_size[1]) // 2
    cv2.putText(img, message, (text_x, text_y), font, 1, (255, 255, 255), 2)
    ret, jpeg = cv2.imencode(".jpg", img)
    return jpeg.tobytes()


# Calibration page is now served by the React app


@calibration.route("/generate_pattern")
def calibration_generate_pattern():
    """Generates and returns a downloadable chessboard pattern as a PDF."""
    try:
        # Accept parameters matching frontend naming
        inner_corners_height = int(request.args.get("inner_corners_height", 5))
        inner_corners_width = int(request.args.get("inner_corners_width", 7))
        square_size_mm = float(request.args.get("square_size_mm", 25))
    except (ValueError, TypeError):
        return jsonify({"error": "Invalid parameters"}), 400

    # Validate dimensions for A4 page (210mm x 297mm)
    board_width_mm = (inner_corners_width + 1) * square_size_mm
    board_height_mm = (inner_corners_height + 1) * square_size_mm

    if board_width_mm > 210 or board_height_mm > 297:
        return jsonify({
            "error": f"Pattern too large for A4 paper. "
                    f"Board size: {board_width_mm:.0f}mm x {board_height_mm:.0f}mm. "
                    f"Max for A4: 210mm x 297mm"
        }), 400

    # Validate minimum dimensions
    if inner_corners_width < 3 or inner_corners_height < 3:
        return jsonify({"error": "Minimum 3x3 inner corners required"}), 400

    if square_size_mm < 5 or square_size_mm > 50:
        return jsonify({"error": "Square size must be between 5mm and 50mm"}), 400

    try:
        buffer = io.BytesIO()
        # rows = inner_corners_height, cols = inner_corners_width
        generate_chessboard_pdf(buffer, inner_corners_height, inner_corners_width, square_size_mm)
        buffer.seek(0)

        response = make_response(buffer.getvalue())
        response.headers["Content-Type"] = "application/pdf"
        response.headers["Content-Disposition"] = (
            f"attachment; filename=chessboard_{inner_corners_width + 1}x{inner_corners_height + 1}_{square_size_mm}mm.pdf"
        )
        return response

    except Exception as e:
        return jsonify({"error": str(e)}), 500


@calibration.route("/generate_charuco_pattern")
def calibration_generate_charuco_pattern():
    """Generates and returns a downloadable ChAruco board pattern as a PDF."""
    try:
        # Accept parameters matching frontend naming
        inner_corners_width = int(request.args.get("inner_corners_width", 7))
        inner_corners_height = int(request.args.get("inner_corners_height", 5))
        square_size_mm = float(request.args.get("square_size_mm", 25))
        marker_dict = request.args.get("marker_dict", "DICT_6X6_250")
    except (ValueError, TypeError):
        return jsonify({"error": "Invalid parameters"}), 400

    # ChAruco boards need squares, not inner corners
    # squares = inner_corners + 1
    squares_x = inner_corners_width + 1
    squares_y = inner_corners_height + 1

    # Marker size is typically 75% of square size for good detection
    marker_size_mm = square_size_mm * 0.75

    # Validate dimensions for A4 page (210mm x 297mm)
    board_width_mm = squares_x * square_size_mm
    board_height_mm = squares_y * square_size_mm

    if board_width_mm > 210 or board_height_mm > 297:
        return jsonify({
            "error": f"ChAruco pattern too large for A4 paper. "
                    f"Board size: {board_width_mm:.0f}mm x {board_height_mm:.0f}mm. "
                    f"Max for A4: 210mm x 297mm"
        }), 400

    # Validate minimum dimensions
    if inner_corners_width < 3 or inner_corners_height < 3:
        return jsonify({"error": "Minimum 3x3 inner corners required"}), 400

    if square_size_mm < 5 or square_size_mm > 50:
        return jsonify({"error": "Square size must be between 5mm and 50mm"}), 400

    # Validate marker dict
    valid_dicts = ["DICT_4X4_50", "DICT_5X5_50", "DICT_6X6_250", "DICT_7X7_1000"]
    if marker_dict not in valid_dicts:
        return jsonify({"error": f"Invalid marker dictionary. Must be one of: {', '.join(valid_dicts)}"}), 400

    try:
        params = {
            "squares_x": squares_x,
            "squares_y": squares_y,
            "square_size": square_size_mm,
            "marker_size": marker_size_mm,
            "dictionary_name": marker_dict,
        }

        buffer = io.BytesIO()
        generate_charuco_board_pdf(buffer, params)
        buffer.seek(0)

        response = make_response(buffer.getvalue())
        response.headers["Content-Type"] = "application/pdf"
        filename = f"charuco_{squares_x}x{squares_y}_{marker_dict}.pdf"
        response.headers["Content-Disposition"] = f"attachment; filename={filename}"
        return response

    except Exception as e:
        return jsonify({"error": str(e)}), 500


@calibration.route("/start", methods=["POST"])
def calibration_start():
    """Starts a new calibration session."""
    data = request.get_json()
    if not data:
        return jsonify({"success": False, "error": "Invalid request format."}), 400

    camera_id = data.get("camera_id")
    pattern_type = data.get("pattern_type")
    pattern_params = data.get("pattern_params")

    if not all([camera_id, pattern_type, pattern_params]):
        return jsonify({"success": False, "error": "Missing required parameters."}), 400

    try:
        current_app.calibration_manager.start_session(
            int(camera_id), pattern_type, pattern_params
        )
        return jsonify({"success": True})
    except (ValueError, KeyError, AttributeError) as e:
        return jsonify(
            {"success": False, "error": f"Invalid parameters for {pattern_type}: {e}"}
        ), 400
    except Exception as e:
        return jsonify(
            {"success": False, "error": f"An unexpected error occurred: {e}"}
        ), 500


@calibration.route("/capture", methods=["POST"])
def calibration_capture():
    """Captures a frame for calibration."""
    data = request.get_json()
    camera_id = data.get("camera_id")
    if not camera_id:
        return jsonify({"success": False, "error": "Camera ID is required."}), 400

    camera = db.session.get(Camera, int(camera_id))
    if not camera:
        return jsonify({"success": False, "error": "Camera not found."}), 404

    frame = camera_stream.get_latest_raw_frame(camera.identifier)
    if frame is None:
        return jsonify(
            {"success": False, "error": "Could not get frame from camera."}
        ), 500

    success, message, _ = current_app.calibration_manager.capture_points(
        int(camera_id), frame
    )
    session = current_app.calibration_manager.get_session(int(camera_id))

    capture_count = 0
    if session:
        if session.get("pattern_type") == "ChAruco":
            capture_count = len(session.get("all_charuco_corners", []))
        else:
            capture_count = len(session.get("img_points", []))

    return jsonify(
        {"success": success, "message": message, "capture_count": capture_count}
    )


@calibration.route("/calculate", methods=["POST"])
def calibration_calculate():
    """Calculates the camera intrinsics."""
    data = request.get_json()
    camera_id = data.get("camera_id")
    if not camera_id:
        return jsonify({"success": False, "error": "Camera ID is required."}), 400

    results = current_app.calibration_manager.calculate_calibration(int(camera_id))
    return jsonify(results)


@calibration.route("/save", methods=["POST"])
def calibration_save():
    """Saves the calibration data."""
    data = request.get_json()
    camera_id = data.get("camera_id")
    matrix = data.get("camera_matrix")
    dist_coeffs = data.get("dist_coeffs")
    error = data.get("reprojection_error")

    if not all([camera_id, matrix, dist_coeffs, error is not None]):
        return jsonify({"success": False, "error": "Missing required parameters."}), 400

    camera = db.session.get(Camera, int(camera_id))
    if not camera:
        return jsonify({"success": False, "error": "Camera not found."}), 404
    camera.camera_matrix_json = json.dumps(matrix)
    camera.dist_coeffs_json = json.dumps(dist_coeffs)
    camera.reprojection_error = float(error)
    db.session.commit()

    # Restart the camera thread to apply the new calibration
    camera_manager.stop_camera_thread(camera.identifier)
    camera_manager.start_camera_thread(
        camera_manager.build_camera_thread_config(camera),
        current_app._get_current_object(),
    )

    return jsonify({"success": True})


@calibration.route("/calibration_feed/<int:camera_id>")
def calibration_feed(camera_id):
    """Streams the standard video feed for a given camera, used on the calibration page."""
    camera = db.session.get(Camera, camera_id)
    if not camera:
        return "Camera not found", 404

    if not camera_manager.is_camera_thread_running(camera.identifier):
        error_img = create_error_image("Camera not connected")
        return Response(error_img, mimetype="image/jpeg")

    return Response(
        camera_stream.get_camera_feed(camera),
        mimetype="multipart/x-mixed-replace; boundary=frame",
    )
