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

import socket
from app import create_app

app = create_app()
socketio = app.socketio  # Get SocketIO instance from app

if __name__ == "__main__":
    # Get configuration from app.config (set by config.py)
    host = app.config.get('HOST', '0.0.0.0')
    port = app.config.get('PORT', 8080)
    debug = app.config.get('DEBUG', False)

    # Display server information
    print("\n" + "="*60)
    print("ArcSight Server Starting")
    print("="*60)

    # Get local IP addresses
    hostname = socket.gethostname()
    try:
        local_ip = socket.gethostbyname(hostname)
        print(f"Local IP: http://{local_ip}:{port}")
    except:
        pass

    if host == '0.0.0.0':
        print(f"Listening on all interfaces: http://0.0.0.0:{port}")
        print(f"Localhost: http://127.0.0.1:{port}")
        print(f"Hostname: http://{hostname}:{port}")
    else:
        print(f"Server: http://{host}:{port}")

    print(f"Mode: {'DEBUG' if debug else 'PRODUCTION'}")
    print(f"WebSocket: Enabled")
    print("="*60 + "\n")

    # IMPORTANT: use_reloader=False to prevent issues with camera threads
    # The reloader would spawn duplicate threads and cause resource conflicts
    # Use socketio.run() instead of app.run() for WebSocket support
    socketio.run(app, host=host, port=port, debug=debug, use_reloader=False, allow_unsafe_werkzeug=True)
