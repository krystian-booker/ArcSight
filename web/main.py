from flask import Flask, render_template, request, redirect, url_for, jsonify, Response
import db
import camera_utils
import cv2
import numpy as np
app = Flask(__name__, template_folder='templates', static_folder='static')

@app.route('/')
def dashboard():
    cameras = db.get_cameras()
    return render_template('index.html', cameras=cameras)

def create_error_image(message, width=640, height=480):
    """Creates a black image with white text."""
    img = np.zeros((height, width, 3), np.uint8)
    font = cv2.FONT_HERSHEY_SIMPLEX
    
    # Calculate text size and position for centering
    text_size = cv2.getTextSize(message, font, 1, 2)[0]
    text_x = (width - text_size[0]) // 2
    text_y = (height + text_size[1]) // 2
    
    cv2.putText(img, message, (text_x, text_y), font, 1, (255, 255, 255), 2)
    
    ret, jpeg = cv2.imencode('.jpg', img)
    return jpeg.tobytes()

@app.route('/video_feed/<int:camera_id>')
def video_feed(camera_id):
    camera = db.get_camera(camera_id)
    if not camera:
        return "Camera not found", 404

    if not camera_utils.check_camera_connection(camera):
        error_img = create_error_image("Camera not connected")
        return Response(error_img, mimetype='image/jpeg')

    return Response(camera_utils.get_camera_feed(camera),
                    mimetype='multipart/x-mixed-replace; boundary=frame')

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
    name = request.form.get('camera-name')
    if name:
        db.update_camera(camera_id, name)
    return redirect(url_for('config'))

@app.route('/cameras/delete/<int:camera_id>', methods=['POST'])
def delete_camera(camera_id):
    db.delete_camera(camera_id)
    return redirect(url_for('config'))

@app.route('/config/genicam/update', methods=['POST'])
def update_genicam_settings():
    path = request.form.get('genicam-cti-path', '').strip()

    if path and path.lower().endswith('.cti'):
        # Basic validation: check if it's a non-empty string and ends with .cti
        db.update_setting('genicam_cti_path', path)
    elif not path:
        # If the path is empty, clear the setting
        db.clear_setting('genicam_cti_path')
    
    return redirect(url_for('config'))

@app.route('/config/genicam/clear', methods=['POST'])
def clear_genicam_settings():
    db.clear_setting('genicam_cti_path')
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
