from flask import render_template, request, redirect, url_for, send_file
from app import db, network_utils
from app.drivers.genicam_driver import GenICamDriver
import os
from . import settings


@settings.route('/')
def settings_page():
    """Renders the application settings page."""
    all_settings = {
        'genicam_cti_path': db.get_setting('genicam_cti_path'),
        'team_number': db.get_setting('team_number'),
        'ip_mode': db.get_setting('ip_mode'),
        'hostname': db.get_setting('hostname'),
    }
    current_network_settings = network_utils.get_network_settings()
    current_hostname = network_utils.get_hostname()
    return render_template('pages/settings.html', 
                           settings=all_settings, 
                           current_network_settings=current_network_settings, 
                           current_hostname=current_hostname)


@settings.route('/global/update', methods=['POST'])
def update_global_settings():
    """Updates global application settings."""
    db.update_setting('team_number', request.form.get('team_number'))
    db.update_setting('ip_mode', request.form.get('ip_mode'))
    db.update_setting('hostname', request.form.get('hostname'))
    return redirect(url_for('settings.settings_page'))


@settings.route('/genicam/update', methods=['POST'])
def update_genicam_settings():
    """Updates the GenICam CTI path."""
    path = request.form.get('genicam-cti-path', '').strip()
    new_path = None

    if path and path.lower().endswith('.cti') and os.path.exists(path):
        db.update_setting('genicam_cti_path', path)
        new_path = path
    else:
        db.clear_setting('genicam_cti_path')
    
    # Re-initialize the driver with the new path
    GenICamDriver.initialize(new_path)
    return redirect(url_for('settings.settings_page'))


@settings.route('/genicam/clear', methods=['POST'])
def clear_genicam_settings():
    """Clears the GenICam CTI path."""
    db.clear_setting('genicam_cti_path')
    # Re-initialize the driver with no CTI file
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
    return send_file(db.DB_PATH, as_attachment=True)


@settings.route('/control/import-db', methods=['POST'])
def import_db():
    """Imports an application database."""
    if 'database' not in request.files:
        return redirect(url_for('settings.settings_page'))
    
    file = request.files['database']
    if file.filename and file.filename.endswith('.db'):
        file.save(db.DB_PATH)
        
    return redirect(url_for('settings.settings_page'))


@settings.route('/control/factory-reset', methods=['POST'])
def factory_reset():
    """Resets the application to its factory settings."""
    db.factory_reset()
    GenICamDriver.initialize(None)
    return redirect(url_for('settings.settings_page'))