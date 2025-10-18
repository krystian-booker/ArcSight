from flask import jsonify, request
from werkzeug.utils import secure_filename
from app.extensions import db
from app import camera_manager
from app.models import Camera, Pipeline
from app.pipeline_validators import validate_pipeline_config, get_default_config
import json
import os
from appdirs import user_data_dir
from . import pipelines

# --- Data Directory Setup ---
APP_NAME = "VisionTools"
APP_AUTHOR = "User"
data_dir = user_data_dir(APP_NAME, APP_AUTHOR)


@pipelines.route("/cameras/<int:camera_id>/pipelines", methods=["GET"])
def get_pipelines_for_camera(camera_id):
    """Returns all pipelines for a given camera."""
    camera = db.session.get(Camera, camera_id)
    if not camera:
        return jsonify({"error": "Camera not found"}), 404
    return jsonify([p.to_dict() for p in camera.pipelines])


@pipelines.route("/cameras/<int:camera_id>/pipelines", methods=["POST"])
def add_pipeline(camera_id):
    """Adds a new pipeline to a camera."""
    camera = db.session.get(Camera, camera_id)
    if not camera:
        return jsonify({"error": "Camera not found"}), 404
    data = request.get_json()
    name = data.get("name")
    pipeline_type = data.get("pipeline_type")

    if not name or not pipeline_type:
        return jsonify({"error": "Name and pipeline_type are required"}), 400

    # Use default config for the pipeline type
    default_config = get_default_config(pipeline_type)

    new_pipeline = Pipeline(
        name=name,
        pipeline_type=pipeline_type,
        config=json.dumps(default_config),
        camera_id=camera_id,
    )
    db.session.add(new_pipeline)
    db.session.commit()

    # Pass primitive data to avoid DB I/O in hot path
    camera_manager.add_pipeline_to_camera(
        identifier=camera.identifier,
        pipeline_id=new_pipeline.id,
        pipeline_type=new_pipeline.pipeline_type,
        pipeline_config_json=new_pipeline.config,
        camera_matrix_json=camera.camera_matrix_json,
        dist_coeffs_json=camera.dist_coeffs_json,
    )
    return jsonify({"success": True, "pipeline": new_pipeline.to_dict()})


@pipelines.route("/pipelines/<int:pipeline_id>", methods=["PUT"])
def update_pipeline(pipeline_id):
    """Updates a pipeline's settings."""
    pipeline = db.session.get(Pipeline, pipeline_id)
    if not pipeline:
        return jsonify({"error": "Pipeline not found"}), 404
    data = request.get_json()
    name = data.get("name")
    pipeline_type = data.get("pipeline_type")

    if not name or not pipeline_type:
        return jsonify({"error": "Name and pipeline_type are required"}), 400

    pipeline.name = name
    pipeline.pipeline_type = pipeline_type
    db.session.commit()

    # Fetch camera data once for primitive parameter passing
    camera = db.session.get(Camera, pipeline.camera_id)
    if camera:
        camera_manager.update_pipeline_in_camera(
            identifier=camera.identifier,
            pipeline_id=pipeline_id,
            pipeline_type=pipeline.pipeline_type,
            pipeline_config_json=pipeline.config,
            camera_matrix_json=camera.camera_matrix_json,
            dist_coeffs_json=camera.dist_coeffs_json,
        )

    return jsonify({"success": True})


@pipelines.route("/pipelines/<int:pipeline_id>/config", methods=["PUT"])
def update_pipeline_config(pipeline_id):
    """Updates a pipeline's configuration."""
    pipeline = db.session.get(Pipeline, pipeline_id)
    if not pipeline:
        return jsonify({"error": "Pipeline not found"}), 404
    config = request.get_json()
    if config is None:
        return jsonify({"error": "Invalid config format"}), 400

    # Validate configuration against schema
    is_valid, error_message = validate_pipeline_config(pipeline.pipeline_type, config)
    if not is_valid:
        return jsonify(
            {"error": "Invalid configuration", "details": error_message}
        ), 400

    pipeline.config = json.dumps(config)
    db.session.commit()

    # Fetch camera data once for primitive parameter passing
    camera = db.session.get(Camera, pipeline.camera_id)
    if camera:
        camera_manager.update_pipeline_in_camera(
            identifier=camera.identifier,
            pipeline_id=pipeline_id,
            pipeline_type=pipeline.pipeline_type,
            pipeline_config_json=pipeline.config,
            camera_matrix_json=camera.camera_matrix_json,
            dist_coeffs_json=camera.dist_coeffs_json,
        )

    return jsonify({"success": True})


@pipelines.route("/pipelines/<int:pipeline_id>/files", methods=["POST"])
def upload_pipeline_file(pipeline_id):
    """Uploads a file for a specific pipeline (e.g., ML model, labels)."""
    if "file" not in request.files:
        return jsonify({"error": "No file part"}), 400

    file = request.files["file"]
    file_type = request.form.get("type")  # 'model' or 'labels'

    if file.filename == "":
        return jsonify({"error": "No selected file"}), 400

    if not file_type:
        return jsonify({"error": "File type is required"}), 400

    # Validate file_type to prevent path traversal
    if file_type not in ["model", "labels"]:
        return jsonify({"error": 'Invalid file type. Must be "model" or "labels"'}), 400

    pipeline = db.session.get(Pipeline, pipeline_id)
    if not pipeline:
        return jsonify({"error": "Pipeline not found"}), 404

    if file:
        safe_filename = secure_filename(file.filename)
        if not safe_filename:
            return jsonify({"error": "Invalid filename"}), 400

        filename = f"pipeline_{pipeline_id}_{file_type}_{safe_filename}"
        save_path = os.path.join(data_dir, filename)

        # Additional security: Ensure save_path is within data_dir
        if not os.path.abspath(save_path).startswith(os.path.abspath(data_dir)):
            return jsonify({"error": "Invalid file path"}), 400

        file.save(save_path)

        config = json.loads(pipeline.config or "{}")
        config[f"{file_type}_path"] = save_path  # Store full path
        config[f"{file_type}_filename"] = safe_filename  # Store filename for reference

        # Validate the updated config
        is_valid, error_message = validate_pipeline_config(
            pipeline.pipeline_type, config
        )
        if not is_valid:
            # Clean up uploaded file if validation fails
            if os.path.exists(save_path):
                os.remove(save_path)
            return jsonify(
                {
                    "error": "Configuration validation failed after file upload",
                    "details": error_message,
                }
            ), 400

        pipeline.config = json.dumps(config)
        db.session.commit()

        # Fetch camera data once for primitive parameter passing
        camera = db.session.get(Camera, pipeline.camera_id)
        if camera:
            camera_manager.update_pipeline_in_camera(
                identifier=camera.identifier,
                pipeline_id=pipeline_id,
                pipeline_type=pipeline.pipeline_type,
                pipeline_config_json=pipeline.config,
                camera_matrix_json=camera.camera_matrix_json,
            )
        return jsonify({"success": True, "filepath": save_path})

    return jsonify({"error": "File upload failed"}), 500


@pipelines.route("/pipelines/<int:pipeline_id>/files", methods=["DELETE"])
def delete_pipeline_file(pipeline_id):
    """Deletes a file associated with a specific pipeline."""
    pipeline = db.session.get(Pipeline, pipeline_id)
    if not pipeline:
        return jsonify({"error": "Pipeline not found"}), 404
    data = request.get_json()
    file_type = data.get("type")

    if not file_type:
        return jsonify({"error": "File type is required"}), 400

    config = json.loads(pipeline.config or "{}")
    filepath_key = f"{file_type}_path"
    file_path = config.get(filepath_key)

    if file_path:
        if os.path.exists(file_path):
            os.remove(file_path)

        del config[filepath_key]
        pipeline.config = json.dumps(config)
        db.session.commit()

        # Fetch camera data once for primitive parameter passing
        camera = db.session.get(Camera, pipeline.camera_id)
        if camera:
            camera_manager.update_pipeline_in_camera(
                identifier=camera.identifier,
                pipeline_id=pipeline_id,
                pipeline_type=pipeline.pipeline_type,
                pipeline_config_json=pipeline.config,
                camera_matrix_json=camera.camera_matrix_json,
            )
        return jsonify({"success": True})

    return jsonify({"error": "File not found in config"}), 404


@pipelines.route("/pipelines/<int:pipeline_id>", methods=["DELETE"])
def delete_pipeline(pipeline_id):
    """Deletes a pipeline."""
    pipeline = db.session.get(Pipeline, pipeline_id)
    if not pipeline:
        return jsonify({"error": "Pipeline not found"}), 404

    # Fetch camera identifier for primitive parameter passing
    camera = db.session.get(Camera, pipeline.camera_id)
    if camera:
        camera_manager.remove_pipeline_from_camera(
            identifier=camera.identifier, pipeline_id=pipeline_id
        )

    db.session.delete(pipeline)
    db.session.commit()

    return jsonify({"success": True})
