import logging
from flask import render_template, request, redirect, url_for, current_app
import json
from app.extensions import db
from app import camera_manager, camera_discovery
from app.drivers.genicam_driver import GenICamDriver
from app.drivers.realsense_driver import RealSenseDriver
from app.enums import CameraType, PipelineType
from app.models import Camera, Pipeline, Setting
from app.services import CameraService, SettingsService
from app.utils.responses import success_response, error_response
from app.camera_types import get_camera_types
from . import cameras

logger = logging.getLogger(__name__)


@cameras.route("/")
def cameras_page():
    """Renders the camera management page."""
    genicam_cti_path = SettingsService.get_genicam_cti_path()
    return render_template(
        "pages/cameras.html",
        genicam_enabled=bool(genicam_cti_path),
    )


@cameras.route("/add", methods=["POST"])
def add_camera():
    """Adds a new camera."""
    name = request.form.get("camera-name")
    camera_type = request.form.get("camera-type")

    # Determine identifier and device info based on camera type
    if camera_type == CameraType.USB.value:
        identifier = request.form.get("usb-camera-select")
        device_info_json = request.form.get("device-info-json")
    elif camera_type == CameraType.GENICAM.value:
        identifier = request.form.get("genicam-camera-select")
        device_info_json = None
    elif camera_type == CameraType.OAKD.value:
        identifier = request.form.get("oakd-camera-select")
        device_info_json = None
    elif camera_type == CameraType.REALSENSE.value:
        identifier = request.form.get("realsense-camera-select")
        device_info_json = None
    else:
        return redirect(url_for("cameras.cameras_page"))

    if not (name and camera_type and identifier):
        return redirect(url_for("cameras.cameras_page"))

    # Check if camera already exists
    if CameraService.get_camera_by_identifier(identifier):
        logger.warning(f"Camera with identifier {identifier} already exists")
        return redirect(url_for("cameras.cameras_page"))

    # Create camera using service
    try:
        camera_data = {
            "name": name,
            "type": camera_type,
            "identifier": identifier,
            "device_info_json": device_info_json,
        }
        new_camera = CameraService.create_camera(camera_data)
    except Exception as create_error:
        logger.error(f"Error creating camera: {create_error}")
        return redirect(url_for("cameras.cameras_page"))

    # Try to start the camera thread - if this fails, delete the camera from DB
    try:
        camera_manager.start_camera_thread(
            camera_manager.build_camera_thread_config(new_camera),
            current_app._get_current_object(),
        )
    except Exception as thread_error:
        logger.error(f"Error starting camera thread: {thread_error}")
        # Thread failed to start, remove the orphaned database entry
        db.session.delete(new_camera)
        db.session.commit()

    return redirect(url_for("cameras.cameras_page"))


@cameras.route("/update/<int:camera_id>", methods=["POST"])
def update_camera(camera_id):
    """Updates a camera's settings."""
    camera = CameraService.get_camera_by_id(camera_id)
    if not camera:
        return redirect(url_for("cameras.cameras_page"))

    name = request.form.get("camera-name")
    if name:
        CameraService.update_camera(camera, {"name": name})
    return redirect(url_for("cameras.cameras_page"))


@cameras.route("/delete/<int:camera_id>", methods=["POST"])
def delete_camera(camera_id):
    """Deletes a camera."""
    camera = CameraService.get_camera_by_id(camera_id)
    if not camera:
        return redirect(url_for("cameras.cameras_page"))

    # Stop thread and wait for confirmation
    camera_manager.stop_camera_thread(camera.identifier)

    # Verify thread actually stopped before deleting DB record
    if camera_manager.is_camera_thread_running(camera.identifier):
        return error_response("Failed to stop camera thread", 500)

    # Delete camera using service
    try:
        CameraService.delete_camera(camera)
    except Exception as e:
        logger.error(f"Failed to delete camera: {e}")

    return redirect(url_for("cameras.cameras_page"))


@cameras.route("/results/<int:camera_id>")
def get_camera_results(camera_id):
    """Returns the latest results from all pipelines for a given camera."""
    camera = CameraService.get_camera_by_id(camera_id)
    if not camera:
        return error_response("Camera not found", 404)

    results = CameraService.get_pipeline_results(camera.identifier)
    if results is None:
        return error_response("Camera thread not running or no results available", 404)

    string_key_results = {str(k): v for k, v in results.items()}
    return success_response(string_key_results)


@cameras.route("/types")
def camera_types():
    """Returns all registered camera types with metadata."""
    types = get_camera_types()
    return success_response(types)


@cameras.route("/discover")
def discover_cameras():
    """Discovers available USB, GenICam, OAK-D, and RealSense cameras."""
    existing_identifiers = request.args.get("existing", "").split(",")
    discovered = camera_discovery.discover_cameras(existing_identifiers)
    return success_response(discovered)


@cameras.route("/status/<int:camera_id>")
def camera_status(camera_id):
    """Returns the connection status of a camera."""
    camera = CameraService.get_camera_by_id(camera_id)
    if not camera:
        return error_response("Camera not found", 404)

    is_running = CameraService.is_camera_active(camera.identifier)
    return success_response({"connected": is_running})


@cameras.route("/controls/<int:camera_id>", methods=["GET"])
def get_camera_controls(camera_id):
    """Returns the control settings for a camera."""
    camera = CameraService.get_camera_by_id(camera_id)
    if not camera:
        return error_response("Camera not found", 404)
    return success_response(camera.to_dict())


@cameras.route("/update_controls/<int:camera_id>", methods=["POST"])
def update_camera_controls(camera_id):
    """Updates the control settings for a camera."""
    data = request.get_json()
    if not data:
        return error_response("Invalid JSON", 400)

    required_fields = [
        "orientation",
        "exposure_mode",
        "exposure_value",
        "gain_mode",
        "gain_value",
    ]
    if not all(field in data for field in required_fields):
        return error_response("Missing one or more required fields", 400)

    # Get camera and track old orientation
    camera = CameraService.get_camera_by_id(camera_id)
    if not camera:
        return error_response("Camera not found", 404)

    old_orientation = camera.orientation

    # Update camera controls using service
    try:
        updates = {
            "orientation": data["orientation"],
            "exposure_mode": data["exposure_mode"],
            "exposure_value": data["exposure_value"],
            "gain_mode": data["gain_mode"],
            "gain_value": data["gain_value"],
        }
        CameraService.update_camera(camera, updates)
    except Exception as e:
        return error_response(f"Failed to update camera controls: {e}", 400)

    return success_response()


@cameras.route("/genicam/nodes/<int:camera_id>", methods=["GET"])
def genicam_nodes(camera_id):
    """Returns the node map for a GenICam camera."""
    camera = CameraService.get_camera_by_id(camera_id)
    if not camera or camera.camera_type != CameraType.GENICAM.value:
        return error_response("Camera not found or not a GenICam device", 404)

    nodes, error = GenICamDriver.get_node_map(camera.identifier)
    if error:
        return error_response(error, 500)

    return success_response({"nodes": nodes})


@cameras.route("/genicam/nodes/<int:camera_id>", methods=["POST"])
def update_genicam_node(camera_id):
    """Updates a node on a GenICam camera."""
    camera = CameraService.get_camera_by_id(camera_id)
    if not camera or camera.camera_type != CameraType.GENICAM.value:
        return error_response("Camera not found or not a GenICam device", 404)

    payload = request.get_json(silent=True) or {}
    node_name = payload.get("name")
    value = payload.get("value")

    success, message, status_code, updated_node = GenICamDriver.update_node(
        camera.identifier, node_name, value
    )

    if success:
        return success_response(
            data={"node": updated_node},
            message=message or "Node updated successfully.",
            code=status_code
        )

    return error_response(message or "Failed to update node.", status_code)


@cameras.route("/realsense/resolutions/<int:camera_id>", methods=["GET"])
def realsense_resolutions(camera_id):
    """Returns supported resolutions for a RealSense camera."""
    camera = CameraService.get_camera_by_id(camera_id)
    if not camera or camera.camera_type != CameraType.REALSENSE.value:
        return error_response("Camera not found or not a RealSense device", 404)

    try:
        # Get supported resolutions from driver
        resolutions = RealSenseDriver.get_supported_resolutions(camera.identifier)

        # Get current camera settings
        current_resolution = None
        current_fps = None
        if camera.resolution_json:
            try:
                res_data = json.loads(camera.resolution_json) if isinstance(camera.resolution_json, str) else camera.resolution_json
                current_resolution = {"width": res_data.get("width"), "height": res_data.get("height")}
            except (json.JSONDecodeError, AttributeError, TypeError):
                pass

        current_fps = camera.framerate
        depth_enabled = camera.depth_enabled if camera.depth_enabled is not None else False

        return success_response({
            "resolutions": resolutions,
            "current": {
                "resolution": current_resolution,
                "fps": current_fps,
                "depth_enabled": depth_enabled
            }
        })

    except Exception as e:
        logger.error(f"Error getting RealSense resolutions for camera {camera_id}: {e}")
        return error_response(f"Failed to query resolutions: {e}", 500)


@cameras.route("/realsense/config/<int:camera_id>", methods=["POST"])
def update_realsense_config(camera_id):
    """Updates RealSense-specific configuration (resolution, framerate, depth)."""
    camera = CameraService.get_camera_by_id(camera_id)
    if not camera or camera.camera_type != CameraType.REALSENSE.value:
        return error_response("Camera not found or not a RealSense device", 404)

    data = request.get_json()
    if not data:
        return error_response("Invalid JSON", 400)

    try:
        updates = {}

        # Handle resolution update
        if "width" in data and "height" in data:
            width = int(data["width"])
            height = int(data["height"])

            # Validate resolution is in supported list
            supported = RealSenseDriver.get_supported_resolutions(camera.identifier)
            is_valid = any(r["width"] == width and r["height"] == height for r in supported)

            if not is_valid:
                return error_response(
                    f"Unsupported resolution {width}x{height}. "
                    f"Please select from the supported resolutions list.",
                    400
                )

            updates["resolution_json"] = json.dumps({"width": width, "height": height})

        # Handle framerate update
        if "fps" in data:
            fps = int(data["fps"])
            if fps <= 0 or fps > 120:
                return error_response("FPS must be between 1 and 120", 400)
            updates["framerate"] = fps

        # Handle depth enabled update
        if "depth_enabled" in data:
            updates["depth_enabled"] = bool(data["depth_enabled"])

        if not updates:
            return error_response("No valid fields to update", 400)

        # Update camera - this will automatically restart the thread via CameraService
        CameraService.update_camera(camera, updates)

        return success_response(
            message="RealSense configuration updated successfully. Camera thread will restart.",
            data={"updated_fields": list(updates.keys())}
        )

    except ValueError as e:
        return error_response(f"Invalid value in request: {e}", 400)
    except Exception as e:
        logger.error(f"Error updating RealSense config for camera {camera_id}: {e}")
        return error_response(f"Failed to update configuration: {e}", 500)
