"""Factory patterns for creating pipeline and driver instances."""

import logging
from typing import Any, Callable, Dict

from app.enums import CameraType, PipelineType
from app.utils.camera_config import CameraConfig

logger = logging.getLogger(__name__)


class PipelineFactory:
    """Factory for creating vision pipeline instances."""

    _registry: Dict[PipelineType, Callable[[Dict[str, Any]], Any]] = {}

    @classmethod
    def register(cls, pipeline_type: PipelineType, creator: Callable[[Dict[str, Any]], Any]) -> None:
        """
        Register a pipeline creator function.

        Args:
            pipeline_type: The type of pipeline
            creator: A callable that takes a config dict and returns a pipeline instance
        """
        cls._registry[pipeline_type] = creator
        logger.debug(f"Registered pipeline creator for {pipeline_type}")

    @classmethod
    def create(cls, pipeline_type: str, config: Dict[str, Any]) -> Any:
        """
        Create a pipeline instance.

        Args:
            pipeline_type: The type of pipeline (string)
            config: Pipeline configuration dictionary

        Returns:
            Pipeline instance

        Raises:
            ValueError: If pipeline type is unknown
        """
        try:
            # Convert string to enum
            enum_type = PipelineType.from_string(pipeline_type)
        except ValueError as e:
            logger.error(f"Unknown pipeline type: {pipeline_type}")
            raise ValueError(f"Unknown pipeline type: {pipeline_type}") from e

        creator = cls._registry.get(enum_type)
        if not creator:
            logger.error(f"No creator registered for pipeline type: {enum_type}")
            raise ValueError(f"No creator registered for pipeline type: {pipeline_type}")

        try:
            pipeline = creator(config)
            logger.debug(f"Created pipeline of type {pipeline_type}")
            return pipeline
        except Exception as e:
            logger.exception(f"Failed to create pipeline of type {pipeline_type}: {e}")
            raise


class DriverFactory:
    """Factory for creating camera driver instances."""

    _registry: Dict[CameraType, Callable[[CameraConfig], Any]] = {}

    @classmethod
    def register(cls, camera_type: CameraType, creator: Callable[[CameraConfig], Any]) -> None:
        """
        Register a driver creator function.

        Args:
            camera_type: The type of camera
            creator: A callable that takes a CameraConfig and returns a driver instance
        """
        cls._registry[camera_type] = creator
        logger.debug(f"Registered driver creator for {camera_type}")

    @classmethod
    def create(cls, camera_type: str, camera_config: CameraConfig) -> Any:
        """
        Create a driver instance.

        Args:
            camera_type: The type of camera (string)
            camera_config: Camera configuration

        Returns:
            Driver instance

        Raises:
            ValueError: If camera type is unknown
        """
        try:
            # Convert string to enum
            enum_type = CameraType.from_string(camera_type)
        except ValueError as e:
            logger.error(f"Unknown camera type: {camera_type}")
            raise ValueError(f"Unknown camera type: {camera_type}") from e

        creator = cls._registry.get(enum_type)
        if not creator:
            logger.error(f"No creator registered for camera type: {enum_type}")
            raise ValueError(f"No creator registered for camera type: {camera_type}")

        try:
            driver = creator(camera_config)
            logger.debug(f"Created driver of type {camera_type}")
            return driver
        except Exception as e:
            logger.exception(f"Failed to create driver of type {camera_type}: {e}")
            raise


def register_pipeline_factories() -> None:
    """Register all available pipeline types with the factory."""
    from app.pipelines.apriltag_pipeline import AprilTagPipeline
    from app.pipelines.coloured_shape_pipeline import ColouredShapePipeline
    from app.pipelines.object_detection_ml_pipeline import ObjectDetectionMLPipeline

    PipelineFactory.register(PipelineType.APRILTAG, AprilTagPipeline)
    PipelineFactory.register(PipelineType.COLOURED_SHAPE, ColouredShapePipeline)
    PipelineFactory.register(PipelineType.OBJECT_DETECTION_ML, ObjectDetectionMLPipeline)
    logger.info("Registered all pipeline factories")


def register_driver_factories() -> None:
    """Register all available driver types with the factory."""
    from app.drivers.usb_driver import USBDriver
    from app.drivers.genicam_driver import GenICamDriver
    from app.drivers.oakd_driver import OAKDDriver
    from app.drivers.realsense_driver import RealSenseDriver

    DriverFactory.register(CameraType.USB, USBDriver)
    DriverFactory.register(CameraType.GENICAM, GenICamDriver)
    DriverFactory.register(CameraType.OAKD, OAKDDriver)
    DriverFactory.register(CameraType.REALSENSE, RealSenseDriver)
    logger.info("Registered all driver factories")
