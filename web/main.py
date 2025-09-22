from flask import Flask, render_template, request, redirect, url_for, jsonify, Response, send_file, g
import db
import camera_utils
import cv2
import numpy as np
import os
import shutil

app = Flask(__name__, template_folder='templates', static_folder='static')

@app.before_request
def before_request():
    """Create a database connection before each request."""
    g.db = db.get_db()

@app.teardown_appcontext
def teardown_db(exception):
    """Close the database connection after each request."""
    db_conn = g.pop('db', None)
    if db_conn is not None:
        db_conn.close()

@app.route('/')
def dashboard():
    cameras = db.get_cameras()
    return render_template('index.html', cameras=cameras)

def create_error_image(message, width=640, height=480):
    """Creates a black image with white text."""
    img = np.zeros((height, width, 3), np.uint8)
    font = cv2.FONT_HERSHEY_SIMPLEX
    
    # Calculate text size and position for centering
    text_size = cv2.getTextSize(message, font, 1, 2)[0]
    text_x = (width - text_size[0]) // 2
    text_y = (height + text_size[1]) // 2
    
    cv2.putText(img, message, (text_x, text_y), font, 1, (255, 255, 255), 2)
    
    ret, jpeg = cv2.imencode('.jpg', img)
    return jpeg.tobytes()

@app.route('/video_feed/<int:camera_id>')
def video_feed(camera_id):
    camera = db.get_camera(camera_id)
    if not camera:
        return "Camera not found", 404

    if not camera_utils.check_camera_connection(camera):
        error_img = create_error_image("Camera not connected")
        return Response(error_img, mimetype='image/jpeg')

    return Response(camera_utils.get_camera_feed(camera),
                    mimetype='multipart/x-mixed-replace; boundary=frame')

@app.route('/cameras')
def cameras():
    cameras = db.get_cameras()
    genicam_cti_path = db.get_setting('genicam_cti_path')
    return render_template('cameras.html', cameras=cameras, genicam_enabled=bool(genicam_cti_path))

@app.route('/settings')
def settings():
    all_settings = {
        'genicam_cti_path': db.get_setting('genicam_cti_path'),
        'team_number': db.get_setting('team_number'),
        'ip_mode': db.get_setting('ip_mode'),
        'hostname': db.get_setting('hostname'),
    }
    return render_template('settings.html', settings=all_settings)

@app.route('/settings/global/update', methods=['POST'])
def update_global_settings():
    db.update_setting('team_number', request.form.get('team_number'))
    db.update_setting('ip_mode', request.form.get('ip_mode'))
    db.update_setting('hostname', request.form.get('hostname'))
    return redirect(url_for('settings'))

@app.route('/cameras/add', methods=['POST'])
def add_camera():
    name = request.form.get('camera-name')
    camera_type = request.form.get('camera-type')
    
    if camera_type == 'USB':
        identifier = request.form.get('usb-camera-select')
    elif camera_type == 'GenICam':
        identifier = request.form.get('genicam-camera-select')
    else:
        # Handle error: invalid camera type
        return redirect(url_for('cameras'))

    if name and camera_type and identifier:
        db.add_camera(name, camera_type, identifier)

    return redirect(url_for('cameras'))

@app.route('/cameras/update/<int:camera_id>', methods=['POST'])
def update_camera(camera_id):
    name = request.form.get('camera-name')
    if name:
        db.update_camera(camera_id, name)
    return redirect(url_for('cameras'))

@app.route('/cameras/delete/<int:camera_id>', methods=['POST'])
def delete_camera(camera_id):
    db.delete_camera(camera_id)
    return redirect(url_for('cameras'))

@app.route('/api/cameras/<int:camera_id>/pipelines', methods=['GET'])
def get_pipelines(camera_id):
    pipelines = db.get_pipelines(camera_id)
    return jsonify([dict(row) for row in pipelines])

@app.route('/api/cameras/<int:camera_id>/pipelines', methods=['POST'])
def add_pipeline(camera_id):
    data = request.get_json()
    name = data.get('name')
    pipeline_type = data.get('pipeline_type')

    if not name or not pipeline_type:
        return jsonify({'error': 'Name and pipeline_type are required'}), 400

    db.add_pipeline(camera_id, name, pipeline_type)
    return jsonify({'success': True})

@app.route('/api/pipelines/<int:pipeline_id>', methods=['PUT'])
def update_pipeline(pipeline_id):
    data = request.get_json()
    name = data.get('name')
    pipeline_type = data.get('pipeline_type')

    if not name or not pipeline_type:
        return jsonify({'error': 'Name and pipeline_type are required'}), 400

    db.update_pipeline(pipeline_id, name, pipeline_type)
    return jsonify({'success': True})

@app.route('/api/pipelines/<int:pipeline_id>', methods=['DELETE'])
def delete_pipeline(pipeline_id):
    db.delete_pipeline(pipeline_id)
    return jsonify({'success': True})

@app.route('/config/genicam/update', methods=['POST'])
def update_genicam_settings():
    path = request.form.get('genicam-cti-path', '').strip()

    if path and path.lower().endswith('.cti'):
        # Basic validation: check if it's a non-empty string and ends with .cti
        db.update_setting('genicam_cti_path', path)
    elif not path:
        # If the path is empty, clear the setting
        db.clear_setting('genicam_cti_path')
    
    # Re-initialize the harvester to apply the new settings
    camera_utils.reinitialize_harvester()
    
    return redirect(url_for('settings'))

@app.route('/config/genicam/clear', methods=['POST'])
def clear_genicam_settings():
    db.clear_setting('genicam_cti_path')
    # Re-initialize the harvester to apply the new settings
    camera_utils.reinitialize_harvester()
    return redirect(url_for('settings'))

@app.route('/api/cameras/discover')
def discover_cameras():
    existing_identifiers = request.args.get('existing', '').split(',')
    
    usb_cameras = camera_utils.list_usb_cameras()
    genicam_cameras = camera_utils.list_genicam_cameras()

    # Filter out already configured cameras
    filtered_usb = [cam for cam in usb_cameras if cam['identifier'] not in existing_identifiers]
    filtered_genicam = [cam for cam in genicam_cameras if cam['identifier'] not in existing_identifiers]

    return jsonify({
        'usb': filtered_usb,
        'genicam': filtered_genicam
    })

@app.route('/api/cameras/status/<int:camera_id>')
def camera_status(camera_id):
    camera = db.get_camera(camera_id)
    if camera:
        is_connected = camera_utils.check_camera_connection(camera)
        return jsonify({'connected': is_connected})
    return jsonify({'error': 'Camera not found'}), 404

@app.route('/api/cameras/controls/<int:camera_id>', methods=['GET'])
def get_camera_controls(camera_id):
    camera = db.get_camera(camera_id)
    if camera:
        controls = {
            'orientation': camera['orientation'],
            'exposure_mode': camera['exposure_mode'],
            'exposure_value': camera['exposure_value'],
            'gain_mode': camera['gain_mode'],
            'gain_value': camera['gain_value'],
        }
        return jsonify(controls)
    return jsonify({'error': 'Camera not found'}), 404

@app.route('/api/cameras/update_controls/<int:camera_id>', methods=['POST'])
def update_camera_controls(camera_id):
    data = request.get_json()
    if not data:
        return jsonify({'error': 'Invalid JSON'}), 400

    orientation = data.get('orientation')
    exposure_mode = data.get('exposure_mode')
    exposure_value = data.get('exposure_value')
    gain_mode = data.get('gain_mode')
    gain_value = data.get('gain_value')

    # Basic validation
    if None in [orientation, exposure_mode, exposure_value, gain_mode, gain_value]:
        return jsonify({'error': 'Missing one or more required fields'}), 400

    db.update_camera_controls(
        camera_id,
        orientation,
        exposure_mode,
        exposure_value,
        gain_mode,
        gain_value
    )
    
    return jsonify({'success': True})

@app.route('/api/genicam/nodes/<int:camera_id>', methods=['GET'])
def genicam_nodes(camera_id):
    camera = db.get_camera(camera_id)
    if not camera or camera['camera_type'] != 'GenICam':
        return jsonify({'error': 'Camera not found or not a GenICam device'}), 404

    nodes, error = camera_utils.get_genicam_node_map(camera['identifier'])
    if error:
        return jsonify({'error': error}), 500

    return jsonify({'nodes': nodes})

@app.route('/api/genicam/nodes/<int:camera_id>', methods=['POST'])
def update_genicam_node(camera_id):
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
        }), 200

    status_code = status_code or 400
    return jsonify({'error': message or 'Failed to update node.'}), status_code

@app.route('/control/restart-app', methods=['POST'])
def restart_app():
    # This is a placeholder. A real implementation would need a more robust way
    # to restart the application, e.g., using a process manager.
    print("Restarting application...")
    os._exit(0)  # This will stop the current process.
    return "Restarting...", 200

@app.route('/control/reboot', methods=['POST'])
def reboot_device():
    # This is a placeholder. The actual command might vary by OS.
    # Use with extreme caution.
    print("Rebooting device...")
    os.system("sudo reboot")
    return "Rebooting...", 200

@app.route('/control/export-db')
def export_db():
    return send_file(db.DB_PATH, as_attachment=True)

@app.route('/control/import-db', methods=['POST'])
def import_db():
    if 'database' not in request.files:
        return redirect(url_for('settings'))
    file = request.files['database']
    if file.filename == '':
        return redirect(url_for('settings'))
    if file:
        file.save(db.DB_PATH)
    return redirect(url_for('settings'))

@app.route('/control/factory-reset', methods=['POST'])
def factory_reset():
    db.factory_reset()
    camera_utils.reinitialize_harvester()
    return redirect(url_for('settings'))

if __name__ == '__main__':
    with app.app_context():
        # Initialize the database and harvester on startup within the app context
        db.init_db()
        camera_utils.initialize_harvester()
    app.run(host='0.0.0.0', port=8080, debug=True, use_reloader=False)