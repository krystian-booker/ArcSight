import os
import atexit
import glob
import logging
from flask import Flask, render_template, send_from_directory
from appdirs import user_data_dir

from .extensions import db
from . import camera_manager
from .drivers.genicam_driver import GenICamDriver
from .calibration_utils import CalibrationManager
from .models import Setting
from .metrics import metrics_registry, system_metrics_collector


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

    # In development mode, suppress Werkzeug's "Running on" messages
    # since users should access Vite on port 8080, not Flask on 5001
    if app.config.get("ENV") == "development":
        log = logging.getLogger('werkzeug')
        log.setLevel(logging.ERROR)

    # Database configuration - set default path if not configured
    if app.config.get("SQLALCHEMY_DATABASE_URI") is None:
        APP_NAME = "VisionTools"
        APP_AUTHOR = "User"
        data_dir = user_data_dir(APP_NAME, APP_AUTHOR)
        os.makedirs(data_dir, exist_ok=True)
        db_path = os.path.join(data_dir, "config.db")
        app.config["SQLALCHEMY_DATABASE_URI"] = f"sqlite:///{db_path}"

    db.init_app(app)
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

    # Import and register the new blueprints
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

    # Start Vite dev server in development mode
    # Auto-detect development mode from Flask config
    is_development = app.config.get("ENV") == "development" or app.config.get("DEBUG")
    # Allow manual override with REACT_DEV_MODE
    react_dev_mode_override = os.environ.get("REACT_DEV_MODE", "").lower()
    if react_dev_mode_override == "true":
        react_dev_mode = True
    elif react_dev_mode_override == "false":
        react_dev_mode = False
    else:
        react_dev_mode = is_development

    vite_process = None
    skip_vite_start = os.environ.get("SKIP_VITE_START", "").lower() == "true"

    if react_dev_mode and not skip_vite_start:
        import subprocess
        import time

        frontend_dir = os.path.dirname(os.path.dirname(__file__))

        # Check if Vite dev server is already running
        try:
            import requests

            requests.get("http://localhost:8080", timeout=1)
            print("✓ Vite dev server already running on http://localhost:8080")
        except Exception:
            # Start Vite dev server
            print("Starting Vite dev server on port 8080...")
            try:
                # Use shell=True on Windows to find npm in PATH
                import platform
                is_windows = platform.system() == "Windows"

                vite_process = subprocess.Popen(
                    ["npm", "run", "dev"],
                    cwd=frontend_dir,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    shell=is_windows,  # Enable shell on Windows to find npm.cmd
                )
                # Wait a bit for server to start
                time.sleep(3)
                print("✓ Development server ready at http://localhost:8080")
                atexit.register(lambda: vite_process.terminate() if vite_process else None)
            except FileNotFoundError:
                print("⚠ Warning: npm not found. Please start Vite manually with 'npm run dev'")
                print("   Make sure Node.js and npm are installed and in your PATH")
            except Exception as e:
                print(f"⚠ Warning: Could not start Vite dev server: {e}")
                print("   Please start it manually with: npm run dev")

    # Verify production build exists when Vite is skipped and not in dev mode
    if not react_dev_mode and skip_vite_start:
        dist_dir = os.path.join(app.static_folder, "dist")
        index_path = os.path.join(dist_dir, "index.html")
        if not os.path.exists(index_path):
            print("⚠ ERROR: Production build not found!")
            print(f"   Expected: {index_path}")
            print("   Run 'npm run build' to create the production build before running tests.")
            print("   Continuing anyway, but React app routes will return 404...")

    # Serve React app for all frontend routes
    @app.route("/", defaults={"path": ""})
    @app.route("/<path:path>")
    def serve_react_app(path):
        """
        Serve React app for all routes not handled by blueprints.

        In development mode (REACT_DEV_MODE=true), proxies to Vite dev server.
        In production mode, serves static build from app/static/dist.
        """
        # Skip API and blueprint routes - they should be handled by Flask blueprints
        # This check prevents the catch-all from interfering with API endpoints
        # Note: Direct page routes like /monitoring, /settings etc. will NOT match
        # these patterns (no trailing content), so they'll be served by React below
        if any(
            path.startswith(prefix) and len(path) > len(prefix)
            for prefix in ("api/", "cameras/", "calibration/", "settings/", "monitoring/")
        ) or path.startswith(("video_feed/", "processed_video_feed/", "static/")):
            # This shouldn't be reached due to blueprint routing, but just in case
            return "Not found", 404

        # Development mode: Serve React HTML that loads Vite dev server
        if react_dev_mode:
            return render_template("react.html", react_dev_mode=True)

        # Production mode: Serve built files from dist directory
        dist_dir = os.path.join(app.static_folder, "dist")

        # Serve static assets from dist (JS, CSS, images, etc.)
        if path.startswith("assets/"):
            file_path = os.path.join(dist_dir, path)
            if os.path.exists(file_path):
                return send_from_directory(dist_dir, path)

        # Serve Vite-generated index.html for all other routes (SPA routing)
        # Vite's build process creates a properly configured index.html with
        # correct script tags, modulepreload hints, and asset paths
        index_path = os.path.join(dist_dir, "index.html")
        if os.path.exists(index_path):
            return send_from_directory(dist_dir, "index.html")

        return "React build not found. Run 'npm run build' to build the frontend.", 404

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
