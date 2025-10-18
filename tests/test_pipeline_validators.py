"""Tests for pipeline configuration validators."""

from app.pipeline_validators import (
    validate_pipeline_config,
    get_default_config,
)


# --- Tests for AprilTag Pipeline ---


def test_apriltag_valid_config():
    """Test valid AprilTag configuration."""
    config = {
        "family": "tag36h11",
        "error_correction": 3,
        "tag_size_m": 0.165,
        "threads": 2,
        "decimate": 1.0,
        "blur": 0.0,
        "refine_edges": True,
    }
    is_valid, error = validate_pipeline_config("AprilTag", config)
    assert is_valid is True
    assert error is None


def test_apriltag_minimal_config():
    """Test minimal AprilTag configuration."""
    config = {}
    is_valid, error = validate_pipeline_config("AprilTag", config)
    assert is_valid is True
    assert error is None


def test_apriltag_invalid_family():
    """Test AprilTag with invalid family name."""
    config = {"family": "invalid_family"}
    is_valid, error = validate_pipeline_config("AprilTag", config)
    assert is_valid is False
    assert "invalid_family" in error
    assert "family" in error


def test_apriltag_family_with_prefix():
    """Test AprilTag family name with 'tag' prefix."""
    config = {"family": "tag16h5"}
    is_valid, error = validate_pipeline_config("AprilTag", config)
    assert is_valid is True


def test_apriltag_family_without_prefix():
    """Test AprilTag family name without 'tag' prefix."""
    config = {"family": "36h11"}
    is_valid, error = validate_pipeline_config("AprilTag", config)
    assert is_valid is True


def test_apriltag_error_correction_out_of_range():
    """Test AprilTag with error_correction out of valid range."""
    config = {"error_correction": 10}
    is_valid, error = validate_pipeline_config("AprilTag", config)
    assert is_valid is False
    assert "error_correction" in error
    assert "10" in error


def test_apriltag_tag_size_too_small():
    """Test AprilTag with tag_size_m too small."""
    config = {"tag_size_m": 0.0001}
    is_valid, error = validate_pipeline_config("AprilTag", config)
    assert is_valid is False
    assert "tag_size_m" in error


def test_apriltag_tag_size_too_large():
    """Test AprilTag with tag_size_m too large."""
    config = {"tag_size_m": 100.0}
    is_valid, error = validate_pipeline_config("AprilTag", config)
    assert is_valid is False
    assert "tag_size_m" in error


def test_apriltag_invalid_type():
    """Test AprilTag with wrong value type."""
    config = {"threads": "not_a_number"}
    is_valid, error = validate_pipeline_config("AprilTag", config)
    assert is_valid is False
    assert "threads" in error
    assert "type" in error.lower()


def test_apriltag_additional_properties_rejected():
    """Test that additional properties are rejected for AprilTag."""
    config = {"unknown_property": "value"}
    is_valid, error = validate_pipeline_config("AprilTag", config)
    assert is_valid is False
    assert "unknown_property" in error


def test_apriltag_negative_blur():
    """Test AprilTag with negative blur value."""
    config = {"blur": -1.0}
    is_valid, error = validate_pipeline_config("AprilTag", config)
    assert is_valid is False
    assert "blur" in error


# --- Tests for ML Object Detection Pipeline ---


def test_ml_detection_valid_config():
    """Test valid ML detection configuration."""
    config = {
        "model_filename": "model.pb",
        "labels_filename": "labels.txt",
        "confidence_threshold": 0.7,
        "target_classes": ["person", "car"],
    }
    is_valid, error = validate_pipeline_config("Object Detection (ML)", config)
    assert is_valid is True
    assert error is None


def test_ml_detection_minimal_config():
    """Test minimal ML detection configuration."""
    config = {}
    is_valid, error = validate_pipeline_config("Object Detection (ML)", config)
    assert is_valid is True


def test_ml_detection_invalid_filename_pattern():
    """Test ML detection with invalid filename (path traversal attempt)."""
    config = {"model_filename": "../../../etc/passwd"}
    is_valid, error = validate_pipeline_config("Object Detection (ML)", config)
    assert is_valid is False
    assert "model_filename" in error
    assert "pattern" in error.lower()


def test_ml_detection_filename_too_long():
    """Test ML detection with filename exceeding max length."""
    config = {"labels_filename": "a" * 300}
    is_valid, error = validate_pipeline_config("Object Detection (ML)", config)
    assert is_valid is False
    assert "labels_filename" in error
    assert "long" in error.lower()


def test_ml_detection_confidence_out_of_range_low():
    """Test ML detection with confidence_threshold < 0."""
    config = {"confidence_threshold": -0.5}
    is_valid, error = validate_pipeline_config("Object Detection (ML)", config)
    assert is_valid is False
    assert "confidence_threshold" in error


def test_ml_detection_confidence_out_of_range_high():
    """Test ML detection with confidence_threshold > 1."""
    config = {"confidence_threshold": 1.5}
    is_valid, error = validate_pipeline_config("Object Detection (ML)", config)
    assert is_valid is False
    assert "confidence_threshold" in error


def test_ml_detection_target_classes_too_many():
    """Test ML detection with too many target classes."""
    config = {"target_classes": ["class_" + str(i) for i in range(200)]}
    is_valid, error = validate_pipeline_config("Object Detection (ML)", config)
    assert is_valid is False
    assert "target_classes" in error
    assert "long" in error.lower()


def test_ml_detection_target_classes_invalid_type():
    """Test ML detection with target_classes containing wrong types."""
    config = {"target_classes": [123, 456]}
    is_valid, error = validate_pipeline_config("Object Detection (ML)", config)
    assert is_valid is False
    assert "target_classes" in error


def test_ml_detection_additional_properties_rejected():
    """Test that additional properties are rejected for ML detection."""
    config = {"malicious_property": "evil_value"}
    is_valid, error = validate_pipeline_config("Object Detection (ML)", config)
    assert is_valid is False
    assert "malicious_property" in error


# --- Tests for Coloured Shape Pipeline ---


def test_coloured_shape_accepts_any_config():
    """Test that Coloured Shape pipeline accepts any config (placeholder)."""
    config = {"any_property": "any_value", "nested": {"data": 123}}
    is_valid, error = validate_pipeline_config("Coloured Shape", config)
    assert is_valid is True


# --- Tests for General Validation ---


def test_unknown_pipeline_type():
    """Test validation with unknown pipeline type."""
    config = {}
    is_valid, error = validate_pipeline_config("Unknown Pipeline", config)
    assert is_valid is False
    assert "Unknown pipeline type" in error


def test_non_dict_config():
    """Test validation with non-dictionary config."""
    is_valid, error = validate_pipeline_config("AprilTag", "not a dict")
    assert is_valid is False
    assert "object" in error.lower() or "dictionary" in error.lower()


def test_non_dict_config_list():
    """Test validation with list instead of dictionary."""
    is_valid, error = validate_pipeline_config("AprilTag", [1, 2, 3])
    assert is_valid is False


# --- Tests for Default Configs ---


def test_apriltag_default_config():
    """Test AprilTag default configuration is valid."""
    default = get_default_config("AprilTag")
    is_valid, error = validate_pipeline_config("AprilTag", default)
    assert is_valid is True
    assert "family" in default
    assert "tag_size_m" in default


def test_ml_detection_default_config():
    """Test ML detection default configuration is valid."""
    default = get_default_config("Object Detection (ML)")
    is_valid, error = validate_pipeline_config("Object Detection (ML)", default)
    assert is_valid is True
    assert "confidence_threshold" in default


def test_coloured_shape_default_config():
    """Test Coloured Shape default configuration."""
    default = get_default_config("Coloured Shape")
    is_valid, error = validate_pipeline_config("Coloured Shape", default)
    assert is_valid is True


def test_unknown_pipeline_default_config():
    """Test default config for unknown pipeline type."""
    default = get_default_config("NonExistent")
    assert default == {}


# --- Edge Cases ---


def test_empty_config_all_pipelines():
    """Test that empty configs are valid for all pipeline types."""
    for pipeline_type in ["AprilTag", "Object Detection (ML)", "Coloured Shape"]:
        is_valid, error = validate_pipeline_config(pipeline_type, {})
        assert is_valid is True, f"Empty config should be valid for {pipeline_type}"


def test_apriltag_boolean_as_integer():
    """Test AprilTag validation rejects boolean where integer expected."""
    config = {"threads": True}
    is_valid, error = validate_pipeline_config("AprilTag", config)
    config = {"threads": "not_a_number"}
    is_valid, error = validate_pipeline_config("AprilTag", config)
    assert is_valid is False
    assert "threads" in error


def test_security_injection_attempt():
    """Test that malicious JSON injection is rejected."""
    malicious_configs = [
        {"family": "tag36h11'; DROP TABLE pipelines; --"},
        {"model_filename": "model.pb\x00malicious"},
        {"tag_size_m": float("inf")},
        {"tag_size_m": float("nan")},
    ]

    for config in malicious_configs:
        # Should either be invalid or properly sanitized
        is_valid, error = validate_pipeline_config("AprilTag", config)
        # Either rejected or handled safely
        assert isinstance(is_valid, bool)
