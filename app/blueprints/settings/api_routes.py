"""
REST API routes for settings management.

Provides JSON-based endpoints for the React frontend to manage application settings.
"""

import json
import logging
import os

from flask import current_app, request, send_file
from werkzeug.utils import secure_filename

from app.extensions import db
from app import network_utils
from app.models import Setting, Camera, Pipeline
from app.drivers.genicam_driver import GenICamDriver
from app.services import SettingsService
from app.utils.responses import success_response, error_response
from app.apriltag_fields import (
    MAX_FIELD_FILE_SIZE,
    ensure_user_fields_dir,
    get_default_fields,
    get_selected_field_name,
    get_user_fields,
    list_all_fields,
    validate_layout_structure,
)
from . import settings

logger = logging.getLogger(__name__)


def get_db_path():
    """Extracts the database file path from the SQLAlchemy URI."""
    uri = current_app.config.get("SQLALCHEMY_DATABASE_URI")
    if uri and uri.startswith("sqlite:///"):
        return uri.replace("sqlite:///", "", 1)
    return None


# ============================================================================
# Settings API Endpoints
# ============================================================================

@settings.route("/api/settings", methods=["GET"])
def get_all_settings():
    """
    Get all application settings.

    Returns:
        JSON response with all settings including network info and AprilTag fields
    """
    all_settings = SettingsService.get_multiple_settings(
        keys=["genicam_cti_path", "team_number", "ip_mode", "hostname"],
        defaults={"ip_mode": "dhcp"}
    )

    current_network_settings = network_utils.get_network_settings()
    current_hostname = network_utils.get_hostname()

    default_fields = [
        {"name": info.name, "path": info.path, "source": info.source}
        for info in get_default_fields()
    ]
    user_fields = [
        {"name": info.name, "path": info.path, "source": info.source}
        for info in get_user_fields()
    ]
    selected_field = get_selected_field_name()

    return success_response({
        "settings": all_settings,
        "network": {
            "current_settings": current_network_settings,
            "current_hostname": current_hostname,
        },
        "apriltag": {
            "default_fields": default_fields,
            "user_fields": user_fields,
            "selected_field": selected_field,
        }
    })


@settings.route("/api/settings/global", methods=["PUT"])
def update_global_settings_api():
    """
    Update global application settings.

    Request body:
        {
            "team_number": "1234",
            "ip_mode": "dhcp" | "static",
            "hostname": "my-robot"
        }

    Returns:
        JSON response with updated settings
    """
    data = request.get_json()

    if not data:
        return error_response("Request body required", 400)

    updates = {}

    if "team_number" in data:
        updates["team_number"] = str(data["team_number"]).strip()

    if "ip_mode" in data:
        ip_mode = str(data["ip_mode"]).lower()
        if ip_mode not in ["dhcp", "static"]:
            return error_response("ip_mode must be 'dhcp' or 'static'", 400)
        updates["ip_mode"] = ip_mode

    if "hostname" in data:
        updates["hostname"] = str(data["hostname"]).strip()

    if not updates:
        return error_response("No valid fields to update", 400)

    SettingsService.set_multiple_settings(updates)

    return success_response({"settings": updates})


@settings.route("/api/settings/genicam", methods=["PUT"])
def update_genicam_settings_api():
    """
    Update GenICam CTI path.

    Request body:
        {
            "cti_path": "/path/to/file.cti"
        }

    Returns:
        JSON response with updated path
    """
    data = request.get_json()

    if not data:
        return error_response("Request body required", 400)

    path = data.get("cti_path", "").strip()

    if not path:
        return error_response("cti_path is required", 400)

    if not path.lower().endswith(".cti"):
        return error_response("File must have .cti extension", 400)

    if not os.path.exists(path):
        return error_response("File does not exist", 400)

    SettingsService.set_genicam_cti_path(path)
    GenICamDriver.initialize(path)

    return success_response({"cti_path": path})


@settings.route("/api/settings/genicam", methods=["DELETE"])
def clear_genicam_settings_api():
    """
    Clear GenICam CTI path.

    Returns:
        JSON success response
    """
    SettingsService.delete_setting("genicam_cti_path")
    GenICamDriver.initialize(None)

    return success_response({"cti_path": None})


# ============================================================================
# AprilTag Field API Endpoints
# ============================================================================

@settings.route("/api/settings/apriltag/fields", methods=["GET"])
def get_apriltag_fields_api():
    """
    Get all available AprilTag field layouts.

    Returns:
        JSON response with default fields, user fields, and selected field
    """
    default_fields = [
        {"name": info.name, "path": info.path, "source": info.source}
        for info in get_default_fields()
    ]
    user_fields = [
        {"name": info.name, "path": info.path, "source": info.source}
        for info in get_user_fields()
    ]
    selected_field = get_selected_field_name()

    return success_response({
        "default_fields": default_fields,
        "user_fields": user_fields,
        "selected_field": selected_field,
    })


@settings.route("/api/settings/apriltag/select", methods=["PUT"])
def select_apriltag_field_api():
    """
    Select an AprilTag field layout.

    Request body:
        {
            "field_name": "2024-crescendo.json"  // or "" to clear
        }

    Returns:
        JSON response with selected field
    """
    data = request.get_json()

    if not data:
        return error_response("Request body required", 400)

    field_name = data.get("field_name", "").strip()

    if field_name:
        # Validate field exists
        all_fields = {info.name for info in list_all_fields()}
        if field_name not in all_fields:
            return error_response("Unknown field layout", 400)

        SettingsService.set_apriltag_field(field_name)
    else:
        # Clear selection
        SettingsService.delete_setting("apriltag_field")

    return success_response({"selected": field_name or None})


@settings.route("/api/settings/apriltag/upload", methods=["POST"])
def upload_apriltag_field_api():
    """
    Upload a custom AprilTag field layout.

    Form data:
        field_layout: JSON file (max 1MB)

    Returns:
        JSON response with uploaded field name
    """
    upload = request.files.get("field_layout")

    if upload is None or not upload.filename:
        return error_response("No file provided", 400)

    filename = secure_filename(upload.filename)

    if not filename.lower().endswith(".json"):
        return error_response("Only .json files are supported", 400)

    raw = upload.read()

    if not raw:
        return error_response("File was empty", 400)

    if len(raw) > MAX_FIELD_FILE_SIZE:
        return error_response("File exceeds size limit (1MB)", 400)

    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        return error_response("File must be UTF-8 encoded", 400)

    try:
        data = json.loads(text)
    except json.JSONDecodeError as e:
        return error_response(f"Invalid JSON: {str(e)}", 400)

    is_valid, error = validate_layout_structure(data)
    if not is_valid:
        return error_response(error or "Invalid layout structure", 400)

    save_dir = ensure_user_fields_dir()
    save_path = os.path.join(save_dir, filename)

    try:
        with open(save_path, "w", encoding="utf-8") as handle:
            handle.write(text)
    except OSError as e:
        logger.error(f"Failed to save field layout: {e}")
        return error_response("Failed to save file", 500)

    return success_response({"name": filename})


@settings.route("/api/settings/apriltag/fields/<field_name>", methods=["DELETE"])
def delete_apriltag_field_api(field_name):
    """
    Delete a user-uploaded AprilTag field layout.

    Path parameter:
        field_name: Name of the field to delete

    Returns:
        JSON response, includes selected=null if deleted field was selected
    """
    if not field_name:
        return error_response("Field name required", 400)

    if not field_name.lower().endswith(".json"):
        return error_response("Invalid field name", 400)

    # Security: Prevent directory traversal
    user_dir = ensure_user_fields_dir()
    base_dir = os.path.normpath(user_dir)
    candidate = os.path.normpath(os.path.join(base_dir, field_name))

    if os.path.commonpath([base_dir, candidate]) != base_dir:
        return error_response("Invalid field name", 400)

    # Prevent deleting default fields
    for info in get_default_fields():
        if info.name == field_name:
            return error_response("Cannot delete default layouts", 400)

    if not os.path.isfile(candidate):
        return error_response("Field not found", 404)

    try:
        os.remove(candidate)
    except OSError as e:
        logger.error(f"Failed to delete field layout: {e}")
        return error_response("Failed to delete file", 500)

    # Clear selection if deleted field was selected
    if get_selected_field_name() == field_name:
        setting = db.session.get(Setting, "apriltag_field")
        if setting:
            db.session.delete(setting)
            db.session.commit()
        return success_response({"selected": None})

    return success_response()


# ============================================================================
# Device Control API Endpoints
# ============================================================================

@settings.route("/api/settings/control/restart-app", methods=["POST"])
def restart_app_api():
    """
    Restart the application.

    Returns:
        JSON response (may not be received due to restart)
    """
    logger.info("Restarting application via API...")
    os._exit(0)
    return success_response({"message": "Restarting..."})


@settings.route("/api/settings/control/reboot", methods=["POST"])
def reboot_device_api():
    """
    Reboot the device.

    Returns:
        JSON response (may not be received due to reboot)
    """
    logger.info("Rebooting device via API...")
    os.system("sudo reboot")
    return success_response({"message": "Rebooting..."})


@settings.route("/api/settings/control/export-db", methods=["GET"])
def export_db_api():
    """
    Export the application database.

    Returns:
        Database file download
    """
    db_path = get_db_path()

    if not db_path or not os.path.exists(db_path):
        return error_response("Database not found", 404)

    return send_file(db_path, as_attachment=True, download_name="arcsight_config.db")


@settings.route("/api/settings/control/import-db", methods=["POST"])
def import_db_api():
    """
    Import an application database.

    Form data:
        database: .db file

    Returns:
        JSON success response
    """
    db_path = get_db_path()

    if not db_path:
        return error_response("Database path not configured", 500)

    if "database" not in request.files:
        return error_response("No file provided", 400)

    file = request.files["database"]

    if not file.filename:
        return error_response("No file selected", 400)

    if not file.filename.endswith(".db"):
        return error_response("File must have .db extension", 400)

    try:
        file.save(db_path)
        return success_response({"message": "Database imported successfully"})
    except Exception as e:
        logger.error(f"Failed to import database: {e}")
        return error_response("Failed to import database", 500)


@settings.route("/api/settings/control/factory-reset", methods=["POST"])
def factory_reset_api():
    """
    Reset the application to factory settings.

    Deletes all cameras, pipelines, and settings.

    Returns:
        JSON success response
    """
    logger.info("Performing factory reset via API...")

    try:
        # Order matters due to foreign key constraints
        db.session.query(Pipeline).delete()
        db.session.query(Camera).delete()
        db.session.query(Setting).delete()
        db.session.commit()

        GenICamDriver.initialize(None)

        return success_response({"message": "Factory reset completed"})
    except Exception as e:
        logger.error(f"Factory reset failed: {e}")
        db.session.rollback()
        return error_response("Factory reset failed", 500)
