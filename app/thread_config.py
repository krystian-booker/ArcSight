"""Thread configuration data structures and builders."""

import logging
from dataclasses import dataclass, field
from typing import List, Optional

from app.models import Camera

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class PipelineThreadConfig:
    """Immutable configuration for a pipeline processing thread."""

    id: int
    pipeline_type: str
    config: str


@dataclass(frozen=True)
class CameraThreadConfig:
    """Immutable configuration for camera acquisition and pipeline threads."""

    id: int
    identifier: str
    camera_type: str
    orientation: int
    camera_matrix_json: Optional[str]
    dist_coeffs_json: Optional[str]
    resolution_json: Optional[str]
    framerate: Optional[int]
    depth_enabled: bool
    exposure_mode: str
    exposure_value: int
    gain_mode: str
    gain_value: int
    pipelines: List[PipelineThreadConfig] = field(default_factory=list)


def build_camera_thread_config(camera: Camera) -> CameraThreadConfig:
    """
    Convert a Camera ORM object into immutable configuration for thread creation.

    This function extracts all necessary data from the ORM object to avoid
    session detachment issues when the configuration is used in threads.

    Args:
        camera: Camera ORM object (must be attached to session)

    Returns:
        CameraThreadConfig with all necessary data
    """
    pipelines = [
        PipelineThreadConfig(
            id=pipeline.id,
            pipeline_type=pipeline.pipeline_type,
            config=pipeline.config,
        )
        for pipeline in camera.pipelines
    ]

    config = CameraThreadConfig(
        id=camera.id,
        identifier=camera.identifier,
        camera_type=camera.camera_type,
        orientation=camera.orientation or 0,
        camera_matrix_json=camera.camera_matrix_json,
        dist_coeffs_json=camera.dist_coeffs_json,
        resolution_json=camera.resolution_json,
        framerate=camera.framerate,
        depth_enabled=camera.depth_enabled or False,
        exposure_mode=camera.exposure_mode or "auto",
        exposure_value=camera.exposure_value or 500,
        gain_mode=camera.gain_mode or "auto",
        gain_value=camera.gain_value or 50,
        pipelines=pipelines,
    )

    logger.debug(
        f"Built thread config for camera {camera.id}: "
        f"{camera.identifier} with {len(pipelines)} pipelines"
    )

    return config
