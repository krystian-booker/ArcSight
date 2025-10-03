from flask import Flask, g
from . import db
from . import camera_manager
from .drivers.genicam_driver import GenICamDriver
from .calibration_utils import CalibrationManager
import atexit


def create_app():
    """Creates and configures the Flask application."""
    app = Flask(__name__, static_folder='static', template_folder='templates')
    app.calibration_manager = CalibrationManager()

    @app.before_request
    def before_request():
        """Creates a database connection before each request."""
        g.db = db.get_db()

    @app.teardown_appcontext
    def teardown_db(exception):
        """Closes the database connection after each request."""
        db_conn = g.pop('db', None)
        if db_conn is not None:
            db_conn.close()

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
        db.init_db()
        cti_path = db.get_setting('genicam_cti_path')
        GenICamDriver.initialize(cti_path)
        camera_manager.start_all_camera_threads(app)

    atexit.register(camera_manager.stop_all_camera_threads)

    return app