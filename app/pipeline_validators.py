"""
Pipeline configuration validators.

Provides JSON schema validation for each pipeline type to prevent
malicious or malformed configurations from crashing vision processing threads.
"""

from typing import Dict, Any, Tuple, Optional


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
    },
    "additionalProperties": False,
}

ML_DETECTION_SCHEMA = {
    "type": "object",
    "properties": {
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
        "confidence_threshold": {
            "type": "number",
            "minimum": 0.0,
            "maximum": 1.0,
            "description": "Minimum confidence for detections",
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
    "AprilTag": APRILTAG_SCHEMA,
    "Object Detection (ML)": ML_DETECTION_SCHEMA,
    "Coloured Shape": COLOURED_SHAPE_SCHEMA,
}


class ValidationError(Exception):
    """Raised when configuration validation fails."""

    pass


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
) -> Tuple[bool, Optional[str]]:
    """
    Validates a pipeline configuration against its schema.

    Args:
        pipeline_type: The type of pipeline (e.g., "AprilTag", "Object Detection (ML)")
        config: The configuration dictionary to validate

    Returns:
        Tuple of (is_valid, error_message)
        - (True, None) if valid
        - (False, error_message) if invalid
    """
    # Check if pipeline type is known
    if pipeline_type not in PIPELINE_SCHEMAS:
        return False, f"Unknown pipeline type: '{pipeline_type}'"

    schema = PIPELINE_SCHEMAS[pipeline_type]

    # Ensure config is a dictionary
    if not isinstance(config, dict):
        return (
            False,
            f"Config must be an object/dictionary, got {type(config).__name__}",
        )

    try:
        # Validate each property in config
        for key, value in config.items():
            if key in schema["properties"]:
                property_schema = schema["properties"][key]
                validate_value(value, property_schema, key, schema)
            elif not schema.get("additionalProperties", False):
                # Schema doesn't allow additional properties
                return (
                    False,
                    f"Unknown property '{key}' not allowed for {pipeline_type} pipeline",
                )

        # All validations passed
        return True, None

    except ValidationError as e:
        return False, str(e)
    except Exception as e:
        return False, f"Validation error: {str(e)}"


def get_default_config(pipeline_type: str) -> Dict[str, Any]:
    """
    Returns a default configuration for a given pipeline type.

    Args:
        pipeline_type: The type of pipeline

    Returns:
        A dictionary containing safe default values
    """
    defaults = {
        "AprilTag": {
            "family": "tag36h11",
            "error_correction": 3,
            "tag_size_m": 0.165,
            "threads": 2,
            "decimate": 1.0,
            "blur": 0.0,
            "refine_edges": True,
        },
        "Object Detection (ML)": {"confidence_threshold": 0.5, "target_classes": []},
        "Coloured Shape": {},
    }

    return defaults.get(pipeline_type, {})
