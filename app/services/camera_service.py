"""Service for camera management business logic."""

import logging
from typing import Any, Dict, List, Optional

from app.extensions import db
from app.models import Camera
from app import camera_manager
from app.utils.camera_config import CameraConfig

logger = logging.getLogger(__name__)


class CameraService:
    """Service for camera-related business operations."""

    @staticmethod
    def get_all_cameras() -> List[Camera]:
        """
        Retrieve all cameras from the database.

        Returns:
            List of Camera objects ordered by ID
        """
        return Camera.query.order_by(Camera.id.asc()).all()

    @staticmethod
    def get_camera_by_id(camera_id: int) -> Optional[Camera]:
        """
        Retrieve a camera by its ID.

        Args:
            camera_id: Camera database ID

        Returns:
            Camera object or None if not found
        """
        return db.session.get(Camera, camera_id)

    @staticmethod
    def get_camera_by_identifier(identifier: str) -> Optional[Camera]:
        """
        Retrieve a camera by its identifier.

        Args:
            identifier: Camera identifier string

        Returns:
            Camera object or None if not found
        """
        return Camera.query.filter_by(identifier=identifier).first()

    @staticmethod
    def create_camera(camera_data: Dict[str, Any]) -> Camera:
        """
        Create a new camera in the database.

        Args:
            camera_data: Dictionary containing camera configuration

        Returns:
            Created Camera object

        Raises:
            Exception: If database operation fails
        """
        camera = Camera(
            identifier=camera_data.get("identifier", ""),
            camera_type=camera_data.get("type", "usb"),
            name=camera_data.get("name"),
            orientation=camera_data.get("orientation", 0),
            exposure_mode=camera_data.get("exposure_mode", "auto"),
            exposure_value=camera_data.get("exposure_value"),
            gain_mode=camera_data.get("gain_mode", "auto"),
            gain_value=camera_data.get("gain_value"),
            resolution_json=camera_data.get("resolution_json"),
            framerate=camera_data.get("framerate"),
            depth_enabled=camera_data.get("depth_enabled", False),
            device_info_json=camera_data.get("device_info_json"),
        )

        db.session.add(camera)
        db.session.commit()

        logger.info(f"Created camera {camera.id}: {camera.identifier}")
        return camera

    @staticmethod
    def update_camera(camera: Camera, updates: Dict[str, Any]) -> Camera:
        """
        Update camera properties.

        Args:
            camera: Camera object to update
            updates: Dictionary of fields to update

        Returns:
            Updated Camera object

        Raises:
            Exception: If database operation fails
        """
        # Track if we need to restart threads
        needs_thread_restart = False
        orientation_changed = False

        # Update simple fields
        for field in ["name", "exposure_mode", "exposure_value", "gain_mode", "gain_value"]:
            if field in updates:
                setattr(camera, field, updates[field])

        # Handle orientation changes (requires thread reconfiguration)
        if "orientation" in updates and camera.orientation != updates["orientation"]:
            camera.orientation = updates["orientation"]
            orientation_changed = True
            needs_thread_restart = True

        # Handle resolution/framerate/depth changes (requires thread restart)
        for field in ["resolution_json", "framerate", "depth_enabled"]:
            if field in updates and getattr(camera, field) != updates[field]:
                setattr(camera, field, updates[field])
                needs_thread_restart = True

        db.session.commit()

        # Notify or restart threads as needed
        if orientation_changed:
            camera_manager.notify_camera_config_update(camera.identifier)
        elif needs_thread_restart:
            # Full thread restart required for resolution/depth changes
            camera_manager.stop_camera_thread(camera.identifier)
            config = camera_manager.build_camera_thread_config(camera)
            from flask import current_app
            camera_manager.start_camera_thread(config, current_app._get_current_object())

        logger.info(f"Updated camera {camera.id}: {camera.identifier}")
        return camera

    @staticmethod
    def delete_camera(camera: Camera) -> None:
        """
        Delete a camera and stop its threads.

        Args:
            camera: Camera object to delete

        Raises:
            Exception: If database operation fails
        """
        identifier = camera.identifier
        camera_id = camera.id

        # Stop threads first
        camera_manager.stop_camera_thread(identifier)

        # Delete from database (cascades to pipelines)
        db.session.delete(camera)
        db.session.commit()

        logger.info(f"Deleted camera {camera_id}: {identifier}")

    @staticmethod
    def get_camera_config(camera: Camera) -> CameraConfig:
        """
        Get a CameraConfig object from a Camera model.

        Args:
            camera: Camera model instance

        Returns:
            CameraConfig dataclass instance
        """
        return CameraConfig.from_camera_data(camera)

    @staticmethod
    def is_camera_active(identifier: str) -> bool:
        """
        Check if a camera thread is currently active.

        Args:
            identifier: Camera identifier

        Returns:
            True if camera thread is running
        """
        return camera_manager.is_camera_thread_running(identifier)

    @staticmethod
    def get_camera_status(identifier: str) -> Dict[str, Any]:
        """
        Get detailed status information for a camera.

        Args:
            identifier: Camera identifier

        Returns:
            Dictionary with status information
        """
        is_running = camera_manager.is_camera_thread_running(identifier)

        status = {
            "is_running": is_running,
            "identifier": identifier,
        }

        if is_running:
            # Could extend this to include frame rate, errors, etc.
            pass

        return status

    @staticmethod
    def get_pipeline_results(identifier: str) -> Optional[Dict]:
        """
        Get the latest pipeline results for a camera.

        Args:
            identifier: Camera identifier

        Returns:
            Dictionary of pipeline results or None if not available
        """
        return camera_manager.get_camera_pipeline_results(identifier)
