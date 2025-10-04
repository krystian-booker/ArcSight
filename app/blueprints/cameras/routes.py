from flask import render_template, request, redirect, url_for, current_app, jsonify
from app import db, camera_manager, camera_discovery
from app.drivers.genicam_driver import GenICamDriver
from . import cameras


@cameras.route('/')
def cameras_page():
    """Renders the camera management page."""
    cameras_list = db.get_cameras()
    genicam_cti_path = db.get_setting('genicam_cti_path')
    return render_template('pages/cameras.html', cameras=cameras_list, genicam_enabled=bool(genicam_cti_path))


@cameras.route('/add', methods=['POST'])
def add_camera():
    """Adds a new camera."""
    name = request.form.get('camera-name')
    camera_type = request.form.get('camera-type')
    
    if camera_type == 'USB':
        identifier = request.form.get('usb-camera-select')
    elif camera_type == 'GenICam':
        identifier = request.form.get('genicam-camera-select')
    elif camera_type == 'OAK-D':
        identifier = request.form.get('oakd-camera-select')
    else:
        return redirect(url_for('cameras.cameras_page'))

    if name and camera_type and identifier:
        db.add_camera(name, camera_type, identifier)
        new_camera = db.get_camera_by_identifier(identifier)
        if new_camera:
            camera_manager.start_camera_thread(dict(new_camera), current_app._get_current_object())

    return redirect(url_for('cameras.cameras_page'))


@cameras.route('/update/<int:camera_id>', methods=['POST'])
def update_camera(camera_id):
    """Updates a camera's settings."""
    name = request.form.get('camera-name')
    if name:
        db.update_camera(camera_id, name)
    return redirect(url_for('cameras.cameras_page'))


@cameras.route('/delete/<int:camera_id>', methods=['POST'])
def delete_camera(camera_id):
    """Deletes a camera."""
    camera = db.get_camera(camera_id)
    if camera:
        camera_manager.stop_camera_thread(camera['identifier'])
    db.delete_camera(camera_id)
    return redirect(url_for('cameras.cameras_page'))

# --- MOVED FROM api/routes.py ---

@cameras.route('/results/<int:camera_id>')
def get_camera_results(camera_id):
    """Returns the latest results from all pipelines for a given camera."""
    camera = db.get_camera(camera_id)
    if not camera:
        return jsonify({'error': 'Camera not found'}), 404
    
    results = camera_manager.get_camera_pipeline_results(camera['identifier'])
    if results is None:
        return jsonify({'error': 'Camera thread not running or no results available'}), 404
        
    string_key_results = {str(k): v for k, v in results.items()}
    return jsonify(string_key_results)


@cameras.route('/discover')
def discover_cameras():
    """Discovers available USB, GenICam, and OAK-D cameras."""
    existing_identifiers = request.args.get('existing', '').split(',')
    
    # Delegate discovery to the new centralized function
    discovered = camera_discovery.discover_cameras(existing_identifiers)

    return jsonify(discovered)


@cameras.route('/status/<int:camera_id>')
def camera_status(camera_id):
    """Returns the connection status of a camera."""
    camera = db.get_camera(camera_id)
    if camera:
        is_running = camera_manager.is_camera_thread_running(camera['identifier'])
        return jsonify({'connected': is_running})
    return jsonify({'error': 'Camera not found'}), 404


@cameras.route('/controls/<int:camera_id>', methods=['GET'])
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


@cameras.route('/update_controls/<int:camera_id>', methods=['POST'])
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


@cameras.route('/genicam/nodes/<int:camera_id>', methods=['GET'])
def genicam_nodes(camera_id):
    """Returns the node map for a GenICam camera."""
    camera = db.get_camera(camera_id)
    if not camera or camera['camera_type'] != 'GenICam':
        return jsonify({'error': 'Camera not found or not a GenICam device'}), 404

    # Call the static method on the driver class
    nodes, error = GenICamDriver.get_node_map(camera['identifier'])
    if error:
        return jsonify({'error': error}), 500

    return jsonify({'nodes': nodes})


@cameras.route('/genicam/nodes/<int:camera_id>', methods=['POST'])
def update_genicam_node(camera_id):
    """Updates a node on a GenICam camera."""
    camera = db.get_camera(camera_id)
    if not camera or camera['camera_type'] != 'GenICam':
        return jsonify({'error': 'Camera not found or not a GenICam device'}), 404

    payload = request.get_json(silent=True) or {}
    node_name = payload.get('name')
    value = payload.get('value')

    # Call the static method on the driver class
    success, message, status_code, updated_node = GenICamDriver.update_node(
        camera['identifier'], node_name, value
    )
    
    if success:
        return jsonify({
            'success': True, 
            'message': message or 'Node updated successfully.',
            'node': updated_node
        }), status_code
    
    return jsonify({'error': message or 'Failed to update node.'}), status_code