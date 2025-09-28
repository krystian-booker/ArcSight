from flask import Flask, g
import atexit
from . import db
from . import camera_utils

def create_app():
    app = Flask(__name__, static_folder='static', template_folder='templates')

    @app.before_request
    def before_request():
        """Create a database connection before each request."""
        g.db = db.get_db()

    @app.teardown_appcontext
    def teardown_db(exception):
        """Close the database connection after each request."""
        db_conn = g.pop('db', None)
        if db_conn is not None:
            db_conn.close()

    # Register blueprint
    from .blueprints.main import main as main_blueprint
    app.register_blueprint(main_blueprint)

    # Initialize db, harvester, and start camera threads
    with app.app_context():
        db.init_db()
        camera_utils.initialize_harvester()
        # Pass the app object directly
        camera_utils.start_all_camera_threads(app)

    # Register a function to stop all threads when the application exits
    atexit.register(camera_utils.stop_all_camera_threads)

    return app