"""Pipeline business logic service layer."""

import json
import logging
import os
from typing import Optional, Dict, Any, List, Tuple

from app.extensions import db
from app.enums import PipelineType
from app.models import Pipeline, Camera
from app.pipeline_validators import validate_pipeline_config, get_default_config, ValidationResult
from app.services.model_service import ModelService
from app.utils.config import DATA_DIR
from app.utils.camera_config import PipelineManagerConfig
from app import camera_manager

logger = logging.getLogger(__name__)


class PipelineService:
    """Service class for pipeline-related business logic."""

    @staticmethod
    def get_pipeline_by_id(pipeline_id: int) -> Optional[Pipeline]:
        """
        Retrieve a pipeline by its ID.

        Args:
            pipeline_id: The pipeline's database ID

        Returns:
            Pipeline object or None if not found
        """
        return db.session.get(Pipeline, pipeline_id)

    @staticmethod
    def get_pipelines_for_camera(camera_id: int) -> List[Pipeline]:
        """
        Get all pipelines for a specific camera.

        Args:
            camera_id: The camera's database ID

        Returns:
            List of Pipeline objects
        """
        camera = db.session.get(Camera, camera_id)
        if not camera:
            return []
        return camera.pipelines

    @staticmethod
    def create_pipeline(
        camera_id: int,
        name: str,
        pipeline_type: str,
        config: Optional[Dict[str, Any]] = None
    ) -> Tuple[Optional[Pipeline], Optional[str]]:
        """
        Create a new pipeline for a camera.

        Args:
            camera_id: The camera's database ID
            name: Human-readable name for the pipeline
            pipeline_type: Type of pipeline (AprilTag, etc.)
            config: Optional configuration dict. If None, uses default config.

        Returns:
            Tuple of (Pipeline object, error message). If successful, error is None.
        """
        # Verify camera exists
        camera = db.session.get(Camera, camera_id)
        if not camera:
            return None, "Camera not found"

        # Use default config if not provided
        if config is None:
            config = get_default_config(pipeline_type)

        # Validate configuration
        validation_result = validate_pipeline_config(pipeline_type, config)
        if not validation_result.is_valid:
            return None, validation_result.error_message

        try:
            new_pipeline = Pipeline(
                name=name,
                pipeline_type=pipeline_type,
                config=json.dumps(config),
                camera_id=camera_id,
            )
            db.session.add(new_pipeline)
            db.session.commit()

            logger.info(f"Created pipeline {new_pipeline.id}: {name} for camera {camera_id}")
            return new_pipeline, None

        except Exception as e:
            db.session.rollback()
            logger.error(f"Error creating pipeline: {e}")
            return None, str(e)

    @staticmethod
    def update_pipeline_metadata(
        pipeline_id: int,
        name: Optional[str] = None,
        pipeline_type: Optional[str] = None
    ) -> Tuple[bool, Optional[str]]:
        """
        Update pipeline metadata (name, type).

        Args:
            pipeline_id: The pipeline's database ID
            name: New name for the pipeline
            pipeline_type: New pipeline type

        Returns:
            Tuple of (success boolean, error message)
        """
        pipeline = PipelineService.get_pipeline_by_id(pipeline_id)
        if not pipeline:
            return False, "Pipeline not found"

        try:
            if name is not None:
                pipeline.name = name
            if pipeline_type is not None:
                pipeline.pipeline_type = pipeline_type

            db.session.commit()
            logger.info(f"Updated pipeline {pipeline_id} metadata")
            return True, None

        except Exception as e:
            db.session.rollback()
            logger.error(f"Error updating pipeline metadata: {e}")
            return False, str(e)

    @staticmethod
    def update_pipeline_config(
        pipeline_id: int,
        config: Dict[str, Any]
    ) -> Tuple[bool, Optional[str]]:
        """
        Update a pipeline's configuration.

        Args:
            pipeline_id: The pipeline's database ID
            config: New configuration dictionary

        Returns:
            Tuple of (success boolean, error message)
        """
        pipeline = PipelineService.get_pipeline_by_id(pipeline_id)
        if not pipeline:
            return False, "Pipeline not found"

        # Validate configuration
        validation_result = validate_pipeline_config(pipeline.pipeline_type, config)
        if not validation_result.is_valid:
            return False, validation_result.error_message

        try:
            pipeline.config = json.dumps(config)
            db.session.commit()
            logger.info(f"Updated pipeline {pipeline_id} configuration")
            return True, None

        except Exception as e:
            db.session.rollback()
            logger.error(f"Error updating pipeline config: {e}")
            return False, str(e)

    @staticmethod
    def delete_pipeline(pipeline_id: int) -> Tuple[bool, Optional[int], Optional[str]]:
        """
        Delete a pipeline from the database.

        Args:
            pipeline_id: The pipeline's database ID

        Returns:
            Tuple of (success, camera_id, error_message)
        """
        pipeline = PipelineService.get_pipeline_by_id(pipeline_id)
        if not pipeline:
            return False, None, "Pipeline not found"

        try:
            camera_id = pipeline.camera_id
            db.session.delete(pipeline)
            db.session.commit()
            logger.info(f"Deleted pipeline {pipeline_id}")
            return True, camera_id, None

        except Exception as e:
            db.session.rollback()
            logger.error(f"Error deleting pipeline: {e}")
            return False, None, str(e)

    @staticmethod
    def validate_config(pipeline_type: str, config: Dict[str, Any]) -> ValidationResult:
        """
        Validate a pipeline configuration.

        Args:
            pipeline_type: Type of pipeline
            config: Configuration dictionary to validate

        Returns:
            ValidationResult object
        """
        return validate_pipeline_config(pipeline_type, config)

    @staticmethod
    def get_default_config(pipeline_type: str) -> Dict[str, Any]:
        """
        Get default configuration for a pipeline type.

        Args:
            pipeline_type: Type of pipeline

        Returns:
            Default configuration dictionary
        """
        return get_default_config(pipeline_type)

    @staticmethod
    def sync_pipeline_to_camera_manager(pipeline: Pipeline) -> bool:
        """
        Synchronize a pipeline to the camera manager.

        Args:
            pipeline: Pipeline object to sync

        Returns:
            True if successful, False otherwise
        """
        camera = db.session.get(Camera, pipeline.camera_id)
        if not camera:
            logger.error(f"Cannot sync pipeline {pipeline.id}: camera {pipeline.camera_id} not found")
            return False

        try:
            config = PipelineManagerConfig(
                pipeline_id=pipeline.id,
                pipeline_type=pipeline.pipeline_type,
                pipeline_config_json=pipeline.config,
                camera_matrix_json=camera.camera_matrix_json,
                dist_coeffs_json=camera.dist_coeffs_json,
            )
            camera_manager.update_pipeline_in_camera(camera.identifier, config)
            return True
        except Exception as e:
            logger.error(f"Error syncing pipeline {pipeline.id} to camera manager: {e}")
            return False

    @staticmethod
    def add_pipeline_to_camera_manager(pipeline: Pipeline) -> bool:
        """
        Add a pipeline to the camera manager.

        Args:
            pipeline: Pipeline object to add

        Returns:
            True if successful, False otherwise
        """
        camera = db.session.get(Camera, pipeline.camera_id)
        if not camera:
            logger.error(f"Cannot add pipeline {pipeline.id}: camera {pipeline.camera_id} not found")
            return False

        try:
            config = PipelineManagerConfig(
                pipeline_id=pipeline.id,
                pipeline_type=pipeline.pipeline_type,
                pipeline_config_json=pipeline.config,
                camera_matrix_json=camera.camera_matrix_json,
                dist_coeffs_json=camera.dist_coeffs_json,
            )
            camera_manager.add_pipeline_to_camera(camera.identifier, config)
            return True
        except Exception as e:
            logger.error(f"Error adding pipeline {pipeline.id} to camera manager: {e}")
            return False

    @staticmethod
    def remove_pipeline_from_camera_manager(camera_identifier: str, pipeline_id: int) -> bool:
        """
        Remove a pipeline from the camera manager.

        Args:
            camera_identifier: Camera's unique identifier
            pipeline_id: Pipeline's database ID

        Returns:
            True if successful, False otherwise
        """
        try:
            camera_manager.remove_pipeline_from_camera(camera_identifier, pipeline_id)
            return True
        except Exception as e:
            logger.error(f"Error removing pipeline {pipeline_id} from camera manager: {e}")
            return False

    @staticmethod
    def get_pipeline_config_dict(pipeline: Pipeline) -> Dict[str, Any]:
        """
        Get pipeline configuration as a dictionary.

        Args:
            pipeline: Pipeline object

        Returns:
            Configuration dictionary
        """
        try:
            return json.loads(pipeline.config) if pipeline.config else {}
        except json.JSONDecodeError:
            logger.error(f"Invalid JSON in pipeline {pipeline.id} config")
            return {}

    @staticmethod
    def get_pipeline_labels(pipeline_id: int) -> Tuple[Optional[List[str]], Optional[str], Optional[str]]:
        """
        Get labels for a pipeline and validate configuration.

        Args:
            pipeline_id: Pipeline's database ID

        Returns:
            Tuple of (labels list, error_message, error_details)
            If successful: (labels, None, None)
            If error: (None, error_msg, error_details)
        """
        pipeline = PipelineService.get_pipeline_by_id(pipeline_id)
        if not pipeline:
            return None, "Pipeline not found", None

        config = PipelineService.get_pipeline_config_dict(pipeline)

        # Get labels path
        labels_path = config.get("labels_path")
        if not labels_path and config.get("labels_filename"):
            labels_path = os.path.join(DATA_DIR, config["labels_filename"])

        # Get labels from file
        labels = ModelService.get_labels_from_file(labels_path) if labels_path else []

        # Validate pipeline configuration
        validation_result = validate_pipeline_config(pipeline.pipeline_type, config)

        if not validation_result.is_valid:
            return None, "Invalid configuration", validation_result.error_message

        # Additional check for ML pipelines
        if (
            pipeline.pipeline_type == PipelineType.OBJECT_DETECTION_ML.value
            and labels
            and not config.get("model_path")
        ):
            error_details = (
                "Model path missing for ML pipeline; upload a model and ensure calibration "
                "values such as tag_size_m are set before deploying."
            )
            return None, "Invalid configuration", error_details

        return labels, None, None
