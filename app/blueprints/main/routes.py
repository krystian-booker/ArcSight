from flask import render_template, request, redirect, url_for, jsonify, Response, send_file, current_app, make_response
from app import db, camera_utils, network_utils
from app.calibration_utils import generate_chessboard_pdf, generate_charuco_board_pdf
import cv2
import io
import numpy as np
import os
import shutil
import time
from . import main

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


@main.route('/')
def dashboard():
    """Renders the main dashboard."""
    cameras = db.get_cameras()
    return render_template('index.html', cameras=cameras)


@main.route('/video_feed/<int:camera_id>')
def video_feed(camera_id):
    """Streams the video feed for a given camera."""
    camera = db.get_camera(camera_id)
    if not camera:
        return "Camera not found", 404

    if not camera_utils.check_camera_connection(dict(camera)):
        error_img = create_error_image("Camera not connected")
        return Response(error_img, mimetype='image/jpeg')

    return Response(camera_utils.get_camera_feed(dict(camera)),
                    mimetype='multipart/x-mixed-replace; boundary=frame')


@main.route('/processed_video_feed/<int:pipeline_id>')
def processed_video_feed(pipeline_id):
    """Streams the processed video feed for a given pipeline."""
    pipeline = db.get_pipeline(pipeline_id)
    if not pipeline:
        error_img = create_error_image("Pipeline not found")
        return Response(error_img, mimetype='image/jpeg', status=404)

    return Response(camera_utils.get_processed_camera_feed(pipeline_id),
                    mimetype='multipart/x-mixed-replace; boundary=frame')


@main.route('/cameras')
def cameras():
    """Renders the camera management page."""
    cameras = db.get_cameras()
    genicam_cti_path = db.get_setting('genicam_cti_path')
    return render_template('cameras.html', cameras=cameras, genicam_enabled=bool(genicam_cti_path))


@main.route('/calibration')
def calibration():
    """Renders the camera calibration page."""
    cameras = db.get_cameras()
    return render_template('calibration.html', cameras=cameras)


@main.route('/calibration/generate_pattern')
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


@main.route('/calibration/generate_charuco_pattern')
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


@main.route('/calibration/start', methods=['POST'])
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


@main.route('/calibration/capture', methods=['POST'])
def calibration_capture():
    """Captures a frame for calibration."""
    data = request.get_json()
    camera_id = data.get('camera_id')
    if not camera_id:
        return jsonify({'success': False, 'error': 'Camera ID is required.'}), 400

    camera = db.get_camera(int(camera_id))
    if not camera:
        return jsonify({'success': False, 'error': 'Camera not found.'}), 404

    frame = camera_utils.get_latest_raw_frame(camera['identifier'])
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


@main.route('/calibration/calculate', methods=['POST'])
def calibration_calculate():
    """Calculates the camera intrinsics."""
    data = request.get_json()
    camera_id = data.get('camera_id')
    if not camera_id:
        return jsonify({'success': False, 'error': 'Camera ID is required.'}), 400

    results = current_app.calibration_manager.calculate_calibration(int(camera_id))
    return jsonify(results)


@main.route('/calibration/save', methods=['POST'])
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
        camera_utils.stop_camera_thread(camera['identifier'])
        camera_utils.start_camera_thread(dict(camera), current_app._get_current_object())

    return jsonify({'success': True})


@main.route('/calibration_feed/<int:camera_id>')
def calibration_feed(camera_id):
    """Streams the standard video feed for a given camera, used on the calibration page."""
    camera = db.get_camera(camera_id)
    if not camera:
        return "Camera not found", 404

    if not camera_utils.check_camera_connection(dict(camera)):
        error_img = create_error_image("Camera not connected")
        return Response(error_img, mimetype='image/jpeg')

    return Response(camera_utils.get_camera_feed(dict(camera)),
                    mimetype='multipart/x-mixed-replace; boundary=frame')


@main.route('/settings')
def settings():
    """Renders the application settings page."""
    all_settings = {
        'genicam_cti_path': db.get_setting('genicam_cti_path'),
        'team_number': db.get_setting('team_number'),
        'ip_mode': db.get_setting('ip_mode'),
        'hostname': db.get_setting('hostname'),
    }
    current_network_settings = network_utils.get_network_settings()
    current_hostname = network_utils.get_hostname()
    return render_template('settings.html', 
                           settings=all_settings, 
                           current_network_settings=current_network_settings, 
                           current_hostname=current_hostname)


@main.route('/settings/global/update', methods=['POST'])
def update_global_settings():
    """Updates global application settings."""
    db.update_setting('team_number', request.form.get('team_number'))
    db.update_setting('ip_mode', request.form.get('ip_mode'))
    db.update_setting('hostname', request.form.get('hostname'))
    return redirect(url_for('main.settings'))


@main.route('/cameras/add', methods=['POST'])
def add_camera():
    """Adds a new camera."""
    name = request.form.get('camera-name')
    camera_type = request.form.get('camera-type')
    
    if camera_type == 'USB':
        identifier = request.form.get('usb-camera-select')
    elif camera_type == 'GenICam':
        identifier = request.form.get('genicam-camera-select')
    else:
        return redirect(url_for('main.cameras'))

    if name and camera_type and identifier:
        db.add_camera(name, camera_type, identifier)
        new_camera = db.get_camera_by_identifier(identifier)
        if new_camera:
            camera_utils.start_camera_thread(dict(new_camera), current_app._get_current_object())

    return redirect(url_for('main.cameras'))


@main.route('/cameras/update/<int:camera_id>', methods=['POST'])
def update_camera(camera_id):
    """Updates a camera's settings."""
    name = request.form.get('camera-name')
    if name:
        db.update_camera(camera_id, name)
    return redirect(url_for('main.cameras'))


@main.route('/cameras/delete/<int:camera_id>', methods=['POST'])
def delete_camera(camera_id):
    """Deletes a camera."""
    camera = db.get_camera(camera_id)
    if camera:
        camera_utils.stop_camera_thread(camera['identifier'])
    db.delete_camera(camera_id)
    return redirect(url_for('main.cameras'))


@main.route('/api/cameras/<int:camera_id>/pipelines', methods=['GET'])
def get_pipelines(camera_id):
    """Returns all pipelines for a given camera."""
    pipelines = db.get_pipelines(camera_id)
    return jsonify([dict(row) for row in pipelines])


@main.route('/api/cameras/<int:camera_id>/pipelines', methods=['POST'])
def add_pipeline(camera_id):
    """Adds a new pipeline to a camera."""
    data = request.get_json()
    name = data.get('name')
    pipeline_type = data.get('pipeline_type')

    if not name or not pipeline_type:
        return jsonify({'error': 'Name and pipeline_type are required'}), 400

    db.add_pipeline(camera_id, name, pipeline_type)
    new_pipeline = None
    pipelines = db.get_pipelines(camera_id)
    for pipeline in pipelines:
        if pipeline['name'] == name and pipeline['pipeline_type'] == pipeline_type:
            new_pipeline = pipeline
            break
    
    if new_pipeline:
        camera_utils.add_pipeline_to_camera(camera_id, dict(new_pipeline), current_app._get_current_object())
        return jsonify({'success': True, 'pipeline_id': new_pipeline['id']})
    
    return jsonify({'error': 'Failed to retrieve new pipeline'}), 500


@main.route('/api/pipelines/<int:pipeline_id>', methods=['PUT'])
def update_pipeline(pipeline_id):
    """Updates a pipeline's settings."""
    data = request.get_json()
    name = data.get('name')
    pipeline_type = data.get('pipeline_type')

    if not name or not pipeline_type:
        return jsonify({'error': 'Name and pipeline_type are required'}), 400

    db.update_pipeline(pipeline_id, name, pipeline_type)
    return jsonify({'success': True})


@main.route('/api/pipelines/<int:pipeline_id>', methods=['DELETE'])
def delete_pipeline(pipeline_id):
    """Deletes a pipeline."""
    pipeline = db.get_pipeline(pipeline_id)
    if pipeline:
        camera_id = pipeline['camera_id']
        camera_utils.remove_pipeline_from_camera(camera_id, pipeline_id, current_app._get_current_object())
        db.delete_pipeline(pipeline_id)
        return jsonify({'success': True})
    return jsonify({'error': 'Pipeline not found'}), 404


@main.route('/api/cameras/results/<int:camera_id>')
def get_camera_results(camera_id):
    """Returns the latest results from all pipelines for a given camera."""
    camera = db.get_camera(camera_id)
    if not camera:
        return jsonify({'error': 'Camera not found'}), 404
    
    results = camera_utils.get_camera_pipeline_results(camera['identifier'])
    if results is None:
        return jsonify({'error': 'Camera thread not running or no results available'}), 404
        
    string_key_results = {str(k): v for k, v in results.items()}
    return jsonify(string_key_results)


@main.route('/config/genicam/update', methods=['POST'])
def update_genicam_settings():
    """Updates the GenICam CTI path."""
    path = request.form.get('genicam-cti-path', '').strip()

    if path and path.lower().endswith('.cti'):
        db.update_setting('genicam_cti_path', path)
    elif not path:
        db.clear_setting('genicam_cti_path')
    
    camera_utils.reinitialize_harvester()
    return redirect(url_for('main.settings'))


@main.route('/config/genicam/clear', methods=['POST'])
def clear_genicam_settings():
    """Clears the GenICam CTI path."""
    db.clear_setting('genicam_cti_path')
    camera_utils.reinitialize_harvester()
    return redirect(url_for('main.settings'))


@main.route('/api/cameras/discover')
def discover_cameras():
    """Discovers available USB and GenICam cameras."""
    existing_identifiers = request.args.get('existing', '').split(',')
    
    usb_cameras = camera_utils.list_usb_cameras()
    genicam_cameras = camera_utils.list_genicam_cameras()

    filtered_usb = [cam for cam in usb_cameras if cam['identifier'] not in existing_identifiers]
    filtered_genicam = [cam for cam in genicam_cameras if cam['identifier'] not in existing_identifiers]

    return jsonify({
        'usb': filtered_usb,
        'genicam': filtered_genicam
    })


@main.route('/api/cameras/status/<int:camera_id>')
def camera_status(camera_id):
    """Returns the connection status of a camera."""
    camera = db.get_camera(camera_id)
    if camera:
        is_connected = camera_utils.check_camera_connection(dict(camera))
        return jsonify({'connected': is_connected})
    return jsonify({'error': 'Camera not found'}), 404


@main.route('/api/cameras/controls/<int:camera_id>', methods=['GET'])
def get_camera_controls(camera_id):
    """Returns the control settings for a camera."""
    camera = db.get_camera(camera_id)
    if camera:
        return jsonify({
            'orientation': camera['orientation'],
            'exposure_mode': camera['exposure_mode'],
            'exposure_value': camera['exposure_value'],
            'gain_mode': camera['gain_mode'],
            'gain_value': camera['gain_value'],
        })
    return jsonify({'error': 'Camera not found'}), 404


@main.route('/api/cameras/update_controls/<int:camera_id>', methods=['POST'])
def update_camera_controls(camera_id):
    """Updates the control settings for a camera."""
    data = request.get_json()
    if not data:
        return jsonify({'error': 'Invalid JSON'}), 400

    required_fields = ['orientation', 'exposure_mode', 'exposure_value', 'gain_mode', 'gain_value']
    if not all(field in data for field in required_fields):
        return jsonify({'error': 'Missing one or more required fields'}), 400

    db.update_camera_controls(
        camera_id,
        data['orientation'],
        data['exposure_mode'],
        data['exposure_value'],
        data['gain_mode'],
        data['gain_value']
    )
    
    return jsonify({'success': True})


@main.route('/api/genicam/nodes/<int:camera_id>', methods=['GET'])
def genicam_nodes(camera_id):
    """Returns the node map for a GenICam camera."""
    camera = db.get_camera(camera_id)
    if not camera or camera['camera_type'] != 'GenICam':
        return jsonify({'error': 'Camera not found or not a GenICam device'}), 404

    nodes, error = camera_utils.get_genicam_node_map(camera['identifier'])
    if error:
        return jsonify({'error': error}), 500

    return jsonify({'nodes': nodes})


@main.route('/api/genicam/nodes/<int:camera_id>', methods=['POST'])
def update_genicam_node(camera_id):
    """Updates a node on a GenICam camera."""
    camera = db.get_camera(camera_id)
    if not camera or camera['camera_type'] != 'GenICam':
        return jsonify({'error': 'Camera not found or not a GenICam device'}), 404

    payload = request.get_json(silent=True) or {}
    node_name = payload.get('name')
    value = payload.get('value')

    success, message, status_code, updated_node = camera_utils.update_genicam_node(camera['identifier'], node_name, value)
    
    if success:
        return jsonify({
            'success': True, 
            'message': message or 'Node updated successfully.',
            'node': updated_node
        }), status_code
    
    return jsonify({'error': message or 'Failed to update node.'}), status_code


@main.route('/control/restart-app', methods=['POST'])
def restart_app():
    """Restarts the application."""
    print("Restarting application...")
    os._exit(0)
    return "Restarting...", 200


@main.route('/control/reboot', methods=['POST'])
def reboot_device():
    """Reboots the device."""
    print("Rebooting device...")
    os.system("sudo reboot")
    return "Rebooting...", 200


@main.route('/control/export-db')
def export_db():
    """Exports the application database."""
    return send_file(db.DB_PATH, as_attachment=True)


@main.route('/control/import-db', methods=['POST'])
def import_db():
    """Imports an application database."""
    if 'database' not in request.files:
        return redirect(url_for('main.settings'))
    
    file = request.files['database']
    if file.filename and file.filename.endswith('.db'):
        file.save(db.DB_PATH)
        
    return redirect(url_for('main.settings'))


@main.route('/control/factory-reset', methods=['POST'])
def factory_reset():
    """Resets the application to its factory settings."""
    db.factory_reset()
    camera_utils.reinitialize_harvester()
    return redirect(url_for('main.settings'))