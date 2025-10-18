"""Application entry point.

Run the Flask application with environment-based configuration.

Environment Variables:
    FLASK_ENV: Set to 'development' for debug mode, 'production' for production
    FLASK_DEBUG: Set to '1' to enable debug mode (alternative to FLASK_ENV)
    HOST: Server host address (default: 0.0.0.0)
    PORT: Server port (default: 8080)

Examples:
    # Production mode (default)
    python run.py

    # Development mode with debug
    FLASK_ENV=development python run.py

    # Or using FLASK_DEBUG
    FLASK_DEBUG=1 python run.py
"""

from app import create_app

app = create_app()

if __name__ == "__main__":
    # Get configuration from app.config (set by config.py)
    host = app.config.get('HOST', '0.0.0.0')
    port = app.config.get('PORT', 8080)
    debug = app.config.get('DEBUG', False)

    # IMPORTANT: use_reloader=False to prevent issues with camera threads
    # The reloader would spawn duplicate threads and cause resource conflicts
    app.run(host=host, port=port, debug=debug, use_reloader=False)
