import os
import atexit
from flask import Flask
from appdirs import user_data_dir

from .extensions import db
from . import camera_manager
from .drivers.genicam_driver import GenICamDriver
from .calibration_utils import CalibrationManager
from .models import Setting


def create_app(config_overrides=None):
    """Creates and configures the Flask application."""
    app = Flask(__name__, static_folder='static', template_folder='templates')
    app.calibration_manager = CalibrationManager()

    # Default configuration
    app.config.from_mapping(
        CAMERA_THREADS_ENABLED=True,
    )

    # Load instance-specific config
    if config_overrides:
        app.config.from_mapping(config_overrides)

    # Database configuration
    APP_NAME = "VisionTools"
    APP_AUTHOR = "User"
    data_dir = user_data_dir(APP_NAME, APP_AUTHOR)
    os.makedirs(data_dir, exist_ok=True)
    db_path = os.path.join(data_dir, "config.db")
    
    # Use provided DB URI or default
    if 'SQLALCHEMY_DATABASE_URI' not in app.config:
        app.config['SQLALCHEMY_DATABASE_URI'] = f'sqlite:///{db_path}'
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

    db.init_app(app)

    # Import and register the new blueprints
    from .blueprints.dashboard import dashboard as dashboard_blueprint
    from .blueprints.cameras import cameras as cameras_blueprint
    from .blueprints.calibration import calibration as calibration_blueprint
    from .blueprints.settings import settings as settings_blueprint
    from .blueprints.pipelines import pipelines as pipelines_blueprint

    app.register_blueprint(dashboard_blueprint)
    app.register_blueprint(cameras_blueprint)
    app.register_blueprint(calibration_blueprint)
    app.register_blueprint(settings_blueprint)
    app.register_blueprint(pipelines_blueprint)

    with app.app_context():
        db.create_all()
        # Only initialize cameras and threads if not disabled
        if app.config.get("CAMERA_THREADS_ENABLED", True):
            genicam_setting = db.session.get(Setting, 'genicam_cti_path')
            cti_path = genicam_setting.value if genicam_setting else ""
            GenICamDriver.initialize(cti_path)
            camera_manager.start_all_camera_threads(app)

    if app.config.get("CAMERA_THREADS_ENABLED", True):
        atexit.register(camera_manager.stop_all_camera_threads)

    return app