"""Integration tests for pipeline routes with validation."""

import pytest
import json
from app.models import Camera, Pipeline
from app.extensions import db


def test_update_pipeline_config_valid(client):
    """Test updating pipeline config with valid data."""
    # Create a test camera and pipeline
    camera = Camera(name="Test Camera", identifier="test_valid_0", camera_type="USB", orientation=0)
    db.session.add(camera)
    db.session.commit()

    pipeline = Pipeline(
        name="Test Pipeline",
        pipeline_type="AprilTag",
        config=json.dumps({}),
        camera_id=camera.id
    )
    db.session.add(pipeline)
    db.session.commit()

    pipeline_id = pipeline.id

    # Valid configuration
    valid_config = {
        "family": "tag36h11",
        "tag_size_m": 0.165,
        "threads": 4
    }

    response = client.put(
        f'/api/pipelines/{pipeline_id}/config',
        data=json.dumps(valid_config),
        content_type='application/json'
    )

    assert response.status_code == 200
    data = json.loads(response.data)
    assert data['success'] is True


def test_update_pipeline_config_invalid(client):
    """Test updating pipeline config with invalid data."""
    camera = Camera(name="Test Camera", identifier="test_invalid_0", camera_type="USB", orientation=0)
    db.session.add(camera)
    db.session.commit()

    pipeline = Pipeline(
        name="Test Pipeline",
        pipeline_type="AprilTag",
        config=json.dumps({}),
        camera_id=camera.id
    )
    db.session.add(pipeline)
    db.session.commit()

    pipeline_id = pipeline.id

    # Invalid configuration - tag_size_m too large
    invalid_config = {
        "tag_size_m": 100.0  # Maximum is 10.0
    }

    response = client.put(
        f'/api/pipelines/{pipeline_id}/config',
        data=json.dumps(invalid_config),
        content_type='application/json'
    )

    assert response.status_code == 400
    data = json.loads(response.data)
    assert 'error' in data
    assert 'Invalid configuration' in data['error']
    assert 'details' in data
    assert 'tag_size_m' in data['details']


def test_update_pipeline_config_malicious_property(client):
    """Test that malicious properties are rejected."""
    camera = Camera(name="Test Camera", identifier="test_malicious_0", camera_type="USB", orientation=0)
    db.session.add(camera)
    db.session.commit()

    pipeline = Pipeline(
        name="Test Pipeline",
        pipeline_type="AprilTag",
        config=json.dumps({}),
        camera_id=camera.id
    )
    db.session.add(pipeline)
    db.session.commit()

    pipeline_id = pipeline.id

    # Configuration with unknown property
    malicious_config = {
        "family": "tag36h11",
        "malicious_code": "__import__('os').system('rm -rf /')"
    }

    response = client.put(
        f'/api/pipelines/{pipeline_id}/config',
        data=json.dumps(malicious_config),
        content_type='application/json'
    )

    assert response.status_code == 400
    data = json.loads(response.data)
    assert 'error' in data
    assert 'malicious_code' in data['details']


def test_update_pipeline_config_type_mismatch(client):
    """Test that type mismatches are detected."""
    camera = Camera(name="Test Camera", identifier="test_type_mismatch_0", camera_type="USB", orientation=0)
    db.session.add(camera)
    db.session.commit()

    pipeline = Pipeline(
        name="Test Pipeline",
        pipeline_type="AprilTag",
        config=json.dumps({}),
        camera_id=camera.id
    )
    db.session.add(pipeline)
    db.session.commit()

    pipeline_id = pipeline.id

    # Wrong type - threads should be integer
    invalid_config = {
        "threads": "not_a_number"
    }

    response = client.put(
        f'/api/pipelines/{pipeline_id}/config',
        data=json.dumps(invalid_config),
        content_type='application/json'
    )

    assert response.status_code == 400
    data = json.loads(response.data)
    assert 'error' in data
    assert 'threads' in data['details']
    assert 'type' in data['details'].lower()


def test_add_pipeline_uses_default_config(client):
    """Test that adding a pipeline uses validated default config."""
    camera = Camera(name="Test Camera", identifier="test_default_config_0", camera_type="USB", orientation=0)
    db.session.add(camera)
    db.session.commit()

    camera_id = camera.id

    response = client.post(
        f'/api/cameras/{camera_id}/pipelines',
        data=json.dumps({
            "name": "New Pipeline",
            "pipeline_type": "AprilTag"
        }),
        content_type='application/json'
    )

    assert response.status_code == 200
    data = json.loads(response.data)
    assert data['success'] is True

    # Verify the default config was applied
    pipeline_data = data['pipeline']
    config = json.loads(pipeline_data['config'])
    assert 'family' in config
    assert 'tag_size_m' in config
    assert config['family'] == 'tag36h11'


def test_update_ml_pipeline_config_valid(client):
    """Test updating ML pipeline config with valid data."""
    camera = Camera(name="Test Camera", identifier="test_ml_valid_0", camera_type="USB", orientation=0)
    db.session.add(camera)
    db.session.commit()

    pipeline = Pipeline(
        name="ML Pipeline",
        pipeline_type="Object Detection (ML)",
        config=json.dumps({}),
        camera_id=camera.id
    )
    db.session.add(pipeline)
    db.session.commit()

    pipeline_id = pipeline.id

    valid_config = {
        "confidence_threshold": 0.7,
        "target_classes": ["person", "car", "dog"]
    }

    response = client.put(
        f'/api/pipelines/{pipeline_id}/config',
        data=json.dumps(valid_config),
        content_type='application/json'
    )

    assert response.status_code == 200
    data = json.loads(response.data)
    assert data['success'] is True


def test_update_ml_pipeline_config_invalid_filename(client):
    """Test that path traversal attempts in filenames are rejected."""
    camera = Camera(name="Test Camera", identifier="test_ml_invalid_filename_0", camera_type="USB", orientation=0)
    db.session.add(camera)
    db.session.commit()

    pipeline = Pipeline(
        name="ML Pipeline",
        pipeline_type="Object Detection (ML)",
        config=json.dumps({}),
        camera_id=camera.id
    )
    db.session.add(pipeline)
    db.session.commit()

    pipeline_id = pipeline.id

    # Attempt path traversal
    malicious_config = {
        "model_filename": "../../../etc/passwd"
    }

    response = client.put(
        f'/api/pipelines/{pipeline_id}/config',
        data=json.dumps(malicious_config),
        content_type='application/json'
    )

    assert response.status_code == 400
    data = json.loads(response.data)
    assert 'error' in data
    assert 'model_filename' in data['details']


def test_update_pipeline_config_nonexistent_pipeline(client):
    """Test updating config for non-existent pipeline."""
    response = client.put(
        '/api/pipelines/99999/config',
        data=json.dumps({"family": "tag36h11"}),
        content_type='application/json'
    )

    assert response.status_code == 404
    if response.data:
        data = json.loads(response.data)
        assert 'error' in data
        assert 'not found' in data['error'].lower()


def test_update_pipeline_config_null_config(client):
    """Test updating pipeline with null/None config."""
    camera = Camera(name="Test Camera", identifier="test_null_config_0", camera_type="USB", orientation=0)
    db.session.add(camera)
    db.session.commit()

    pipeline = Pipeline(
        name="Test Pipeline",
        pipeline_type="AprilTag",
        config=json.dumps({}),
        camera_id=camera.id
    )
    db.session.add(pipeline)
    db.session.commit()

    pipeline_id = pipeline.id

    response = client.put(
        f'/api/pipelines/{pipeline_id}/config',
        data='null',
        content_type='application/json'
    )

    assert response.status_code == 400
    data = json.loads(response.data)
    assert 'error' in data
