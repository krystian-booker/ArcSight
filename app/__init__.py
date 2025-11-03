import os
import atexit
import logging
import logging.handlers
from flask import Flask

from .utils.config import DATA_DIR
from .extensions import db
from . import camera_manager
from .drivers.genicam_driver import GenICamDriver
from .calibration_utils import CalibrationManager
from .models import Setting
from .metrics import metrics_registry, system_metrics_collector


def configure_logging(app):
    """
    Configure application-wide logging.

    Sets up both file and console logging with appropriate formatters
    and log levels based on the Flask environment.
    """
    # Determine log level based on environment
    if app.debug:
        log_level = logging.DEBUG
    else:
        log_level = logging.INFO

    # Create logs directory in user data dir
    log_dir = os.path.join(DATA_DIR, "logs")
    os.makedirs(log_dir, exist_ok=True)

    # Create formatter
    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )

    # Console handler
    console_handler = logging.StreamHandler()
    console_handler.setLevel(log_level)
    console_handler.setFormatter(formatter)

    # File handler with rotation
    log_file = os.path.join(log_dir, "arcsight.log")
    file_handler = logging.handlers.RotatingFileHandler(
        log_file,
        maxBytes=10 * 1024 * 1024,  # 10 MB
        backupCount=5
    )
    file_handler.setLevel(log_level)
    file_handler.setFormatter(formatter)

    # Configure root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)

    # Remove existing handlers to avoid duplicates
    root_logger.handlers.clear()

    # Add handlers
    root_logger.addHandler(console_handler)
    root_logger.addHandler(file_handler)

    # Set log level for werkzeug (Flask's server) to WARNING to reduce noise
    logging.getLogger('werkzeug').setLevel(logging.WARNING)

    app.logger.info(f"Logging configured at {log_level} level")


def create_app(config_overrides=None):
    """Creates and configures the Flask application.

    Args:
        config_overrides: Optional dictionary of config values to override.
                         Typically used for testing.

    Returns:
        Flask: Configured Flask application instance
    """
    app = Flask(__name__, static_folder="static", template_folder="templates")
    app.calibration_manager = CalibrationManager()

    # Load configuration from config.py (environment-based)
    from config import get_config

    config_class = get_config()
    app.config.from_object(config_class)

    # Apply test-specific or instance-specific overrides
    if config_overrides:
        app.config.from_mapping(config_overrides)

    # Production-specific initialization
    if hasattr(config_class, "init_app"):
        config_class.init_app(app)

    # Configure logging
    configure_logging(app)

    # Database configuration - set default path if not configured
    if app.config.get("SQLALCHEMY_DATABASE_URI") is None:
        os.makedirs(DATA_DIR, exist_ok=True)
        db_path = os.path.join(DATA_DIR, "config.db")
        app.config["SQLALCHEMY_DATABASE_URI"] = f"sqlite:///{db_path}"

    db.init_app(app)

    # Initialize WebSocket support
    from .blueprints.websocket import init_socketio
    socketio = init_socketio(app)
    app.socketio = socketio  # Store reference for access in other modules

    metrics_registry.configure(
        enabled=app.config.get("METRICS_ENABLED", True),
        window_seconds=app.config.get("METRICS_WINDOW_SECONDS", 300.0),
        fps_window_seconds=app.config.get("METRICS_FPS_WINDOW_SECONDS", 10.0),
        memory_sampler_interval=app.config.get("METRICS_MEMORY_SAMPLE_SECONDS", 2.0),
        queue_high_utilization_pct=app.config.get(
            "PIPELINE_QUEUE_HIGH_UTILIZATION_PCT", 80.0
        ),
        latency_warn_ms=app.config.get("PIPELINE_LATENCY_WARN_MS", 150.0),
    )
    if app.config.get("METRICS_ENABLED", True):
        metrics_registry.start_memory_sampler()
        system_metrics_collector.start()
        atexit.register(metrics_registry.shutdown)
        atexit.register(system_metrics_collector.stop)

    # Import and register API blueprints (must be before react_app)
    from .blueprints.dashboard import dashboard as dashboard_blueprint
    from .blueprints.cameras import cameras as cameras_blueprint
    from .blueprints.calibration import calibration as calibration_blueprint
    from .blueprints.settings import settings as settings_blueprint
    from .blueprints.pipelines import pipelines as pipelines_blueprint
    from .blueprints.monitoring import monitoring as monitoring_blueprint

    app.register_blueprint(dashboard_blueprint)
    app.register_blueprint(cameras_blueprint)
    app.register_blueprint(calibration_blueprint)
    app.register_blueprint(settings_blueprint)
    app.register_blueprint(pipelines_blueprint)
    app.register_blueprint(monitoring_blueprint)

    # Register test mock blueprint if E2E testing is enabled
    if os.getenv("E2E_TESTING", "false").lower() == "true":
        from .blueprints.test_mock import test_mock as test_mock_blueprint

        app.register_blueprint(test_mock_blueprint)

    # Register React app blueprint LAST (catch-all for React Router)
    # This allows API routes to take precedence
    from .blueprints.react_app import bp as react_app_blueprint

    app.register_blueprint(react_app_blueprint)

    with app.app_context():
        db.create_all()

        # Only initialize cameras and threads if not disabled
        if app.config.get("CAMERA_THREADS_ENABLED", True):
            genicam_setting = db.session.get(Setting, "genicam_cti_path")
            cti_path = genicam_setting.value if genicam_setting else ""
            GenICamDriver.initialize(cti_path)
            camera_manager.start_all_camera_threads(app)

    if app.config.get("CAMERA_THREADS_ENABLED", True):
        atexit.register(camera_manager.stop_all_camera_threads)

    return app
