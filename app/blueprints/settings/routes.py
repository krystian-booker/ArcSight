from flask import render_template, request, redirect, url_for, send_file, current_app
from app.extensions import db
from app import network_utils
from app.models import Setting, Camera, Pipeline
from app.drivers.genicam_driver import GenICamDriver
import os
from . import settings

def get_db_path():
    """Extracts the database file path from the SQLAlchemy URI."""
    uri = current_app.config.get('SQLALCHEMY_DATABASE_URI')
    if uri and uri.startswith('sqlite:///'):
        return uri.replace('sqlite:///', '', 1)
    return None

@settings.route('/')
def settings_page():
    """Renders the application settings page."""
    all_settings = {
        'genicam_cti_path': (db.session.get(Setting, 'genicam_cti_path') or {}).value or "",
        'team_number': (db.session.get(Setting, 'team_number') or {}).value or "",
        'ip_mode': (db.session.get(Setting, 'ip_mode') or {}).value or "dhcp",
        'hostname': (db.session.get(Setting, 'hostname') or {}).value or "",
    }
    current_network_settings = network_utils.get_network_settings()
    current_hostname = network_utils.get_hostname()
    return render_template('pages/settings.html', 
                           settings=all_settings, 
                           current_network_settings=current_network_settings, 
                           current_hostname=current_hostname)

def _update_setting(key, value):
    """Helper to update a setting in the database."""
    setting = db.session.get(Setting, key)
    if setting:
        setting.value = value
    else:
        setting = Setting(key=key, value=value)
        db.session.add(setting)

@settings.route('/global/update', methods=['POST'])
def update_global_settings():
    """Updates global application settings."""
    _update_setting('team_number', request.form.get('team_number', ''))
    _update_setting('ip_mode', request.form.get('ip_mode', 'dhcp'))
    _update_setting('hostname', request.form.get('hostname', ''))
    db.session.commit()
    return redirect(url_for('settings.settings_page'))


@settings.route('/genicam/update', methods=['POST'])
def update_genicam_settings():
    """Updates the GenICam CTI path."""
    path = request.form.get('genicam-cti-path', '').strip()
    new_path = None

    if path and path.lower().endswith('.cti') and os.path.exists(path):
        _update_setting('genicam_cti_path', path)
        new_path = path
    else:
        setting = db.session.get(Setting, 'genicam_cti_path')
        if setting:
            db.session.delete(setting)
    
    db.session.commit()
    GenICamDriver.initialize(new_path)
    return redirect(url_for('settings.settings_page'))


@settings.route('/genicam/clear', methods=['POST'])
def clear_genicam_settings():
    """Clears the GenICam CTI path."""
    setting = db.session.get(Setting, 'genicam_cti_path')
    if setting:
        db.session.delete(setting)
        db.session.commit()
    GenICamDriver.initialize(None)
    return redirect(url_for('settings.settings_page'))


@settings.route('/control/restart-app', methods=['POST'])
def restart_app():
    """Restarts the application."""
    print("Restarting application...")
    os._exit(0)
    return "Restarting...", 200


@settings.route('/control/reboot', methods=['POST'])
def reboot_device():
    """Reboots the device."""
    print("Rebooting device...")
    os.system("sudo reboot")
    return "Rebooting...", 200


@settings.route('/control/export-db')
def export_db():
    """Exports the application database."""
    db_path = get_db_path()
    if db_path and os.path.exists(db_path):
        return send_file(db_path, as_attachment=True)
    return "Database not found.", 404


@settings.route('/control/import-db', methods=['POST'])
def import_db():
    """Imports an application database."""
    db_path = get_db_path()
    if not db_path:
        return "Database path not configured.", 500
        
    if 'database' not in request.files:
        return redirect(url_for('settings.settings_page'))
    
    file = request.files['database']
    if file.filename and file.filename.endswith('.db'):
        file.save(db_path)
        
    return redirect(url_for('settings.settings_page'))


@settings.route('/control/factory-reset', methods=['POST'])
def factory_reset():
    """Resets the application to its factory settings."""
    # Order matters due to foreign key constraints
    db.session.query(Pipeline).delete()
    db.session.query(Camera).delete()
    db.session.query(Setting).delete()
    db.session.commit()
    
    GenICamDriver.initialize(None)
    return redirect(url_for('settings.settings_page'))