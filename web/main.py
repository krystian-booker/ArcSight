from flask import Flask, render_template, request, redirect, url_for, jsonify
import db
import camera_utils

app = Flask(__name__, template_folder='templates', static_folder='static')

@app.route('/')
def dashboard():
    return render_template('index.html')

@app.route('/config')
def config():
    cameras = db.get_cameras()
    genicam_cti_path = db.get_setting('genicam_cti_path')
    return render_template('config.html', cameras=cameras, genicam_cti_path=genicam_cti_path)

@app.route('/cameras/add', methods=['POST'])
def add_camera():
    name = request.form.get('camera-name')
    camera_type = request.form.get('camera-type')
    
    if camera_type == 'USB':
        identifier = request.form.get('usb-camera-select')
    elif camera_type == 'GenICam':
        identifier = request.form.get('genicam-camera-select')
    else:
        # Handle error: invalid camera type
        return redirect(url_for('config'))

    if name and camera_type and identifier:
        db.add_camera(name, camera_type, identifier)

    return redirect(url_for('config'))

@app.route('/cameras/update/<int:camera_id>', methods=['POST'])
def update_camera(camera_id):
    name = request.form.get('edit-camera-name')
    if name:
        db.update_camera(camera_id, name)
    return redirect(url_for('config'))

@app.route('/cameras/delete/<int:camera_id>', methods=['POST'])
def delete_camera(camera_id):
    db.delete_camera(camera_id)
    return redirect(url_for('config'))

@app.route('/config/genicam/update', methods=['POST'])
def update_genicam_settings():
    cti_path = request.form.get('genicam-cti-path')
    if cti_path is not None:
        db.update_setting('genicam_cti_path', cti_path)
    return redirect(url_for('config'))

@app.route('/api/cameras/discover')
def discover_cameras():
    existing_identifiers = request.args.get('existing', '').split(',')
    
    usb_cameras = camera_utils.list_usb_cameras()
    genicam_cameras = camera_utils.list_genicam_cameras()

    # Filter out already configured cameras
    filtered_usb = [cam for cam in usb_cameras if cam['identifier'] not in existing_identifiers]
    filtered_genicam = [cam for cam in genicam_cameras if cam['identifier'] not in existing_identifiers]

    return jsonify({
        'usb': filtered_usb,
        'genicam': filtered_genicam
    })

@app.route('/api/cameras/status/<int:camera_id>')
def camera_status(camera_id):
    camera = db.get_camera(camera_id)
    if camera:
        is_connected = camera_utils.check_camera_connection(camera)
        return jsonify({'connected': is_connected})
    return jsonify({'error': 'Camera not found'}), 404

if __name__ == '__main__':
    # Initialize the database on startup
    db.init_db()
    app.run(host='0.0.0.0', port=8080, debug=True, use_reloader=False)
