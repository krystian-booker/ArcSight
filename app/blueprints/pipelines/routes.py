from flask import jsonify, request
from werkzeug.utils import secure_filename
from app.extensions import db
from app import camera_manager
from app.models import Camera, Pipeline
from app.pipeline_validators import validate_pipeline_config, get_default_config
from app.hw.accel import get_ml_availability
from app.ml import (
    convert_yolo_weights_to_onnx,
    convert_onnx_to_rknn,
    validate_onnx_model,
    infer_model_type,
)
from typing import Any, Dict, List, Optional, Tuple
import json
import os
from appdirs import user_data_dir
from . import pipelines

# --- Data Directory Setup ---
APP_NAME = "VisionTools"
APP_AUTHOR = "User"
data_dir = user_data_dir(APP_NAME, APP_AUTHOR)


def _remove_file(path: Optional[str]) -> None:
    if path and os.path.exists(path):
        try:
            os.remove(path)
        except OSError:
            pass


def _apply_model_upload(
    pipeline_id: int,
    config: Dict[str, Any],
    safe_filename: str,
    save_path: str,
) -> Tuple[bool, Optional[str]]:
    """Updates pipeline configuration after a model upload."""
    updated_config = dict(config)
    updated_config["model_filename"] = safe_filename
    updated_config["model_path"] = save_path
    updated_config.setdefault("accelerator", "none")

    inferred_type = infer_model_type(safe_filename) or "yolo"
    extension = os.path.splitext(safe_filename)[1].lower()

    previous_converted = config.get("converted_onnx_path")
    previous_rknn = config.get("rknn_path")

    if inferred_type == "tflite":
        updated_config["model_type"] = "tflite"
        updated_config["tflite_delegate"] = (
            updated_config.get("tflite_delegate") or "CPU"
        )
        updated_config.pop("onnx_provider", None)
        updated_config.pop("converted_onnx_path", None)
        updated_config.pop("converted_onnx_filename", None)
        updated_config.pop("rknn_path", None)
        if updated_config.get("accelerator") == "rknn":
            updated_config["accelerator"] = "none"
    elif inferred_type == "rknn":
        updated_config["model_type"] = "yolo"
        updated_config["accelerator"] = "rknn"
        updated_config["rknn_path"] = save_path
        updated_config.pop("converted_onnx_path", None)
        updated_config.pop("converted_onnx_filename", None)
        updated_config.pop("tflite_delegate", None)
    else:  # YOLO / ONNX path
        updated_config["model_type"] = "yolo"
        updated_config["onnx_provider"] = (
            updated_config.get("onnx_provider") or "CPUExecutionProvider"
        )
        updated_config.pop("tflite_delegate", None)

        if extension == ".onnx":
            is_valid, message = validate_onnx_model(save_path)
            if not is_valid:
                return False, message
            updated_config["converted_onnx_path"] = save_path
            updated_config["converted_onnx_filename"] = safe_filename
        elif extension in [".pt", ".weights"]:
            base_name = os.path.splitext(safe_filename)[0]
            converted_filename = f"pipeline_{pipeline_id}_{base_name}.onnx"
            converted_path = os.path.join(data_dir, converted_filename)
            success, message, output_path = convert_yolo_weights_to_onnx(
                save_path,
                converted_path,
                img_size=int(updated_config.get("img_size", 640)),
            )
            if not success:
                _remove_file(converted_path)
                return False, message
            updated_config["converted_onnx_path"] = output_path
            updated_config["converted_onnx_filename"] = os.path.basename(output_path)
        else:
            return (
                False,
                "Unsupported model format. Upload .onnx, .pt, .weights, .tflite, or .rknn files.",
            )

        availability = get_ml_availability()
        rknn_supported = availability.get("accelerators", {}).get(
            "rknn", False
        ) and updated_config.get("converted_onnx_path")
        if rknn_supported:
            converted_name = os.path.splitext(
                os.path.basename(updated_config["converted_onnx_path"])
            )[0]
            rknn_filename = f"{converted_name}.rknn"
            rknn_path = os.path.join(data_dir, rknn_filename)
            success, message, output_path = convert_onnx_to_rknn(
                updated_config["converted_onnx_path"], rknn_path
            )
            if success and output_path:
                updated_config["rknn_path"] = output_path
                updated_config["accelerator"] = "rknn"
            else:
                if message:
                    print(f"RKNN conversion skipped: {message}")
                updated_config.pop("rknn_path", None)
                if updated_config.get("accelerator") == "rknn":
                    updated_config["accelerator"] = "none"
        else:
            updated_config.pop("rknn_path", None)
            if updated_config.get("accelerator") == "rknn":
                updated_config["accelerator"] = "none"

    # Apply updates atomically
    config.clear()
    config.update(updated_config)

    # Remove stale artefacts
    if previous_converted and previous_converted != config.get("converted_onnx_path"):
        _remove_file(previous_converted)
    if previous_rknn and previous_rknn != config.get("rknn_path"):
        _remove_file(previous_rknn)

    return True, None


@pipelines.route("/pipelines/ml/availability", methods=["GET"])
def ml_pipeline_availability():
    """Exposes detected ML runtime capabilities for the frontend."""
    return jsonify(get_ml_availability())


@pipelines.route("/pipelines/<int:pipeline_id>/labels", methods=["GET"])
def get_pipeline_labels(pipeline_id: int):
    """Returns the label list for a pipeline, if available."""
    pipeline = db.session.get(Pipeline, pipeline_id)
    if not pipeline:
        return jsonify({"error": "Pipeline not found"}), 404

    config = json.loads(pipeline.config or "{}")
    labels_path = config.get("labels_path")
    if not labels_path and config.get("labels_filename"):
        labels_path = os.path.join(data_dir, config["labels_filename"])

    labels: List[str] = []
    if labels_path and os.path.exists(labels_path):
        try:
            with open(labels_path, "r", encoding="utf-8") as handle:
                labels = [line.strip() for line in handle if line.strip()]
        except OSError:
            labels = []

    return jsonify({"labels": labels})


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
        if file_type == "labels":
            config["labels_path"] = save_path
            config["labels_filename"] = safe_filename
            # Reset target classes selection so UI can refresh from new labels
            config["target_classes"] = config.get("target_classes", [])
        else:
            success, error_message = _apply_model_upload(
                pipeline_id, config, safe_filename, save_path
            )
            if not success:
                _remove_file(save_path)
                return (
                    jsonify(
                        {
                            "error": "Model upload failed",
                            "details": error_message or "Unknown error",
                        }
                    ),
                    400,
                )

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
        return jsonify(
            {
                "success": True,
                "filepath": save_path,
                "filename": safe_filename,
                "config": config,
            }
        )

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
        _remove_file(file_path)
        config.pop(filepath_key, None)
        filename_key = f"{file_type}_filename"
        config.pop(filename_key, None)

        if file_type == "labels":
            config["target_classes"] = []
        elif file_type == "model":
            _remove_file(config.pop("converted_onnx_path", None))
            config.pop("converted_onnx_filename", None)
            _remove_file(config.pop("rknn_path", None))
            config["accelerator"] = "none"
            config["model_type"] = "yolo"
            config.pop("tflite_delegate", None)
            config["onnx_provider"] = "CPUExecutionProvider"

        is_valid, error_message = validate_pipeline_config(
            pipeline.pipeline_type, config
        )
        if not is_valid:
            return (
                jsonify(
                    {
                        "error": "Invalid configuration after file deletion",
                        "details": error_message,
                    }
                ),
                400,
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
        return jsonify({"success": True, "config": config})

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
