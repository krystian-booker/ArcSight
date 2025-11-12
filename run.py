"""Application entry point.

Run the Flask application with environment-based configuration.

Environment Variables:
    FLASK_ENV: Set to 'production' for production mode, 'development' for dev mode
    FLASK_DEBUG: Set to '0' to disable debug mode (alternative to FLASK_ENV)
    HOST: Server host address (default: 0.0.0.0)
    PORT: Server port (default: 5001 in dev, 8080 in production)

Examples:
    # Development mode (default) - auto-starts Vite on port 8080
    # Flask runs on port 5001, Vite proxies API requests
    python run.py
    # Then visit: http://localhost:8080

    # Production mode - Flask serves React build on port 8080
    FLASK_ENV=production python run.py

    # Or using FLASK_DEBUG
    FLASK_DEBUG=0 python run.py
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
