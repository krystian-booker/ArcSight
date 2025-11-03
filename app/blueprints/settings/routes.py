import json
import logging
import os

from flask import (
    current_app,
    redirect,
    render_template,
    request,
    send_file,
    url_for,
)
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


@settings.route("/")
def settings_page():
    """Renders the application settings page."""
    all_settings = SettingsService.get_multiple_settings(
        keys=["genicam_cti_path", "team_number", "ip_mode", "hostname"],
        defaults={"ip_mode": "dhcp"}
    )
    current_network_settings = network_utils.get_network_settings()
    current_hostname = network_utils.get_hostname()
    default_fields = get_default_fields()
    user_fields = get_user_fields()
    selected_field = get_selected_field_name()
    return render_template(
        "pages/settings.html",
        settings=all_settings,
        current_network_settings=current_network_settings,
        current_hostname=current_hostname,
        default_fields=default_fields,
        user_fields=user_fields,
        selected_field=selected_field,
    )


@settings.route("/global/update", methods=["POST"])
def update_global_settings():
    """Updates global application settings."""
    SettingsService.set_multiple_settings({
        "team_number": request.form.get("team_number", ""),
        "ip_mode": request.form.get("ip_mode", "dhcp"),
        "hostname": request.form.get("hostname", ""),
    })
    return redirect(url_for("settings.settings_page"))


@settings.route("/genicam/update", methods=["POST"])
def update_genicam_settings():
    """Updates the GenICam CTI path."""
    path = request.form.get("genicam-cti-path", "").strip()
    new_path = None

    if path and path.lower().endswith(".cti") and os.path.exists(path):
        SettingsService.set_genicam_cti_path(path)
        new_path = path
    else:
        SettingsService.delete_setting("genicam_cti_path")

    GenICamDriver.initialize(new_path)
    return redirect(url_for("settings.settings_page"))


@settings.route("/genicam/clear", methods=["POST"])
def clear_genicam_settings():
    """Clears the GenICam CTI path."""
    SettingsService.delete_setting("genicam_cti_path")
    GenICamDriver.initialize(None)
    return redirect(url_for("settings.settings_page"))


@settings.route("/control/restart-app", methods=["POST"])
def restart_app():
    """Restarts the application."""
    logger.info("Restarting application...")
    os._exit(0)
    return "Restarting...", 200


@settings.route("/control/reboot", methods=["POST"])
def reboot_device():
    """Reboots the device."""
    logger.info("Rebooting device...")
    os.system("sudo reboot")
    return "Rebooting...", 200


@settings.route("/control/export-db")
def export_db():
    """Exports the application database."""
    db_path = get_db_path()
    if db_path and os.path.exists(db_path):
        return send_file(db_path, as_attachment=True)
    return "Database not found.", 404


@settings.route("/control/import-db", methods=["POST"])
def import_db():
    """Imports an application database."""
    db_path = get_db_path()
    if not db_path:
        return "Database path not configured.", 500

    if "database" not in request.files:
        return redirect(url_for("settings.settings_page"))

    file = request.files["database"]
    if file.filename and file.filename.endswith(".db"):
        file.save(db_path)

    return redirect(url_for("settings.settings_page"))


@settings.route("/control/factory-reset", methods=["POST"])
def factory_reset():
    """Resets the application to its factory settings."""
    # Order matters due to foreign key constraints
    db.session.query(Pipeline).delete()
    db.session.query(Camera).delete()
    db.session.query(Setting).delete()
    db.session.commit()

    GenICamDriver.initialize(None)
    return redirect(url_for("settings.settings_page"))


def _is_valid_field_name(name: str) -> bool:
    return name in {info.name for info in list_all_fields()}


def _extract_field_name() -> str:
    if request.is_json:
        payload = request.get_json(silent=True) or {}
        return (payload.get("field_name") or "").strip()
    return (request.form.get("field_name", "")).strip()


@settings.route("/apriltag/select", methods=["POST"])
def select_apriltag_field():
    """Persist the selected AprilTag field layout."""
    field_name = _extract_field_name()
    if field_name and not _is_valid_field_name(field_name):
        return error_response("Unknown field layout", 400)

    if field_name:
        SettingsService.set_apriltag_field(field_name)
    else:
        SettingsService.delete_setting("apriltag_field")

    return success_response({"selected": field_name or None})


@settings.route("/apriltag/upload", methods=["POST"])
def upload_apriltag_field():
    """Handle JSON uploads for custom AprilTag fields."""
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
        return error_response("File exceeds size limit", 400)
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        return error_response("File must be UTF-8 encoded", 400)

    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return error_response("Invalid JSON", 400)

    is_valid, error = validate_layout_structure(data)
    if not is_valid:
        return error_response(error or "Invalid layout structure", 400)

    save_dir = ensure_user_fields_dir()
    save_path = os.path.join(save_dir, filename)
    try:
        with open(save_path, "w", encoding="utf-8") as handle:
            handle.write(text)
    except OSError:
        return error_response("Failed to save file", 500)

    return success_response({"name": filename})


@settings.route("/apriltag/delete", methods=["POST"])
def delete_apriltag_field():
    """Remove a user-uploaded AprilTag field layout."""
    field_name = _extract_field_name()
    if not field_name:
        return error_response("Field name required", 400)
    if not field_name.lower().endswith(".json"):
        return error_response("Invalid field name", 400)

    user_dir = ensure_user_fields_dir()
    base_dir = os.path.normpath(user_dir)
    candidate = os.path.normpath(os.path.join(base_dir, field_name))
    if os.path.commonpath([base_dir, candidate]) != base_dir:
        return error_response("Invalid field name", 400)

    for info in get_default_fields():
        if info.name == field_name:
            return error_response("Cannot delete default layouts", 400)

    if not os.path.isfile(candidate):
        return error_response("Field not found", 404)

    try:
        os.remove(candidate)
    except OSError:
        return error_response("Failed to delete file", 500)

    if get_selected_field_name() == field_name:
        setting = db.session.get(Setting, "apriltag_field")
        if setting:
            db.session.delete(setting)
            db.session.commit()
        return success_response({"selected": None})

    return success_response()
