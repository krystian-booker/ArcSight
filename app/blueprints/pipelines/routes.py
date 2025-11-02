import logging
from flask import request
from werkzeug.utils import secure_filename
from app.extensions import db
from app import camera_manager
from app.models import Camera, Pipeline
from app.pipeline_validators import validate_pipeline_config, get_default_config
from app.hw.accel import get_ml_availability
from app.services.model_service import ModelService
from app.utils.responses import success_response, error_response
from app.utils.config import DATA_DIR
import json
import os
from . import pipelines

logger = logging.getLogger(__name__)


@pipelines.route("/cameras", methods=["GET"])
def list_cameras():
    """Returns all registered cameras."""
    cameras = Camera.query.order_by(Camera.id.asc()).all()
    return success_response([camera.to_dict() for camera in cameras])


# Removed: _remove_file - now use ModelService.remove_file()
# Removed: _apply_model_upload - now use ModelService.apply_model_upload()


@pipelines.route("/pipelines/ml/availability", methods=["GET"])
def ml_pipeline_availability():
    """Exposes detected ML runtime capabilities for the frontend."""
    return success_response(get_ml_availability())


@pipelines.route("/pipelines/<int:pipeline_id>/labels", methods=["GET"])
def get_pipeline_labels(pipeline_id: int):
    """Returns the label list for a pipeline, if available."""
    pipeline = db.session.get(Pipeline, pipeline_id)
    if not pipeline:
        return error_response("Pipeline not found", 404)

    config = json.loads(pipeline.config or "{}")
    labels_path = config.get("labels_path")
    if not labels_path and config.get("labels_filename"):
        labels_path = os.path.join(DATA_DIR, config["labels_filename"])

    # Use ModelService to get labels
    labels = ModelService.get_labels_from_file(labels_path) if labels_path else []

    # Check if validation result uses dataclass pattern
    validation_result = validate_pipeline_config(pipeline.pipeline_type, config)
    error_msg = None
    error_details = None

    if hasattr(validation_result, 'is_valid'):
        # New ValidationResult dataclass pattern
        if not validation_result.is_valid:
            error_msg = "Invalid configuration"
            error_details = validation_result.error_message
    else:
        # Legacy tuple pattern
        is_valid, error_message = validation_result
        if not is_valid:
            error_msg = "Invalid configuration"
            error_details = error_message

    # Additional check for ML pipelines
    if (
        pipeline.pipeline_type == "Object Detection (ML)"
        and labels
        and not config.get("model_path")
    ):
        error_msg = "Invalid configuration"
        error_details = (
            "Model path missing for ML pipeline; upload a model and ensure calibration "
            "values such as tag_size_m are set before deploying."
        )

    if error_msg:
        return error_response(error_msg, 400, details=error_details)

    return success_response({"labels": labels})


@pipelines.route("/cameras/<int:camera_id>/pipelines", methods=["GET"])
def get_pipelines_for_camera(camera_id):
    """Returns all pipelines for a given camera."""
    camera = db.session.get(Camera, camera_id)
    if not camera:
        return error_response("Camera not found", 404)
    return success_response([p.to_dict() for p in camera.pipelines])


@pipelines.route("/cameras/<int:camera_id>/pipelines", methods=["POST"])
def add_pipeline(camera_id):
    """Adds a new pipeline to a camera."""
    camera = db.session.get(Camera, camera_id)
    if not camera:
        return error_response("Camera not found", 404)
    data = request.get_json()
    name = data.get("name")
    pipeline_type = data.get("pipeline_type")

    if not name or not pipeline_type:
        return error_response("Name and pipeline_type are required", 400)

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
    return success_response({"pipeline": new_pipeline.to_dict()}, code=201)


@pipelines.route("/pipelines/<int:pipeline_id>", methods=["PUT"])
def update_pipeline(pipeline_id):
    """Updates a pipeline's settings."""
    pipeline = db.session.get(Pipeline, pipeline_id)
    if not pipeline:
        return error_response("Pipeline not found", 404)
    data = request.get_json()
    name = data.get("name")
    pipeline_type = data.get("pipeline_type")

    if not name or not pipeline_type:
        return error_response("Name and pipeline_type are required", 400)

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

    return success_response()


@pipelines.route("/pipelines/<int:pipeline_id>/config", methods=["PUT"])
def update_pipeline_config(pipeline_id):
    """Updates a pipeline's configuration."""
    pipeline = db.session.get(Pipeline, pipeline_id)
    if not pipeline:
        return error_response("Pipeline not found", 404)
    config = request.get_json()
    if config is None:
        return error_response("Invalid config format", 400)

    # Validate configuration against schema
    is_valid, error_message = validate_pipeline_config(pipeline.pipeline_type, config)
    if not is_valid:
        return error_response("Invalid configuration", 400, details=error_message)

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

    return success_response()


@pipelines.route("/pipelines/<int:pipeline_id>/files", methods=["POST"])
def upload_pipeline_file(pipeline_id):
    """Uploads a file for a specific pipeline (e.g., ML model, labels)."""
    if "file" not in request.files:
        return error_response("No file part", 400)

    file = request.files["file"]
    file_type = request.form.get("type")  # 'model' or 'labels'

    if file.filename == "":
        return error_response("No selected file", 400)

    if not file_type:
        return error_response("File type is required", 400)

    # Validate file_type to prevent path traversal
    if file_type not in ["model", "labels"]:
        return error_response('Invalid file type. Must be "model" or "labels"', 400)

    pipeline = db.session.get(Pipeline, pipeline_id)
    if not pipeline:
        return error_response("Pipeline not found", 404)

    if file:
        safe_filename = secure_filename(file.filename)
        if not safe_filename:
            return error_response("Invalid filename", 400)

        filename = f"pipeline_{pipeline_id}_{file_type}_{safe_filename}"
        save_path = os.path.join(DATA_DIR, filename)

        # Additional security: Ensure save_path is within DATA_DIR
        if not os.path.abspath(save_path).startswith(os.path.abspath(DATA_DIR)):
            return error_response("Invalid file path", 400)

        file.save(save_path)

        config = json.loads(pipeline.config or "{}")
        if file_type == "labels":
            config["labels_path"] = save_path
            config["labels_filename"] = safe_filename
            # Reset target classes selection so UI can refresh from new labels
            config["target_classes"] = config.get("target_classes", [])
        else:
            # Use ModelService for model upload processing
            success, error_message = ModelService.apply_model_upload(
                pipeline_id, config, safe_filename, save_path
            )
            if not success:
                ModelService.remove_file(save_path)
                return error_response(
                    "Model upload failed",
                    400,
                    details=error_message or "Unknown error"
                )

        # Validate the updated config
        is_valid, error_message = validate_pipeline_config(
            pipeline.pipeline_type, config
        )
        if not is_valid:
            # Clean up uploaded file if validation fails
            if os.path.exists(save_path):
                os.remove(save_path)
            return error_response(
                "Configuration validation failed after file upload",
                400,
                details=error_message
            )

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
        return success_response(
            {
                "filepath": save_path,
                "filename": safe_filename,
                "config": config,
            }
        )

    return error_response("File upload failed", 500)


@pipelines.route("/pipelines/<int:pipeline_id>/files", methods=["DELETE"])
def delete_pipeline_file(pipeline_id):
    """Deletes a file associated with a specific pipeline."""
    pipeline = db.session.get(Pipeline, pipeline_id)
    if not pipeline:
        return error_response("Pipeline not found", 404)
    data = request.get_json()
    file_type = data.get("type")

    if not file_type:
        return error_response("File type is required", 400)

    config = json.loads(pipeline.config or "{}")
    filepath_key = f"{file_type}_path"
    file_path = config.get(filepath_key)

    if file_path:
        ModelService.remove_file(file_path)
        config.pop(filepath_key, None)
        filename_key = f"{file_type}_filename"
        config.pop(filename_key, None)

        if file_type == "labels":
            config["target_classes"] = []
        elif file_type == "model":
            ModelService.remove_file(config.pop("converted_onnx_path", None))
            config.pop("converted_onnx_filename", None)
            ModelService.remove_file(config.pop("rknn_path", None))
            config["accelerator"] = "none"
            config["model_type"] = "yolo"
            config.pop("tflite_delegate", None)
            config["onnx_provider"] = "CPUExecutionProvider"

        is_valid, error_message = validate_pipeline_config(
            pipeline.pipeline_type, config
        )
        if not is_valid:
            return error_response(
                "Invalid configuration after file deletion",
                400,
                details=error_message
            )

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
        return success_response({"config": config})

    return error_response("File not found in config", 404)


@pipelines.route("/pipelines/<int:pipeline_id>", methods=["DELETE"])
def delete_pipeline(pipeline_id):
    """Deletes a pipeline."""
    pipeline = db.session.get(Pipeline, pipeline_id)
    if not pipeline:
        return error_response("Pipeline not found", 404)

    # Fetch camera identifier for primitive parameter passing
    camera = db.session.get(Camera, pipeline.camera_id)
    if camera:
        camera_manager.remove_pipeline_from_camera(
            identifier=camera.identifier, pipeline_id=pipeline_id
        )

    db.session.delete(pipeline)
    db.session.commit()

    return success_response()
