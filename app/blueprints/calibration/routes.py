from flask import render_template, request, jsonify, Response, send_file, current_app, make_response
from app import db, camera_manager, camera_stream
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
    ret, jpeg = cv2.imencode('.jpg', img)
    return jpeg.tobytes()


@calibration.route('/')
def calibration_page():
    """Renders the camera calibration page."""
    cameras = db.get_cameras()
    return render_template('calibration.html', cameras=cameras)


@calibration.route('/generate_pattern')
def calibration_generate_pattern():
    """Generates and returns a downloadable chessboard pattern as a PDF."""
    try:
        rows = int(request.args.get('rows', 7))
        cols = int(request.args.get('cols', 10))
        square_size_mm = float(request.args.get('square_size', 20))
    except (ValueError, TypeError):
        return "Invalid parameters", 400

    try:
        buffer = io.BytesIO()
        generate_chessboard_pdf(buffer, rows, cols, square_size_mm)
        buffer.seek(0)
        
        response = make_response(buffer.getvalue())
        response.headers['Content-Type'] = 'application/pdf'
        response.headers['Content-Disposition'] = f'attachment; filename=chessboard_{cols+1}x{rows+1}_{square_size_mm}mm.pdf'
        return response

    except Exception as e:
        return str(e), 500


@calibration.route('/generate_charuco_pattern')
def calibration_generate_charuco_pattern():
    """Generates and returns a downloadable ChAruco board pattern as a PDF."""
    try:
        params = {
            'squares_x': int(request.args.get('squares_x')),
            'squares_y': int(request.args.get('squares_y')),
            'square_size': float(request.args.get('square_size')),
            'marker_size': float(request.args.get('marker_size')),
            'dictionary_name': request.args.get('dictionary_name')
        }
    except (ValueError, TypeError, KeyError):
        return "Invalid parameters", 400

    try:
        buffer = io.BytesIO()
        generate_charuco_board_pdf(buffer, params)
        buffer.seek(0)
        
        response = make_response(buffer.getvalue())
        response.headers['Content-Type'] = 'application/pdf'
        filename = f"charuco_{params['squares_x']}x{params['squares_y']}_{params['dictionary_name']}.pdf"
        response.headers['Content-Disposition'] = f'attachment; filename={filename}'
        return response

    except Exception as e:
        return str(e), 500


@calibration.route('/start', methods=['POST'])
def calibration_start():
    """Starts a new calibration session."""
    data = request.get_json()
    if not data:
        return jsonify({'success': False, 'error': 'Invalid request format.'}), 400

    camera_id = data.get('camera_id')
    pattern_type = data.get('pattern_type')
    pattern_params = data.get('pattern_params')

    if not all([camera_id, pattern_type, pattern_params]):
        return jsonify({'success': False, 'error': 'Missing required parameters.'}), 400

    try:
        current_app.calibration_manager.start_session(
            int(camera_id), 
            pattern_type, 
            pattern_params
        )
        return jsonify({'success': True})
    except (ValueError, KeyError, AttributeError) as e:
        return jsonify({'success': False, 'error': f'Invalid parameters for {pattern_type}: {e}'}), 400
    except Exception as e:
        return jsonify({'success': False, 'error': f'An unexpected error occurred: {e}'}), 500


@calibration.route('/capture', methods=['POST'])
def calibration_capture():
    """Captures a frame for calibration."""
    data = request.get_json()
    camera_id = data.get('camera_id')
    if not camera_id:
        return jsonify({'success': False, 'error': 'Camera ID is required.'}), 400

    camera = db.get_camera(int(camera_id))
    if not camera:
        return jsonify({'success': False, 'error': 'Camera not found.'}), 404

    frame = camera_stream.get_latest_raw_frame(camera['identifier'])
    if frame is None:
        return jsonify({'success': False, 'error': 'Could not get frame from camera.'}), 500

    success, message, _ = current_app.calibration_manager.capture_points(int(camera_id), frame)
    session = current_app.calibration_manager.get_session(int(camera_id))
    
    capture_count = 0
    if session:
        if session.get('pattern_type') == 'ChAruco':
            capture_count = len(session.get('all_charuco_corners', []))
        else:
            capture_count = len(session.get('img_points', []))


    return jsonify({'success': success, 'message': message, 'capture_count': capture_count})


@calibration.route('/calculate', methods=['POST'])
def calibration_calculate():
    """Calculates the camera intrinsics."""
    data = request.get_json()
    camera_id = data.get('camera_id')
    if not camera_id:
        return jsonify({'success': False, 'error': 'Camera ID is required.'}), 400

    results = current_app.calibration_manager.calculate_calibration(int(camera_id))
    return jsonify(results)


@calibration.route('/save', methods=['POST'])
def calibration_save():
    """Saves the calibration data."""
    data = request.get_json()
    camera_id = data.get('camera_id')
    matrix = data.get('camera_matrix')
    dist_coeffs = data.get('dist_coeffs')
    error = data.get('reprojection_error')

    if not all([camera_id, matrix, dist_coeffs, error]):
        return jsonify({'success': False, 'error': 'Missing required parameters.'}), 400

    db.update_camera_calibration(int(camera_id), matrix, dist_coeffs, float(error))
    
    # Restart the camera thread to apply the new calibration
    camera = db.get_camera(int(camera_id))
    if camera:
        camera_manager.stop_camera_thread(camera['identifier'])
        camera_manager.start_camera_thread(dict(camera), current_app._get_current_object())

    return jsonify({'success': True})


@calibration.route('/calibration_feed/<int:camera_id>')
def calibration_feed(camera_id):
    """Streams the standard video feed for a given camera, used on the calibration page."""
    camera = db.get_camera(camera_id)
    if not camera:
        return "Camera not found", 404

    if not camera_manager.is_camera_thread_running(camera['identifier']):
        error_img = create_error_image("Camera not connected")
        return Response(error_img, mimetype='image/jpeg')

    return Response(camera_stream.get_camera_feed(dict(camera)),
                    mimetype='multipart/x-mixed-replace; boundary=frame')