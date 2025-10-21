from flask import render_template, request, redirect, url_for, current_app, jsonify
import json
from app.extensions import db
from app import camera_manager, camera_discovery
from app.drivers.genicam_driver import GenICamDriver
from app.models import Camera, Pipeline, Setting
from . import cameras


@cameras.route("/")
def cameras_page():
    """Renders the camera management page."""
    genicam_setting = db.session.get(Setting, "genicam_cti_path")
    return render_template(
        "pages/cameras.html",
        genicam_enabled=bool(genicam_setting and genicam_setting.value),
    )


@cameras.route("/add", methods=["POST"])
def add_camera():
    """Adds a new camera."""
    name = request.form.get("camera-name")
    camera_type = request.form.get("camera-type")

    if camera_type == "USB":
        identifier = request.form.get("usb-camera-select")
        # Get additional device metadata from the form if available
        device_info_json = request.form.get("device-info-json")
    elif camera_type == "GenICam":
        identifier = request.form.get("genicam-camera-select")
        device_info_json = None
    elif camera_type == "OAK-D":
        identifier = request.form.get("oakd-camera-select")
        device_info_json = None
    else:
        return redirect(url_for("cameras.cameras_page"))

    if name and camera_type and identifier:
        existing_camera = Camera.query.filter_by(identifier=identifier).first()
        if not existing_camera:
            new_camera = Camera(
                name=name,
                camera_type=camera_type,
                identifier=identifier,
                device_info_json=device_info_json,
            )
            # Add a default pipeline
            default_pipeline = Pipeline(
                name="default", pipeline_type="AprilTag", config=json.dumps({})
            )
            new_camera.pipelines.append(default_pipeline)

            db.session.add(new_camera)

            try:
                db.session.commit()

                # Try to start the camera thread - if this fails, delete the camera from DB
                try:
                    camera_manager.start_camera_thread(
                        camera_manager.build_camera_thread_config(new_camera),
                        current_app._get_current_object(),
                    )
                except Exception as thread_error:
                    print(f"Error starting camera thread: {thread_error}")
                    # Thread failed to start, remove the orphaned database entry
                    db.session.delete(new_camera)
                    db.session.commit()
                    raise

            except Exception as e:
                db.session.rollback()
                print(f"Error adding camera: {e}")
                # Camera and pipeline will be removed from database due to rollback

    return redirect(url_for("cameras.cameras_page"))


@cameras.route("/update/<int:camera_id>", methods=["POST"])
def update_camera(camera_id):
    """Updates a camera's settings."""
    name = request.form.get("camera-name")
    camera = db.session.get(Camera, camera_id)
    if name:
        camera.name = name
        db.session.commit()
    return redirect(url_for("cameras.cameras_page"))


@cameras.route("/delete/<int:camera_id>", methods=["POST"])
def delete_camera(camera_id):
    """Deletes a camera."""
    camera = db.session.get(Camera, camera_id)
    if camera:
        identifier = camera.identifier
        # Stop thread and wait for confirmation
        camera_manager.stop_camera_thread(identifier)

        # Verify thread actually stopped before deleting DB record
        if camera_manager.is_camera_thread_running(identifier):
            return jsonify({"error": "Failed to stop camera thread"}), 500

        db.session.delete(camera)
        db.session.commit()
    return redirect(url_for("cameras.cameras_page"))


@cameras.route("/results/<int:camera_id>")
def get_camera_results(camera_id):
    """Returns the latest results from all pipelines for a given camera."""
    camera = db.session.get(Camera, camera_id)
    if not camera:
        return jsonify({"error": "Camera not found"}), 404

    results = camera_manager.get_camera_pipeline_results(camera.identifier)
    if results is None:
        return jsonify(
            {"error": "Camera thread not running or no results available"}
        ), 404

    string_key_results = {str(k): v for k, v in results.items()}
    return jsonify(string_key_results)


@cameras.route("/discover")
def discover_cameras():
    """Discovers available USB, GenICam, and OAK-D cameras."""
    existing_identifiers = request.args.get("existing", "").split(",")
    discovered = camera_discovery.discover_cameras(existing_identifiers)
    return jsonify(discovered)


@cameras.route("/status/<int:camera_id>")
def camera_status(camera_id):
    """Returns the connection status of a camera."""
    camera = db.session.get(Camera, camera_id)
    if camera:
        is_running = camera_manager.is_camera_thread_running(camera.identifier)
        return jsonify({"connected": is_running})
    return jsonify({"error": "Camera not found"}), 404


@cameras.route("/controls/<int:camera_id>", methods=["GET"])
def get_camera_controls(camera_id):
    """Returns the control settings for a camera."""
    camera = db.session.get(Camera, camera_id)
    if camera:
        return jsonify(camera.to_dict())
    return jsonify({"error": "Camera not found"}), 404


@cameras.route("/update_controls/<int:camera_id>", methods=["POST"])
def update_camera_controls(camera_id):
    """Updates the control settings for a camera."""
    camera = db.session.get(Camera, camera_id)
    data = request.get_json()
    if not data:
        return jsonify({"error": "Invalid JSON"}), 400

    required_fields = [
        "orientation",
        "exposure_mode",
        "exposure_value",
        "gain_mode",
        "gain_value",
    ]
    if not all(field in data for field in required_fields):
        return jsonify({"error": "Missing one or more required fields"}), 400

    # Track if orientation changed
    old_orientation = camera.orientation
    new_orientation = data["orientation"]

    camera.orientation = new_orientation
    camera.exposure_mode = data["exposure_mode"]
    camera.exposure_value = data["exposure_value"]
    camera.gain_mode = data["gain_mode"]
    camera.gain_value = data["gain_value"]
    db.session.commit()

    # Notify the camera thread of orientation change via event
    if old_orientation != new_orientation:
        camera_manager.notify_camera_config_update(camera.identifier, new_orientation)

    return jsonify({"success": True})


@cameras.route("/genicam/nodes/<int:camera_id>", methods=["GET"])
def genicam_nodes(camera_id):
    """Returns the node map for a GenICam camera."""
    camera = db.session.get(Camera, camera_id)
    if not camera or camera.camera_type != "GenICam":
        return jsonify({"error": "Camera not found or not a GenICam device"}), 404

    nodes, error = GenICamDriver.get_node_map(camera.identifier)
    if error:
        return jsonify({"error": error}), 500

    return jsonify({"nodes": nodes})


@cameras.route("/genicam/nodes/<int:camera_id>", methods=["POST"])
def update_genicam_node(camera_id):
    """Updates a node on a GenICam camera."""
    camera = db.session.get(Camera, camera_id)
    if not camera or camera.camera_type != "GenICam":
        return jsonify({"error": "Camera not found or not a GenICam device"}), 404

    payload = request.get_json(silent=True) or {}
    node_name = payload.get("name")
    value = payload.get("value")

    success, message, status_code, updated_node = GenICamDriver.update_node(
        camera.identifier, node_name, value
    )

    if success:
        return jsonify(
            {
                "success": True,
                "message": message or "Node updated successfully.",
                "node": updated_node,
            }
        ), status_code

    return jsonify({"error": message or "Failed to update node."}), status_code
