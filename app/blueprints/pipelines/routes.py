from flask import jsonify, request, current_app
from app import db, camera_manager
import json
import os
from . import pipelines


@pipelines.route('/cameras/<int:camera_id>/pipelines', methods=['GET'])
def get_pipelines(camera_id):
    """Returns all pipelines for a given camera."""
    pipelines = db.get_pipelines(camera_id)
    return jsonify([dict(row) for row in pipelines])


@pipelines.route('/cameras/<int:camera_id>/pipelines', methods=['POST'])
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


@pipelines.route('/pipelines/<int:pipeline_id>', methods=['PUT'])
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


@pipelines.route('/pipelines/<int:pipeline_id>/config', methods=['PUT'])
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


@pipelines.route('/pipelines/<int:pipeline_id>/files', methods=['POST'])
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


@pipelines.route('/pipelines/<int:pipeline_id>/files', methods=['DELETE'])
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


@pipelines.route('/pipelines/<int:pipeline_id>', methods=['DELETE'])
def delete_pipeline(pipeline_id):
    """Deletes a pipeline."""
    pipeline = db.get_pipeline(pipeline_id)
    if pipeline:
        camera_id = pipeline['camera_id']
        camera_manager.remove_pipeline_from_camera(camera_id, pipeline_id, current_app._get_current_object())
        db.delete_pipeline(pipeline_id)
        return jsonify({'success': True})
    return jsonify({'error': 'Pipeline not found'}), 404