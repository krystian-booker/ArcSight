from flask import render_template, request, redirect, url_for, current_app
from app import db, camera_manager
from . import cameras


@cameras.route('/')
def cameras_page():
    """Renders the camera management page."""
    cameras_list = db.get_cameras()
    genicam_cti_path = db.get_setting('genicam_cti_path')
    return render_template('cameras.html', cameras=cameras_list, genicam_enabled=bool(genicam_cti_path))


@cameras.route('/add', methods=['POST'])
def add_camera():
    """Adds a new camera."""
    name = request.form.get('camera-name')
    camera_type = request.form.get('camera-type')
    
    if camera_type == 'USB':
        identifier = request.form.get('usb-camera-select')
    elif camera_type == 'GenICam':
        identifier = request.form.get('genicam-camera-select')
    elif camera_type == 'OAK-D':
        identifier = request.form.get('oakd-camera-select')
    else:
        return redirect(url_for('cameras.cameras_page'))

    if name and camera_type and identifier:
        db.add_camera(name, camera_type, identifier)
        new_camera = db.get_camera_by_identifier(identifier)
        if new_camera:
            camera_manager.start_camera_thread(dict(new_camera), current_app._get_current_object())

    return redirect(url_for('cameras.cameras_page'))


@cameras.route('/update/<int:camera_id>', methods=['POST'])
def update_camera(camera_id):
    """Updates a camera's settings."""
    name = request.form.get('camera-name')
    if name:
        db.update_camera(camera_id, name)
    return redirect(url_for('cameras.cameras_page'))


@cameras.route('/delete/<int:camera_id>', methods=['POST'])
def delete_camera(camera_id):
    """Deletes a camera."""
    camera = db.get_camera(camera_id)
    if camera:
        camera_manager.stop_camera_thread(camera['identifier'])
    db.delete_camera(camera_id)
    return redirect(url_for('cameras.cameras_page'))