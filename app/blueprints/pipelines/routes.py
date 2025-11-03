import logging
import os

from flask import request
from werkzeug.utils import secure_filename

from app.hw.accel import get_ml_availability
from app.models import Camera
from app.services import PipelineService, CameraService
from app.services.model_service import ModelService
from app.utils.responses import success_response, error_response
from app.utils.config import DATA_DIR
from . import pipelines

logger = logging.getLogger(__name__)


@pipelines.route("/cameras", methods=["GET"])
def list_cameras():
    """Returns all registered cameras."""
    cameras = Camera.query.order_by(Camera.id.asc()).all()
    return success_response([camera.to_dict() for camera in cameras])


@pipelines.route("/pipelines/ml/availability", methods=["GET"])
def ml_pipeline_availability():
    """Exposes detected ML runtime capabilities for the frontend."""
    return success_response(get_ml_availability())


@pipelines.route("/pipelines/<int:pipeline_id>/labels", methods=["GET"])
def get_pipeline_labels_route(pipeline_id: int):
    """Returns the label list for a pipeline, if available."""
    labels, error_msg, error_details = PipelineService.get_pipeline_labels(pipeline_id)

    if error_msg:
        status_code = 404 if error_msg == "Pipeline not found" else 400
        return error_response(error_msg, status_code, details=error_details)

    return success_response({"labels": labels})


@pipelines.route("/cameras/<int:camera_id>/pipelines", methods=["GET"])
def get_pipelines_for_camera(camera_id):
    """Returns all pipelines for a given camera."""
    pipelines_list = PipelineService.get_pipelines_for_camera(camera_id)
    return success_response([p.to_dict() for p in pipelines_list])


@pipelines.route("/cameras/<int:camera_id>/pipelines", methods=["POST"])
def add_pipeline(camera_id):
    """Adds a new pipeline to a camera."""
    data = request.get_json()
    name = data.get("name")
    pipeline_type = data.get("pipeline_type")

    if not name or not pipeline_type:
        return error_response("Name and pipeline_type are required", 400)

    # Create pipeline using service
    new_pipeline, error = PipelineService.create_pipeline(
        camera_id=camera_id,
        name=name,
        pipeline_type=pipeline_type
    )

    if error:
        status_code = 404 if error == "Camera not found" else 400
        return error_response(error, status_code)

    # Add pipeline to camera manager
    PipelineService.add_pipeline_to_camera_manager(new_pipeline)

    return success_response({"pipeline": new_pipeline.to_dict()}, code=201)


@pipelines.route("/pipelines/<int:pipeline_id>", methods=["PUT"])
def update_pipeline(pipeline_id):
    """Updates a pipeline's settings."""
    data = request.get_json()
    name = data.get("name")
    pipeline_type = data.get("pipeline_type")

    if not name or not pipeline_type:
        return error_response("Name and pipeline_type are required", 400)

    # Update pipeline using service
    success, error = PipelineService.update_pipeline_metadata(
        pipeline_id=pipeline_id,
        name=name,
        pipeline_type=pipeline_type
    )

    if not success:
        status_code = 404 if error == "Pipeline not found" else 400
        return error_response(error, status_code)

    # Sync to camera manager
    pipeline = PipelineService.get_pipeline_by_id(pipeline_id)
    if pipeline:
        PipelineService.sync_pipeline_to_camera_manager(pipeline)

    return success_response()


@pipelines.route("/pipelines/<int:pipeline_id>/config", methods=["PUT"])
def update_pipeline_config(pipeline_id):
    """Updates a pipeline's configuration."""
    config = request.get_json()
    if config is None:
        return error_response("Invalid config format", 400)

    # Update config using service
    success, error = PipelineService.update_pipeline_config(pipeline_id, config)

    if not success:
        status_code = 404 if error == "Pipeline not found" else 400
        return error_response(error or "Invalid configuration", status_code)

    # Sync to camera manager
    pipeline = PipelineService.get_pipeline_by_id(pipeline_id)
    if pipeline:
        PipelineService.sync_pipeline_to_camera_manager(pipeline)

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

    pipeline = PipelineService.get_pipeline_by_id(pipeline_id)
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

        config = PipelineService.get_pipeline_config_dict(pipeline)
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
        validation_result = PipelineService.validate_config(
            pipeline.pipeline_type, config
        )
        if not validation_result.is_valid:
            # Clean up uploaded file if validation fails
            if os.path.exists(save_path):
                os.remove(save_path)
            return error_response(
                "Configuration validation failed after file upload",
                400,
                details=validation_result.error_message
            )

        # Update config in database
        success, error = PipelineService.update_pipeline_config(pipeline_id, config)
        if not success:
            return error_response(error or "Failed to update config", 500)

        # Sync to camera manager
        PipelineService.sync_pipeline_to_camera_manager(pipeline)

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
    pipeline = PipelineService.get_pipeline_by_id(pipeline_id)
    if not pipeline:
        return error_response("Pipeline not found", 404)

    data = request.get_json()
    file_type = data.get("type")

    if not file_type:
        return error_response("File type is required", 400)

    config = PipelineService.get_pipeline_config_dict(pipeline)
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

        validation_result = PipelineService.validate_config(
            pipeline.pipeline_type, config
        )
        if not validation_result.is_valid:
            return error_response(
                "Invalid configuration after file deletion",
                400,
                details=validation_result.error_message
            )

        # Update config in database
        success, error = PipelineService.update_pipeline_config(pipeline_id, config)
        if not success:
            return error_response(error or "Failed to update config", 500)

        # Sync to camera manager
        PipelineService.sync_pipeline_to_camera_manager(pipeline)

        return success_response({"config": config})

    return error_response("File not found in config", 404)


@pipelines.route("/pipelines/<int:pipeline_id>", methods=["DELETE"])
def delete_pipeline(pipeline_id):
    """Deletes a pipeline."""
    # Get pipeline to retrieve camera info before deletion
    pipeline = PipelineService.get_pipeline_by_id(pipeline_id)
    if not pipeline:
        return error_response("Pipeline not found", 404)

    # Remove from camera manager first
    camera = CameraService.get_camera_by_id(pipeline.camera_id)
    if camera:
        PipelineService.remove_pipeline_from_camera_manager(
            camera.identifier, pipeline_id
        )

    # Delete from database
    success, _, error = PipelineService.delete_pipeline(pipeline_id)
    if not success:
        return error_response(error or "Failed to delete pipeline", 500)

    return success_response()
