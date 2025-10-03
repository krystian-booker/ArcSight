from flask import jsonify, request, current_app
from app import db, camera_manager, camera_discovery
from app.drivers.genicam_driver import GenICamDriver
import json
import os
from . import api


@api.route('/cameras/<int:camera_id>/pipelines', methods=['GET'])
def get_pipelines(camera_id):
    """Returns all pipelines for a given camera."""
    pipelines = db.get_pipelines(camera_id)
    return jsonify([dict(row) for row in pipelines])


@api.route('/cameras/<int:camera_id>/pipelines', methods=['POST'])
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
        camera_manager.add_pipeline_to_camera(camera_id, dict(new_pipeline), current_app._get_current_object())
        return jsonify({'success': True, 'pipeline_id': new_pipeline['id']})
    
    return jsonify({'error': 'Failed to retrieve new pipeline'}), 500


@api.route('/pipelines/<int:pipeline_id>', methods=['PUT'])
def update_pipeline(pipeline_id):
    """Updates a pipeline's settings."""
    data = request.get_json()
    name = data.get('name')
    pipeline_type = data.get('pipeline_type')

    if not name or not pipeline_type:
        return jsonify({'error': 'Name and pipeline_type are required'}), 400

    db.update_pipeline(pipeline_id, name, pipeline_type)
    
    # Also update the pipeline in the running camera thread
    pipeline = db.get_pipeline(pipeline_id)
    if pipeline:
        camera_manager.update_pipeline_in_camera(
            pipeline['camera_id'], 
            pipeline_id, 
            current_app._get_current_object()
        )

    return jsonify({'success': True})


@api.route('/pipelines/<int:pipeline_id>/config', methods=['PUT'])
def update_pipeline_config(pipeline_id):
    """Updates a pipeline's configuration."""
    config = request.get_json()
    if config is None:
        return jsonify({'error': 'Invalid config format'}), 400

    db.update_pipeline_config(pipeline_id, config)
    
    # Also update the pipeline in the running camera thread
    pipeline = db.get_pipeline(pipeline_id)
    if pipeline:
        camera_manager.update_pipeline_in_camera(
            pipeline['camera_id'], 
            pipeline_id, 
            current_app._get_current_object()
        )

    return jsonify({'success': True})


@api.route('/pipelines/<int:pipeline_id>/files', methods=['POST'])
def upload_pipeline_file(pipeline_id):
    """Uploads a file for a specific pipeline (e.g., ML model, labels)."""
    if 'file' not in request.files:
        return jsonify({'error': 'No file part'}), 400
    
    file = request.files['file']
    file_type = request.form.get('type') # 'model' or 'labels'

    if file.filename == '':
        return jsonify({'error': 'No selected file'}), 400
    
    if not file_type:
        return jsonify({'error': 'File type is required'}), 400

    pipeline = db.get_pipeline(pipeline_id)
    if not pipeline:
        return jsonify({'error': 'Pipeline not found'}), 404

    if file:
        # Save the file to the same directory as the database
        upload_dir = os.path.dirname(db.DB_PATH)
        filename = f"pipeline_{pipeline_id}_{file_type}_{file.filename}"
        save_path = os.path.join(upload_dir, filename)
        file.save(save_path)

        # Update the pipeline's config with the new filename
        config = json.loads(pipeline['config'] or '{}')
        config[f'{file_type}_filename'] = filename
        db.update_pipeline_config(pipeline_id, config)
        
        # Also update the pipeline in the running camera thread
        if pipeline:
            camera_manager.update_pipeline_in_camera(
                pipeline['camera_id'], 
                pipeline_id, 
                current_app._get_current_object()
            )

        return jsonify({'success': True, 'filename': filename})

    return jsonify({'error': 'File upload failed'}), 500


@api.route('/pipelines/<int:pipeline_id>/files', methods=['DELETE'])
def delete_pipeline_file(pipeline_id):
    """Deletes a file associated with a specific pipeline."""
    data = request.get_json()
    file_type = data.get('type')

    if not file_type:
        return jsonify({'error': 'File type is required'}), 400

    pipeline = db.get_pipeline(pipeline_id)
    if not pipeline:
        return jsonify({'error': 'Pipeline not found'}), 404

    config = json.loads(pipeline['config'] or '{}')
    filename_key = f'{file_type}_filename'
    filename = config.get(filename_key)

    if filename:
        file_path = os.path.join(os.path.dirname(db.DB_PATH), filename)
        if os.path.exists(file_path):
            os.remove(file_path)

        # Remove the filename from the config
        del config[filename_key]
        db.update_pipeline_config(pipeline_id, config)
        
        # Also update the pipeline in the running camera thread
        if pipeline:
            camera_manager.update_pipeline_in_camera(
                pipeline['camera_id'], 
                pipeline_id, 
                current_app._get_current_object()
            )

        return jsonify({'success': True})

    return jsonify({'error': 'File not found in config'}), 404


@api.route('/pipelines/<int:pipeline_id>', methods=['DELETE'])
def delete_pipeline(pipeline_id):
    """Deletes a pipeline."""
    pipeline = db.get_pipeline(pipeline_id)
    if pipeline:
        camera_id = pipeline['camera_id']
        camera_manager.remove_pipeline_from_camera(camera_id, pipeline_id, current_app._get_current_object())
        db.delete_pipeline(pipeline_id)
        return jsonify({'success': True})
    return jsonify({'error': 'Pipeline not found'}), 404


@api.route('/cameras/results/<int:camera_id>')
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


@api.route('/cameras/discover')
def discover_cameras():
    """Discovers available USB, GenICam, and OAK-D cameras."""
    existing_identifiers = request.args.get('existing', '').split(',')
    
    # Delegate discovery to the new centralized function
    discovered = camera_discovery.discover_cameras(existing_identifiers)

    return jsonify(discovered)


@api.route('/cameras/status/<int:camera_id>')
def camera_status(camera_id):
    """Returns the connection status of a camera."""
    camera = db.get_camera(camera_id)
    if camera:
        is_running = camera_manager.is_camera_thread_running(camera['identifier'])
        return jsonify({'connected': is_running})
    return jsonify({'error': 'Camera not found'}), 404


@api.route('/cameras/controls/<int:camera_id>', methods=['GET'])
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


@api.route('/cameras/update_controls/<int:camera_id>', methods=['POST'])
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


@api.route('/genicam/nodes/<int:camera_id>', methods=['GET'])
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


@api.route('/genicam/nodes/<int:camera_id>', methods=['POST'])
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