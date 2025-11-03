"""
Pipeline configuration validators.

Provides JSON schema validation for each pipeline type to prevent
malicious or malformed configurations from crashing vision processing threads.
"""

import os
from dataclasses import dataclass
from typing import Dict, Any, Optional

from .enums import PipelineType

# Enumerations for ML pipeline configuration
ML_MODEL_TYPES = ["yolo", "tflite"]
ONNX_EXECUTION_PROVIDERS = [
    "CPUExecutionProvider",
    "CUDAExecutionProvider",
    "TensorrtExecutionProvider",
    "CoreMLExecutionProvider",
    "OpenVINOExecutionProvider",
]
TFLITE_DELEGATES = ["CPU", "GPU", "EdgeTPU"]
ML_ACCELERATORS = ["none", "rknn"]


@dataclass
class ValidationResult:
    """Result of a pipeline configuration validation."""

    is_valid: bool
    error_message: Optional[str] = None

    @classmethod
    def success(cls) -> "ValidationResult":
        """Create a successful validation result."""
        return cls(is_valid=True, error_message=None)

    @classmethod
    def failure(cls, error_message: str) -> "ValidationResult":
        """Create a failed validation result with an error message."""
        return cls(is_valid=False, error_message=error_message)


def recommended_apriltag_threads(
    cpu_count: Optional[int] = None, cap: int = 4
) -> int:
    """
    Return a safe default thread count for AprilTag detection based on host CPU.

    Args:
        cpu_count: Optional override primarily used in tests.
        cap: Upper bound to prevent exhausting compute resources.
    """
    detected = cpu_count if cpu_count is not None else os.cpu_count()
    try:
        detected_int = int(detected) if detected is not None else 1
    except (TypeError, ValueError):
        detected_int = 1

    if detected_int < 1:
        detected_int = 1

    return max(1, min(cap, detected_int))


# Define schemas for each pipeline type
APRILTAG_SCHEMA = {
    "type": "object",
    "properties": {
        "family": {
            "type": "string",
            "enum": [
                "tag16h5",
                "tag25h9",
                "tag36h11",
                "tagCircle21h7",
                "tagCircle49h12",
                "tagCustom48h12",
                "tagStandard41h12",
                "tagStandard52h13",
                "16h5",
                "25h9",
                "36h11",
                "Circle21h7",
                "Circle49h12",
                "Custom48h12",
                "Standard41h12",
                "Standard52h13",
            ],
            "description": "AprilTag family to detect",
        },
        "error_correction": {
            "type": "integer",
            "minimum": 0,
            "maximum": 7,
            "description": "Error correction bits (0-7)",
        },
        "tag_size_m": {
            "type": "number",
            "minimum": 0.001,
            "maximum": 10.0,
            "description": "Physical size of the tag in meters",
        },
        "threads": {
            "type": "integer",
            "minimum": 1,
            "maximum": 16,
            "description": "Number of detector threads",
        },
        "auto_threads": {
            "type": "boolean",
            "description": "Automatically scale threads based on host CPU",
        },
        "decimate": {
            "type": "number",
            "minimum": 1.0,
            "maximum": 4.0,
            "description": "Detection decimation factor",
        },
        "blur": {
            "type": "number",
            "minimum": 0.0,
            "maximum": 10.0,
            "description": "Gaussian blur sigma",
        },
        "refine_edges": {
            "type": "boolean",
            "description": "Whether to refine tag edges",
        },
        "decision_margin": {
            "type": "number",
            "minimum": 0.0,
            "maximum": 250.0,
            "description": "Minimum decision margin for tag acceptance",
        },
        "pose_iterations": {
            "type": "integer",
            "minimum": 0,
            "maximum": 500,
            "description": "Number of iterations for pose estimation refinement",
        },
        "decode_sharpening": {
            "type": "number",
            "minimum": 0.0,
            "maximum": 1.0,
            "description": "Sharpening for decode stage",
        },
        "multi_tag_enabled": {
            "type": "boolean",
            "description": "Enable multi-tag pose estimation for improved accuracy",
        },
        "ransac_reproj_threshold": {
            "type": "number",
            "minimum": 0.01,
            "maximum": 50.0,
            "description": "RANSAC reprojection threshold in pixels",
        },
        "ransac_confidence": {
            "type": "number",
            "minimum": 0.5,
            "maximum": 0.9999,
            "description": "Probability that the RANSAC solution is correct",
        },
        "min_inliers": {
            "type": "integer",
            "minimum": 4,
            "maximum": 200,
            "description": "Minimum inlier correspondences required for multi-tag pose",
        },
        "use_prev_guess": {
            "type": "boolean",
            "description": "Use the previous pose as an initial guess for RANSAC",
        },
        "publish_field_pose": {
            "type": "boolean",
            "description": "Publish the camera pose in field coordinates when layout is available",
        },
        "output_quaternion": {
            "type": "boolean",
            "description": "Include quaternion outputs alongside Euler angles",
        },
        "multi_tag_error_threshold": {
            "type": "number",
            "minimum": 0.0,
            "maximum": 100.0,
            "description": "Per-tag reprojection error threshold before pruning (pixels)",
        },
    },
    "additionalProperties": False,
}

ML_DETECTION_SCHEMA = {
    "type": "object",
    "properties": {
        "model_type": {
            "type": "string",
            "enum": ML_MODEL_TYPES,
            "description": "Indicates the format of the uploaded model",
        },
        "model_filename": {
            "type": "string",
            "pattern": "^[a-zA-Z0-9_\\-\\.]+$",
            "maxLength": 255,
            "description": "Model file name (must be alphanumeric with -, _, .)",
        },
        "labels_filename": {
            "type": "string",
            "pattern": "^[a-zA-Z0-9_\\-\\.]+$",
            "maxLength": 255,
            "description": "Labels file name (must be alphanumeric with -, _, .)",
        },
        "model_path": {
            "type": "string",
            "maxLength": 1024,
            "description": "Full path to model file (set by file upload)",
        },
        "labels_path": {
            "type": "string",
            "maxLength": 1024,
            "description": "Full path to labels file (set by file upload)",
        },
        "converted_onnx_path": {
            "type": "string",
            "maxLength": 1024,
            "description": "Path to converted ONNX model (for YOLO uploads)",
        },
        "converted_onnx_filename": {
            "type": "string",
            "pattern": "^[a-zA-Z0-9_\\-\\.]+$",
            "maxLength": 255,
            "description": "Filename of converted ONNX model stored for pipeline",
        },
        "rknn_path": {
            "type": "string",
            "maxLength": 1024,
            "description": "Path to RKNN model for Orange Pi NPU execution",
        },
        "onnx_provider": {
            "type": "string",
            "enum": ONNX_EXECUTION_PROVIDERS,
            "description": "ONNX Runtime execution provider to use",
        },
        "tflite_delegate": {
            "type": "string",
            "enum": TFLITE_DELEGATES,
            "description": "TFLite delegate to use for inference",
        },
        "accelerator": {
            "type": "string",
            "enum": ML_ACCELERATORS,
            "description": "Optional accelerator configuration (e.g., RKNN NPU)",
        },
        "confidence_threshold": {
            "type": "number",
            "minimum": 0.0,
            "maximum": 1.0,
            "description": "Minimum confidence for detections",
        },
        "nms_iou_threshold": {
            "type": "number",
            "minimum": 0.0,
            "maximum": 1.0,
            "description": "IoU threshold used during non-max suppression",
        },
        "max_detections": {
            "type": "integer",
            "minimum": 1,
            "maximum": 500,
            "description": "Maximum number of detections returned per frame",
        },
        "img_size": {
            "type": "integer",
            "minimum": 32,
            "maximum": 2048,
            "description": "Square input size expected by the model (e.g., 640)",
        },
        "target_classes": {
            "type": "array",
            "items": {"type": "string", "maxLength": 100},
            "maxItems": 100,
            "description": "List of target class names to detect",
        },
    },
    "additionalProperties": False,
}

COLOURED_SHAPE_SCHEMA = {
    "type": "object",
    "properties": {
        # Placeholder - can be extended when implementation is added
    },
    "additionalProperties": True,  # Allow any config for placeholder pipeline
}

# Map pipeline types to their schemas
PIPELINE_SCHEMAS = {
    PipelineType.APRILTAG.value: APRILTAG_SCHEMA,
    PipelineType.OBJECT_DETECTION_ML.value: ML_DETECTION_SCHEMA,
    PipelineType.COLOURED_SHAPE.value: COLOURED_SHAPE_SCHEMA,
}


class ValidationError(Exception):
    """Raised when configuration validation fails."""

    pass


def _validate_ml_pipeline_relationships(config: Dict[str, Any]) -> None:
    """Performs cross-field validation for ML object detection pipeline configs."""

    model_type = config.get("model_type")
    accelerator = config.get("accelerator", "none")

    if model_type and model_type not in ML_MODEL_TYPES:
        raise ValidationError(
            f"Unsupported model_type '{model_type}'. Expected one of {ML_MODEL_TYPES}."
        )

    if accelerator not in ML_ACCELERATORS:
        raise ValidationError(
            f"Unsupported accelerator '{accelerator}'. Expected one of {ML_ACCELERATORS}."
        )

    if model_type == "yolo":
        # ONNX provider is required for YOLO execution (unless RKNN is selected)
        if accelerator != "rknn":
            provider = config.get("onnx_provider")
            if provider not in ONNX_EXECUTION_PROVIDERS:
                raise ValidationError(
                    "onnx_provider must be one of "
                    f"{ONNX_EXECUTION_PROVIDERS} when using YOLO without RKNN."
                )
        if "tflite_delegate" in config:
            raise ValidationError(
                "tflite_delegate is not applicable when model_type is 'yolo'."
            )
        if "rknn_path" in config and accelerator != "rknn":
            raise ValidationError(
                "rknn_path provided but accelerator is not set to 'rknn'."
            )
    elif model_type == "tflite":
        delegate = config.get("tflite_delegate")
        if delegate not in TFLITE_DELEGATES:
            raise ValidationError(
                f"tflite_delegate must be one of {TFLITE_DELEGATES} when using TFLite."
            )
        if config.get("onnx_provider"):
            raise ValidationError(
                "onnx_provider is not applicable when model_type is 'tflite'."
            )
        if accelerator == "rknn":
            raise ValidationError(
                "accelerator 'rknn' is only valid for YOLO/ONNX models on Orange Pi 5."
            )

    if accelerator == "rknn":
        rknn_path = config.get("rknn_path")
        if not rknn_path:
            raise ValidationError(
                "rknn_path is required when accelerator is set to 'rknn'."
            )
        if not config.get("converted_onnx_path"):
            raise ValidationError(
                "converted_onnx_path is required when accelerator is 'rknn'."
            )


def validate_type(value: Any, expected_type: str, path: str = "") -> None:
    """Validates that a value matches the expected JSON schema type."""
    type_map = {
        "string": str,
        "integer": int,
        "number": (int, float),
        "boolean": bool,
        "array": list,
        "object": dict,
    }

    if expected_type not in type_map:
        raise ValidationError(f"Unknown type '{expected_type}' in schema")

    expected_python_type = type_map[expected_type]
    if not isinstance(value, expected_python_type):
        raise ValidationError(
            f"Invalid type at '{path}': expected {expected_type}, got {type(value).__name__}"
        )


def validate_string_constraints(value: str, constraints: Dict, path: str) -> None:
    """Validates string-specific constraints."""
    if "enum" in constraints:
        if value not in constraints["enum"]:
            raise ValidationError(
                f"Invalid value at '{path}': '{value}' not in allowed values {constraints['enum']}"
            )

    if "pattern" in constraints:
        import re

        if not re.match(constraints["pattern"], value):
            raise ValidationError(
                f"Invalid format at '{path}': '{value}' does not match pattern {constraints['pattern']}"
            )

    if "maxLength" in constraints:
        if len(value) > constraints["maxLength"]:
            raise ValidationError(
                f"String too long at '{path}': {len(value)} > {constraints['maxLength']}"
            )


def validate_number_constraints(value: float, constraints: Dict, path: str) -> None:
    """Validates number-specific constraints."""
    if "minimum" in constraints:
        if value < constraints["minimum"]:
            raise ValidationError(
                f"Value too small at '{path}': {value} < {constraints['minimum']}"
            )

    if "maximum" in constraints:
        if value > constraints["maximum"]:
            raise ValidationError(
                f"Value too large at '{path}': {value} > {constraints['maximum']}"
            )


def validate_array_constraints(
    value: list, constraints: Dict, path: str, schema: Dict
) -> None:
    """Validates array-specific constraints."""
    if "maxItems" in constraints:
        if len(value) > constraints["maxItems"]:
            raise ValidationError(
                f"Array too long at '{path}': {len(value)} > {constraints['maxItems']}"
            )

    if "items" in constraints:
        for i, item in enumerate(value):
            validate_value(item, constraints["items"], f"{path}[{i}]", schema)


def validate_value(
    value: Any, property_schema: Dict, path: str, parent_schema: Dict
) -> None:
    """Validates a single value against its schema definition."""
    expected_type = property_schema.get("type")
    if expected_type:
        validate_type(value, expected_type, path)

        if expected_type == "string":
            validate_string_constraints(value, property_schema, path)
        elif expected_type in ("number", "integer"):
            validate_number_constraints(value, property_schema, path)
        elif expected_type == "array":
            validate_array_constraints(value, property_schema, path, parent_schema)


def validate_pipeline_config(
    pipeline_type: str, config: Dict[str, Any]
) -> ValidationResult:
    """
    Validates a pipeline configuration against its schema.

    Args:
        pipeline_type: The type of pipeline (e.g., "AprilTag", "Object Detection (ML)")
        config: The configuration dictionary to validate

    Returns:
        ValidationResult with is_valid boolean and optional error_message
    """
    # Check if pipeline type is known
    if pipeline_type not in PIPELINE_SCHEMAS:
        return ValidationResult.failure(f"Unknown pipeline type: '{pipeline_type}'")

    schema = PIPELINE_SCHEMAS[pipeline_type]

    # Ensure config is a dictionary
    if not isinstance(config, dict):
        return ValidationResult.failure(
            f"Config must be an object/dictionary, got {type(config).__name__}"
        )

    try:
        # Validate each property in config
        for key, value in config.items():
            if key in schema["properties"]:
                property_schema = schema["properties"][key]
                validate_value(value, property_schema, key, schema)
            elif not schema.get("additionalProperties", False):
                # Schema doesn't allow additional properties
                return ValidationResult.failure(
                    f"Unknown property '{key}' not allowed for {pipeline_type} pipeline"
                )

        if pipeline_type == PipelineType.OBJECT_DETECTION_ML.value:
            _validate_ml_pipeline_relationships(config)

        # All validations passed
        return ValidationResult.success()

    except ValidationError as e:
        return ValidationResult.failure(str(e))
    except Exception as e:
        return ValidationResult.failure(f"Validation error: {str(e)}")


def get_default_config(pipeline_type: str) -> Dict[str, Any]:
    """
    Returns a default configuration for a given pipeline type.

    Args:
        pipeline_type: The type of pipeline

    Returns:
        A dictionary containing safe default values
    """
    recommended_threads = recommended_apriltag_threads()
    defaults = {
        "AprilTag": {
            "family": "tag36h11",
            "error_correction": 2,
            "tag_size_m": 0.165,
            "threads": recommended_threads,
            "auto_threads": True,
            "decimate": 1.0,
            "blur": 0.0,
            "refine_edges": True,
            "decision_margin": 35.0,
            "pose_iterations": 40,
            "decode_sharpening": 0.25,
            "multi_tag_enabled": False,
            "ransac_reproj_threshold": 1.2,
            "ransac_confidence": 0.999,
            "min_inliers": 12,
            "use_prev_guess": True,
            "publish_field_pose": True,
            "output_quaternion": True,
            "multi_tag_error_threshold": 6.0,
        },
        "Object Detection (ML)": {
            "model_type": "yolo",
            "confidence_threshold": 0.5,
            "nms_iou_threshold": 0.45,
            "target_classes": [],
            "onnx_provider": "CPUExecutionProvider",
            "accelerator": "none",
            "max_detections": 100,
            "img_size": 640,
        },
        "Coloured Shape": {},
    }

    return defaults.get(pipeline_type, {})
