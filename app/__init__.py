from flask import Flask, g
from . import db
from . import camera_utils
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

    from .blueprints.main import main as main_blueprint
    app.register_blueprint(main_blueprint)

    with app.app_context():
        db.init_db()
        camera_utils.initialize_harvester()
        camera_utils.start_all_camera_threads(app)

    atexit.register(camera_utils.stop_all_camera_threads)

    return app