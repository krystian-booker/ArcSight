from pathlib import Path
import threading
import time
from flask import Flask, jsonify, request, Response, send_file, send_from_directory
import db
import camera_utils
import cv2
import numpy as np
import os

BASE_DIR = Path(__file__).resolve().parent
DIST_DIR = BASE_DIR / 'frontend' / 'dist'

app = Flask(__name__)


def create_error_image(message, width=640, height=480):
    """Creates a black image with white text."""
    img = np.zeros((height, width, 3), np.uint8)
    font = cv2.FONT_HERSHEY_SIMPLEX

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
        return 'Camera not found', 404

    if not camera_utils.check_camera_connection(camera):
        error_img = create_error_image('Camera not connected')
        return Response(error_img, mimetype='image/jpeg')

    return Response(camera_utils.get_camera_feed(camera), mimetype='multipart/x-mixed-replace; boundary=frame')


@app.route('/api/cameras', methods=['GET'])
def list_cameras():
    cameras = [dict(camera) for camera in db.get_cameras()]
    genicam_enabled = bool(db.get_setting('genicam_cti_path'))
    return jsonify({'cameras': cameras, 'genicam_enabled': genicam_enabled})


@app.route('/settings/global/update', methods=['POST'])
def update_global_settings():
    db.update_setting('team_number', request.form.get('team_number', ''))
    db.update_setting('ip_mode', request.form.get('ip_mode', 'DHCP'))
    db.update_setting('hostname', request.form.get('hostname', 'vision-tools'))
    return jsonify({'success': True})


@app.route('/cameras/add', methods=['POST'])
def add_camera():
    name = (request.form.get('camera-name') or '').strip()
    camera_type = request.form.get('camera-type')

    identifier = ''
    if camera_type == 'USB':
        identifier = request.form.get('usb-camera-select', '')
    elif camera_type == 'GenICam':
        identifier = request.form.get('genicam-camera-select', '')

    if not name or not camera_type or not identifier:
        return jsonify({'error': 'Missing required camera information.'}), 400

    db.add_camera(name, camera_type, identifier)
    return jsonify({'success': True})


@app.route('/cameras/update/<int:camera_id>', methods=['POST'])
def update_camera(camera_id):
    name = (request.form.get('camera-name') or '').strip()
    if not name:
        return jsonify({'error': 'Camera name is required.'}), 400

    db.update_camera(camera_id, name)
    return jsonify({'success': True})


@app.route('/cameras/delete/<int:camera_id>', methods=['POST'])
def delete_camera(camera_id):
    db.delete_camera(camera_id)
    return jsonify({'success': True})


@app.route('/config/genicam/update', methods=['POST'])
def update_genicam_settings():
    path = (request.form.get('genicam-cti-path') or '').strip()

    if path and path.lower().endswith('.cti'):
        db.update_setting('genicam_cti_path', path)
    elif not path:
        db.clear_setting('genicam_cti_path')

    camera_utils.reinitialize_harvester()
    return jsonify({'success': True})


@app.route('/config/genicam/clear', methods=['POST'])
def clear_genicam_settings():
    db.clear_setting('genicam_cti_path')
    camera_utils.reinitialize_harvester()
    return jsonify({'success': True})


@app.route('/api/settings', methods=['GET'])
def api_settings():
    return jsonify({
        'team_number': db.get_setting('team_number') or '',
        'ip_mode': db.get_setting('ip_mode') or 'DHCP',
        'hostname': db.get_setting('hostname') or 'vision-tools',
        'genicam_cti_path': db.get_setting('genicam_cti_path') or '',
    })


@app.route('/api/cameras/discover')
def discover_cameras():
    existing_arg = request.args.get('existing', '')
    existing_identifiers = [item for item in existing_arg.split(',') if item]

    usb_cameras = camera_utils.list_usb_cameras()
    genicam_cameras = camera_utils.list_genicam_cameras()

    filtered_usb = [cam for cam in usb_cameras if cam['identifier'] not in existing_identifiers]
    filtered_genicam = [cam for cam in genicam_cameras if cam['identifier'] not in existing_identifiers]

    return jsonify({'usb': filtered_usb, 'genicam': filtered_genicam})


@app.route('/api/cameras/status/<int:camera_id>')
def camera_status(camera_id):
    camera = db.get_camera(camera_id)
    if camera:
        is_connected = camera_utils.check_camera_connection(camera)
        return jsonify({'connected': is_connected})
    return jsonify({'error': 'Camera not found'}), 404


@app.route('/api/genicam/nodes/<int:camera_id>', methods=['GET'])
def genicam_nodes(camera_id):
    camera = db.get_camera(camera_id)
    if not camera or camera['camera_type'] != 'GenICam':
        return jsonify({'error': 'Camera not found or not a GenICam device'}), 404

    nodes, error = camera_utils.get_genicam_node_map(camera['identifier'])
    if error:
        return jsonify({'error': error}), 500

    return jsonify({'nodes': nodes})


@app.route('/api/genicam/nodes/<int:camera_id>', methods=['POST'])
def update_genicam_node(camera_id):
    camera = db.get_camera(camera_id)
    if not camera or camera['camera_type'] != 'GenICam':
        return jsonify({'error': 'Camera not found or not a GenICam device'}), 404

    payload = request.get_json(silent=True) or {}
    node_name = payload.get('name')
    value = payload.get('value')

    success, message, status_code, updated_node = camera_utils.update_genicam_node(camera['identifier'], node_name, value)
    if success:
        return jsonify({'success': True, 'message': message or 'Node updated successfully.', 'node': updated_node}), 200

    status_code = status_code or 400
    return jsonify({'error': message or 'Failed to update node.'}), status_code


@app.route('/control/restart-app', methods=['POST'])
def restart_app():
    def shutdown():
        time.sleep(0.5)
        os._exit(0)

    threading.Thread(target=shutdown, daemon=True).start()
    return jsonify({'success': True, 'message': 'Restarting application...'}), 200


@app.route('/control/reboot', methods=['POST'])
def reboot_device():
    def reboot():
        os.system('sudo reboot')

    threading.Thread(target=reboot, daemon=True).start()
    return jsonify({'success': True, 'message': 'Rebooting device...'}), 200


@app.route('/control/export-db')
def export_db():
    return send_file(db.DB_PATH, as_attachment=True)


@app.route('/control/import-db', methods=['POST'])
def import_db():
    file = request.files.get('database')
    if not file or file.filename == '':
        return jsonify({'error': 'No database file provided.'}), 400

    file.save(db.DB_PATH)
    return jsonify({'success': True})


@app.route('/control/factory-reset', methods=['POST'])
def factory_reset():
    db.factory_reset()
    camera_utils.reinitialize_harvester()
    return jsonify({'success': True})


@app.route('/', defaults={'path': ''})
@app.route('/<path:path>')
def serve_frontend(path):
    if not DIST_DIR.exists():
        return 'Frontend build not found.', 404

    requested_path = DIST_DIR / path
    if path and requested_path.exists():
        if requested_path.is_file():
            return send_from_directory(DIST_DIR, path)
        if requested_path.is_dir() and (requested_path / 'index.html').exists():
            return send_from_directory(requested_path, 'index.html')

    return send_from_directory(DIST_DIR, 'index.html')


if __name__ == '__main__':
    db.init_db()
    camera_utils.initialize_harvester()
    app.run(host='0.0.0.0', port=8080, debug=True, use_reloader=False)
